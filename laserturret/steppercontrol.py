from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import time
import RPi.GPIO as GPIO

class StepperMotor:
    def __init__(self, motor_channel, limit_switch_pin=None, limit_switch_direction=None, steps_per_rev=200, microsteps=8, name="Motor"):
        """
        Initialize the stepper motor using Adafruit MotorKit.

        :param motor_channel: The motor channel (1, 2, 3, or 4) on the Adafruit Motor HAT.
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

        # Initialize MotorKit instance with microsteps
        self.kit = MotorKit(steppers_microsteps=microsteps)
        self.motor = self.kit.stepper1 if motor_channel == 1 else self.kit.stepper2

        # Default microstepping settings
        self.step_style = stepper.SINGLE
        
        self.motor_direction = None
        self.set_direction('CW')

        # Setup limit switch pin if provided
        if self.limit_switch_pin is not None:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.limit_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            GPIO.add_event_detect(self.limit_switch_pin, GPIO.RISING, callback=self.limit_switch_callback, bouncetime=200)

    def set_direction(self, direction):
        """
        Set the rotation direction.

        :param direction: 'CW' for clockwise, 'CCW' for counter-clockwise.
        """
        if direction == 'CW':
            self.motor_direction = stepper.FORWARD
            if self.limit_switch_direction == 'CCW':
                self.stop_flag = False  # Reset stop flag if moving away from limit
        elif direction == 'CCW':
            self.motor_direction = stepper.BACKWARD
            if self.limit_switch_direction == 'CW':
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
                print(f"{self.name}: Movement stopped due to limit detection.")
                break
            self.motor.onestep(direction=self.motor_direction, style=self.step_style)
            time.sleep(delay)

    def release(self):
        """
        Release the motor to disable it and allow free movement.
        """
        self.motor.release()

    def limit_switch_callback(self, channel):
        """
        Callback function for limit detection.
        """
        print(f"{self.name}: Travel limit reached.")
        self.stop_flag = True

    def cleanup(self):
        """
        Clean up GPIO settings.
        """
        GPIO.cleanup()
