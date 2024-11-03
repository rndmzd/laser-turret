from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import logging
import time
import RPi.GPIO as GPIO
import threading
from typing import Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

CLOCKWISE = 'CW'
COUNTER_CLOCKWISE = 'CCW'

class MotorStatus(Enum):
    """Enum for motor status"""
    INITIALIZING = "initializing"
    IDLE = "idle"
    MOVING = "moving"
    ERROR = "error"
    LIMIT_REACHED = "limit_reached"
    CALIBRATING = "calibrating"

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
        direction_timeout: int = 30,
        kit: Optional[MotorKit] = None,
        interactive_test_mode: bool = False):
        """
        Initialize the stepper motor with improved error checking and thread safety.

        Args:
            motor_channel: Motor channel (1 or 2)
            cw_limit_switch_pin: GPIO pin for clockwise limit switch
            ccw_limit_switch_pin: GPIO pin for counter-clockwise limit switch
            steps_per_rev: Steps per revolution
            microsteps: Number of microsteps
            skip_direction_check: Skip direction verification
            perform_calibration: Perform initial calibration
            limit_backoff_steps: Steps to back off after hitting limit
            name: Motor name for logging
            calibration_timeout: Timeout for calibration in seconds
            movement_timeout: Timeout for movement operations in seconds
            kit: Optional pre-configured MotorKit instance
        """
        """Initialize the stepper motor with improved error checking and thread safety."""
        # First try to cleanup any existing GPIO setup
        try:
            if cw_limit_switch_pin:
                try:
                    GPIO.remove_event_detect(cw_limit_switch_pin)
                except:
                    pass
                try:
                    GPIO.cleanup(cw_limit_switch_pin)
                except:
                    pass
                    
            if ccw_limit_switch_pin:
                try:
                    GPIO.remove_event_detect(ccw_limit_switch_pin)
                except:
                    pass
                try:
                    GPIO.cleanup(ccw_limit_switch_pin)
                except:
                    pass
        except:
            pass
        
        # Validate configuration
        self._validate_config(
            motor_channel,
            cw_limit_switch_pin,
            ccw_limit_switch_pin,
            steps_per_rev,
            microsteps
        )

        # Initialize basic attributes
        self.lock = threading.Lock()
        self.state = MotorState(status=MotorStatus.INITIALIZING)
        self.motor_channel = motor_channel
        self.cw_limit_switch_pin = cw_limit_switch_pin
        self.ccw_limit_switch_pin = ccw_limit_switch_pin
        self.steps_per_rev = steps_per_rev
        self.name = name
        self.limit_backoff_steps = limit_backoff_steps
        self.total_travel_steps = None
        self.calibration_timeout = calibration_timeout
        self.movement_timeout = movement_timeout

        # Initialize MotorKit
        try:
            self.kit = kit if kit else MotorKit(steppers_microsteps=microsteps)
            self.motor = self.kit.stepper1 if motor_channel == 1 else self.kit.stepper2
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize MotorKit: {str(e)}")

        self.step_style = stepper.SINGLE
        
        # Initialize GPIO
        try:
            self._setup_gpio()
        except Exception as e:
            raise ConfigurationError(f"Failed to setup GPIO: {str(e)}")
        
        if not interactive_test_mode:
            try:
                self.confirm_limit_switches(
                    skip_direction_check=skip_direction_check, 
                    timeout=direction_timeout
                )
            except Exception as e:
                logger.error(f"[{self.name}] Error during limit switch confirmation: {e}")
                self.release()
                self.cleanup()
                raise
        
            if perform_calibration:
                self.calibrate()

    def _validate_config(self, motor_channel: int, cw_pin: Optional[int],
                        ccw_pin: Optional[int], steps_per_rev: int,
                        microsteps: int) -> None:
        """Validate configuration parameters"""
        if motor_channel not in [1, 2]:
            raise ConfigurationError("Motor channel must be 1 or 2.")
        
        if steps_per_rev <= 0:
            raise ConfigurationError("Steps per revolution must be positive.")
        
        if microsteps not in [1, 2, 4, 8, 16]:
            raise ConfigurationError("Microsteps must be 1, 2, 4, 8, or 16.")
        
        # Validate GPIO pins
        valid_pins = set(range(2, 28))  # Valid BCM pins on RPi
        if cw_pin and cw_pin not in valid_pins:
            raise ConfigurationError(f"Invalid CW limit switch pin: {cw_pin}")
        if ccw_pin and ccw_pin not in valid_pins:
            raise ConfigurationError(f"Invalid CCW limit switch pin: {ccw_pin}")
        if cw_pin and ccw_pin and cw_pin == ccw_pin:
            raise ConfigurationError("CW and CCW limit switch pins must be different.")

    def _setup_gpio(self) -> None:
        """Setup GPIO with proper error handling"""
        try:
            # First try to clean up any existing GPIO setup for our pins
            if self.cw_limit_switch_pin:
                try:
                    GPIO.remove_event_detect(self.cw_limit_switch_pin)
                except:
                    pass
                try:
                    GPIO.cleanup(self.cw_limit_switch_pin)
                except:
                    pass
                    
            if self.ccw_limit_switch_pin:
                try:
                    GPIO.remove_event_detect(self.ccw_limit_switch_pin)
                except:
                    pass
                try:
                    GPIO.cleanup(self.ccw_limit_switch_pin)
                except:
                    pass

            # Set mode after cleanup
            GPIO.setmode(GPIO.BCM)
            
            # Setup limit switch pins with pull-up resistors
            for pin, direction in [(self.cw_limit_switch_pin, CLOCKWISE),
                                (self.ccw_limit_switch_pin, COUNTER_CLOCKWISE)]:
                if pin is not None:
                    try:
                        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                        GPIO.add_event_detect(
                            pin,
                            GPIO.FALLING,
                            callback=lambda channel, dir=direction:
                                self.limit_switch_callback(channel, dir),
                            bouncetime=200
                        )
                    except Exception as e:
                        self.cleanup()
                        raise ConfigurationError(f"Failed to setup GPIO pin {pin}: {str(e)}")

        except Exception as e:
            raise ConfigurationError(f"Failed to setup GPIO: {str(e)}")

    def get_status(self) -> MotorState:
        """Get current motor status"""
        with self.lock:
            return self.state
    
    def confirm_motor_direction(self, timeout: Optional[float] = None) -> None:
        """Test motor direction with user confirmation and timeout
        
        Args:
            timeout: Optional timeout in seconds for user response
        
        Raises:
            ConfigurationError: If direction is incorrect or confirmation times out
        """
        try:
            with self.lock:
                self.state.status = MotorStatus.INITIALIZING
                
            logger.info("Testing clockwise movement...")
            self.set_direction(CLOCKWISE)
            self.step(5, delay=0.1)

            start_time = time.time()
            while True:
                user_response = input("Did the motor move clockwise? (yes/no): ").strip().lower()
                if timeout and (time.time() - start_time > timeout):
                    error_msg = f"[{self.name}] Direction confirmation timeout."
                    logger.error(error_msg)
                    raise ConfigurationError(error_msg)
                    
                if user_response in ['yes', 'no']:
                    break
                print("Please answer 'yes' or 'no'")

            if user_response != 'yes':
                error_msg = f"[{self.name}] Motor direction incorrect. Check wiring."
                logger.error(error_msg)
                raise ConfigurationError(error_msg)
                
        except KeyboardInterrupt:
            logger.info(f"[{self.name}] Direction confirmation interrupted by user.")
            self.release()
            raise
            
        except Exception as e:
            with self.lock:
                self.state.status = MotorStatus.ERROR
                self.state.error_message = str(e)
            raise
            
        finally:
            with self.lock:
                if self.state.status != MotorStatus.ERROR:
                    self.state.status = MotorStatus.IDLE
    
    def confirm_limit_switches(self, skip_direction_check: bool = False, timeout: Optional[float] = None) -> None:
        """
        Confirm both limit switches are working correctly.
        This is an interactive method that requires user input.
        
        Args:
            skip_direction_check: If True, skips the initial direction verification
            timeout: Optional timeout in seconds for user responses
        """
        logger.info(f"\n[{self.name}] Testing limit switches...")

        if not skip_direction_check:
            self.confirm_motor_direction(timeout=timeout)
            
        logger.info(f"\n[{self.name}] Testing limit switches...")

        # Test both limit switches
        logger.info("\nPlease trigger each limit switch to confirm they're working:")

        if self.cw_limit_switch_pin:
            logger.info("1. Trigger the CW limit switch...")
            trigger_time = time.time()
            while not self.state.triggered_limit:
                time.sleep(0.1)
                if time.time() - trigger_time > self.movement_timeout:
                    error_msg = f"[{self.name}] Timeout waiting for CW limit switch."
                    logger.error(error_msg)
                    raise ConfigurationError(error_msg)
            if self.state.triggered_limit != CLOCKWISE:
                error_msg = f"[{self.name}] Wrong limit switch triggered. Check wiring."
                logger.error(error_msg)
                raise ConfigurationError(error_msg)
            with self.lock:
                self.state.triggered_limit = None
                self.state.status = MotorStatus.IDLE

        if self.ccw_limit_switch_pin:
            logger.info("2. Trigger the CCW limit switch...")
            trigger_time = time.time()
            while not self.state.triggered_limit:
                time.sleep(0.1)
                if time.time() - trigger_time > self.movement_timeout:
                    error_msg = f"[{self.name}] Timeout waiting for CCW limit switch."
                    logger.error(error_msg)
                    raise ConfigurationError(error_msg)
            if self.state.triggered_limit != COUNTER_CLOCKWISE:
                error_msg = f"[{self.name}] Wrong limit switch triggered. Check wiring."
                logger.error(error_msg)
                raise ConfigurationError(error_msg)
            with self.lock:
                self.state.triggered_limit = None
                self.state.status = MotorStatus.IDLE

        logger.info("Limit switch testing complete.")

    def get_limit_switch_states(self) -> Tuple[Optional[bool], Optional[bool]]:
        """
        Get the current state of both limit switches.
        
        Returns:
            Tuple of (CW limit state, CCW limit state)
            None if limit switch is not configured
            True if limit switch is triggered
            False if limit switch is not triggered
        """
        with self.lock:
            cw_state = (GPIO.input(self.cw_limit_switch_pin) == 0
                       if self.cw_limit_switch_pin else None)
            ccw_state = (GPIO.input(self.ccw_limit_switch_pin) == 0
                        if self.ccw_limit_switch_pin else None)
            return (cw_state, ccw_state)

    def set_direction(self, direction: str) -> None:
        """Set motor direction with improved thread safety"""
        if direction not in [CLOCKWISE, COUNTER_CLOCKWISE]:
            raise ValueError(f"Invalid direction: {direction}")
        
        with self.lock:
            # Check if movement is allowed
            if ((direction == CLOCKWISE and self.state.triggered_limit == CLOCKWISE) or
                (direction == COUNTER_CLOCKWISE and self.state.triggered_limit == COUNTER_CLOCKWISE)):
                raise LimitSwitchError(
                    f"Cannot move {direction}, limit switch triggered."
                )
            
            self.state.direction = direction
            self.motor_direction = (stepper.FORWARD if direction == CLOCKWISE
                                  else stepper.BACKWARD)
            
            # Reset stop condition if moving away from triggered limit
            if ((direction == COUNTER_CLOCKWISE and self.state.triggered_limit == CLOCKWISE) or
                (direction == CLOCKWISE and self.state.triggered_limit == COUNTER_CLOCKWISE)):
                self.state.triggered_limit = None
                self.state.status = MotorStatus.IDLE

    def limit_switch_callback(self, channel: int, direction: str) -> None:
        """Thread-safe limit switch callback"""
        with self.lock:
            self.state.triggered_limit = direction
            self.state.status = MotorStatus.LIMIT_REACHED
            logger.info(f"[{self.name}] {direction} limit switch triggered.")

    def step(self, steps: int, delay: float = 0.001) -> int:
        """
        Move motor with timeout and improved error handling
        
        Args:
            steps: Number of steps to move
            delay: Delay between steps in seconds
            
        Returns:
            Number of steps actually moved
            
        Raises:
            MotorError: If movement times out or other error occurs
        """
        if steps < 0:
            raise ValueError("Steps must be positive")
        
        start_time = time.time()
        actual_steps = 0
        
        try:
            with self.lock:
                self.state.status = MotorStatus.MOVING
            
            for _ in range(steps):
                if time.time() - start_time > self.movement_timeout:
                    raise MotorError("Movement operation timed out.")
                
                with self.lock:
                    if self.state.triggered_limit:
                        break
                    
                    self.motor.onestep(
                        direction=self.motor_direction,
                        style=self.step_style
                    )
                    
                    if self.motor_direction == stepper.FORWARD:
                        self.state.position += 1
                    else:
                        self.state.position -= 1
                    
                actual_steps += 1
                time.sleep(delay)
                
        except KeyboardInterrupt:
            logger.info(f"[{self.name}] Movement interrupted by user.")
            self.release()
            raise
                
        except Exception as e:
            with self.lock:
                self.state.status = MotorStatus.ERROR
                self.state.error_message = str(e)
            raise
        
        finally:
            with self.lock:
                if self.state.status != MotorStatus.ERROR:
                    self.state.status = MotorStatus.IDLE
        
        return actual_steps

    def calibrate(self) -> None:
        """Calibrate with timeout and improved error handling"""
        if not (self.cw_limit_switch_pin and self.ccw_limit_switch_pin):
            raise CalibrationError("Both limit switches required for calibration.")
        
        start_time = time.time()
        
        try:
            with self.lock:
                self.state.status = MotorStatus.CALIBRATING
                self.release()
            
            logger.info(f"[{self.name}] Starting calibration...")
            
            # Move to CCW limit
            self.set_direction(COUNTER_CLOCKWISE)
            while not self.state.triggered_limit:
                if time.time() - start_time > self.calibration_timeout:
                    raise CalibrationError("Calibration timed out.")
                self.step(1, delay=0.01)
            
            # Move away from CCW limit
            self.set_direction(CLOCKWISE)
            self.step(self.limit_backoff_steps, delay=0.01)
            
            # Move to CW limit while counting steps
            step_count = 0
            self.set_direction(CLOCKWISE)
            
            while not self.state.triggered_limit:
                if time.time() - start_time > self.calibration_timeout:
                    raise CalibrationError("Calibration timed out.")
                step_count += self.step(1, delay=0.01)
            
            # Store total travel distance
            self.total_travel_steps = step_count
            
            # Move to center position
            self.set_direction(COUNTER_CLOCKWISE)
            self.step(step_count // 2, delay=0.01)
            
            with self.lock:
                self.state.position = 0
                self.state.status = MotorStatus.IDLE
            
            logger.info(
                f"[{self.name}] Calibration complete. "
                f"Total travel: {self.total_travel_steps} steps"
            )
            
        except KeyboardInterrupt:
            logger.info(f"[{self.name}] Calibration interrupted by user.")
            self.release()
            raise
            
        except Exception as e:
            with self.lock:
                self.state.status = MotorStatus.ERROR
                self.state.error_message = str(e)
            self.release()
            raise CalibrationError(f"Calibration failed: {str(e)}")

    def release(self) -> None:
        """Thread-safe motor release"""
        with self.lock:
            self.motor.release()
            self.state.status = MotorStatus.IDLE
            self.state.triggered_limit = None

    def cleanup(self) -> None:
        """Cleanup specific GPIO pins only"""
        pins_to_cleanup = []
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
                
        logger.info(f"[{self.name}] GPIO cleanup complete.")