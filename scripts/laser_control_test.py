import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from laserturret.lasercontrol import LaserControl

# Basic usage
laser = LaserControl(gpio_pin=18)  # Initialize with default 1kHz PWM
laser.on()  # Turn on at 100% power
laser.set_power(50)  # Set to 50% power
laser.off()  # Turn off
laser.cleanup()  # Clean up GPIO

# Using power level during initialization
laser = LaserControl(gpio_pin=18, initial_power=50)  # Start at 50% power
laser.on()  # Turns on at 50%

# Using the pulse function
laser.pulse(duration=0.5, power_level=75)  # 0.5 second pulse at 75% power

# Using as context manager
with LaserControl(gpio_pin=18) as laser:
    laser.on(power_level=50)
    # Do something
    laser.off()
# GPIO automatically cleaned up after context