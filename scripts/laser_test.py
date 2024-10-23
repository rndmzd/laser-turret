import RPi.GPIO as GPIO
import time

# Use Broadcom pin numbering
GPIO.setmode(GPIO.BCM)

# Set up GPIO 18 as an output pin
GPIO.setup(18, GPIO.OUT, initial=GPIO.LOW)

try:
    while True:
        # Wait for user input
        input("Press Enter to activate GPIO 18 (laser) for 1 second.\
              Make sure to wear safety goggles and point turret in a safe direction.")
        
        # Set GPIO 18 HIGH
        GPIO.output(18, GPIO.HIGH)
        print("GPIO 18 is HIGH")
        
        # Wait for 1 second
        time.sleep(1)
        
        # Set GPIO 18 LOW
        GPIO.output(18, GPIO.LOW)
        print("GPIO 18 is LOW")

except KeyboardInterrupt:
    # Graceful exit on Ctrl+C
    print("\nExiting...")

finally:
    # Clean up GPIO to reset all channels
    GPIO.cleanup()
