import RPi.GPIO as GPIO
import time

# Define GPIO pin numbers for the sensors
# SENSOR_1_PIN = 17  # GPIO pin for Sensor 1
SENSOR_2_PIN = 27  # GPIO pin for Sensor 2

# Callback functions to handle events
"""def sensor1_callback(channel):
    if GPIO.input(SENSOR_1_PIN):
        print("Sensor 1 detected no magnetic field (HIGH)")
    else:
        print("Sensor 1 detected a magnetic field (LOW)")"""

def sensor2_callback(channel):
    if GPIO.input(SENSOR_2_PIN):
        print("Sensor 2 detected no magnetic field (HIGH)")
    else:
        print("Sensor 2 detected a magnetic field (LOW)")

# Setup GPIO
GPIO.setmode(GPIO.BCM)  # Use Broadcom pin numbering
# GPIO.setup(SENSOR_1_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Enable internal pull-up for sensor 1
GPIO.setup(SENSOR_2_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Enable internal pull-up for sensor 2

# Event detection on both rising and falling edges
# GPIO.add_event_detect(SENSOR_1_PIN, GPIO.BOTH, callback=sensor1_callback)
GPIO.add_event_detect(SENSOR_2_PIN, GPIO.BOTH, callback=sensor2_callback)

try:
    print("Monitoring Hall sensors. Press Ctrl+C to exit.")
    while True:
        time.sleep(1)  # Keep the script running

except KeyboardInterrupt:
    print("Exiting program")

finally:
    GPIO.cleanup()  # Clean up all GPIO when the program exits
