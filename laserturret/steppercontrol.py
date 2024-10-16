import RPi.GPIO as GPIO
import time

class StepperMotor:
    def __init__(self, ms_pins, dir_pin, step_pin, limit_pin=None, limit_direction=None, steps_per_rev=200, name="Motor"):
        """
        Initialize the stepper motor.

        :param ms_pins: A dictionary with keys 'MS1', 'MS2', 'MS3' and their corresponding GPIO pin numbers.
        :param dir_pin: The GPIO pin number connected to the DIR pin of the A4988.
        :param step_pin: The GPIO pin number connected to the STEP pin of the A4988.
        :param limit_pin: GPIO pin for the Hall sensor to detect travel limit.
        :param limit_direction: 'CW' or 'CCW' indicating the direction towards the limit sensor.
        :param steps_per_rev: Number of steps per revolution for the stepper motor.
        :param name: Name of the motor (for identification in prints).
        """
        self.ms_pins = ms_pins
        self.dir_pin = dir_pin
        self.step_pin = step_pin
        self.limit_pin = limit_pin
        self.limit_direction = limit_direction
        self.steps_per_rev = steps_per_rev
        self.name = name
        self.stop_flag = False

        # Setup GPIO mode
        GPIO.setmode(GPIO.BCM)

        # Setup output pins
        GPIO.setup(self.dir_pin, GPIO.OUT)
        GPIO.setup(self.step_pin, GPIO.OUT)

        for pin in self.ms_pins.values():
            GPIO.setup(pin, GPIO.OUT)

        # Setup limit sensor pin if provided
        if self.limit_pin is not None:
            GPIO.setup(self.limit_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            GPIO.add_event_detect(self.limit_pin, GPIO.RISING, callback=self.limit_callback, bouncetime=200)

        # Set default direction and microstepping mode
        GPIO.output(self.dir_pin, GPIO.LOW)
        self.set_microstepping('FULL')

    def set_microstepping(self, mode):
        """
        Set the microstepping mode.

        :param mode: One of 'FULL', 'HALF', 'QUARTER', 'EIGHTH', 'SIXTEENTH'.
        """
        modes = {
            'FULL':      (GPIO.LOW, GPIO.LOW, GPIO.LOW),
            'HALF':      (GPIO.HIGH, GPIO.LOW, GPIO.LOW),
            'QUARTER':   (GPIO.LOW, GPIO.HIGH, GPIO.LOW),
            'EIGHTH':    (GPIO.HIGH, GPIO.HIGH, GPIO.LOW),
            'SIXTEENTH': (GPIO.HIGH, GPIO.HIGH, GPIO.HIGH)
        }
        if mode in modes:
            ms1_state, ms2_state, ms3_state = modes[mode]
            GPIO.output(self.ms_pins['MS1'], ms1_state)
            GPIO.output(self.ms_pins['MS2'], ms2_state)
            GPIO.output(self.ms_pins['MS3'], ms3_state)
        else:
            raise ValueError("Invalid microstepping mode. Choose from 'FULL', 'HALF', 'QUARTER', 'EIGHTH', 'SIXTEENTH'.")

    def set_direction(self, direction):
        """
        Set the rotation direction.

        :param direction: 'CW' for clockwise, 'CCW' for counter-clockwise.
        """
        if direction == 'CW':
            GPIO.output(self.dir_pin, GPIO.HIGH)
            if self.limit_direction == 'CCW':
                self.stop_flag = False  # Reset stop flag if moving away from limit
        elif direction == 'CCW':
            GPIO.output(self.dir_pin, GPIO.LOW)
            if self.limit_direction == 'CW':
                self.stop_flag = False  # Reset stop flag if moving away from limit
        else:
            raise ValueError("Invalid direction. Use 'CW' or 'CCW'.")

    def step(self, steps, delay=0.1):
        """
        Move the motor a specific number of steps.

        :param steps: Number of steps to move.
        :param delay: Delay between steps in seconds.
        """
        for _ in range(steps):
            if self.stop_flag:
                print(f"{self.name}: Movement stopped due to limit detection.")
                break
            GPIO.output(self.step_pin, GPIO.HIGH)
            time.sleep(delay)
            GPIO.output(self.step_pin, GPIO.LOW)
            time.sleep(delay)

    def limit_callback(self, channel):
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
