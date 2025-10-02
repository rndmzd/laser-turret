"""
Centralized configuration management for laser turret.

Provides type-safe, validated access to configuration values with defaults.
"""

import configparser
import os
from typing import Optional, Any, Dict, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing"""
    pass


class ConfigManager:
    """Centralized configuration manager with validation and defaults"""
    
    # Default values
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
    
    # Valid pin ranges
    VALID_GPIO_PINS = range(2, 28)  # BCM pins 2-27
    
    def __init__(self, config_file: str = 'laserturret.conf'):
        """
        Initialize configuration manager.
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self._loaded = False
        self._cache: Dict[str, Any] = {}
        
    def load(self, required: bool = True) -> None:
        """
        Load configuration from file.
        
        Args:
            required: If True, raise error if file not found
        """
        if not os.path.exists(self.config_file):
            if required:
                raise ConfigurationError(f"Configuration file not found: {self.config_file}")
            else:
                logger.warning(f"Config file not found, using defaults: {self.config_file}")
                self._loaded = True
                return
        
        try:
            self.config.read(self.config_file)
            self._loaded = True
            logger.info(f"Loaded configuration from {self.config_file}")
            self._validate_config()
        except Exception as e:
            raise ConfigurationError(f"Failed to load config: {e}")
    
    def _validate_config(self) -> None:
        """Validate configuration values"""
        # Validate GPIO pins
        gpio_pins = [
            self.get_gpio_pin('x_ccw_limit_pin'),
            self.get_gpio_pin('x_cw_limit_pin'),
            self.get_gpio_pin('y_ccw_limit_pin'),
            self.get_gpio_pin('y_cw_limit_pin'),
            self.get_motor_pin('x_dir_pin'),
            self.get_motor_pin('x_step_pin'),
            self.get_motor_pin('x_enable_pin'),
            self.get_motor_pin('y_dir_pin'),
            self.get_motor_pin('y_step_pin'),
            self.get_motor_pin('y_enable_pin'),
            self.get_motor_pin('ms1_pin'),
            self.get_motor_pin('ms2_pin'),
            self.get_motor_pin('ms3_pin'),
            self.get_laser_pin(),
        ]
        
        # Check for duplicate pins
        pin_usage = {}
        for pin in gpio_pins:
            if pin in pin_usage:
                raise ConfigurationError(
                    f"Pin {pin} is assigned to multiple functions: "
                    f"{pin_usage[pin]} and another function"
                )
            pin_usage[pin] = True
        
        # Validate pin ranges
        for pin in gpio_pins:
            if pin not in self.VALID_GPIO_PINS:
                raise ConfigurationError(f"Invalid GPIO pin: {pin}")
        
        # Validate microsteps
        microsteps = self.get_motor_microsteps()
        if microsteps not in [1, 2, 4, 8, 16]:
            raise ConfigurationError(f"Invalid microsteps value: {microsteps}. Must be 1, 2, 4, 8, or 16")
        
        # Validate MQTT port
        port = self.get_mqtt_port()
        if not 1 <= port <= 65535:
            raise ConfigurationError(f"Invalid MQTT port: {port}")
        
        logger.info("Configuration validation passed")
    
    def _get(self, section: str, key: str, value_type: type = str, default: Any = None) -> Any:
        """
        Get configuration value with type conversion and default.
        
        Args:
            section: Configuration section
            key: Configuration key
            value_type: Type to convert to
            default: Default value if not found
        """
        cache_key = f"{section}.{key}"
        
        # Return cached value if available
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if not self._loaded:
            self.load(required=False)
        
        # Try to get from config file
        if self.config.has_option(section, key):
            try:
                if value_type == int:
                    value = self.config.getint(section, key)
                elif value_type == float:
                    value = self.config.getfloat(section, key)
                elif value_type == bool:
                    value = self.config.getboolean(section, key)
                else:
                    value = self.config.get(section, key)
            except ValueError as e:
                raise ConfigurationError(f"Invalid value for {section}.{key}: {e}")
        else:
            # Use default from DEFAULTS dict or provided default
            if section in self.DEFAULTS and key in self.DEFAULTS[section]:
                value = self.DEFAULTS[section][key]
            elif default is not None:
                value = default
            else:
                raise ConfigurationError(f"Missing required config: {section}.{key}")
        
        # Cache the value
        self._cache[cache_key] = value
        return value
    
    # GPIO Configuration
    def get_gpio_pin(self, pin_name: str) -> int:
        """Get GPIO pin number"""
        return self._get('GPIO', pin_name, int)
    
    # Motor Configuration
    def get_motor_pin(self, pin_name: str) -> int:
        """Get motor control pin number"""
        return self._get('Motor', pin_name, int)
    
    def get_motor_microsteps(self) -> int:
        """Get motor microstepping value"""
        return self._get('Motor', 'microsteps', int)
    
    def get_motor_steps_per_rev(self) -> int:
        """Get motor steps per revolution"""
        return self._get('Motor', 'steps_per_rev', int)
    
    # Control Configuration
    def get_control_max_steps(self) -> int:
        """Get maximum steps per update"""
        return self._get('Control', 'max_steps_per_update', int)
    
    def get_control_deadzone(self) -> int:
        """Get control deadzone value"""
        return self._get('Control', 'deadzone', int)
    
    def get_control_speed_scaling(self) -> float:
        """Get control speed scaling factor"""
        return self._get('Control', 'speed_scaling', float)
    
    def get_control_step_delay(self) -> float:
        """Get step delay in seconds"""
        return self._get('Control', 'step_delay', float)
    
    # MQTT Configuration
    def get_mqtt_broker(self) -> str:
        """Get MQTT broker address"""
        return self._get('MQTT', 'broker', str)
    
    def get_mqtt_port(self) -> int:
        """Get MQTT broker port"""
        return self._get('MQTT', 'port', int)
    
    def get_mqtt_topic(self) -> str:
        """Get MQTT topic"""
        return self._get('MQTT', 'topic', str)
    
    # Laser Configuration
    def get_laser_pin(self) -> int:
        """Get laser control pin"""
        return self._get('Laser', 'laser_pin', int)
    
    def get_laser_max_power(self) -> int:
        """Get maximum laser power percentage"""
        return self._get('Laser', 'laser_max_power', int)
    
    # Camera Configuration
    def get_camera_width(self) -> int:
        """Get camera width"""
        return self._get('Camera', 'width', int)
    
    def get_camera_height(self) -> int:
        """Get camera height"""
        return self._get('Camera', 'height', int)
    
    def get_camera_format(self) -> str:
        """Get camera format"""
        return self._get('Camera', 'format', str)
    
    def get_camera_buffer_count(self) -> int:
        """Get camera buffer count"""
        return self._get('Camera', 'buffer_count', int)
    
    # Convenience methods
    def get_motor_config(self, axis: str) -> Dict[str, int]:
        """
        Get complete motor configuration for an axis.
        
        Args:
            axis: 'x' or 'y'
        
        Returns:
            Dictionary with motor pin configuration
        """
        if axis not in ['x', 'y']:
            raise ValueError(f"Invalid axis: {axis}. Must be 'x' or 'y'")
        
        return {
            'step_pin': self.get_motor_pin(f'{axis}_step_pin'),
            'dir_pin': self.get_motor_pin(f'{axis}_dir_pin'),
            'enable_pin': self.get_motor_pin(f'{axis}_enable_pin'),
            'cw_limit_pin': self.get_gpio_pin(f'{axis}_cw_limit_pin'),
            'ccw_limit_pin': self.get_gpio_pin(f'{axis}_ccw_limit_pin'),
            'ms1_pin': self.get_motor_pin('ms1_pin'),
            'ms2_pin': self.get_motor_pin('ms2_pin'),
            'ms3_pin': self.get_motor_pin('ms3_pin'),
            'steps_per_rev': self.get_motor_steps_per_rev(),
            'microsteps': self.get_motor_microsteps(),
        }
    
    def get_all_config(self) -> Dict[str, Dict[str, Any]]:
        """Get all configuration as dictionary"""
        if not self._loaded:
            self.load(required=False)
        
        result = {}
        for section in self.config.sections():
            result[section] = dict(self.config.items(section))
        
        # Add defaults for missing sections
        for section, values in self.DEFAULTS.items():
            if section not in result:
                result[section] = values
        
        return result
    
    def reload(self) -> None:
        """Reload configuration from file"""
        self._cache.clear()
        self._loaded = False
        self.load()
    
    def __repr__(self) -> str:
        return f"ConfigManager(config_file='{self.config_file}', loaded={self._loaded})"


# Global singleton instance
_global_config: Optional[ConfigManager] = None


def get_config(config_file: str = 'laserturret.conf') -> ConfigManager:
    """
    Get global configuration manager instance.
    
    Args:
        config_file: Path to configuration file
    
    Returns:
        ConfigManager instance
    """
    global _global_config
    
    if _global_config is None:
        _global_config = ConfigManager(config_file)
        _global_config.load(required=False)
    
    return _global_config


def reset_config() -> None:
    """Reset global configuration (useful for testing)"""
    global _global_config
    _global_config = None
