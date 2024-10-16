import RPi.GPIO as GPIO
import time

# Define GPIO pin numbers for the sensors
SENSOR_1_PIN = 17  # GPIO pin for Sensor 1
SENSOR_2_PIN = 27  # GPIO pin for Sensor 2

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(SENSOR_1_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(SENSOR_2_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

try:
    while True:
        sensor1_state = GPIO.input(SENSOR_1_PIN)
        sensor2_state = GPIO.input(SENSOR_2_PIN)
        print(f"Sensor 1: {'HIGH' if sensor1_state else 'LOW'}")
        print(f"Sensor 2: {'HIGH' if sensor2_state else 'LOW'}")
        time.sleep(1)

except KeyboardInterrupt:
    print("Exiting program")

finally:
    GPIO.cleanup()
