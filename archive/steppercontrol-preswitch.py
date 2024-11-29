from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import logging
import time
import RPi.GPIO as GPIO
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
        motor_channel: int,
        cw_limit_switch_pin: Optional[int] = None,
        ccw_limit_switch_pin: Optional[int] = None,
        steps_per_rev: int = 200,
        microsteps: int = 8,
        step_style: Optional[str] = "MICROSTEP",
        skip_direction_check: bool = False,
        perform_calibration: bool = True,
        limit_backoff_steps: int = 1,
        name: str = "Motor",
        calibration_timeout: int = 30,
        movement_timeout: int = 10,
        deadzone: int = 10,
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
        self.deadzone = deadzone

        if step_style not in ["SINGLE", "DOUBLE", "INTERLEAVE", "MICROSTEP"]:
            raise ConfigurationError("Invalid step style. Must be SINGLE, DOUBLE, INTERLEAVE, or MICROSTEP.")
        if step_style == "SINGLE":
            self.step_style = stepper.SINGLE
        elif step_style == "DOUBLE":
            self.step_style = stepper.DOUBLE
        elif step_style == "INTERLEAVE":
            self.step_style = stepper.INTERLEAVE
        else:
            self.step_style = stepper.MICROSTEP

        # Initialize MotorKit
        try:
            self.kit = kit if kit else MotorKit(steppers_microsteps=microsteps)
            self.motor = self.kit.stepper1 if motor_channel == 1 else self.kit.stepper2
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize MotorKit: {str(e)}")

        # Initialize GPIO
        try:
            self._setup_gpio()
        except Exception as e:
            raise ConfigurationError(f"Failed to setup GPIO: {str(e)}")
        
        # Add command processing thread components
        self.command_queue = queue.Queue(maxsize=1)  # Only keep latest command
        self.running = True
        self.last_command = 0
        self.command_thread = threading.Thread(
            target=self._process_command_queue,
            name=f"{name}_command_thread",
            daemon=True
        )
        self.command_thread.start()

        # Continue with existing initialization (calibration etc.)
        if not interactive_test_mode and not skip_direction_check:
            try:
                self.confirm_limit_switches()
            except Exception as e:
                logger.error(f"[{self.name}] Error during limit switch confirmation: {e}")
                self.running = False
                self.command_thread.join(timeout=1.0)
                self.release()
                self.cleanup()
                raise
        
        if not interactive_test_mode and perform_calibration:
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
            
            # Add timestamps to track last trigger time for each switch
            self._last_cw_trigger = 0
            self._last_ccw_trigger = 0
            self.debounce_time = 0.1  # 100ms debounce window
            
            # Setup limit switch pins with pull-up resistors and improved callback
            for pin, direction in [(self.cw_limit_switch_pin, CLOCKWISE),
                                (self.ccw_limit_switch_pin, COUNTER_CLOCKWISE)]:
                if pin is not None:
                    try:
                        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                        GPIO.add_event_detect(
                            pin,
                            GPIO.FALLING,
                            callback=lambda channel, dir=direction:
                                self._limit_switch_handler(channel, dir),
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
                print("Please answer 'yes' or 'no'.")

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
    
    def confirm_limit_switches(self) -> None:
        """
        Verify limit switch functionality by requesting manual confirmation.
        Used during initialization to ensure switches are properly connected and working.
        
        Raises:
            LimitSwitchError: If switches don't trigger within timeout or wrong switch triggered
        """
        if not (self.cw_limit_switch_pin or self.ccw_limit_switch_pin):
            logger.info(f"[{self.name}] No limit switches configured, skipping verification.")
            return
            
        logger.info(f"\n[{self.name}] Testing limit switches...")
        logger.info("Please trigger each limit switch to confirm they're working:")
        
        timeout = 30  # seconds
        switches_to_test = []
        
        if self.cw_limit_switch_pin:
            switches_to_test.append((CLOCKWISE, "CW"))
        if self.ccw_limit_switch_pin:
            switches_to_test.append((COUNTER_CLOCKWISE, "CCW"))
        
        for direction, name in switches_to_test:
            start_time = time.time()
            logger.info(f"Trigger the {name} limit switch...")
            
            # Wait for correct switch to trigger
            while True:
                if time.time() - start_time > timeout:
                    raise LimitSwitchError(
                        f"Timeout waiting for {name} limit switch confirmation"
                    )
                    
                with self.lock:
                    if self.state.triggered_limit == direction:
                        logger.info(f"[{self.name}] {name} limit switch verified")
                        # Reset the triggered state
                        self.state.triggered_limit = None
                        self.state.status = MotorStatus.IDLE
                        break
                    elif self.state.triggered_limit:
                        raise LimitSwitchError(
                            f"Wrong limit switch triggered: expected {name}, "
                            f"got {self.state.triggered_limit}"
                        )
                        
                time.sleep(0.1)
        
        logger.info(f"[{self.name}] All limit switches verified!")

    def get_limit_switch_states(self) -> Tuple[Optional[bool], Optional[bool]]:
        """
        Get the current state of both limit switches with improved debouncing.
        
        Returns:
            Tuple of (CW limit state, CCW limit state)
            None if limit switch is not configured
            True if limit switch is triggered (pressed)
            False if limit switch is not triggered
        """
        with self.lock:
            def read_switch_with_verification(pin: Optional[int]) -> Optional[bool]:
                if pin is None:
                    return None
                    
                # Take multiple readings over a short period
                readings = []
                for _ in range(5):
                    readings.append(GPIO.input(pin) == 0)
                    time.sleep(0.001)  # 1ms between readings
                    
                # Return True only if majority of readings indicate switch is pressed
                return sum(readings) >= 3
            
            cw_state = read_switch_with_verification(self.cw_limit_switch_pin)
            ccw_state = read_switch_with_verification(self.ccw_limit_switch_pin)
            
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
    
    def _limit_switch_handler(self, channel: int, direction: str) -> None:
        """
        Fast limit switch event handler with minimal processing
        """
        current_time = time.time()
        
        # Quick debounce check without lock
        if direction == CLOCKWISE:
            if current_time - self._last_cw_trigger < self.debounce_time:
                return
            self._last_cw_trigger = current_time
        else:  # COUNTER_CLOCKWISE
            if current_time - self._last_ccw_trigger < self.debounce_time:
                return
            self._last_ccw_trigger = current_time
        
        # Quick state update without lock if switch is actually pressed
        if GPIO.input(channel) == 0:  # Switch is pressed (pulled low)
            self.state.triggered_limit = direction
            self.state.status = MotorStatus.LIMIT_REACHED
            logger.info(f"[{self.name}] {direction} limit switch triggered")
    
    def _calculate_step_delay(self, command_value: float) -> Optional[float]:
        """
        Calculate step delay based on command value magnitude with smoother control.
        """
        # Tuned delay bounds (in seconds)
        MIN_DELAY = 0.00005  # Maximum speed
        MAX_DELAY = 0.1   # Minimum speed
        # DEADZONE = 5         # Smaller deadzone for more responsive control
        
        # Check deadzone
        abs_value = abs(command_value)
        if abs_value < self.deadzone:
            return None
            
        # Use cubic mapping for smoother acceleration
        command_range = 100 - self.deadzone
        normalized_command = (abs_value - self.deadzone) / command_range
        
        # Cubic curve for even smoother acceleration
        exponential_factor = 1.0  # Exponential scaling factor
        speed_multiplier = pow(normalized_command, exponential_factor)
        
        # Calculate delay with cubic curve
        delay_range = MAX_DELAY - MIN_DELAY
        delay = MAX_DELAY - (speed_multiplier * delay_range)
        
        return max(MIN_DELAY, min(MAX_DELAY, delay))
    
    def _process_command_queue(self):
        """
        Continuously process motor commands in separate thread.
        """
        while self.running:
            try:
                # Get latest command value, discard old ones
                try:
                    while True:
                        command = self.command_queue.get_nowait()
                        self.last_command = command
                except queue.Empty:
                    command = self.last_command

                # Process the command
                if abs(command) < self.deadzone:  # Deadzone
                    with self.lock:
                        if self.state.status not in [MotorStatus.ERROR, MotorStatus.LIMIT_REACHED]:
                            self.state.status = MotorStatus.HOLDING
                    time.sleep(0.001)  # Short sleep when idle
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

                # Calculate delay based on command magnitude with better low-speed control
                abs_value = abs(command)
                min_delay = 0.00001   # 10 microseconds at full speed
                max_delay = 0.001     # 1000 microseconds (1ms) at minimum speed
                # Exponential scaling for better low-speed control
                speed_factor = pow(abs_value / 100.0, 3)  # Cubic scaling gives more granularity at low speeds
                delay = max_delay - (speed_factor * (max_delay - min_delay))
                
                # Update status
                with self.lock:
                    self.state.status = MotorStatus.MOVING

                # Single step with calculated delay
                self.motor.onestep(direction=self.motor_direction, style=self.step_style)
                
                # Update position
                with self.lock:
                    if self.motor_direction == stepper.FORWARD:
                        self.state.position += 1
                    else:
                        self.state.position -= 1

                # Apply delay for speed control
                time.sleep(delay)

                # Log movement occasionally (every 100 steps)
                if self.state.position % 100 == 0:
                    logger.debug(f"[{self.name}] Command: {command:.1f}, "
                        f"Speed factor: {speed_factor:.3f}, "
                        f"Delay: {delay*1e6:.1f}µs, "
                        f"Direction: {direction}")

            except Exception as e:
                logger.error(f"[{self.name}] Error in command thread: {str(e)}")
                time.sleep(0.1)  # Prevent tight error loop

    def process_command(self, command_value: float) -> None:
        """
        Queue new command for processing.
        Overwrites any existing command in queue.
        """
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

    def step(self, steps: int, delay: float = 0.0001) -> int:
        """
        Move motor with smoother motion control.
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
            
            self.state.status = MotorStatus.MOVING
            
            # Distribute steps evenly over time
            step_delay = delay / max(1, steps)  # Distribute delay across steps
            
            for _ in range(steps):
                # Check for timeout
                if time.time() - start_time > self.movement_timeout:
                    raise MotorError("Movement operation timed out")
                
                # Check for limit switch
                if self.state.triggered_limit:
                    break
                
                # Single step
                self.motor.onestep(
                    direction=self.motor_direction,
                    style=self.step_style
                )
                
                # Update position
                if self.motor_direction == stepper.FORWARD:
                    self.state.position += 1
                else:
                    self.state.position -= 1
                
                actual_steps += 1
                
                # Use the distributed delay
                time.sleep(step_delay)
                
        except Exception as e:
            self.state.status = MotorStatus.ERROR
            self.state.error_message = str(e)
            raise
        
        finally:
            if self.state.status != MotorStatus.ERROR:
                self.state.status = (MotorStatus.LIMIT_REACHED 
                                if self.state.triggered_limit 
                                else MotorStatus.IDLE)
        
        return actual_steps

    def calibrate(self) -> None:
        """Calibrate with improved feedback and error handling"""
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
            while not self.state.triggered_limit:
                if time.time() - start_time > self.calibration_timeout:
                    raise CalibrationError("Calibration timed out waiting for CCW limit")
                steps = self.step(1, delay=0.0005)  # Move in smaller increments
                logger.info(f"[{self.name}] Moved {steps} steps toward CCW limit")
                if steps == 0:  # If we couldn't move, might be at limit already
                    break
            
            if not self.state.triggered_limit:
                raise CalibrationError("Failed to reach CCW limit")
            
            logger.info(f"[{self.name}] Reached CCW limit")
            
            # Move away from CCW limit
            logger.info(f"[{self.name}] Backing off from CCW limit...")
            self.state.triggered_limit = None  # Clear the limit state
            self.set_direction(CLOCKWISE)
            backoff_steps = self.step(self.limit_backoff_steps, delay=0.0005)
            logger.info(f"[{self.name}] Backed off {backoff_steps} steps from CCW limit")
            
            # Now move to CW limit while counting steps
            logger.info(f"[{self.name}] Moving to CW limit...")
            self.set_direction(CLOCKWISE)
            total_steps = 0
            
            while not self.state.triggered_limit:
                if time.time() - start_time > self.calibration_timeout:
                    raise CalibrationError("Calibration timed out waiting for CW limit")
                steps = self.step(1, delay=0.0005)  # Move in smaller increments
                total_steps += steps
                logger.info(f"[{self.name}] Moved {steps} steps toward CW limit (Total: {total_steps})")
                if steps == 0:  # If we couldn't move, might be at limit
                    break
            
            if not self.state.triggered_limit:
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

    def release(self) -> None:
        """Thread-safe motor release"""
        with self.lock:
            self.motor.release()
            self.state.status = MotorStatus.IDLE
            self.state.triggered_limit = None

    def hold_position(self) -> None:
        """Hold motor in current position"""
        with self.lock:
            if self.state.status not in [MotorStatus.ERROR, MotorStatus.LIMIT_REACHED]:
                self.state.status = MotorStatus.HOLDING

    def cleanup(self):
        """Enhanced cleanup with thread shutdown."""
        logger.info(f"[{self.name}] Starting cleanup...")
        
        # Stop command processing thread
        self.running = False
        if hasattr(self, 'command_thread'):
            self.command_thread.join(timeout=1.0)
        
        # Release motor
        self.release()
        
        # Cleanup GPIO
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
                
        logger.info(f"[{self.name}] Cleanup complete.")
