# Hardware Abstraction Layer

The laser turret project includes a hardware abstraction layer (HAL) that enables development and testing without physical hardware.

## Overview

The HAL provides abstract interfaces for:

- **GPIO operations** - Pin I/O, PWM, event detection
- **Camera operations** - Frame capture, metadata, configuration
- **Mock implementations** - Simulated hardware for testing

### Supported Hardware

- **Raspberry Pi 5** - Uses `lgpio` library
- **Raspberry Pi 4 and earlier** - Uses `RPi.GPIO` library (legacy)
- **Development/Testing** - Mock implementations (no hardware required)

## Benefits

✅ **Develop without hardware** - Write and test code on any machine  
✅ **Unit testing** - Test hardware interactions in CI/CD  
✅ **Rapid prototyping** - Iterate quickly without setup  
✅ **Debugging** - Simulate edge cases and failure modes  
✅ **Cross-platform** - Develop on Windows/Mac, deploy to Pi  

## Architecture

```
┌─────────────────────────────────────────┐
│         Application Code                │
│   (LaserControl, StepperMotor, etc.)    │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│      Hardware Interfaces (ABC)          │
│  • GPIOInterface                        │
│  • PWMInterface                         │
│  • CameraInterface                      │
└────────┬──────────────────┬─────────────┘
         │                  │
    ┌────▼────┐        ┌───▼────┐
    │  Real   │        │  Mock  │
    │Hardware │        │Hardware│
    └─────────┘        └────────┘
    lgpio (Pi 5)       Simulated
    RPi.GPIO (Pi 4-)   No Pi needed
    Picamera2
```

## Usage

### Using Real Hardware (Default)

```python
from laserturret.lasercontrol import LaserControl

# Auto-detects lgpio (Pi 5) or RPi.GPIO (Pi 4-), falls back to mock
laser = LaserControl(gpio_pin=12)
```

### Using Mock Hardware Explicitly

```python
from laserturret.lasercontrol import LaserControl
from laserturret.hardware_interface import MockGPIO

# Force mock implementation
mock_gpio = MockGPIO()
laser = LaserControl(gpio_pin=12, gpio_backend=mock_gpio)

# Test without physical hardware
laser.on(power_level=50)
laser.pulse(duration=0.5)
laser.off()
```

### Testing Camera Without Hardware

```python
from laserturret.hardware_interface import MockCamera

camera = MockCamera(width=1920, height=1080)
camera.start()

# Returns a test pattern frame
frame = camera.capture_array()
metadata = camera.capture_metadata()

camera.stop()
```

## GPIO Interface

### Methods

| Method | Description |
|--------|-------------|
| `setup(pin, mode, pull_up_down)` | Configure pin as INPUT/OUTPUT |
| `output(pin, value)` | Write digital value to pin |
| `input(pin)` | Read digital value from pin |
| `add_event_detect(pin, edge, callback)` | Detect rising/falling edges |
| `remove_event_detect(pin)` | Remove edge detection |
| `cleanup(pins)` | Release GPIO resources |
| `pwm(pin, frequency)` | Create PWM instance |

### Example: Simulating Limit Switches

```python
from laserturret.hardware_interface import MockGPIO, Edge, PinMode, PullMode

mock_gpio = MockGPIO()

# Setup input with callback
def limit_reached(pin):
    print(f"Limit switch {pin} triggered!")

mock_gpio.setup(18, PinMode.INPUT, pull_up_down=PullMode.UP)
mock_gpio.add_event_detect(18, Edge.FALLING, callback=limit_reached)

# Simulate switch press
mock_gpio.trigger_event(18, 0)  # Falling edge: 1 → 0
```

## PWM Interface

### Methods

| Method | Description |
|--------|-------------|
| `start(duty_cycle)` | Start PWM with duty cycle (0-100%) |
| `change_duty_cycle(duty_cycle)` | Update duty cycle |
| `change_frequency(frequency)` | Update PWM frequency |
| `stop()` | Stop PWM |

### Example: Testing Laser PWM

```python
from laserturret.hardware_interface import MockGPIO

mock_gpio = MockGPIO()
pwm = mock_gpio.pwm(pin=12, frequency=1000)

pwm.start(0)  # Start at 0%
pwm.change_duty_cycle(50)  # Set to 50%
pwm.change_duty_cycle(100)  # Set to 100%
pwm.stop()

# Check state
print(f"PWM duty cycle: {pwm.duty_cycle}%")
print(f"PWM running: {pwm.running}")
```

## Camera Interface

### Methods

| Method | Description |
|--------|-------------|
| `configure(config)` | Set camera configuration |
| `start()` | Start camera |
| `stop()` | Stop camera |
| `capture_array()` | Capture frame as numpy array |
| `capture_metadata()` | Get frame metadata (exposure, gain, etc.) |
| `camera_controls` | Available controls (property) |

### Example: Testing Video Pipeline

```python
from laserturret.hardware_interface import MockCamera
import cv2

camera = MockCamera(width=640, height=480)
camera.configure({'format': 'RGB888'})
camera.start()

# Process frames
for i in range(10):
    frame = camera.capture_array()
    metadata = camera.capture_metadata()
    
    # Add overlay
    cv2.putText(frame, f"Frame {i}", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    print(f"Captured frame {i}: {metadata}")

camera.stop()
```

## Backend Selection

The `get_gpio_backend()` and `get_camera_backend()` functions automatically choose the appropriate implementation:

```python
from laserturret.hardware_interface import get_gpio_backend, get_camera_backend

# Auto-detect: tries lgpio (Pi 5) → RPi.GPIO (Pi 4-) → mock
gpio = get_gpio_backend()
camera = get_camera_backend()

# Force mock for testing
gpio = get_gpio_backend(mock=True)
camera = get_camera_backend(mock=True)
```

### GPIO Backend Priority

The system tries GPIO libraries in this order:

1. **lgpio** - Raspberry Pi 5 (preferred)
2. **RPi.GPIO** - Raspberry Pi 4 and earlier (legacy)
3. **MockGPIO** - Fallback for development/testing

This ensures compatibility across all Raspberry Pi models.

## Testing

### Running Mock Hardware Tests

```bash
cd scripts
python3 test_with_mock_hardware.py
```

This runs a complete test suite using mock hardware:

- LaserControl PWM operations
- MockCamera frame capture
- GPIO event detection
- Pin state management

### Unit Testing Example

```python
import unittest
from laserturret.lasercontrol import LaserControl
from laserturret.hardware_interface import MockGPIO

class TestLaserControl(unittest.TestCase):
    def setUp(self):
        self.mock_gpio = MockGPIO()
        self.laser = LaserControl(gpio_pin=12, gpio_backend=self.mock_gpio)
    
    def test_power_level(self):
        self.laser.set_power(50)
        self.assertEqual(self.laser.power_level, 50)
    
    def test_on_off(self):
        self.laser.on()
        self.assertTrue(self.laser.is_on)
        
        self.laser.off()
        self.assertFalse(self.laser.is_on)
    
    def tearDown(self):
        self.laser.cleanup()

if __name__ == '__main__':
    unittest.main()
```

## Migration Guide

### Existing Code

```python
# Old: Direct RPi.GPIO usage (doesn't work on Pi 5!)
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(12, GPIO.OUT)
pwm = GPIO.PWM(12, 1000)
pwm.start(0)
```

### With HAL

```python
# New: Using hardware abstraction (works on all Pi models)
from laserturret.hardware_interface import get_gpio_backend, PinMode

gpio = get_gpio_backend()  # Auto-detects lgpio/RPi.GPIO
gpio.setup(12, PinMode.OUTPUT)
pwm = gpio.pwm(12, frequency=1000)
pwm.start(0)
```

### Benefits of Migration

1. **Raspberry Pi 5 Support** - Works on Pi 5 (RPi.GPIO doesn't!)
2. **Testability** - Can run without Pi hardware
3. **Flexibility** - Easy to swap implementations
4. **Type Safety** - Clear interfaces with type hints
5. **Debugging** - Mock implementations log all operations
6. **CI/CD** - Run tests in any environment
7. **Backward Compatible** - Still works on Pi 4 and earlier

## Implementation Details

### Mock GPIO State

MockGPIO maintains internal state for all pins:

```python
{
    pin_number: {
        'mode': PinMode.INPUT or PinMode.OUTPUT,
        'value': 0 or 1,
        'pull': PullMode.OFF/UP/DOWN
    }
}
```

### Mock Camera Frames

MockCamera generates test pattern frames:

- Red gradient (left → right)
- Green gradient (top → bottom)
- Blue constant value
- Frame counter overlay area

### Logging

All mock operations are logged at DEBUG level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now see all mock hardware operations
laser.on()  # MockGPIO: Set pin 12 to 1
```

## Advanced Usage

### Custom Mock Behavior

```python
class CustomMockGPIO(MockGPIO):
    def input(self, pin):
        # Simulate noisy sensor
        import random
        if random.random() < 0.01:  # 1% noise
            return 1 - self.pins[pin]['value']
        return super().input(pin)
```

### Injecting Failures

```python
class FailingCamera(CameraInterface):
    def capture_array(self):
        raise RuntimeError("Camera disconnected")
    
    # ... implement other required methods

# Test error handling
camera = FailingCamera()
try:
    frame = camera.capture_array()
except RuntimeError as e:
    print(f"Handled error: {e}")
```

### Recording Mock Interactions

```python
class RecordingGPIO(MockGPIO):
    def __init__(self):
        super().__init__()
        self.history = []
    
    def output(self, pin, value):
        self.history.append(('output', pin, value))
        super().output(pin, value)

# Later: analyze GPIO operations
gpio = RecordingGPIO()
# ... use gpio ...
print(f"Total GPIO operations: {len(gpio.history)}")
```

## Best Practices

1. **Always use interfaces** - Don't import `RPi.GPIO` directly in application code
2. **Test with mocks** - Write unit tests using mock implementations
3. **Auto-detect by default** - Let the system choose real vs mock hardware
4. **Explicit for tests** - Pass mock backends explicitly in test code
5. **Log operations** - Enable DEBUG logging during development

## Future Enhancements

Potential additions to the HAL:

- I2C/SPI interfaces for sensors
- Servo motor abstraction
- ADC/DAC interfaces
- Network/MQTT abstraction
- Configurable mock behaviors (delay, failure injection)
- Recording/playback of GPIO sequences

## See Also

- `test_with_mock_hardware.py` - Example test script
- `laserturret/hardware_interface.py` - Implementation
- `laserturret/lasercontrol.py` - Example usage
