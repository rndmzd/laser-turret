import RPi.GPIO as GPIO
import time

# Set up GPIO using BCM numbering
GPIO.setmode(GPIO.BCM)

# Define the GPIO pin connected to the Hall sensor
HALL_SENSOR_PIN = 22  # You can change this if using a different pin

# Set up the GPIO pin as input (the external pull-up resistor is used)
GPIO.setup(HALL_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Hall Sensor Test Program")
print("Press Ctrl+C to exit")

try:
    while True:
        if GPIO.input(HALL_SENSOR_PIN) == GPIO.LOW:
            print("Magnet detected!")
        else:
            print("No magnet.")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("Program terminated by user")
finally:
    GPIO.cleanup()
