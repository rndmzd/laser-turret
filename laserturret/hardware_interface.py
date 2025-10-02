"""
Hardware abstraction layer for laser turret components.

Provides abstract interfaces and implementations for GPIO, camera, and other hardware,
enabling testing without physical hardware.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Any, Tuple
from enum import IntEnum
import logging

logger = logging.getLogger(__name__)


class PinMode(IntEnum):
    """GPIO pin modes"""
    INPUT = 0
    OUTPUT = 1


class PullMode(IntEnum):
    """GPIO pull-up/down modes"""
    OFF = 0
    DOWN = 1
    UP = 2


class Edge(IntEnum):
    """GPIO edge detection"""
    RISING = 1
    FALLING = 2
    BOTH = 3


class GPIOInterface(ABC):
    """Abstract interface for GPIO operations"""
    
    @abstractmethod
    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        """Configure a GPIO pin"""
        pass
    
    @abstractmethod
    def output(self, pin: int, value: int) -> None:
        """Set output value on a pin"""
        pass
    
    @abstractmethod
    def input(self, pin: int) -> int:
        """Read input value from a pin"""
        pass
    
    @abstractmethod
    def add_event_detect(
        self, 
        pin: int, 
        edge: Edge, 
        callback: Optional[Callable] = None,
        bouncetime: int = 0
    ) -> None:
        """Add edge detection with optional callback"""
        pass
    
    @abstractmethod
    def remove_event_detect(self, pin: int) -> None:
        """Remove edge detection from a pin"""
        pass
    
    @abstractmethod
    def cleanup(self, pins: Optional[list] = None) -> None:
        """Clean up GPIO resources"""
        pass
    
    @abstractmethod
    def pwm(self, pin: int, frequency: float) -> 'PWMInterface':
        """Create PWM instance for a pin"""
        pass


class PWMInterface(ABC):
    """Abstract interface for PWM operations"""
    
    @abstractmethod
    def start(self, duty_cycle: float) -> None:
        """Start PWM with given duty cycle (0-100)"""
        pass
    
    @abstractmethod
    def change_duty_cycle(self, duty_cycle: float) -> None:
        """Change PWM duty cycle"""
        pass
    
    @abstractmethod
    def change_frequency(self, frequency: float) -> None:
        """Change PWM frequency"""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop PWM"""
        pass


class CameraInterface(ABC):
    """Abstract interface for camera operations"""
    
    @abstractmethod
    def configure(self, config: dict) -> None:
        """Configure camera with settings"""
        pass
    
    @abstractmethod
    def start(self) -> None:
        """Start camera"""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop camera"""
        pass
    
    @abstractmethod
    def capture_array(self) -> Any:
        """Capture frame as numpy array"""
        pass
    
    @abstractmethod
    def capture_metadata(self) -> dict:
        """Capture frame metadata"""
        pass
    
    @property
    @abstractmethod
    def camera_controls(self) -> dict:
        """Get available camera controls"""
        pass


# Real hardware implementations

class LgpioGPIO(GPIOInterface):
    """Raspberry Pi 5 GPIO implementation using lgpio"""
    
    def __init__(self):
        try:
            import lgpio
            self.lgpio = lgpio
            # Open GPIO chip (gpiochip4 on Pi 5)
            self.chip = self._open_chip()
            self._pin_configs = {}  # Track pin configurations
            logger.info(f"Initialized lgpio with chip handle {self.chip}")
        except ImportError:
            raise ImportError("lgpio not available. Install with: pip install lgpio")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize lgpio: {e}")
    
    def _open_chip(self):
        """Open the GPIO chip - tries chip 4 (Pi 5) then chip 0 (Pi 4-)"""
        for chip_num in [4, 0]:
            try:
                chip = self.lgpio.gpiochip_open(chip_num)
                logger.info(f"Opened gpiochip{chip_num}")
                return chip
            except Exception as e:
                logger.debug(f"Could not open gpiochip{chip_num}: {e}")
                continue
        raise RuntimeError("Could not open any GPIO chip (tried 4, 0)")
    
    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        # Check if pin is already configured with the same settings
        if pin in self._pin_configs:
            existing = self._pin_configs[pin]
            if existing['mode'] == mode and existing['pull'] == pull_up_down:
                # Pin already configured correctly, skip
                logger.debug(f"Pin {pin} already configured with mode={mode}, pull={pull_up_down}")
                return
            else:
                # Pin configured differently, need to reconfigure
                logger.warning(f"Pin {pin} already configured, freeing before reconfiguration")
                try:
                    self.lgpio.gpio_free(self.chip, pin)
                except:
                    pass
        
        # Configure pin direction and pull-up/down
        flags = 0
        
        if mode == PinMode.INPUT:
            if pull_up_down == PullMode.UP:
                flags = self.lgpio.SET_PULL_UP
            elif pull_up_down == PullMode.DOWN:
                flags = self.lgpio.SET_PULL_DOWN
            else:
                flags = self.lgpio.SET_PULL_NONE
            
            self.lgpio.gpio_claim_input(self.chip, pin, flags)
        else:  # OUTPUT
            self.lgpio.gpio_claim_output(self.chip, pin, 0)  # Start low
        
        self._pin_configs[pin] = {'mode': mode, 'pull': pull_up_down}
    
    def output(self, pin: int, value: int) -> None:
        self.lgpio.gpio_write(self.chip, pin, 1 if value else 0)
    
    def input(self, pin: int) -> int:
        return self.lgpio.gpio_read(self.chip, pin)
    
    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable] = None,
        bouncetime: int = 0
    ) -> None:
        # lgpio uses alerts for edge detection
        if edge == Edge.RISING:
            lgpio_edge = self.lgpio.RISING_EDGE
        elif edge == Edge.FALLING:
            lgpio_edge = self.lgpio.FALLING_EDGE
        else:
            lgpio_edge = self.lgpio.BOTH_EDGES
        
        self.lgpio.gpio_claim_alert(self.chip, pin, lgpio_edge)
        
        if callback:
            # Store callback for this pin
            if not hasattr(self, '_callbacks'):
                self._callbacks = {}
            self._callbacks[pin] = callback
            
            # Note: lgpio requires polling or using gpio_get_chip_info
            # For production use, consider using a background thread to poll alerts
            logger.warning("lgpio event callbacks require manual polling - consider using gpiozero for full event support")
    
    def remove_event_detect(self, pin: int) -> None:
        # Free the pin to remove alert
        self.lgpio.gpio_free(self.chip, pin)
        if hasattr(self, '_callbacks') and pin in self._callbacks:
            del self._callbacks[pin]
    
    def cleanup(self, pins: Optional[list] = None) -> None:
        if pins:
            # Clean up specific pins only (for individual motor cleanup)
            for pin in pins:
                try:
                    self.lgpio.gpio_free(self.chip, pin)
                    # Remove from tracked configs
                    if pin in self._pin_configs:
                        del self._pin_configs[pin]
                except:
                    pass
            # Do NOT close chip when cleaning specific pins (shared singleton)
        else:
            # Full cleanup - free all configured pins and close chip
            for pin in list(self._pin_configs.keys()):
                try:
                    self.lgpio.gpio_free(self.chip, pin)
                except:
                    pass
            self._pin_configs.clear()
            
            # Close chip handle
            try:
                self.lgpio.gpiochip_close(self.chip)
            except:
                pass
    
    def pwm(self, pin: int, frequency: float) -> PWMInterface:
        return LgpioPWM(self.lgpio, self.chip, pin, frequency)


class LgpioPWM(PWMInterface):
    """Raspberry Pi 5 PWM implementation using lgpio"""
    
    def __init__(self, lgpio_module, chip: int, pin: int, frequency: float):
        self.lgpio = lgpio_module
        self.chip = chip
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = 0
        self.running = False
        
        # Claim the pin for PWM
        try:
            self.lgpio.gpio_claim_output(self.chip, pin, 0)
        except:
            pass  # May already be claimed
    
    def start(self, duty_cycle: float) -> None:
        self.duty_cycle = duty_cycle
        self.running = True
        
        # lgpio PWM: frequency in Hz, duty cycle in range 0-100
        # Convert duty cycle percentage to lgpio range (0-100)
        self.lgpio.tx_pwm(self.chip, self.pin, self.frequency, self.duty_cycle)
        logger.debug(f"LgpioPWM: Started on pin {self.pin} with duty cycle {duty_cycle}%")
    
    def change_duty_cycle(self, duty_cycle: float) -> None:
        self.duty_cycle = duty_cycle
        if self.running:
            self.lgpio.tx_pwm(self.chip, self.pin, self.frequency, self.duty_cycle)
        logger.debug(f"LgpioPWM: Changed duty cycle to {duty_cycle}%")
    
    def change_frequency(self, frequency: float) -> None:
        self.frequency = frequency
        if self.running:
            self.lgpio.tx_pwm(self.chip, self.pin, self.frequency, self.duty_cycle)
        logger.debug(f"LgpioPWM: Changed frequency to {frequency}Hz")
    
    def stop(self) -> None:
        self.running = False
        # Stop PWM by setting to 0
        self.lgpio.tx_pwm(self.chip, self.pin, self.frequency, 0)
        logger.debug(f"LgpioPWM: Stopped on pin {self.pin}")


class RPiGPIO(GPIOInterface):
    """Raspberry Pi GPIO implementation using RPi.GPIO (for Pi 4 and earlier)"""
    
    def __init__(self):
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(GPIO.BCM)
            self.GPIO.setwarnings(False)
            logger.info("Initialized RPi.GPIO (legacy)")
        except ImportError:
            raise ImportError("RPi.GPIO not available. Install with: pip install RPi.GPIO")
    
    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        gpio_mode = self.GPIO.IN if mode == PinMode.INPUT else self.GPIO.OUT
        
        if pull_up_down == PullMode.UP:
            pud = self.GPIO.PUD_UP
        elif pull_up_down == PullMode.DOWN:
            pud = self.GPIO.PUD_DOWN
        else:
            pud = self.GPIO.PUD_OFF
        
        self.GPIO.setup(pin, gpio_mode, pull_up_down=pud)
    
    def output(self, pin: int, value: int) -> None:
        self.GPIO.output(pin, self.GPIO.HIGH if value else self.GPIO.LOW)
    
    def input(self, pin: int) -> int:
        return 1 if self.GPIO.input(pin) == self.GPIO.HIGH else 0
    
    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable] = None,
        bouncetime: int = 0
    ) -> None:
        if edge == Edge.RISING:
            gpio_edge = self.GPIO.RISING
        elif edge == Edge.FALLING:
            gpio_edge = self.GPIO.FALLING
        else:
            gpio_edge = self.GPIO.BOTH
        
        self.GPIO.add_event_detect(pin, gpio_edge, callback=callback, bouncetime=bouncetime)
    
    def remove_event_detect(self, pin: int) -> None:
        self.GPIO.remove_event_detect(pin)
    
    def cleanup(self, pins: Optional[list] = None) -> None:
        if pins:
            self.GPIO.cleanup(pins)
        else:
            self.GPIO.cleanup()
    
    def pwm(self, pin: int, frequency: float) -> PWMInterface:
        return RPiPWM(self.GPIO, pin, frequency)


class RPiPWM(PWMInterface):
    """Raspberry Pi PWM implementation"""
    
    def __init__(self, gpio_module, pin: int, frequency: float):
        self.pwm = gpio_module.PWM(pin, frequency)
    
    def start(self, duty_cycle: float) -> None:
        self.pwm.start(duty_cycle)
    
    def change_duty_cycle(self, duty_cycle: float) -> None:
        self.pwm.ChangeDutyCycle(duty_cycle)
    
    def change_frequency(self, frequency: float) -> None:
        self.pwm.ChangeFrequency(frequency)
    
    def stop(self) -> None:
        self.pwm.stop()


class PiCamera2(CameraInterface):
    """Raspberry Pi Camera implementation using Picamera2"""
    
    def __init__(self):
        try:
            from picamera2 import Picamera2
            self.picam = Picamera2()
            logger.info("Initialized Picamera2")
        except ImportError:
            raise ImportError("Picamera2 not available. Install with: pip install picamera2")
    
    def configure(self, config: dict) -> None:
        self.picam.configure(config)
    
    def start(self) -> None:
        self.picam.start()
    
    def stop(self) -> None:
        self.picam.stop()
    
    def capture_array(self) -> Any:
        return self.picam.capture_array()
    
    def capture_metadata(self) -> dict:
        return self.picam.capture_metadata()
    
    @property
    def camera_controls(self) -> dict:
        return self.picam.camera_controls


# Mock implementations for testing

class MockGPIO(GPIOInterface):
    """Mock GPIO implementation for testing without hardware"""
    
    def __init__(self):
        self.pins = {}  # pin -> {'mode': mode, 'value': value, 'pull': pull}
        self.event_callbacks = {}  # pin -> callback
        self.pwm_instances = {}  # pin -> MockPWM
        logger.info("Initialized MockGPIO")
    
    def setup(self, pin: int, mode: PinMode, pull_up_down: PullMode = PullMode.OFF) -> None:
        self.pins[pin] = {
            'mode': mode,
            'value': 1 if pull_up_down == PullMode.UP else 0,
            'pull': pull_up_down
        }
        logger.debug(f"MockGPIO: Setup pin {pin} as {'INPUT' if mode == PinMode.INPUT else 'OUTPUT'}")
    
    def output(self, pin: int, value: int) -> None:
        if pin not in self.pins:
            self.setup(pin, PinMode.OUTPUT)
        self.pins[pin]['value'] = 1 if value else 0
        logger.debug(f"MockGPIO: Set pin {pin} to {self.pins[pin]['value']}")
    
    def input(self, pin: int) -> int:
        if pin not in self.pins:
            self.setup(pin, PinMode.INPUT)
        value = self.pins[pin]['value']
        logger.debug(f"MockGPIO: Read pin {pin} = {value}")
        return value
    
    def add_event_detect(
        self,
        pin: int,
        edge: Edge,
        callback: Optional[Callable] = None,
        bouncetime: int = 0
    ) -> None:
        self.event_callbacks[pin] = {
            'edge': edge,
            'callback': callback,
            'bouncetime': bouncetime
        }
        logger.debug(f"MockGPIO: Added event detect on pin {pin}")
    
    def remove_event_detect(self, pin: int) -> None:
        if pin in self.event_callbacks:
            del self.event_callbacks[pin]
            logger.debug(f"MockGPIO: Removed event detect from pin {pin}")
    
    def cleanup(self, pins: Optional[list] = None) -> None:
        if pins:
            for pin in pins:
                if pin in self.pins:
                    del self.pins[pin]
                if pin in self.event_callbacks:
                    del self.event_callbacks[pin]
                if pin in self.pwm_instances:
                    del self.pwm_instances[pin]
        else:
            self.pins.clear()
            self.event_callbacks.clear()
            self.pwm_instances.clear()
        logger.debug("MockGPIO: Cleaned up")
    
    def pwm(self, pin: int, frequency: float) -> PWMInterface:
        pwm_instance = MockPWM(pin, frequency)
        self.pwm_instances[pin] = pwm_instance
        return pwm_instance
    
    def trigger_event(self, pin: int, value: int) -> None:
        """Simulate an event on a pin (for testing)"""
        if pin in self.event_callbacks:
            old_value = self.pins.get(pin, {}).get('value', 0)
            self.pins[pin]['value'] = value
            
            event = self.event_callbacks[pin]
            edge = event['edge']
            callback = event['callback']
            
            # Check if edge matches
            if ((edge == Edge.RISING and old_value == 0 and value == 1) or
                (edge == Edge.FALLING and old_value == 1 and value == 0) or
                (edge == Edge.BOTH and old_value != value)):
                
                if callback:
                    logger.debug(f"MockGPIO: Triggering callback for pin {pin}")
                    callback(pin)


class MockPWM(PWMInterface):
    """Mock PWM implementation for testing"""
    
    def __init__(self, pin: int, frequency: float):
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = 0
        self.running = False
        logger.debug(f"MockPWM: Created on pin {pin} with frequency {frequency}Hz")
    
    def start(self, duty_cycle: float) -> None:
        self.duty_cycle = duty_cycle
        self.running = True
        logger.debug(f"MockPWM: Started on pin {self.pin} with duty cycle {duty_cycle}%")
    
    def change_duty_cycle(self, duty_cycle: float) -> None:
        self.duty_cycle = duty_cycle
        logger.debug(f"MockPWM: Changed duty cycle to {duty_cycle}%")
    
    def change_frequency(self, frequency: float) -> None:
        self.frequency = frequency
        logger.debug(f"MockPWM: Changed frequency to {frequency}Hz")
    
    def stop(self) -> None:
        self.running = False
        logger.debug(f"MockPWM: Stopped on pin {self.pin}")


class MockCamera(CameraInterface):
    """Mock camera implementation for testing"""
    
    def __init__(self, width: int = 1920, height: int = 1080):
        import numpy as np
        self.width = width
        self.height = height
        self.np = np
        self.running = False
        self.config = {}
        self._frame_count = 0
        logger.info(f"Initialized MockCamera ({width}x{height})")
    
    def configure(self, config: dict) -> None:
        self.config = config
        logger.debug("MockCamera: Configured")
    
    def start(self) -> None:
        self.running = True
        logger.debug("MockCamera: Started")
    
    def stop(self) -> None:
        self.running = False
        logger.debug("MockCamera: Stopped")
    
    def capture_array(self) -> Any:
        """Generate a test pattern frame"""
        self._frame_count += 1
        
        # Create a simple gradient test pattern
        frame = self.np.zeros((self.height, self.width, 3), dtype=self.np.uint8)
        
        # Add gradient
        for y in range(self.height):
            for x in range(self.width):
                frame[y, x] = [
                    int((x / self.width) * 255),  # Red gradient left-right
                    int((y / self.height) * 255),  # Green gradient top-bottom
                    128  # Blue constant
                ]
        
        # Add frame counter text area (simulated)
        frame[0:50, 0:200] = [255, 255, 255]  # White rectangle for text
        
        return frame
    
    def capture_metadata(self) -> dict:
        """Return mock metadata"""
        return {
            'ExposureTime': 20000,  # microseconds
            'AnalogueGain': 1.0,
            'FrameNumber': self._frame_count
        }
    
    @property
    def camera_controls(self) -> dict:
        """Return mock camera controls"""
        return {
            'ExposureTime': (100, 100000, 1),
            'AnalogueGain': (1.0, 16.0, 0.1),
            'Brightness': (-1.0, 1.0, 0.01),
            'Contrast': (0.0, 2.0, 0.01)
        }


# Global GPIO backend singleton
_gpio_backend_instance: Optional[GPIOInterface] = None


def get_gpio_backend(mock: bool = False) -> GPIOInterface:
    """
    Get GPIO backend based on environment (singleton pattern).
    
    Tries backends in this order:
    1. lgpio (Raspberry Pi 5)
    2. RPi.GPIO (Raspberry Pi 4 and earlier)
    3. MockGPIO (fallback for testing)
    
    Args:
        mock: If True, force mock implementation
    
    Returns:
        GPIOInterface instance (singleton)
    """
    global _gpio_backend_instance
    
    # Return existing instance if available
    if _gpio_backend_instance is not None:
        return _gpio_backend_instance
    
    if mock:
        logger.info("Using mock GPIO backend")
        _gpio_backend_instance = MockGPIO()
        return _gpio_backend_instance
    
    # Try lgpio first (Pi 5 compatible)
    try:
        backend = LgpioGPIO()
        logger.info("Using LgpioGPIO backend")
        _gpio_backend_instance = backend
        return backend
    except (ImportError, RuntimeError) as e:
        logger.debug(f"lgpio not available: {e}")
    
    # Fall back to RPi.GPIO (Pi 4 and earlier)
    try:
        backend = RPiGPIO()
        logger.info("Using RPiGPIO backend (legacy)")
        _gpio_backend_instance = backend
        return backend
    except ImportError:
        logger.debug("RPi.GPIO not available")
    
    # Final fallback to mock
    logger.warning("No GPIO library available (tried lgpio, RPi.GPIO), falling back to mock")
    _gpio_backend_instance = MockGPIO()
    return _gpio_backend_instance


def get_camera_backend(mock: bool = False) -> CameraInterface:
    """
    Get camera backend based on environment.
    
    Args:
        mock: If True, force mock implementation
    
    Returns:
        CameraInterface instance
    """
    if mock:
        logger.info("Using mock camera backend")
        return MockCamera()
    
    try:
        return PiCamera2()
    except ImportError:
        logger.warning("Picamera2 not available, falling back to mock")
        return MockCamera()
