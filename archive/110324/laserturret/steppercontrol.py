from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import logging
import time
import RPi.GPIO as GPIO

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class StepperMotorOld:
    def __init__(
            self,
            motor_channel,
            cw_limit_switch_pin=None,
            ccw_limit_switch_pin=None,
            steps_per_rev=200,
            microsteps=8,
            skip_direction_check=False,
            perform_calibration=True,
            limit_backoff_steps=1,
            name="Motor"):
        """
        Initialize the stepper motor using Adafruit MotorKit.

        :param motor_channel: The motor channel (1 or 2) on the Adafruit Motor HAT.
        :param cw_limit_switch_pin: GPIO pin for the clockwise limit switch.
        :param ccw_limit_switch_pin: GPIO pin for the counter-clockwise limit switch.
        :param steps_per_rev: Number of steps per revolution for the stepper motor.
        :param microsteps: Number of microsteps to set for the motor.
        :param name: Name of the motor (for identification in prints).
        """
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
        self.kit = MotorKit(steppers_microsteps=microsteps)
        if motor_channel not in [1, 2]:
            raise ValueError("Invalid motor channel. Use 1 or 2.")
        self.motor = self.kit.stepper1 if motor_channel == 1 else self.kit.stepper2

        # Default microstepping settings
        self.step_style = stepper.SINGLE
        
        self.motor_direction = None
        self.set_direction('CW')  # Default direction

        # Setup limit switch pins if provided
        GPIO.setmode(GPIO.BCM)
        
        if self.cw_limit_switch_pin is not None:
            GPIO.setup(self.cw_limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(self.cw_limit_switch_pin, GPIO.FALLING, 
                                callback=lambda channel: self.limit_switch_callback(channel, 'CW'), 
                                bouncetime=200)
            
        if self.ccw_limit_switch_pin is not None:
            GPIO.setup(self.ccw_limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(self.ccw_limit_switch_pin, GPIO.FALLING, 
                                callback=lambda channel: self.limit_switch_callback(channel, 'CCW'), 
                                bouncetime=200)

        # Check if either limit switch is already triggered
        if self._check_initial_limits():
            logger.warn(f"[{self.name}] Limit switch already triggered. Move away from limit switches and restart.")
            self.release()
            self.cleanup()
            exit()
        
        if not skip_direction_check:
            self.confirm_limit_switches()
        
        if perform_calibration:
            self.calibrate()

    def _check_initial_limits(self):
        """Check if either limit switch is triggered on startup."""
        if (self.cw_limit_switch_pin and GPIO.input(self.cw_limit_switch_pin) == 0) or \
           (self.ccw_limit_switch_pin and GPIO.input(self.ccw_limit_switch_pin) == 0):
            return True
        return False

    def set_direction(self, direction):
        """
        Set the rotation direction.

        :param direction: 'CW' for clockwise, 'CCW' for counter-clockwise.
        """
        if direction not in ['CW', 'CCW']:
            raise ValueError("Invalid direction. Use 'CW' or 'CCW'.")
            
        # Only allow movement if we're not moving toward a triggered limit
        if (direction == 'CW' and self.triggered_limit == 'CW') or \
           (direction == 'CCW' and self.triggered_limit == 'CCW'):
            logger.warning(f"[{self.name}] Cannot move {direction}, limit switch triggered.")
            return False
            
        self.motor_direction = stepper.FORWARD if direction == 'CW' else stepper.BACKWARD
        
        # Reset stop flag if moving away from triggered limit
        if ((direction == 'CCW' and self.triggered_limit == 'CW') or 
            (direction == 'CW' and self.triggered_limit == 'CCW')):
            self.stop_flag = False
            self.triggered_limit = None
            
        return True

    def limit_switch_callback(self, channel, direction):
        """
        Callback function for limit detection.

        :param channel: GPIO channel that triggered the callback
        :param direction: 'CW' or 'CCW' indicating which limit switch was triggered
        """
        self.stop_flag = True
        self.triggered_limit = direction
        logger.info(f"[{self.name}] {direction} limit switch triggered.")

    def confirm_limit_switches(self):
        """
        Confirm both limit switches are working correctly.
        """
        print(f"\n[{self.name}] Testing limit switches...")
        
        # Test CW direction
        print("Testing clockwise movement...")
        self.set_direction('CW')
        self.step(5, delay=0.1)
        
        user_response = input("Did the motor move clockwise? (yes/no): ").strip().lower()
        if user_response != 'yes':
            logger.error(f"[{self.name}] Motor direction incorrect. Check wiring.")
            exit(1)
        
        # Test both limit switches
        print("\nPlease trigger each limit switch to confirm they're working:")
        
        if self.cw_limit_switch_pin:
            print("1. Trigger the CW limit switch...")
            while not self.triggered_limit:
                time.sleep(0.1)
            if self.triggered_limit != 'CW':
                logger.error(f"[{self.name}] Wrong limit switch triggered. Check wiring.")
                exit(1)
            self.triggered_limit = None
            self.stop_flag = False
            
        if self.ccw_limit_switch_pin:
            print("2. Trigger the CCW limit switch...")
            while not self.triggered_limit:
                time.sleep(0.1)
            if self.triggered_limit != 'CCW':
                logger.error(f"[{self.name}] Wrong limit switch triggered. Check wiring.")
                exit(1)
            self.triggered_limit = None
            self.stop_flag = False
        
        print("Limit switch testing complete.")

    def calibrate(self):
        """
        Calibrate the motor by measuring the total travel distance between limit switches.
        """
        if not (self.cw_limit_switch_pin and self.ccw_limit_switch_pin):
            raise ValueError("Both limit switch pins must be set for calibration.")
        
        self.release()
        logger.info(f"[{self.name}] Starting calibration...")
        
        # Move to CCW limit
        self.set_direction('CCW')
        self.stop_flag = False
        self.triggered_limit = None
        step_count = 0
        while not self.stop_flag:
            self.step(1, delay=0.01)
            step_count += 1
            if step_count > 10000:  # Safety limit
                logger.error(f"[{self.name}] Calibration failed: CCW limit not found")
                return
        
        # Move away from CCW limit
        self.set_direction('CW')
        self.step(self.limit_backoff_steps, delay=0.01)
        
        # Move to CW limit while counting steps
        self.stop_flag = False
        self.triggered_limit = None
        step_count = 0
        while not self.stop_flag:
            self.step(1, delay=0.01)
            step_count += 1
            if step_count > 10000:  # Safety limit
                logger.error(f"[{self.name}] Calibration failed: CW limit not found")
                return
        
        # Store total travel distance
        self.total_travel_steps = step_count
        
        # Move to center position
        self.set_direction('CCW')
        self.step(step_count // 2, delay=0.01)
        self.position = 0  # Set center position as zero
        
        logger.info(f"[{self.name}] Calibration complete. Total travel: {self.total_travel_steps} steps")

    def step(self, steps, delay=0.00001):
        """
        Move the motor a specific number of steps.

        :param steps: Number of steps to move.
        :param delay: Delay between steps in seconds.
        """
        actual_steps = 0
        for _ in range(steps):
            if self.stop_flag:
                logger.warning(f"[{self.name}] Movement stopped due to limit detection.")
                break
            self.motor.onestep(direction=self.motor_direction, style=self.step_style)
            if self.motor_direction == stepper.FORWARD:
                self.position += 1
            else:
                self.position -= 1
            actual_steps += 1
            time.sleep(delay)
        
        return actual_steps

    def release(self):
        """
        Release the motor to disable it and allow free movement.
        """
        self.motor.release()
        self.position = 0
        self.stop_flag = False
        self.triggered_limit = None

    def cleanup(self):
        """
        Clean up GPIO settings.
        """
        if self.cw_limit_switch_pin:
            GPIO.cleanup(self.cw_limit_switch_pin)
        if self.ccw_limit_switch_pin:
            GPIO.cleanup(self.ccw_limit_switch_pin)
