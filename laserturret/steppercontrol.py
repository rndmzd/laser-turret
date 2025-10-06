import logging
import time
import threading
from typing import Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass
import queue
from .hardware_interface import get_gpio_backend, PinMode, PullMode, Edge
from laserturret.motion.constants import MICROSTEP_CONFIG, CLOCKWISE, COUNTER_CLOCKWISE

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Microstep resolution truth table
# MS1 MS2 MS3 Resolution
#  0   0   0   Full step (1)
#  1   0   0   Half step (1/2)
#  0   1   0   Quarter step (1/4)
#  1   1   0   Eighth step (1/8)
#  1   1   1   Sixteenth step (1/16)

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

class StepperMotor:
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
        interactive_test_mode: bool = False,
        start_thread: bool = True,
        gpio_backend=None):
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
        self.enabled = False

        # Initialize GPIO backend
        self.gpio = gpio_backend if gpio_backend is not None else get_gpio_backend()
        
        # Setup motor control pins
        self.gpio.setup(self.step_pin, PinMode.OUTPUT)
        self.gpio.setup(self.dir_pin, PinMode.OUTPUT)
        self.gpio.setup(self.enable_pin, PinMode.OUTPUT)
        for pin in self.ms_pins:
            self.gpio.setup(pin, PinMode.OUTPUT)
            
        # Set microstepping configuration
        ms1_val, ms2_val, ms3_val = MICROSTEP_CONFIG[microsteps]
        self.gpio.output(self.ms_pins[0], ms1_val)
        self.gpio.output(self.ms_pins[1], ms2_val)
        self.gpio.output(self.ms_pins[2], ms3_val)
        
        # Disable motor initially
        self.gpio.output(self.enable_pin, 1)  # Active LOW
        
        # Setup limit switches with pull-ups (polling-based, not event-based)
        if cw_limit_switch_pin:
            self.gpio.setup(cw_limit_switch_pin, PinMode.INPUT, pull_up_down=PullMode.UP)
            
        if ccw_limit_switch_pin:
            self.gpio.setup(ccw_limit_switch_pin, PinMode.INPUT, pull_up_down=PullMode.UP)
        
        # Initialize command processing thread
        if start_thread:
            self.command_queue = queue.Queue(maxsize=1)
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

    def _check_limit_switch(self, direction: str) -> bool:
        """
        Check if a limit switch is triggered by polling.
        
        Args:
            direction: CLOCKWISE or COUNTER_CLOCKWISE
            
        Returns:
            True if the limit switch for that direction is pressed (active LOW)
        """
        try:
            if direction == CLOCKWISE:
                if self.cw_limit_switch_pin is None:
                    return False
                # Switch is pressed when pin reads LOW (0)
                return self.gpio.input(self.cw_limit_switch_pin) == 0
            else:  # COUNTER_CLOCKWISE
                if self.ccw_limit_switch_pin is None:
                    return False
                return self.gpio.input(self.ccw_limit_switch_pin) == 0
        except Exception as e:
            logger.debug(f"[{self.name}] Failed to read limit switch (GPIO may be cleaned up): {e}")
            return False

    def enable(self) -> None:
        """Enable the motor driver (active LOW)"""
        try:
            self.gpio.output(self.enable_pin, 0)
            self.enabled = True
        except Exception as e:
            logger.debug(f"[{self.name}] Failed to enable motor (GPIO may be cleaned up): {e}")

    def disable(self) -> None:
        """Disable the motor driver"""
        try:
            self.gpio.output(self.enable_pin, 1)
            self.enabled = False
        except Exception as e:
            logger.debug(f"[{self.name}] Failed to disable motor (GPIO may be cleaned up): {e}")

    def set_direction(self, direction: str) -> None:
        """Set motor direction"""
        if direction not in [CLOCKWISE, COUNTER_CLOCKWISE]:
            raise ValueError(f"Invalid direction: {direction}")
        
        with self.lock:
            # Check if limit switch is currently pressed in the direction we want to move
            if self._check_limit_switch(direction):
                raise LimitSwitchError(f"Cannot move {direction}, limit switch is pressed.")
            
            self.state.direction = direction
            try:
                self.gpio.output(self.dir_pin, 1 if direction == CLOCKWISE else 0)
            except Exception as e:
                logger.debug(f"[{self.name}] Failed to set direction (GPIO may be cleaned up): {e}")
                raise
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
            # Check initial limit state by polling
            if self._check_limit_switch(self.state.direction):
                raise LimitSwitchError(
                    f"Cannot move {self.state.direction}, limit switch is pressed"
                )
            
            self.enable()  # Enable motor
            self.state.status = MotorStatus.MOVING
            
            for _ in range(steps):
                # Check for timeout
                if time.time() - start_time > self.movement_timeout:
                    raise MotorError("Movement operation timed out")
                
                # Check for limit switch by polling
                if self._check_limit_switch(self.state.direction):
                    logger.info(f"[{self.name}] {self.state.direction} limit switch detected during movement")
                    with self.lock:
                        self.state.triggered_limit = self.state.direction
                        self.state.status = MotorStatus.LIMIT_REACHED
                    break
                
                # Generate step pulse
                try:
                    self.gpio.output(self.step_pin, 1)
                    time.sleep(delay / 2)  # Half delay for pulse width
                    self.gpio.output(self.step_pin, 0)
                    time.sleep(delay / 2)  # Half delay between steps
                except Exception as gpio_error:
                    # GPIO error during step - might be cleanup in progress
                    logger.debug(f"[{self.name}] GPIO error during step: {gpio_error}")
                    break
                
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
                # Update status based on current limit switch state
                if (self._check_limit_switch(CLOCKWISE) or 
                    self._check_limit_switch(COUNTER_CLOCKWISE)):
                    self.state.status = MotorStatus.LIMIT_REACHED
                else:
                    self.state.status = MotorStatus.IDLE
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

                # Check limit switches by polling
                if self._check_limit_switch(direction):
                    with self.lock:
                        self.state.triggered_limit = direction
                        self.state.status = MotorStatus.LIMIT_REACHED
                    time.sleep(0.001)
                    continue

                # Calculate delay and move one step
                delay = self._calculate_step_delay(command)
                if delay:
                    self.enable()
                    self.step(1, delay)

            except Exception as e:
                # Check if we're being cleaned up
                if not self.running:
                    logger.debug(f"[{self.name}] Command thread exiting due to cleanup")
                    break
                logger.error(f"[{self.name}] Error in command thread: {str(e)}")
                time.sleep(0.1)

    def process_command(self, command_value: float) -> None:
        """Queue new command for processing"""
        if not hasattr(self, 'command_queue'):
            return
        try:
            # Clear queue and add new command
            while not self.command_queue.empty():
                try:
                    self.command_queue.get_nowait()
                except queue.Empty:
                    break
            self.command_queue.put(command_value)
        except Exception as e:
            logger.error(f"[{self.name}] Error queueing command: {str(e)}")
    
    def release(self) -> None:
        """Release the motor and reset state"""
        self.disable()  # Disable motor driver
        with self.lock:
            self.state.status = MotorStatus.IDLE
            self.state.triggered_limit = None

    def cleanup(self) -> None:
        """Clean up GPIO and threads"""
        logger.info(f"[{self.name}] Starting cleanup...")
        
        # Stop command processing thread
        self.running = False
        if hasattr(self, 'command_thread'):
            self.command_thread.join(timeout=1.0)
            if self.command_thread.is_alive():
                logger.warning(f"[{self.name}] Command thread did not stop within timeout")
        
        # Release motor
        self.release()
        
        # Clean up GPIO - only cleanup pins unique to this motor
        # Do NOT cleanup ms_pins as they may be shared with other motors
        pins_to_cleanup = [self.step_pin, self.dir_pin, self.enable_pin]
        if self.cw_limit_switch_pin:
            pins_to_cleanup.append(self.cw_limit_switch_pin)
        if self.ccw_limit_switch_pin:
            pins_to_cleanup.append(self.ccw_limit_switch_pin)
                
        try:
            self.gpio.cleanup(pins_to_cleanup)
        except:
            pass
                
        logger.info(f"[{self.name}] Cleanup complete.")

    def confirm_limit_switches(self) -> None:
        """
        Verify limit switch functionality by requesting manual confirmation.
        """
        if not (self.cw_limit_switch_pin or self.ccw_limit_switch_pin):
            logger.info(f"[{self.name}] No limit switches configured, skipping verification.")
            return
            
        logger.info(f"\n{'='*60}")
        logger.info(f"[{self.name}] LIMIT SWITCH VERIFICATION")
        logger.info(f"{'='*60}")
        logger.info(f"Motor: {self.name}")
        
        if self.cw_limit_switch_pin:
            logger.info(f"  CW Limit Switch:  GPIO Pin {self.cw_limit_switch_pin}")
        if self.ccw_limit_switch_pin:
            logger.info(f"  CCW Limit Switch: GPIO Pin {self.ccw_limit_switch_pin}")
        
        logger.info(f"\nPlease manually trigger each limit switch when prompted.")
        logger.info(f"You have 30 seconds for each switch.\n")
        
        timeout = 30  # seconds
        switches_to_test = []
        
        if self.cw_limit_switch_pin:
            switches_to_test.append((CLOCKWISE, "CW", "CLOCKWISE"))
        if self.ccw_limit_switch_pin:
            switches_to_test.append((COUNTER_CLOCKWISE, "CCW", "COUNTER-CLOCKWISE"))
        
        for idx, (direction, name, full_name) in enumerate(switches_to_test, 1):
            start_time = time.time()
            logger.info(f"[{idx}/{len(switches_to_test)}] >>> TRIGGER THE {name} ({full_name}) LIMIT SWITCH FOR {self.name} <<<")
            logger.info(f"      (GPIO Pin {self.cw_limit_switch_pin if direction == CLOCKWISE else self.ccw_limit_switch_pin})")
            logger.info(f"      Waiting...")
            
            # Wait for correct switch to trigger
            while True:
                if time.time() - start_time > timeout:
                    raise LimitSwitchError(
                        f"Timeout: {name} limit switch for {self.name} was not triggered within {timeout} seconds."
                    )
                    
                # Poll the switch directly
                if self._check_limit_switch(direction):
                    logger.info(f"      [OK] {name} limit switch verified (GPIO Pin {self.cw_limit_switch_pin if direction == CLOCKWISE else self.ccw_limit_switch_pin})")
                    with self.lock:
                        self.state.triggered_limit = None
                        self.state.status = MotorStatus.IDLE
                    # Wait for release
                    time.sleep(0.3)
                    logger.info(f"")
                    break
                    
                time.sleep(0.1)
        
        logger.info(f"{'='*60}")
        logger.info(f"[{self.name}] [SUCCESS] ALL LIMIT SWITCHES VERIFIED!")
        logger.info(f"{'='*60}\n")

    def calibrate(self) -> None:
        """Calibrate by finding limits and centering"""
        if not (self.cw_limit_switch_pin and self.ccw_limit_switch_pin):
            raise CalibrationError("Both limit switches required for calibration")
        
        start_time = time.time()
        
        try:
            logger.info(f"[{self.name}] Starting calibration...")
            
            # Clear any previous state
            self.state.triggered_limit = None
            self.state.status = MotorStatus.CALIBRATING
            self.release()
            
            # First move to CCW limit
            logger.info(f"[{self.name}] Moving to CCW limit...")
            self.set_direction(COUNTER_CLOCKWISE)
            while not self._check_limit_switch(COUNTER_CLOCKWISE):
                if time.time() - start_time > self.calibration_timeout:
                    raise CalibrationError("Calibration timed out waiting for CCW limit")
                steps = self.step(1, delay=0.0005)  # Move in smaller increments
                time.sleep(0.001)
                if steps == 0:  # If we couldn't move, might be at limit already
                    break
            
            if not self._check_limit_switch(COUNTER_CLOCKWISE):
                raise CalibrationError("Failed to reach CCW limit")
            
            logger.info(f"[{self.name}] Reached CCW limit")
            
            # Move away from CCW limit
            logger.info(f"[{self.name}] Backing off from CCW limit...")
            self.state.triggered_limit = None  # Clear the limit state
            self.set_direction(CLOCKWISE)
            backoff_steps = self.step(self.limit_backoff_steps, delay=0.0005)
            logger.debug(f"[{self.name}] Backed off {backoff_steps} steps from CCW limit")
            
            # Find CW limit and measure total travel
            logger.info(f"[{self.name}] Finding CW limit and measuring range...")
            self.set_direction(CLOCKWISE)
            total_steps = 0
            
            while not self._check_limit_switch(CLOCKWISE):
                if time.time() - start_time > self.calibration_timeout:
                    raise CalibrationError("Calibration timed out waiting for CW limit")
                steps = self.step(1, delay=0.0005)  # Move in smaller increments
                total_steps += steps
                time.sleep(0.001)
                if steps == 0:  # If we couldn't move, might be at limit
                    break
            
            if not self._check_limit_switch(CLOCKWISE):
                raise CalibrationError("Failed to reach CW limit")
            
            logger.info(f"[{self.name}] Reached CW limit. Total travel: {total_steps} steps")
            
            # Store total travel distance
            self.total_travel_steps = total_steps
            
            # Move to center position
            logger.info(f"[{self.name}] Moving to center position...")
            self.state.triggered_limit = None  # Clear the limit state
            self.set_direction(COUNTER_CLOCKWISE)
            center_steps = self.step(total_steps // 2, delay=0.0005)
            logger.info(f"[{self.name}] Moved {center_steps} steps to center")
            
            # Reset position counter to 0 at center
            self.state.position = 0
            self.state.status = MotorStatus.IDLE
            
            logger.info(
                f"[{self.name}] Calibration complete. "
                f"Total travel: {self.total_travel_steps} steps"
            )
            
        except Exception as e:
            logger.error(f"[{self.name}] Calibration failed: {str(e)}")
            self.state.status = MotorStatus.ERROR
            self.state.error_message = str(e)
            self.release()
            raise CalibrationError(f"Calibration failed: {str(e)}")

    def get_status(self) -> MotorState:
        """Get current motor status"""
        with self.lock:
            return self.state

    def status(self) -> dict:
        with self.lock:
            return {
                'type': 'axis',
                'name': self.name,
                'enabled': self.enabled,
                'moving': self.state.status == MotorStatus.MOVING,
                'position': {'steps': self.state.position},
                'direction': self.state.direction,
                'limits': {
                    'triggered': self.state.triggered_limit,
                    'cw_pin': self.cw_limit_switch_pin,
                    'ccw_pin': self.ccw_limit_switch_pin,
                },
                'microstep': self.microsteps,
                'steps_per_rev': self.steps_per_rev,
                'calibration': {
                    'total_travel_steps': self.total_travel_steps,
                    'is_calibrated': self.total_travel_steps is not None,
                },
                'error': {
                    'message': self.state.error_message,
                    'status': self.state.status.value if self.state.status == MotorStatus.ERROR else None,
                },
            }

    def get_limit_switch_states(self) -> Tuple[Optional[bool], Optional[bool]]:
        """Get the current state of both limit switches"""
        with self.lock:
            def read_switch_with_verification(pin: Optional[int]) -> Optional[bool]:
                if pin is None:
                    return None
                    
                # Take multiple readings over a short period
                readings = []
                for _ in range(5):
                    readings.append(self.gpio.input(pin) == 0)
                    time.sleep(0.001)
                    
                # Return True only if majority of readings indicate switch is pressed
                return sum(readings) >= 3
            
            cw_state = read_switch_with_verification(self.cw_limit_switch_pin)
            ccw_state = read_switch_with_verification(self.ccw_limit_switch_pin)
            
            return (cw_state, ccw_state)