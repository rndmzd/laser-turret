import RPi.GPIO as GPIO
import time

# Define GPIO pins for Hall sensors
hall_sensor_pins = {'X': 18, 'Y': 25}

try:
    # Setup GPIO mode
    GPIO.setmode(GPIO.BCM)

    # Setup Hall sensor pins as input
    GPIO.setup(hall_sensor_pins['X'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(hall_sensor_pins['Y'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    print("Monitoring Hall sensors for X and Y axes...")
    print("Manually move the turret to test if the sensors are detecting travel limits.")

    while True:
        # Read Hall sensor states
        x_limit_reached = GPIO.input(hall_sensor_pins['X'])
        y_limit_reached = GPIO.input(hall_sensor_pins['Y'])

        if x_limit_reached:
            print("X-axis limit detected!")
        if y_limit_reached:
            print("Y-axis limit detected!")

        # Small delay to prevent excessive CPU usage
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nTest interrupted by user.")

finally:
    # Clean up GPIO settings
    GPIO.cleanup()
    print("GPIO cleanup complete.")