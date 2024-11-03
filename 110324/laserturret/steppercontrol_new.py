from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import logging
import time
import RPi.GPIO as GPIO
import threading

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

CLOCKWISE = 'CW'
COUNTER_CLOCKWISE = 'CCW'

class StepperMotor:
    def __init__(
            self,
            motor_channel: int,
            cw_limit_switch_pin: int = None,
            ccw_limit_switch_pin: int = None,
            steps_per_rev: int = 200,
            microsteps: int = 8,
            skip_direction_check: bool = False,
            perform_calibration: bool = True,
            limit_backoff_steps: int = 1,
            name: str = "Motor",
            kit: MotorKit = None):
        """
        Initialize the stepper motor using Adafruit MotorKit.

        :param motor_channel: The motor channel (1 or 2) on the Adafruit Motor HAT.
        :param cw_limit_switch_pin: GPIO pin for the clockwise limit switch.
        :param ccw_limit_switch_pin: GPIO pin for the counter-clockwise limit switch.
        :param steps_per_rev: Number of steps per revolution for the stepper motor.
        :param microsteps: Number of microsteps to set for the motor.
        :param skip_direction_check: Whether to skip the direction check.
        :param perform_calibration: Whether to perform calibration.
        :param limit_backoff_steps: Number of steps to back off after hitting a limit switch.
        :param name: Name of the motor (for identification in logs).
        :param kit: An instance of MotorKit; if None, a new instance will be created.
        """
        self.lock = threading.Lock()
        self.motor_channel = motor_channel
        self.cw_limit_switch_pin = cw_limit_switch_pin
        self.ccw_limit_switch_pin = ccw_limit_switch_pin
        self.steps_per_rev = steps_per_rev
        self.name = name
        self.stop_flag = False
        self.limit_backoff_steps = limit_backoff_steps
        self.triggered_limit = None  # Tracks which limit switch was triggered

        self.position = 0
        self.total_travel_steps = None  # Will be set during calibration

        # Initialize MotorKit instance with microsteps
        if kit is None:
            self.kit = MotorKit(steppers_microsteps=microsteps)
        else:
            self.kit = kit

        if motor_channel not in [1, 2]:
            raise ValueError("Invalid motor channel. Use 1 or 2.")
        self.motor = self.kit.stepper1 if motor_channel == 1 else self.kit.stepper2

        # Default microstepping settings
        self.step_style = stepper.SINGLE

        self.motor_direction = None
        self.set_direction(CLOCKWISE)  # Default direction

        # Setup limit switch pins if provided
        GPIO.setmode(GPIO.BCM)

        if self.cw_limit_switch_pin is not None:
            GPIO.setup(self.cw_limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(self.cw_limit_switch_pin, GPIO.FALLING,
                                  callback=lambda channel: self.limit_switch_callback(channel, CLOCKWISE),
                                  bouncetime=200)

        if self.ccw_limit_switch_pin is not None:
            GPIO.setup(self.ccw_limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(self.ccw_limit_switch_pin, GPIO.FALLING,
                                  callback=lambda channel: self.limit_switch_callback(channel, COUNTER_CLOCKWISE),
                                  bouncetime=200)

        # Check if either limit switch is already triggered
        if self._check_initial_limits():
            logger.warning(f"[{self.name}] Limit switch already triggered. Move away from limit switches and restart.")
            self.release()
            self.cleanup()
            raise RuntimeError("Limit switch already triggered on startup.")

        if not skip_direction_check:
            try:
                self.confirm_limit_switches()
            except Exception as e:
                logger.error(f"[{self.name}] Error during limit switch confirmation: {e}")
                self.release()
                self.cleanup()
                raise

        if perform_calibration:
            self.calibrate()

    def _check_initial_limits(self) -> bool:
        """Check if either limit switch is triggered on startup."""
        if (self.cw_limit_switch_pin and GPIO.input(self.cw_limit_switch_pin) == 0) or \
           (self.ccw_limit_switch_pin and GPIO.input(self.ccw_limit_switch_pin) == 0):
            return True
        return False

    def set_direction(self, direction: str) -> None:
        """
        Set the rotation direction.

        :param direction: 'CW' for clockwise, 'CCW' for counter-clockwise.
        """
        if direction not in [CLOCKWISE, COUNTER_CLOCKWISE]:
            raise ValueError("Invalid direction. Use 'CW' or 'CCW'.")

        # Only allow movement if we're not moving toward a triggered limit
        if (direction == CLOCKWISE and self.triggered_limit == CLOCKWISE) or \
           (direction == COUNTER_CLOCKWISE and self.triggered_limit == COUNTER_CLOCKWISE):
            error_msg = f"[{self.name}] Cannot move {direction}, limit switch triggered."
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        self.motor_direction = stepper.FORWARD if direction == CLOCKWISE else stepper.BACKWARD

        # Reset stop flag if moving away from triggered limit
        if ((direction == COUNTER_CLOCKWISE and self.triggered_limit == CLOCKWISE) or
            (direction == CLOCKWISE and self.triggered_limit == COUNTER_CLOCKWISE)):
            with self.lock:
                self.stop_flag = False
                self.triggered_limit = None

    def limit_switch_callback(self, channel: int, direction: str) -> None:
        """
        Callback function for limit detection.

        :param channel: GPIO channel that triggered the callback
        :param direction: 'CW' or 'CCW' indicating which limit switch was triggered
        """
        with self.lock:
            self.stop_flag = True
            self.triggered_limit = direction
        logger.info(f"[{self.name}] {direction} limit switch triggered.")

    def confirm_limit_switches(self) -> None:
        """
        Confirm both limit switches are working correctly.
        """
        logger.info(f"\n[{self.name}] Testing limit switches...")

        # Test CW direction
        logger.info("Testing clockwise movement...")
        self.set_direction(CLOCKWISE)
        self.step(5, delay=0.1)

        user_response = input("Did the motor move clockwise? (yes/no): ").strip().lower()
        if user_response != 'yes':
            error_msg = f"[{self.name}] Motor direction incorrect. Check wiring."
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Test both limit switches
        logger.info("\nPlease trigger each limit switch to confirm they're working:")

        if self.cw_limit_switch_pin:
            logger.info("1. Trigger the CW limit switch...")
            while not self.triggered_limit:
                time.sleep(0.1)
            if self.triggered_limit != CLOCKWISE:
                error_msg = f"[{self.name}] Wrong limit switch triggered. Check wiring."
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            with self.lock:
                self.triggered_limit = None
                self.stop_flag = False

        if self.ccw_limit_switch_pin:
            logger.info("2. Trigger the CCW limit switch...")
            while not self.triggered_limit:
                time.sleep(0.1)
            if self.triggered_limit != COUNTER_CLOCKWISE:
                error_msg = f"[{self.name}] Wrong limit switch triggered. Check wiring."
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            with self.lock:
                self.triggered_limit = None
                self.stop_flag = False

        logger.info("Limit switch testing complete.")

    def calibrate(self) -> None:
        """
        Calibrate the motor by measuring the total travel distance between limit switches.
        """
        if not (self.cw_limit_switch_pin and self.ccw_limit_switch_pin):
            raise ValueError("Both limit switch pins must be set for calibration.")

        self.release()
        logger.info(f"[{self.name}] Starting calibration...")

        # Move to CCW limit
        self.set_direction(COUNTER_CLOCKWISE)
        with self.lock:
            self.stop_flag = False
            self.triggered_limit = None
        step_count = 0
        try:
            while not self.stop_flag:
                self.step(1, delay=0.01)
                step_count += 1
                if step_count > 10000:  # Safety limit
                    error_msg = f"[{self.name}] Calibration failed: CCW limit not found within step limit."
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
        except Exception as e:
            self.release()
            self.cleanup()
            raise

        # Move away from CCW limit
        self.set_direction(CLOCKWISE)
        self.step(self.limit_backoff_steps, delay=0.01)

        # Move to CW limit while counting steps
        self.set_direction(CLOCKWISE)
        with self.lock:
            self.stop_flag = False
            self.triggered_limit = None
        step_count = 0
        try:
            while not self.stop_flag:
                self.step(1, delay=0.01)
                step_count += 1
                if step_count > 10000:  # Safety limit
                    error_msg = f"[{self.name}] Calibration failed: CW limit not found within step limit."
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
        except Exception as e:
            self.release()
            self.cleanup()
            raise

        # Store total travel distance
        self.total_travel_steps = step_count

        # Move to center position
        self.set_direction(COUNTER_CLOCKWISE)
        self.step(step_count // 2, delay=0.01)
        self.position = 0  # Set center position as zero

        logger.info(f"[{self.name}] Calibration complete. Total travel: {self.total_travel_steps} steps")

    def step(self, steps: int, delay: float = 0.001) -> int:
        """
        Move the motor a specific number of steps.

        :param steps: Number of steps to move.
        :param delay: Delay between steps in seconds.
        """
        actual_steps = 0
        for _ in range(steps):
            with self.lock:
                if self.stop_flag:
                    logger.warning(f"[{self.name}] Movement stopped due to limit detection.")
                    break
            self.motor.onestep(direction=self.motor_direction, style=self.step_style)
            with self.lock:
                if self.motor_direction == stepper.FORWARD:
                    self.position += 1
                else:
                    self.position -= 1
            actual_steps += 1
            time.sleep(delay)

        return actual_steps

    def release(self) -> None:
        """
        Release the motor to disable it and allow free movement.
        """
        self.motor.release()
        # Decide whether to reset position or not
        # self.position = 0  # Commented out as per suggestion #16
        with self.lock:
            self.stop_flag = False
            self.triggered_limit = None

    def cleanup(self) -> None:
        """
        Clean up GPIO settings.
        """
        GPIO.cleanup()
        logger.info(f"[{self.name}] GPIO cleanup complete.")
