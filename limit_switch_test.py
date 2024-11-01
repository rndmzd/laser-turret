import RPi.GPIO as GPIO
import time

# Set up GPIO mode
GPIO.setmode(GPIO.BCM)

# Define GPIO pins for limit switches
limit_switch_pins = [17, 22, 23, 27]

# Set up each limit switch pin as input with pull-up resistor
for pin in limit_switch_pins:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

try:
    print("Monitoring limit switches. Press Ctrl+C to exit.")
    while True:
        for pin in limit_switch_pins:
            if GPIO.input(pin) == GPIO.LOW:  # Limit switch is pressed (assuming normally open switch)
                print(f"Limit switch on GPIO {pin} is triggered.")
        time.sleep(0.1)  # Small delay to reduce CPU usage

except KeyboardInterrupt:
    print("Exiting program")

finally:
    GPIO.cleanup()  # Reset GPIO settings
