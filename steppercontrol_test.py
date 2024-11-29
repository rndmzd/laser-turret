import RPi.GPIO as GPIO
import logging
import time
import threading
from typing import Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass
import queue

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

CLOCKWISE = 'CW'
COUNTER_CLOCKWISE = 'CCW'

# Pin mapping for motor channels
MOTOR_PIN_MAP = {
    1: {  # Motor 1 (Y-axis)
        'STEP': 24,
        'DIR': 26,
        'ENABLE': 6,
        'MS1': 17,
        'MS2': 27,
        'MS3': 22
    },
    2: {  # Motor 2 (X-axis)
        'STEP': 23,
        'DIR': 19,
        'ENABLE': 5,
        'MS1': 17,
        'MS2': 27,
        'MS3': 22
    }
}

# Microstep resolution truth table
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

class StepperMotor:  # Changed name back to match tests
    def __init__(
        self,
        motor_channel: int,
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
        Maintains compatibility with existing test suite.

        Args:
            motor_channel: Motor channel (1 or 2)
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
        if motor_channel not in MOTOR_PIN_MAP:
            raise ConfigurationError("Motor channel must be 1 or 2.")
        if microsteps not in MICROSTEP_CONFIG:
            raise ConfigurationError(f"Invalid microstep resolution: {microsteps}")
        
        # Get pin mapping for this motor
        pins = MOTOR_PIN_MAP[motor_channel]
        
        # Initialize basic attributes
        self.lock = threading.Lock()
        self.state = MotorState(status=MotorStatus.INITIALIZING)
        self.motor_channel = motor_channel
        self.step_pin = pins['STEP']
        self.dir_pin = pins['DIR']
        self.enable_pin = pins['ENABLE']
        self.ms_pins = (pins['MS1'], pins['MS2'], pins['MS3'])
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
        self.release()
        
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

    def release(self) -> None:
        """Release the motor (disable driver)"""
        GPIO.output(self.enable_pin, GPIO.HIGH)  # Active LOW
        with self.lock:
            self.state.status = MotorStatus.IDLE
            self.state.triggered_limit = None

    def cleanup(self) -> None:
        """Enhanced cleanup with thread shutdown."""
        logger.info(f"[{self.name}] Starting cleanup...")
        
        # Stop command processing thread
        self.running = False
        if hasattr(self, 'command_thread'):
            self.command_thread.join(timeout=1.0)
        
        # Release motor
        self.release()
        
        # Cleanup GPIO
        pins_to_cleanup = [self.step_pin, self.dir_pin, self.enable_pin]
        pins_to_cleanup.extend(self.ms_pins)
        if self.cw_limit_switch_pin:
            pins_to_cleanup.append(self.cw_limit_switch_pin)
        if self.ccw_limit_switch_pin:
            pins_to_cleanup.append(self.ccw_limit_switch_pin)
                
        for pin in pins_to_cleanup:
            try:
                GPIO.remove_event_detect(pin)
            except:
                pass
            try:
                GPIO.cleanup(pin)
            except:
                pass
                
        logger.info(f"[{self.name}] Cleanup complete.")

    def get_status(self) -> MotorState:
        """Get current motor status"""
        with self.lock:
            return self.state

    def get_limit_switch_states(self) -> Tuple[Optional[bool], Optional[bool]]:
        """Get the current state of both limit switches"""
        with self.lock:
            def read_switch_with_verification(pin: Optional[int]) -> Optional[bool]:
                if pin is None:
                    return None
                    
                # Take multiple readings over a short period
                readings = []
                for _ in range(5):
                    readings.append(GPIO.input(pin) == 0)
                    time.sleep(0.001)
                    
                # Return True only if majority of readings indicate switch is pressed
                return sum(readings) >= 3
            
            cw_state = read_switch_with_verification(self.cw_limit_switch_pin)
            ccw_state = read_switch_with_verification(self.ccw_limit_switch_pin)
            
            return (cw_state, ccw_state)

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
        """Move motor a specified number of steps"""
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
            
            # Enable motor
            GPIO.output(self.enable_pin, GPIO.LOW)  # Active LOW
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
            self.release()
        
        return actual_steps
    