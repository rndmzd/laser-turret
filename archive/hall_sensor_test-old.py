import RPi.GPIO as GPIO
import time

# Set up GPIO using BCM numbering
GPIO.setmode(GPIO.BCM)

# Define the GPIO pin connected to the Hall sensor
HALL_SENSOR_X = 17  # You can change this if using
HALL_SENSOR_Y = 22  # You can change this if using a different pin

# Set up the GPIO pin as input (the external pull-up resistor is used)
GPIO.setup(HALL_SENSOR_X, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(HALL_SENSOR_Y, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Hall Sensor Test Program")
print("Press Ctrl+C to exit")

try:
    while True:
        if GPIO.input(HALL_SENSOR_Y) == GPIO.LOW:
            print("Y magnet detected!")
        else:
            print("No Y magnet detected.")
        time.sleep(0.5)
        if GPIO.input(HALL_SENSOR_X) == GPIO.LOW:
            print("X magnet detected!")
        else:
            print("No X magnet detected.")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("Program terminated by user")
finally:
    GPIO.cleanup()
