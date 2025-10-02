import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
from laserturret.hardware_interface import get_gpio_backend, PinMode

# Get GPIO backend (auto-detects lgpio/RPi.GPIO)
gpio = get_gpio_backend()

# Set up GPIO 18 as an output pin
gpio.setup(18, PinMode.OUTPUT)
gpio.output(18, 0)

try:
    while True:
        # Wait for user input
        input("Press Enter to activate GPIO 18 (laser) for 1 second.\n"
              "Make sure to wear safety goggles and point turret in a safe direction.")
        
        # Set GPIO 18 HIGH
        gpio.output(18, 1)
        print("GPIO 18 is HIGH")
        
        # Wait for 1 second
        time.sleep(1)
        
        # Set GPIO 18 LOW
        gpio.output(18, 0)
        print("GPIO 18 is LOW")

except KeyboardInterrupt:
    # Graceful exit on Ctrl+C
    print("\nExiting...")

finally:
    # Clean up GPIO to reset all channels
    gpio.cleanup([18])
