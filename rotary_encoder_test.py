import RPi.GPIO as GPIO
import time

# Use BCM GPIO references
GPIO.setmode(GPIO.BCM)

# Define GPIO signals to use
CLK = 5    # Rotary encoder CLK pin
DT = 6     # Rotary encoder DT pin
SW = 13    # Rotary encoder switch pin (optional)

# Set up the GPIO pins
GPIO.setup(CLK, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(DT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(SW, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Initialize counter
counter = 0
clkLastState = GPIO.input(CLK)

print("Rotary Encoder Test")
print("Press Ctrl+C to exit")

try:
    while True:
        clkState = GPIO.input(CLK)
        dtState = GPIO.input(DT)

        if clkState != clkLastState:
            if dtState != clkState:
                counter += 1
                direction = "Clockwise"
            else:
                counter -= 1
                direction = "Counterclockwise"

            print(f"Rotated {direction} | Counter: {counter}")
            clkLastState = clkState

        # Check the switch (if connected)
        if GPIO.input(SW) == GPIO.LOW:
            print("Button Pressed")
            time.sleep(0.3)  # Debounce delay

        time.sleep(0.01)  # Loop delay

except KeyboardInterrupt:
    print("Test interrupted by user")
finally:
    GPIO.cleanup()
