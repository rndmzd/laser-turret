import logging
from time import sleep
from typing import Optional
from .hardware_interface import GPIOInterface, get_gpio_backend, PinMode

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class LaserControl:
    def __init__(
        self, 
        gpio_pin: int, 
        pwm_frequency: float = 1000, 
        initial_power: float = 0, 
        name: str = "Laser",
        gpio_backend: Optional[GPIOInterface] = None
    ):
        """
        Initialize laser control with optional PWM support.

        :param gpio_pin: GPIO pin number (BCM) connected to the laser MOSFET
        :param pwm_frequency: PWM frequency in Hz (default 1000Hz)
        :param initial_power: Initial power level 0-100 (default 0)
        :param name: Name identifier for logging
        :param gpio_backend: Optional GPIO backend (defaults to auto-detect)
        """
        self.gpio_pin = gpio_pin
        self.name = name
        self.pwm_frequency = pwm_frequency
        self._power_level = 0
        self.is_on = False

        # Initialize GPIO backend
        self.gpio = gpio_backend if gpio_backend else get_gpio_backend()
        self.gpio.setup(self.gpio_pin, PinMode.OUTPUT)
        
        # Initialize PWM
        self.pwm = self.gpio.pwm(self.gpio_pin, pwm_frequency)
        self.pwm.start(0)  # Start with 0% duty cycle
        
        # Set initial power level
        self.set_power(initial_power)
        
        logger.info(f"[{self.name}] Initialized on GPIO {gpio_pin} with {pwm_frequency}Hz PWM")

    @property
    def power_level(self):
        """Get current power level (0-100)."""
        return self._power_level

    def set_power(self, level):
        """
        Set laser power level (0-100).
        
        :param level: Power level as percentage (0-100)
        :returns: True if successful, False if invalid level
        """
        if not isinstance(level, (int, float)):
            logger.error(f"[{self.name}] Power level must be a number")
            return False
            
        if not 0 <= level <= 100:
            logger.error(f"[{self.name}] Power level must be between 0 and 100")
            return False

        self._power_level = level
        self.pwm.change_duty_cycle(level)
        logger.debug(f"[{self.name}] Power level set to {level}%")
        return True

    def on(self, power_level=None):
        """
        Turn laser on. Optionally set power level.
        
        :param power_level: Optional power level (0-100)
        """
        if power_level is not None:
            self.set_power(power_level)
        elif self._power_level == 0:
            self.set_power(100)  # Default to full power if no level set
            
        self.is_on = True
        logger.info(f"[{self.name}] Laser ON at {self._power_level}% power")

    def off(self):
        """Turn laser off while preserving last power level setting."""
        self.pwm.change_duty_cycle(0)
        self.is_on = False
        logger.info(f"[{self.name}] Laser OFF")

    def pulse(self, duration, power_level=None):
        """
        Pulse the laser for a specified duration.
        
        :param duration: Pulse duration in seconds
        :param power_level: Optional power level for pulse (0-100)
        """
        original_power = self._power_level
        
        if power_level is not None:
            self.set_power(power_level)
            
        self.on()
        sleep(duration)
        self.off()
        
        # Restore original power level
        if power_level is not None:
            self.set_power(original_power)
            
        logger.debug(f"[{self.name}] Completed {duration}s pulse at {self._power_level}% power")

    def cleanup(self):
        """Clean up GPIO resources."""
        self.off()
        self.pwm.stop()
        self.gpio.cleanup([self.gpio_pin])
        logger.info(f"[{self.name}] Cleaned up GPIO resources")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()