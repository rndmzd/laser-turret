# Configuration Management

The laser turret uses a centralized configuration manager for type-safe, validated access to all settings.

## Quick Start

### Using Configuration

```python
from laserturret import get_config

# Get global config instance
config = get_config()

# Access configuration values
laser_pin = config.get_laser_pin()
broker = config.get_mqtt_broker()

# Get complete motor configuration
x_motor = config.get_motor_config('x')
```

### Configuration File

Create `laserturret.conf` in the project root (copy from `laserturret.conf.example`):

```ini
[GPIO]
x_ccw_limit_pin = 21
x_cw_limit_pin = 18
y_ccw_limit_pin = 4
y_cw_limit_pin = 20

[MQTT]
broker = localhost
port = 1883
topic = laserturret

[Motor]
x_dir_pin = 19
x_step_pin = 23
x_enable_pin = 5
y_dir_pin = 26
y_step_pin = 24
y_enable_pin = 6
ms1_pin = 17
ms2_pin = 27
ms3_pin = 22
microsteps = 8
steps_per_rev = 200

[Control]
max_steps_per_update = 50
deadzone = 5
speed_scaling = 0.10
step_delay = 0.0005

[Laser]
laser_pin = 12
laser_max_power = 100

[Camera]
width = 1920
height = 1080
format = RGB888
buffer_count = 2
```

## Features

### ✅ Type Safety
All values are properly typed and converted:
- `int` for pin numbers and counts
- `float` for delays and scaling
- `str` for addresses and topics
- `bool` for flags

### ✅ Validation
Configuration is validated on load:
- Pin numbers must be valid BCM GPIO (2-27)
- No duplicate pin assignments
- Microsteps must be 1, 2, 4, 8, or 16
- MQTT port must be 1-65535

### ✅ Defaults
Built-in defaults for all values, so config file is optional:
```python
config = get_config()  # Works even without laserturret.conf
```

### ✅ Caching
Values are cached after first access for performance.

## API Reference

### Creating Config Manager

```python
from laserturret.config_manager import ConfigManager, get_config

# Method 1: Global singleton (recommended)
config = get_config()

# Method 2: Custom instance
config = ConfigManager('my_config.conf')
config.load()
```

### GPIO Configuration

| Method | Returns | Description |
|--------|---------|-------------|
| `get_gpio_pin(name)` | `int` | Get GPIO pin by name |

```python
x_cw_limit = config.get_gpio_pin('x_cw_limit_pin')
```

### Motor Configuration

| Method | Returns | Description |
|--------|---------|-------------|
| `get_motor_pin(name)` | `int` | Get motor control pin |
| `get_motor_microsteps()` | `int` | Get microstepping value |
| `get_motor_steps_per_rev()` | `int` | Get steps per revolution |
| `get_motor_config(axis)` | `dict` | Get complete motor config |

```python
# Individual values
step_pin = config.get_motor_pin('x_step_pin')
microsteps = config.get_motor_microsteps()

# Complete motor configuration
x_motor = config.get_motor_config('x')
# Returns: {
#     'step_pin': 23,
#     'dir_pin': 19,
#     'enable_pin': 5,
#     'cw_limit_pin': 18,
#     'ccw_limit_pin': 21,
#     'ms1_pin': 17,
#     'ms2_pin': 27,
#     'ms3_pin': 22,
#     'steps_per_rev': 200,
#     'microsteps': 8
# }
```

### Control Configuration

| Method | Returns | Description |
|--------|---------|-------------|
| `get_control_max_steps()` | `int` | Max steps per update |
| `get_control_deadzone()` | `int` | Input deadzone |
| `get_control_speed_scaling()` | `float` | Speed scaling factor |
| `get_control_step_delay()` | `float` | Delay between steps |

```python
deadzone = config.get_control_deadzone()
delay = config.get_control_step_delay()
```

### MQTT Configuration

| Method | Returns | Description |
|--------|---------|-------------|
| `get_mqtt_broker()` | `str` | Broker address |
| `get_mqtt_port()` | `int` | Broker port |
| `get_mqtt_topic()` | `str` | Topic name |

```python
broker = config.get_mqtt_broker()
port = config.get_mqtt_port()
topic = config.get_mqtt_topic()
```

### Laser Configuration

| Method | Returns | Description |
|--------|---------|-------------|
| `get_laser_pin()` | `int` | Laser control pin |
| `get_laser_max_power()` | `int` | Max power (0-100) |

```python
laser_pin = config.get_laser_pin()
max_power = config.get_laser_max_power()
```

### Camera Configuration

| Method | Returns | Description |
|--------|---------|-------------|
| `get_camera_width()` | `int` | Camera width |
| `get_camera_height()` | `int` | Camera height |
| `get_camera_format()` | `str` | Pixel format |
| `get_camera_buffer_count()` | `int` | Number of buffers |

```python
width = config.get_camera_width()
height = config.get_camera_height()
```

### Utility Methods

```python
# Get all configuration as dictionary
all_config = config.get_all_config()

# Reload from file
config.reload()
```

## Usage Examples

### In Application Code

```python
from laserturret import get_config
from laserturret.lasercontrol import LaserControl
from laserturret.steppercontrol import StepperMotor

config = get_config()

# Initialize laser
laser = LaserControl(
    gpio_pin=config.get_laser_pin(),
    initial_power=0
)

# Initialize motors
x_motor_cfg = config.get_motor_config('x')
motor_x = StepperMotor(
    step_pin=x_motor_cfg['step_pin'],
    dir_pin=x_motor_cfg['dir_pin'],
    enable_pin=x_motor_cfg['enable_pin'],
    # ... other pins
)
```

### In Test Code

```python
from laserturret.config_manager import ConfigManager, reset_config

def test_with_custom_config():
    # Reset global config
    reset_config()
    
    # Create test config
    config = ConfigManager('test_config.conf')
    config.load(required=False)
    
    # Use test values
    assert config.get_laser_pin() == 12
```

### Handling Missing Config

```python
from laserturret.config_manager import ConfigurationError, get_config

try:
    config = get_config()
    config.load(required=True)  # Raise error if missing
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    # Use defaults or exit
```

## Validation

The config manager validates:

### Pin Assignments
- All pins must be valid BCM GPIO (2-27)
- No duplicate pin assignments
- Raises `ConfigurationError` if invalid

### Motor Settings
- Microsteps must be 1, 2, 4, 8, or 16
- Steps per revolution must be positive

### MQTT Settings
- Port must be 1-65535

### Error Handling

```python
try:
    config = get_config()
    config.load()
except ConfigurationError as e:
    print(f"Invalid configuration: {e}")
    # Handle error
```

## Defaults

Built-in defaults (used when config file missing):

```python
DEFAULTS = {
    'GPIO': {
        'x_ccw_limit_pin': 21,
        'x_cw_limit_pin': 18,
        'y_ccw_limit_pin': 4,
        'y_cw_limit_pin': 20,
    },
    'MQTT': {
        'broker': 'localhost',
        'port': 1883,
        'topic': 'laserturret',
    },
    'Motor': {
        'x_dir_pin': 19,
        'x_step_pin': 23,
        'x_enable_pin': 5,
        'y_dir_pin': 26,
        'y_step_pin': 24,
        'y_enable_pin': 6,
        'ms1_pin': 17,
        'ms2_pin': 27,
        'ms3_pin': 22,
        'microsteps': 8,
        'steps_per_rev': 200,
    },
    'Control': {
        'max_steps_per_update': 50,
        'deadzone': 5,
        'speed_scaling': 0.10,
        'step_delay': 0.0005,
    },
    'Laser': {
        'laser_pin': 12,
        'laser_max_power': 100,
    },
    'Camera': {
        'width': 1920,
        'height': 1080,
        'format': 'RGB888',
        'buffer_count': 2,
    }
}
```

## Migration Guide

### Old Code (Direct ConfigParser)

```python
import configparser

config = configparser.ConfigParser()
config.read('laserturret.conf')

laser_pin = int(config['Laser']['laser_pin'])
broker = config['MQTT']['broker']
port = int(config['MQTT']['port'])
```

### New Code (ConfigManager)

```python
from laserturret import get_config

config = get_config()

laser_pin = config.get_laser_pin()  # Type-safe, validated
broker = config.get_mqtt_broker()
port = config.get_mqtt_port()
```

### Benefits

1. **Type safety** - No manual int() conversion
2. **Validation** - Automatic checks on load
3. **Defaults** - Works without config file
4. **Caching** - Better performance
5. **Error handling** - Clear error messages
6. **Convenience methods** - `get_motor_config()` etc.

## Advanced Usage

### Custom Validation

Extend `ConfigManager` for custom validation:

```python
from laserturret.config_manager import ConfigManager, ConfigurationError

class CustomConfigManager(ConfigManager):
    def _validate_config(self):
        super()._validate_config()
        
        # Custom validation
        if self.get_laser_max_power() > 50:
            raise ConfigurationError("Laser power limited to 50% for safety")
```

### Environment-Specific Configs

```python
import os
from laserturret import get_config

env = os.getenv('ENVIRONMENT', 'production')
config_file = f'config.{env}.conf'

config = get_config(config_file)
```

### Config Hot-Reload

```python
import signal
from laserturret import get_config

config = get_config()

def reload_config(signum, frame):
    print("Reloading configuration...")
    config.reload()

signal.signal(signal.SIGHUP, reload_config)
```

## Troubleshooting

### Config File Not Found

```
ConfigurationError: Configuration file not found: laserturret.conf
```

**Solution:** 
- Copy `laserturret.conf.example` to `laserturret.conf`
- Or use `config.load(required=False)` to use defaults

### Invalid Pin Assignment

```
ConfigurationError: Invalid GPIO pin: 30
```

**Solution:** Ensure pins are in valid range (2-27 for BCM)

### Duplicate Pin

```
ConfigurationError: Pin 12 is assigned to multiple functions
```

**Solution:** Each pin can only be assigned to one function

### Invalid Microsteps

```
ConfigurationError: Invalid microsteps value: 5. Must be 1, 2, 4, 8, or 16
```

**Solution:** Use valid microstepping values

## Best Practices

1. **Use global instance** - `get_config()` for singleton pattern
2. **Load early** - Load config at application startup
3. **Validate on load** - Always call `config.load()` 
4. **Use type-safe methods** - `get_laser_pin()` instead of raw access
5. **Handle errors** - Catch `ConfigurationError` appropriately
6. **Document custom sections** - If extending config
7. **Test with defaults** - Ensure app works without config file
