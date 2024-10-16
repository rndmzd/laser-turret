import RPi.GPIO as GPIO
import time

class StepperMotor:
    def __init__(self, ms_pins, dir_pin, step_pin, limit_pin=None, limit_direction=None, steps_per_rev=200, name="Motor"):
        """
        Initialize the stepper motor with limit detection.

        :param ms_pins: A dictionary with keys 'MS1', 'MS2', 'MS3' and their corresponding GPIO pin numbers.
        :param dir_pin: The GPIO pin number connected to the DIR pin of the A4988.
        :param step_pin: The GPIO pin number connected to the STEP pin of the A4988.
        :param limit_pin: The GPIO pin number connected to the Hall effect sensor (limit switch).
        :param steps_per_rev: Number of steps per revolution (depends on the motor and microstepping mode).
        :param name: Name of the motor (for identification in prints).
        """
        self.ms_pins = ms_pins
        self.dir_pin = dir_pin
        self.step_pin = step_pin
        self.limit_pin = limit_pin
        self.steps_per_rev = steps_per_rev
        self.name = name

        # Setup output pins
        GPIO.setup(self.dir_pin, GPIO.OUT)
        GPIO.setup(self.step_pin, GPIO.OUT)

        for pin in self.ms_pins.values():
            GPIO.setup(pin, GPIO.OUT)

        # Setup input pin for limit switch if provided
        if self.limit_pin is not None:
            GPIO.setup(self.limit_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Enable internal pull-up resistor

        # Set default direction and microstepping mode
        GPIO.output(self.dir_pin, GPIO.LOW)
        self.set_microstepping('FULL')

    def is_limit_reached(self):
        """
        Check if the limit switch (Hall effect sensor) is activated.
        """
        if self.limit_pin is not None:
            return GPIO.input(self.limit_pin) == GPIO.LOW  # Assuming active-low sensor
        return False

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
            # Adjust steps per revolution according to microstepping mode
            full_steps_per_rev = 200  # Common for 1.8-degree stepper motors
            multiplier = {'FULL': 1, 'HALF': 2, 'QUARTER': 4, 'EIGHTH': 8, 'SIXTEENTH': 16}
            self.steps_per_rev = full_steps_per_rev * multiplier[mode]
        else:
            raise ValueError("Invalid microstepping mode. Choose from 'FULL', 'HALF', 'QUARTER', 'EIGHTH', 'SIXTEENTH'.")

    def set_direction(self, direction):
        """
        Set the rotation direction.

        :param direction: 'CW' for clockwise, 'CCW' for counter-clockwise.
        """
        if direction == 'CW':
            GPIO.output(self.dir_pin, GPIO.HIGH)
        elif direction == 'CCW':
            GPIO.output(self.dir_pin, GPIO.LOW)
        else:
            raise ValueError("Invalid direction. Use 'CW' or 'CCW'.")

    def step(self, steps, delay=0.001, check_limit=False):
        """
        Move the motor a specific number of steps, optionally checking the limit switch.

        :param steps: Number of steps to move.
        :param delay: Delay between steps in seconds.
        :param check_limit: If True, monitor the limit switch during movement.
        """
        for _ in range(steps):
            # Check limit switch before each step
            if check_limit and self.is_limit_reached():
                print(f"{self.name}: Limit reached. Stopping motor.")
                break

            GPIO.output(self.step_pin, GPIO.HIGH)
            time.sleep(delay)
            GPIO.output(self.step_pin, GPIO.LOW)
            time.sleep(delay)

    def rotate(self, revolutions, delay=0.001, check_limit=False):
        steps = int(self.steps_per_rev * revolutions)
        self.step(steps, delay, check_limit)

    def move_to_limit(self, delay=0.001):
        """
        Move the motor until the limit switch is activated.
        """
        while not self.is_limit_reached():
            GPIO.output(self.step_pin, GPIO.HIGH)
            time.sleep(delay)
            GPIO.output(self.step_pin, GPIO.LOW)
            time.sleep(delay)
        print(f"{self.name}: Limit switch activated.")

    def cleanup(self):
        GPIO.cleanup()
