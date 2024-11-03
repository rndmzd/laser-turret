import RPi.GPIO as GPIO
import time

# Define GPIO pins for Hall sensors
limit_switch_pins = {'X': 17, 'Y': 27}

try:
    # Setup GPIO mode
    GPIO.setmode(GPIO.BCM)

    # Setup Hall sensor pins as input
    GPIO.setup(limit_switch_pins['X'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(limit_switch_pins['Y'], GPIO.IN, pull_up_down=GPIO.PUD_UP)

    print("Monitoring Hall sensors for X and Y axes...")
    print("Manually move the turret to test if the sensors are detecting travel limits.")

    while True:
        # Read Hall sensor states
        x_limit_reached = GPIO.input(limit_switch_pins['X'])
        y_limit_reached = GPIO.input(limit_switch_pins['Y'])

        if not x_limit_reached:
            print("X-axis limit detected!")
        if not y_limit_reached:
            print("Y-axis limit detected!")

        # Small delay to prevent excessive CPU usage
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nTest interrupted by user.")

finally:
    # Clean up GPIO settings
    GPIO.cleanup()
    print("GPIO cleanup complete.")