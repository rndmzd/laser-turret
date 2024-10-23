from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import logging
import time
import RPi.GPIO as GPIO

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class StepperMotor:
    def __init__(
            self,
            motor_channel,
            limit_switch_pin=None,
            limit_switch_direction=None,
            steps_per_rev=200,
            microsteps=8,
            skip_direction_check=False,
            perform_calibration=True,
            limit_backoff_steps=5,
            name="Motor"):
        """
        Initialize the stepper motor using Adafruit MotorKit.

        :param motor_channel: The motor channel (1 or 2) on the Adafruit Motor HAT.
        :param limit_switch_pin: GPIO pin for the limit switch to detect travel limit.
        :param limit_switch_direction: 'CW' or 'CCW' indicating the direction towards the limit switch.
        :param steps_per_rev: Number of steps per revolution for the stepper motor.
        :param microsteps: Number of microsteps to set for the motor.
        :param name: Name of the motor (for identification in prints).
        """
        self.motor_channel = motor_channel
        self.limit_switch_pin = limit_switch_pin
        self.limit_switch_direction = limit_switch_direction
        self.steps_per_rev = steps_per_rev
        self.name = name
        self.stop_flag = False
        self.limit_backoff_steps = limit_backoff_steps

        self.position = 0

        # Initialize MotorKit instance with microsteps
        self.kit = MotorKit(steppers_microsteps=microsteps)
        if motor_channel not in [1, 2]:
            raise ValueError("Invalid motor channel. Use 1 or 2.")
        self.motor = self.kit.stepper1 if motor_channel == 1 else self.kit.stepper2

        # Default microstepping settings
        self.step_style = stepper.SINGLE
        
        self.motor_direction = None
        self.set_direction(limit_switch_direction if limit_switch_direction is not None else 'CW')

        # Setup limit switch pin if provided
        if self.limit_switch_pin is not None:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(self.limit_switch_pin, GPIO.FALLING, callback=self.limit_switch_callback, bouncetime=200)
            if GPIO.input(self.limit_switch_pin) == 0:
                logger.warn(f"{self.name}: Limit switch already triggered.")
                self.position = 0
        
        # Initialize position
        if not skip_direction_check:
            self.confirm_limit_switch()
        
        if perform_calibration:
            self.calibrate()

    def set_direction(self, direction):
        """
        Set the rotation direction.

        :param direction: 'CW' for clockwise, 'CCW' for counter-clockwise.
        """
        if direction == 'CW':
            self.motor_direction = stepper.FORWARD
            if self.limit_switch_direction == 'CCW' and self.stop_flag == True:
                self.stop_flag = False  # Reset stop flag if moving away from limit
        elif direction == 'CCW':
            self.motor_direction = stepper.BACKWARD
            if self.limit_switch_direction == 'CW' and self.stop_flag == True:
                self.stop_flag = False  # Reset stop flag if moving away from limit
        else:
            raise ValueError("Invalid direction. Use 'CW' or 'CCW'.")

    def set_microstepping(self, style):
        """
        Set the microstepping mode.

        :param style: One of 'SINGLE', 'DOUBLE', 'INTERLEAVE', 'MICROSTEP'.
        """
        styles = {
            'SINGLE': stepper.SINGLE,
            'DOUBLE': stepper.DOUBLE,
            'INTERLEAVE': stepper.INTERLEAVE,
            'MICROSTEP': stepper.MICROSTEP
        }
        if style in styles:
            self.step_style = styles[style]
        else:
            raise ValueError("Invalid microstepping style. Choose from 'SINGLE', 'DOUBLE', 'INTERLEAVE', 'MICROSTEP'.")

    def step(self, steps, delay=0.00001):
        """
        Move the motor a specific number of steps.

        :param steps: Number of steps to move.
        :param delay: Delay between steps in seconds.
        """

        for _ in range(steps):
            if self.stop_flag:
                logger.warning(f"{self.name}: Movement stopped due to limit detection.")
                break
            self.position = self.motor.onestep(direction=self.motor_direction, style=self.step_style)
            logger.debug(f"[{self.name}] self.position: {self.position}")
            time.sleep(delay)
        
        return self.position

    def release(self):
        """
        Release the motor to disable it and allow free movement.
        """
        self.motor.release()
        self.position = 0
        self.stop_flag = False

    def limit_switch_callback(self, channel):
        """
        Callback function for limit detection.
        """
        self.stop_flag = True
        print(f"{self.name}: Limit switch triggered.")
    
    def confirm_limit_switch(self):
        """
        Confirm the limit switch direction after moving a few steps.
        """
        while True:
            self.step(5, delay=0.1)
            user_response = input(f"Was this the direction towards the limit switch? (yes/no/move): ").strip().lower()
            if user_response == 'yes':
                limit_direction_confirm = False
                if self.limit_switch_direction == 'CW' and self.motor_direction == stepper.FORWARD:
                    limit_direction_confirm = True
                elif self.limit_switch_direction == 'CCW' and self.motor_direction == stepper.BACKWARD:
                    limit_direction_confirm = True
                
                if limit_direction_confirm:
                    logger.info(f"{self.name}: Direction confirmed. Proceeding.")
                    break
                else:
                    logger.error(f"{self.name}: Limit switch direction in init arguments must be changed.")
                    exit(1)
            
            elif user_response == 'move':
                continue

            else:
                logger.error(f"{self.name}: Limit switch direction in init arguments must be changed.")
                exit(1)
        
        print("Manually activate the limit switch to confirm.")
        user_response = input("Was the correct limit switch activated? (yes/no): ").strip().lower()
        if user_response != 'yes':
            logger.error(f"{self.name}: Fix pin assignments then restart program.")
            exit(1)
    
    def calibrate(self):
        """
        Calibrate the motor by moving towards the limit switch and counting steps.
        """
        if self.limit_switch_pin is None or self.limit_switch_direction is None:
            raise ValueError("Limit switch pin and direction must be set for calibration.")
        
        logger.info(f"{self.name}: Calibrating motor.")
        self.set_direction(self.limit_switch_direction)
        self.stop_flag = False
        self.step(10000, delay=0.05)  # Move until the limit switch is triggered
        self.set_direction('CW' if self.limit_switch_direction == 'CCW' else 'CCW')
        self.step(self.limit_backoff_steps, delay=0.05)  # Move away from the limit switch
        self.position = 0

        logger.info("Calibration complete.")

    def cleanup(self):
        """
        Clean up GPIO settings.
        """
        GPIO.cleanup()