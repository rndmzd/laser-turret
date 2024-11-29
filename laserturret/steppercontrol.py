import RPi.GPIO as GPIO
import logging
import time
import threading
from typing import Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass
import queue

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

CLOCKWISE = 'CW'
COUNTER_CLOCKWISE = 'CCW'

# Microstep resolution truth table
# MS1 MS2 MS3 Resolution
#  0   0   0   Full step (1)
#  1   0   0   Half step (1/2)
#  0   1   0   Quarter step (1/4)
#  1   1   0   Eighth step (1/8)
#  1   1   1   Sixteenth step (1/16)
MICROSTEP_CONFIG = {
    1: (0, 0, 0),    # Full step
    2: (1, 0, 0),    # Half step
    4: (0, 1, 0),    # Quarter step
    8: (1, 1, 0),    # Eighth step
    16: (1, 1, 1)    # Sixteenth step
}

class MotorStatus(Enum):
    """Enum for motor status"""
    INITIALIZING = "initializing"
    IDLE = "idle"
    MOVING = "moving"
    ERROR = "error"
    LIMIT_REACHED = "limit_reached"
    CALIBRATING = "calibrating"
    HOLDING = "holding"

class MotorError(Exception):
    """Base exception for motor errors"""
    pass

class LimitSwitchError(MotorError):
    """Exception for limit switch related errors"""
    pass

class CalibrationError(MotorError):
    """Exception for calibration related errors"""
    pass

class ConfigurationError(MotorError):
    """Exception for configuration related errors"""
    pass

@dataclass
class MotorState:
    """Data class for motor state"""
    position: int = 0
    status: MotorStatus = MotorStatus.IDLE
    direction: Optional[str] = None
    triggered_limit: Optional[str] = None
    error_message: Optional[str] = None

class A4988StepperMotor:
    def __init__(
        self,
        step_pin: int,
        dir_pin: int,
        enable_pin: int,
        ms1_pin: int,
        ms2_pin: int,
        ms3_pin: int,
        cw_limit_switch_pin: Optional[int] = None,
        ccw_limit_switch_pin: Optional[int] = None,
        steps_per_rev: int = 200,
        microsteps: int = 8,
        skip_direction_check: bool = False,
        perform_calibration: bool = True,
        limit_backoff_steps: int = 1,
        name: str = "Motor",
        calibration_timeout: int = 30,
        movement_timeout: int = 10,
        deadzone: int = 10,
        interactive_test_mode: bool = False):
        """
        Initialize stepper motor control using A4988 driver.

        Args:
            step_pin: GPIO pin connected to STEP input
            dir_pin: GPIO pin connected to DIR input
            enable_pin: GPIO pin connected to ENABLE input
            ms1_pin: GPIO pin connected to MS1 input
            ms2_pin: GPIO pin connected to MS2 input
            ms3_pin: GPIO pin connected to MS3 input
            cw_limit_switch_pin: GPIO pin for clockwise limit switch
            ccw_limit_switch_pin: GPIO pin for counter-clockwise limit switch
            steps_per_rev: Steps per revolution (typically 200 for 1.8° motors)
            microsteps: Microstepping resolution (1, 2, 4, 8, or 16)
            skip_direction_check: Skip direction verification
            perform_calibration: Perform initial calibration
            limit_backoff_steps: Steps to back off after hitting limit
            name: Motor name for logging
            calibration_timeout: Timeout for calibration in seconds
            movement_timeout: Timeout for movement operations in seconds
            deadzone: Command deadzone
        """
        # Validate configuration
        if microsteps not in MICROSTEP_CONFIG:
            raise ConfigurationError(f"Invalid microstep resolution: {microsteps}")
        
        # Initialize basic attributes
        self.lock = threading.Lock()
        self.state = MotorState(status=MotorStatus.INITIALIZING)
        self.step_pin = step_pin
        self.dir_pin = dir_pin
        self.enable_pin = enable_pin
        self.ms_pins = (ms1_pin, ms2_pin, ms3_pin)
        self.cw_limit_switch_pin = cw_limit_switch_pin
        self.ccw_limit_switch_pin = ccw_limit_switch_pin
        self.steps_per_rev = steps_per_rev
        self.microsteps = microsteps
        self.name = name
        self.limit_backoff_steps = limit_backoff_steps
        self.total_travel_steps = None
        self.calibration_timeout = calibration_timeout
        self.movement_timeout = movement_timeout
        self.deadzone = deadzone

        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        
        # Setup motor control pins
        GPIO.setup(self.step_pin, GPIO.OUT)
        GPIO.setup(self.dir_pin, GPIO.OUT)
        GPIO.setup(self.enable_pin, GPIO.OUT)
        for pin in self.ms_pins:
            GPIO.setup(pin, GPIO.OUT)
            
        # Set microstepping configuration
        ms1_val, ms2_val, ms3_val = MICROSTEP_CONFIG[microsteps]
        GPIO.output(self.ms_pins[0], ms1_val)
        GPIO.output(self.ms_pins[1], ms2_val)
        GPIO.output(self.ms_pins[2], ms3_val)
        
        # Disable motor initially
        GPIO.output(self.enable_pin, GPIO.HIGH)  # Active LOW
        
        # Setup limit switches with debouncing
        self._last_cw_trigger = 0
        self._last_ccw_trigger = 0
        self.debounce_time = 0.1  # 100ms debounce window
        
        if cw_limit_switch_pin:
            GPIO.setup(cw_limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(
                cw_limit_switch_pin,
                GPIO.FALLING,
                callback=lambda channel: self._limit_switch_handler(channel, CLOCKWISE),
                bouncetime=200
            )
            
        if ccw_limit_switch_pin:
            GPIO.setup(ccw_limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(
                ccw_limit_switch_pin,
                GPIO.FALLING,
                callback=lambda channel: self._limit_switch_handler(channel, COUNTER_CLOCKWISE),
                bouncetime=200
            )
        
        # Initialize command processing thread
        self.command_queue = queue.Queue(maxsize=1)  # Only keep latest command
        self.running = True
        self.last_command = 0
        self.command_thread = threading.Thread(
            target=self._process_command_queue,
            name=f"{name}_command_thread",
            daemon=True
        )
        self.command_thread.start()

        # Perform initialization checks if not in test mode
        if not interactive_test_mode:
            if not skip_direction_check:
                self.confirm_limit_switches()
            if perform_calibration:
                self.calibrate()

    def _limit_switch_handler(self, channel: int, direction: str) -> None:
        """Fast limit switch event handler with minimal processing"""
        current_time = time.time()
        
        # Quick debounce check
        if direction == CLOCKWISE:
            if current_time - self._last_cw_trigger < self.debounce_time:
                return
            self._last_cw_trigger = current_time
        else:  # COUNTER_CLOCKWISE
            if current_time - self._last_ccw_trigger < self.debounce_time:
                return
            self._last_ccw_trigger = current_time
        
        # Update state if switch is actually pressed
        if GPIO.input(channel) == 0:  # Switch is pressed (pulled low)
            with self.lock:
                self.state.triggered_limit = direction
                self.state.status = MotorStatus.LIMIT_REACHED
            logger.info(f"[{self.name}] {direction} limit switch triggered")

    def enable(self) -> None:
        """Enable the motor driver (active LOW)"""
        GPIO.output(self.enable_pin, GPIO.LOW)

    def disable(self) -> None:
        """Disable the motor driver"""
        GPIO.output(self.enable_pin, GPIO.HIGH)

    def set_direction(self, direction: str) -> None:
        """Set motor direction"""
        if direction not in [CLOCKWISE, COUNTER_CLOCKWISE]:
            raise ValueError(f"Invalid direction: {direction}")
        
        with self.lock:
            # Check if movement is allowed
            if ((direction == CLOCKWISE and self.state.triggered_limit == CLOCKWISE) or
                (direction == COUNTER_CLOCKWISE and self.state.triggered_limit == COUNTER_CLOCKWISE)):
                raise LimitSwitchError(f"Cannot move {direction}, limit switch triggered.")
            
            self.state.direction = direction
            GPIO.output(self.dir_pin, GPIO.HIGH if direction == CLOCKWISE else GPIO.LOW)
            
            # Reset stop condition if moving away from triggered limit
            if ((direction == COUNTER_CLOCKWISE and self.state.triggered_limit == CLOCKWISE) or
                (direction == CLOCKWISE and self.state.triggered_limit == COUNTER_CLOCKWISE)):
                self.state.triggered_limit = None
                self.state.status = MotorStatus.IDLE

    def step(self, steps: int, delay: float = 0.0001) -> int:
        """
        Move motor a specified number of steps.
        
        Args:
            steps: Number of steps to move
            delay: Delay between steps in seconds
            
        Returns:
            Number of steps actually moved
        """
        if steps < 0:
            raise ValueError("Steps must be positive")
        
        start_time = time.time()
        actual_steps = 0
        
        try:
            # Check initial limit state
            if ((self.state.direction == CLOCKWISE and 
                self.state.triggered_limit == CLOCKWISE) or
                (self.state.direction == COUNTER_CLOCKWISE and 
                self.state.triggered_limit == COUNTER_CLOCKWISE)):
                raise LimitSwitchError(
                    f"Cannot move {self.state.direction}, limit switch already triggered"
                )
            
            self.enable()  # Enable motor
            self.state.status = MotorStatus.MOVING
            
            for _ in range(steps):
                # Check for timeout
                if time.time() - start_time > self.movement_timeout:
                    raise MotorError("Movement operation timed out")
                
                # Check for limit switch
                if self.state.triggered_limit:
                    break
                
                # Generate step pulse
                GPIO.output(self.step_pin, GPIO.HIGH)
                time.sleep(delay / 2)  # Half delay for pulse width
                GPIO.output(self.step_pin, GPIO.LOW)
                time.sleep(delay / 2)  # Half delay between steps
                
                # Update position
                if self.state.direction == CLOCKWISE:
                    self.state.position += 1
                else:
                    self.state.position -= 1
                
                actual_steps += 1
                
        except Exception as e:
            self.state.status = MotorStatus.ERROR
            self.state.error_message = str(e)
            raise
        
        finally:
            if self.state.status != MotorStatus.ERROR:
                self.state.status = (MotorStatus.LIMIT_REACHED 
                                   if self.state.triggered_limit 
                                   else MotorStatus.IDLE)
            self.disable()  # Disable motor after movement
        
        return actual_steps

    def _calculate_step_delay(self, command_value: float) -> Optional[float]:
        """Calculate step delay based on command value magnitude"""
        # Tuned delay bounds (in seconds)
        MIN_DELAY = 0.00005  # Maximum speed
        MAX_DELAY = 0.1      # Minimum speed
        
        # Check deadzone
        abs_value = abs(command_value)
        if abs_value < self.deadzone:
            return None
            
        # Cubic mapping for smoother acceleration
        command_range = 100 - self.deadzone
        normalized_command = (abs_value - self.deadzone) / command_range
        speed_multiplier = pow(normalized_command, 3)  # Cubic curve
        
        delay = MAX_DELAY - (speed_multiplier * (MAX_DELAY - MIN_DELAY))
        return max(MIN_DELAY, min(MAX_DELAY, delay))

    def _process_command_queue(self):
        """Process movement commands in separate thread"""
        while self.running:
            try:
                # Get latest command value
                try:
                    while True:
                        command = self.command_queue.get_nowait()
                        self.last_command = command
                except queue.Empty:
                    command = self.last_command

                # Process the command
                if abs(command) < self.deadzone:
                    self.disable()  # Disable motor in deadzone
                    time.sleep(0.001)
                    continue

                # Set direction
                direction = CLOCKWISE if command > 0 else COUNTER_CLOCKWISE
                
                # Check if we need to change direction
                if self.state.direction != direction:
                    try:
                        self.set_direction(direction)
                        time.sleep(0.001)  # Brief pause for direction change
                    except LimitSwitchError:
                        continue

                # Check limit switches
                if ((direction == CLOCKWISE and self.state.triggered_limit == CLOCKWISE) or
                    (direction == COUNTER_CLOCKWISE and self.state.triggered_limit == COUNTER_CLOCKWISE)):
                    time.sleep(0.001)
                    continue

                # Calculate delay and move one step
                delay = self._calculate_step_delay(command)
                if delay:
                    self.enable()
                    self.step(1, delay)

            except Exception as e:
                logger.error(f"[{self.name}] Error in command thread: {str(e)}")
                time.sleep(0.1)

    def process_command(self, command_value: float) -> None:
        """Queue new command for processing"""
        try:
            # Clear queue and add new command
            while not self.command_queue.empty():
                try:
                    self.command_queue.get_nowait()
                except queue.Empty:
                    break
            self.command_queue.put(command_value)
        except Exception as e:
            logger.error