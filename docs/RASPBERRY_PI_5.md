# Raspberry Pi 5 Support

This document explains how the laser turret supports Raspberry Pi 5, which requires different GPIO libraries than earlier models.

## Background

**Raspberry Pi 5 uses a different GPIO interface** and the traditional `RPi.GPIO` library **does not work** on Pi 5. The Pi 5 requires the newer `lgpio` library.

## Automatic Detection

The laser turret **automatically detects** which GPIO library to use:

1. **Tries lgpio first** (Raspberry Pi 5)
2. **Falls back to RPi.GPIO** (Raspberry Pi 4 and earlier)
3. **Uses MockGPIO** if neither is available (for testing)

**You don't need to do anything** - the code automatically selects the correct backend.

## Installation

### On Raspberry Pi 5

```bash
# Install system packages
sudo apt-get update
sudo apt-get install -y python3-lgpio python3-picamera2 python3-opencv

# Install Python packages
pip3 install lgpio
```

### On Raspberry Pi 4 and Earlier

```bash
# Install system packages
sudo apt-get update
sudo apt-get install -y python3-rpi.gpio python3-picamera2 python3-opencv

# RPi.GPIO is usually pre-installed
```

### Install Project Dependencies

```bash
cd ~/laser-turret
pip3 install -r requirements.txt
```

## Technical Details

### Hardware Abstraction Layer

The project uses a **Hardware Abstraction Layer (HAL)** that provides:

- `LgpioGPIO` - For Raspberry Pi 5
- `RPiGPIO` - For Raspberry Pi 4 and earlier (legacy)
- `MockGPIO` - For testing without hardware

All three implement the same `GPIOInterface`, so application code works on any platform.

### Key Differences

| Feature | RPi.GPIO | lgpio |
|---------|----------|-------|
| Pi 5 Support | ❌ No | ✅ Yes |
| Pi 4- Support | ✅ Yes | ⚠️ Varies |
| Chip Access | `/dev/mem` | `/dev/gpiochipN` |
| Event Callbacks | Built-in | Manual polling |
| PWM | Software | Hardware/Software |

### Event Detection

**Important**: `lgpio` event callbacks work differently than `RPi.GPIO`:

- **RPi.GPIO**: Callbacks run automatically in background thread
- **lgpio**: Requires manual polling of alerts

The `LgpioGPIO` class implements basic alert setup, but for production use with intensive event handling, consider using `gpiozero` with the lgpio pin factory:

```python
# Alternative: Use gpiozero for full event support
import os
os.environ['GPIOZERO_PIN_FACTORY'] = 'lgpio'

from gpiozero import Button
button = Button(18)
button.when_pressed = my_callback
```

## Usage Example

```python
from laserturret.hardware_interface import get_gpio_backend, PinMode

# Automatically selects lgpio on Pi 5, RPi.GPIO on Pi 4-
gpio = get_gpio_backend()

# Same API on all platforms
gpio.setup(18, PinMode.INPUT, pull_up_down=PullMode.UP)
value = gpio.input(18)
gpio.output(23, 1)

# PWM also works the same
pwm = gpio.pwm(12, frequency=1000)
pwm.start(50)  # 50% duty cycle
```

## Verifying Your GPIO Backend

Run this to see which backend is being used:

```python
from laserturret.hardware_interface import get_gpio_backend

gpio = get_gpio_backend()
print(f"Using GPIO backend: {type(gpio).__name__}")
```

Output on Pi 5:

```
Using GPIO backend: LgpioGPIO
```

Output on Pi 4:

```
Using GPIO backend: RPiGPIO
```

## Testing Without Hardware

The mock GPIO backend lets you test on any machine:

```python
from laserturret.hardware_interface import get_gpio_backend

# Force mock mode (no Pi required)
gpio = get_gpio_backend(mock=True)
```

## Troubleshooting

### "lgpio not available" on Pi 5

Install the package:

```bash
sudo apt-get install python3-lgpio
pip3 install lgpio
```

### "Could not open any GPIO chip"

Check that gpiochip devices exist:

```bash
ls /dev/gpiochip*
```

On Pi 5, you should see `/dev/gpiochip4` (pinctrl-rp1).

Verify permissions:

```bash
sudo usermod -a -G gpio $USER
# Log out and back in
```

### PWM Not Working

lgpio PWM uses different mechanisms than RPi.GPIO. For hardware PWM, use gpiozero:

```python
import os
os.environ['GPIOZERO_PIN_FACTORY'] = 'lgpio'

from gpiozero import PWMLED
laser = PWMLED(12)
laser.value = 0.5  # 50% brightness
```

## Migration from RPi.GPIO

If you have existing code using RPi.GPIO directly:

### Before (doesn't work on Pi 5)

```python
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(12, GPIO.OUT)
pwm = GPIO.PWM(12, 1000)
pwm.start(50)
```

### After (works on all Pi models)

```python
from laserturret.hardware_interface import get_gpio_backend, PinMode

gpio = get_gpio_backend()
gpio.setup(12, PinMode.OUTPUT)
pwm = gpio.pwm(12, frequency=1000)
pwm.start(50)
```

## Resources

- [lgpio Documentation](http://abyz.me.uk/lg/lgpio.html)
- [gpiozero Documentation](https://gpiozero.readthedocs.io/)
- [Raspberry Pi 5 GPIO Changes](https://www.raspberrypi.com/documentation/computers/raspberry-pi-5.html)

## Summary

✅ **Raspberry Pi 5 is fully supported** using lgpio  
✅ **Automatic backend selection** - just install and use  
✅ **Backward compatible** with Pi 4 and earlier  
✅ **Same API** across all platforms  
✅ **Testable** without hardware using mock backend  

The laser turret works seamlessly on Raspberry Pi 5, 4, 3, and earlier models!
