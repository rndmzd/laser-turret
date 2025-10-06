"""
Stepper motor controller for camera tracking.

Provides precise camera positioning using stepper motors with X/Y axis control.
Includes calibration, safety limits, and smooth motion control.
"""

import time
import threading
import logging
import json
import os
from typing import Tuple, Optional
from dataclasses import dataclass, asdict
from laserturret.motion.constants import MICROSTEP_CONFIG, CLOCKWISE, COUNTER_CLOCKWISE
from laserturret.motion.axis import StepperAxis
from laserturret.steppercontrol import MotorError, LimitSwitchError

logger = logging.getLogger(__name__)


@dataclass
class StepperCalibration:
    """Calibration data for camera tracking"""
    # Steps per pixel movement in camera frame
    x_steps_per_pixel: float = 0.1  # Default, needs calibration
    y_steps_per_pixel: float = 0.1  # Default, needs calibration
    
    # Current position in steps (relative to home/center)
    x_position: int = 0
    y_position: int = 0
    
    # Movement limits in steps from center
    x_max_steps: int = 2000
    y_max_steps: int = 2000
    
    # Speed settings
    step_delay: float = 0.001  # Delay between steps (seconds)
    acceleration_steps: int = 50  # Steps to accelerate/decelerate
    
    # Dead zone in pixels - don't move if object is this close to center
    dead_zone_pixels: int = 20
    
    # Calibration status
    is_calibrated: bool = False  # Must be True before camera movement enabled
    calibration_timestamp: Optional[str] = None  # When calibration was performed


class StepperController:
    """
    Controls stepper motors for camera tracking.
    
    Provides smooth, calibrated camera movement to keep tracked objects
    centered in the frame.
    """
    
    def __init__(self, gpio_interface, config_manager, calibration_file='camera_calibration.json'):
        """
        Initialize stepper controller.
        
        Args:
            gpio_interface: GPIOInterface instance for hardware control
            config_manager: ConfigManager instance for pin configuration
            calibration_file: Path to calibration data file
        """
        self.gpio = gpio_interface
        self.config = config_manager
        self.calibration_file = calibration_file
        self.calibration = StepperCalibration()
        
        # Motor pins
        self.x_step_pin = config_manager.get_motor_pin('x_step_pin')
        self.x_dir_pin = config_manager.get_motor_pin('x_dir_pin')
        self.x_enable_pin = config_manager.get_motor_pin('x_enable_pin')
        
        self.y_step_pin = config_manager.get_motor_pin('y_step_pin')
        self.y_dir_pin = config_manager.get_motor_pin('y_dir_pin')
        self.y_enable_pin = config_manager.get_motor_pin('y_enable_pin')
        
        # Microstepping pins
        self.ms1_pin = config_manager.get_motor_pin('ms1_pin')
        self.ms2_pin = config_manager.get_motor_pin('ms2_pin')
        self.ms3_pin = config_manager.get_motor_pin('ms3_pin')
        
        # Limit switches (optional safety)
        try:
            self.x_cw_limit = config_manager.get_gpio_pin('x_cw_limit_pin')
            self.x_ccw_limit = config_manager.get_gpio_pin('x_ccw_limit_pin')
            self.y_cw_limit = config_manager.get_gpio_pin('y_cw_limit_pin')
            self.y_ccw_limit = config_manager.get_gpio_pin('y_ccw_limit_pin')
            self.has_limit_switches = True
        except:
            self.has_limit_switches = False
            logger.warning("Limit switches not configured - using software limits only")
        
        # Axis drivers
        try:
            x_cfg = self.config.get_motor_config('x')
            y_cfg = self.config.get_motor_config('y')
            self.axis_x = StepperAxis(
                step_pin=x_cfg['step_pin'],
                dir_pin=x_cfg['dir_pin'],
                enable_pin=x_cfg['enable_pin'],
                ms1_pin=x_cfg['ms1_pin'],
                ms2_pin=x_cfg['ms2_pin'],
                ms3_pin=x_cfg['ms3_pin'],
                cw_limit_switch_pin=x_cfg.get('cw_limit_pin'),
                ccw_limit_switch_pin=x_cfg.get('ccw_limit_pin'),
                steps_per_rev=x_cfg['steps_per_rev'],
                microsteps=x_cfg['microsteps'],
                skip_direction_check=True,
                perform_calibration=False,
                name='AxisX',
                start_thread=False,
                gpio_backend=self.gpio,
            )
            self.axis_y = StepperAxis(
                step_pin=y_cfg['step_pin'],
                dir_pin=y_cfg['dir_pin'],
                enable_pin=y_cfg['enable_pin'],
                ms1_pin=y_cfg['ms1_pin'],
                ms2_pin=y_cfg['ms2_pin'],
                ms3_pin=y_cfg['ms3_pin'],
                cw_limit_switch_pin=y_cfg.get('cw_limit_pin'),
                ccw_limit_switch_pin=y_cfg.get('ccw_limit_pin'),
                steps_per_rev=y_cfg['steps_per_rev'],
                microsteps=y_cfg['microsteps'],
                skip_direction_check=True,
                perform_calibration=False,
                name='AxisY',
                start_thread=False,
                gpio_backend=self.gpio,
            )
        except Exception as _:
            self.axis_x = None
            self.axis_y = None
        
        # State
        self.enabled = False
        self.moving = False
        self.movement_lock = threading.Lock()
        
        # Initialize GPIO
        self._setup_gpio()
        
        # Load calibration if available
        self.load_calibration()
        
        logger.info("StepperController initialized")
    
    def _setup_gpio(self):
        """Configure GPIO pins for stepper motors"""
        from laserturret.hardware_interface import PinMode, PullMode
        
        # Setup motor control pins as outputs
        self.gpio.setup(self.x_step_pin, PinMode.OUTPUT)
        self.gpio.setup(self.x_dir_pin, PinMode.OUTPUT)
        self.gpio.setup(self.x_enable_pin, PinMode.OUTPUT)
        
        self.gpio.setup(self.y_step_pin, PinMode.OUTPUT)
        self.gpio.setup(self.y_dir_pin, PinMode.OUTPUT)
        self.gpio.setup(self.y_enable_pin, PinMode.OUTPUT)
        
        self.gpio.setup(self.ms1_pin, PinMode.OUTPUT)
        self.gpio.setup(self.ms2_pin, PinMode.OUTPUT)
        self.gpio.setup(self.ms3_pin, PinMode.OUTPUT)
        
        # Setup limit switches if available
        if self.has_limit_switches:
            self.gpio.setup(self.x_cw_limit, PinMode.INPUT, PullMode.UP)
            self.gpio.setup(self.x_ccw_limit, PinMode.INPUT, PullMode.UP)
            self.gpio.setup(self.y_cw_limit, PinMode.INPUT, PullMode.UP)
            self.gpio.setup(self.y_ccw_limit, PinMode.INPUT, PullMode.UP)
        
        # Set microstepping (1/8 step for smooth motion)
        microsteps = self.config.get_motor_microsteps()
        self.microsteps = microsteps
        self._set_microstepping(microsteps)
        
        # Disable motors initially
        self.gpio.output(self.x_enable_pin, 1)  # Active low - 1 is disabled
        self.gpio.output(self.y_enable_pin, 1)
        
        logger.debug("GPIO pins configured for stepper control")
    
    def _set_microstepping(self, microsteps: int):
        """
        Set microstepping mode.
        
        Args:
            microsteps: 1, 2, 4, 8, or 16
        """
        # MS1, MS2, MS3 truth table for A4988/DRV8825 drivers
        settings = MICROSTEP_CONFIG
        
        if microsteps in settings:
            ms1, ms2, ms3 = settings[microsteps]
            self.gpio.output(self.ms1_pin, ms1)
            self.gpio.output(self.ms2_pin, ms2)
            self.gpio.output(self.ms3_pin, ms3)
            logger.debug(f"Microstepping set to 1/{microsteps}")
        else:
            logger.error(f"Invalid microstepping value: {microsteps}")
    
    def enable(self):
        """Enable stepper motors"""
        self.gpio.output(self.x_enable_pin, 0)  # Active low
        self.gpio.output(self.y_enable_pin, 0)
        self.enabled = True
        logger.info("Stepper motors enabled")
    
    def disable(self):
        """Disable stepper motors"""
        self.gpio.output(self.x_enable_pin, 1)
        self.gpio.output(self.y_enable_pin, 1)
        self.enabled = False
        if self.calibration.is_calibrated:
            self.calibration.is_calibrated = False
            self.calibration.calibration_timestamp = None
            self.save_calibration()
        logger.info("Stepper motors disabled")
    
    def check_limit_switch(self, axis: str, direction: int) -> bool:
        """
        Check if limit switch is triggered.
        
        Args:
            axis: 'x' or 'y'
            direction: 1 for CW, -1 for CCW
            
        Returns:
            True if limit switch is triggered (movement should stop)
        """
        if not self.has_limit_switches:
            return False
        
        try:
            if axis == 'x':
                if direction > 0:
                    return self.gpio.input(self.x_cw_limit) == 0  # Active low
                else:
                    return self.gpio.input(self.x_ccw_limit) == 0
            else:  # y axis - inverted to match reversed direction signal
                # Y-axis direction is inverted, so limit switches are also inverted
                if direction > 0:
                    return self.gpio.input(self.y_ccw_limit) == 0  # Check CCW when moving "positive"
                else:
                    return self.gpio.input(self.y_cw_limit) == 0   # Check CW when moving "negative"
        except Exception as e:
            logger.error(f"Error reading limit switch: {e}")
            return False
    
    def check_software_limits(self, axis: str, steps: int) -> int:
        """
        Check and constrain movement within software limits.
        
        Args:
            axis: 'x' or 'y'
            steps: Requested steps (signed)
            
        Returns:
            Constrained steps within limits
        """
        if axis == 'x':
            new_pos = self.calibration.x_position + steps
            max_steps = self.calibration.x_max_steps
            
            if new_pos > max_steps:
                steps = max_steps - self.calibration.x_position
            elif new_pos < -max_steps:
                steps = -max_steps - self.calibration.x_position
        else:  # y axis
            new_pos = self.calibration.y_position + steps
            max_steps = self.calibration.y_max_steps
            
            if new_pos > max_steps:
                steps = max_steps - self.calibration.y_position
            elif new_pos < -max_steps:
                steps = -max_steps - self.calibration.y_position
        
        return steps
    
    def step(self, axis: str, steps: int, delay: Optional[float] = None, bypass_limits: bool = False):
        """
        Execute steps on specified axis with acceleration.
        
        Args:
            axis: 'x' or 'y'
            steps: Number of steps (signed - positive or negative for direction)
            delay: Optional delay between steps (uses calibration default if None)
            bypass_limits: If True, bypass software position limits (used during calibration)
        """
        if not self.enabled:
            logger.warning("Cannot step - motors not enabled")
            return
        
        if steps == 0:
            return
        
        # Apply software limits unless bypassed (e.g., during calibration)
        if not bypass_limits:
            steps = self.check_software_limits(axis, steps)
            if steps == 0:
                logger.debug(f"Movement constrained by software limits on {axis} axis")
                return
        
        motor = self.axis_x if axis == 'x' else self.axis_y
        if motor is None:
            return
        direction_sign = 1 if steps > 0 else -1
        total = abs(steps)
        if delay is None:
            delay = self.calibration.step_delay
        accel = min(self.calibration.acceleration_steps, total // 2)
        moved_total = 0
        try:
            if axis == 'x':
                dir_const = CLOCKWISE if direction_sign > 0 else COUNTER_CLOCKWISE
            else:
                dir_const = COUNTER_CLOCKWISE if direction_sign > 0 else CLOCKWISE
            motor.set_direction(dir_const)
        except LimitSwitchError:
            return
        if accel > 0:
            k = min(accel, 10)
            seg_delays = []
            seg_sizes = []
            for s in range(k):
                start = (s * accel) // k
                end = ((s + 1) * accel) // k
                size = end - start
                if size <= 0:
                    continue
                mid = (start + end) / 2.0
                ratio = (mid) / accel
                cur = delay + (delay * 2 * (1 - ratio))
                seg_delays.append(cur)
                seg_sizes.append(size)
            for size, cur in zip(seg_sizes, seg_delays):
                try:
                    moved = motor.step(size, cur)
                except (MotorError, LimitSwitchError):
                    break
                moved_total += moved
        const_size = total - 2 * accel
        if const_size > 0:
            try:
                moved = motor.step(const_size, delay)
            except (MotorError, LimitSwitchError):
                moved = 0
            moved_total += moved
        if accel > 0:
            for size, cur in zip(reversed(seg_sizes), reversed(seg_delays)):
                try:
                    moved = motor.step(size, cur)
                except (MotorError, LimitSwitchError):
                    break
                moved_total += moved
        if axis == 'x':
            self.calibration.x_position += direction_sign * moved_total
        else:
            self.calibration.y_position += direction_sign * moved_total
        self.enable()
        logger.debug(f"Moved {moved_total} steps on {axis} axis, position: ({self.calibration.x_position}, {self.calibration.y_position})")
    
    def move_to_center_object(self, object_center_x: int, object_center_y: int,
                              frame_width: int, frame_height: int) -> bool:
        """
        Move camera to center object under crosshair.
        
        Args:
            object_center_x: X coordinate of object center in pixels
            object_center_y: Y coordinate of object center in pixels
            frame_width: Width of camera frame in pixels
            frame_height: Height of camera frame in pixels
            
        Returns:
            True if movement was executed, False if within dead zone
        """
        if not self.enabled:
            return False
        
        # Calculate offset from center
        center_x = frame_width // 2
        center_y = frame_height // 2
        
        offset_x = object_center_x - center_x
        offset_y = object_center_y - center_y
        
        # Check dead zone
        if abs(offset_x) <= self.calibration.dead_zone_pixels and \
           abs(offset_y) <= self.calibration.dead_zone_pixels:
            return False  # Object already centered
        
        # Convert pixel offset to steps
        # Camera moves in same direction as offset to center the clicked position
        steps_x = int(offset_x * self.calibration.x_steps_per_pixel)
        steps_y = int(offset_y * self.calibration.y_steps_per_pixel)
        
        # Execute movement in a thread to not block
        with self.movement_lock:
            self.moving = True
            try:
                # Move both axes
                if steps_x != 0:
                    self.step('x', steps_x)
                if steps_y != 0:
                    self.step('y', steps_y)
            finally:
                self.moving = False
        
        return True
    
    def home(self):
        """
        Home the camera to center position.
        
        Moves back to (0, 0) position.
        """
        if not self.enabled:
            logger.warning("Cannot home - motors not enabled")
            return
        
        logger.info(f"Homing camera from position "
                   f"({self.calibration.x_position}, {self.calibration.y_position})")
        
        with self.movement_lock:
            # Move back to zero position
            self.step('x', -self.calibration.x_position)
            self.step('y', -self.calibration.y_position)
        
        logger.info("Camera homed to center position")
        self.enable()
    
    def set_home_position(self):
        """
        Set the current position as the new home position (0, 0).
        Useful for manual calibration adjustments.
        Requires calibration to have been performed.
        """
        if not self.calibration.is_calibrated:
            logger.error("Cannot set home position - calibration required")
            return False
        
        logger.info(f"Setting current position "
                   f"({self.calibration.x_position}, {self.calibration.y_position}) as home")
        self.calibration.x_position = 0
        self.calibration.y_position = 0
        logger.info("Home position updated")
        
        # Save updated calibration
        self.save_calibration()
        return True
    
    def manual_move(self, axis: str, steps: int):
        """
        Manually move camera by specified steps.
        
        Args:
            axis: 'x' or 'y'
            steps: Number of steps (signed for direction)
        """
        if not self.enabled:
            logger.warning("Cannot move - motors not enabled")
            return False
        
        with self.movement_lock:
            self.moving = True
            try:
                self.step(axis, steps)
                return True
            finally:
                self.moving = False
    
    def auto_calibrate(self, callback=None) -> dict:
        """
        Automatically calibrate camera by finding limits and centering.
        
        This will:
        1. Find limit switches or max range in each direction for both axes
        2. Calculate the center position
        3. Move to center and set as home (0, 0)
        4. Update max_steps limits based on discovered range
        
        Args:
            callback: Optional function(status, message) to report progress
        
        Returns:
            dict with calibration results
        """
        if not self.enabled:
            return {'success': False, 'message': 'Motors not enabled'}
        
        def report(status, message):
            logger.info(f"Auto-calibration: {message}")
            if callback:
                callback(status, message)
        
        report('info', 'Starting automatic calibration...')
        
        with self.movement_lock:
            self.moving = True
            try:
                results = {}
                
                # Calibrate X axis
                report('info', 'Calibrating X axis - finding limits')
                x_range = self._find_axis_limits('x', report)
                results['x_range'] = x_range
                
                # Calibrate Y axis
                report('info', 'Calibrating Y axis - finding limits')
                y_range = self._find_axis_limits('y', report)
                results['y_range'] = y_range
                
                # Calculate center and move there
                x_center = (x_range['min'] + x_range['max']) // 2
                y_center = (y_range['min'] + y_range['max']) // 2
                
                report('info', f'Moving to center position: X={x_center}, Y={y_center}')
                
                # Move to center (bypass limits since we're still calibrating) using default step delay
                self.step('x', x_center - self.calibration.x_position, bypass_limits=True)
                self.step('y', y_center - self.calibration.y_position, bypass_limits=True)
                
                # Set this as home (0, 0)
                self.calibration.x_position = 0
                self.calibration.y_position = 0
                
                # Update max limits based on discovered range
                x_half_range = (x_range['max'] - x_range['min']) // 2
                y_half_range = (y_range['max'] - y_range['min']) // 2
                
                self.calibration.x_max_steps = x_half_range
                self.calibration.y_max_steps = y_half_range
                
                # Mark as calibrated and save timestamp
                from datetime import datetime
                self.calibration.is_calibrated = True
                self.calibration.calibration_timestamp = datetime.now().isoformat()
                
                # Save calibration to file
                self.save_calibration()
                self.enable()
                
                report('success', f'Calibration complete! Range: X=±{x_half_range}, Y=±{y_half_range}')
                
                return {
                    'success': True,
                    'x_range': x_half_range,
                    'y_range': y_half_range,
                    'message': 'Calibration successful'
                }
                
            except Exception as e:
                error_msg = f'Calibration failed: {str(e)}'
                report('error', error_msg)
                return {'success': False, 'message': error_msg}
            
            finally:
                self.moving = False
    
    def _find_axis_limits(self, axis: str, report) -> dict:
        """
        Find the limits of movement for an axis.
        
        Returns:
            dict with 'min' and 'max' step positions
        """
        max_search_steps = 5000  # Maximum steps to search in each direction
        search_speed = 0.001  # Step delay during calibration
        
        # Save current position
        if axis == 'x':
            start_pos = self.calibration.x_position
        else:
            start_pos = self.calibration.y_position
        
        # Find positive limit
        report('info', f'{axis.upper()} axis: searching positive direction')
        steps_moved = 0
        
        for i in range(max_search_steps):
            if self.has_limit_switches and self.check_limit_switch(axis, 1):
                report('info', f'{axis.upper()} axis: positive limit switch found')
                break
            
            self.step(axis, 1, delay=search_speed, bypass_limits=True)
            steps_moved += 1
            
            # Report progress every 500 steps
            if steps_moved % 500 == 0:
                report('info', f'{axis.upper()} axis: {steps_moved} steps positive')
        else:
            report('info', f'{axis.upper()} axis: max search range reached ({max_search_steps} steps)')
        
        positive_limit = steps_moved
        
        # Return to start
        report('info', f'{axis.upper()} axis: returning to start position')
        self.step(axis, -steps_moved, delay=search_speed, bypass_limits=True)
        
        # Find negative limit
        report('info', f'{axis.upper()} axis: searching negative direction')
        steps_moved = 0
        
        for i in range(max_search_steps):
            if self.has_limit_switches and self.check_limit_switch(axis, -1):
                report('info', f'{axis.upper()} axis: negative limit switch found')
                break
            
            self.step(axis, -1, delay=search_speed, bypass_limits=True)
            steps_moved += 1
            
            # Report progress every 500 steps
            if steps_moved % 500 == 0:
                report('info', f'{axis.upper()} axis: {steps_moved} steps negative')
        else:
            report('info', f'{axis.upper()} axis: max search range reached ({max_search_steps} steps)')
        
        negative_limit = -steps_moved
        
        report('info', f'{axis.upper()} axis range: {negative_limit} to {positive_limit} steps')
        
        return {
            'min': negative_limit,
            'max': positive_limit
        }
    
    def calibrate_steps_per_pixel(self, axis: str, pixels_moved: float, 
                                   steps_executed: int):
        """
        Calibrate the steps-per-pixel ratio for an axis.
        
        Args:
            axis: 'x' or 'y'
            pixels_moved: How many pixels the object moved in frame
            steps_executed: How many steps were executed
        """
        if pixels_moved == 0:
            logger.warning("Cannot calibrate with zero pixel movement")
            return
        
        steps_per_pixel = abs(steps_executed / pixels_moved)
        
        if axis == 'x':
            self.calibration.x_steps_per_pixel = steps_per_pixel
            logger.info(f"X axis calibrated: {steps_per_pixel:.3f} steps/pixel")
        else:
            self.calibration.y_steps_per_pixel = steps_per_pixel
            logger.info(f"Y axis calibrated: {steps_per_pixel:.3f} steps/pixel")
    
    def save_calibration(self):
        """Save calibration data to file"""
        try:
            # Convert calibration to dict
            cal_data = asdict(self.calibration)
            
            # Save to JSON file
            with open(self.calibration_file, 'w') as f:
                json.dump(cal_data, f, indent=2)
            
            logger.info(f"Calibration saved to {self.calibration_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save calibration: {e}")
            return False
    
    def load_calibration(self):
        """Load calibration data from file if it exists"""
        try:
            if os.path.exists(self.calibration_file):
                with open(self.calibration_file, 'r') as f:
                    cal_data = json.load(f)
                
                # Update calibration object
                self.calibration.x_steps_per_pixel = cal_data.get('x_steps_per_pixel', 0.1)
                self.calibration.y_steps_per_pixel = cal_data.get('y_steps_per_pixel', 0.1)
                self.calibration.x_position = cal_data.get('x_position', 0)
                self.calibration.y_position = cal_data.get('y_position', 0)
                self.calibration.x_max_steps = cal_data.get('x_max_steps', 2000)
                self.calibration.y_max_steps = cal_data.get('y_max_steps', 2000)
                self.calibration.step_delay = cal_data.get('step_delay', 0.001)
                self.calibration.acceleration_steps = cal_data.get('acceleration_steps', 50)
                self.calibration.dead_zone_pixels = cal_data.get('dead_zone_pixels', 20)
                self.calibration.is_calibrated = cal_data.get('is_calibrated', False)
                self.calibration.calibration_timestamp = cal_data.get('calibration_timestamp')
                
                logger.info(f"Calibration loaded from {self.calibration_file}")
                if self.calibration.is_calibrated:
                    logger.info(f"System is calibrated (timestamp: {self.calibration.calibration_timestamp})")
                else:
                    logger.warning("Calibration file exists but system not marked as calibrated")
                return True
            else:
                logger.info("No calibration file found - calibration required")
                return False
        except Exception as e:
            logger.error(f"Failed to load calibration: {e}")
            return False
    
    def is_calibrated(self) -> bool:
        """Check if system has been calibrated"""
        return self.calibration.is_calibrated
    
    def get_status(self) -> dict:
        """Get current controller status"""
        return {
            'enabled': self.enabled,
            'moving': self.moving,
            'position': {
                'x': self.calibration.x_position,
                'y': self.calibration.y_position
            },
            'calibration': {
                'x_steps_per_pixel': self.calibration.x_steps_per_pixel,
                'y_steps_per_pixel': self.calibration.y_steps_per_pixel,
                'dead_zone_pixels': self.calibration.dead_zone_pixels,
                'is_calibrated': self.calibration.is_calibrated,
                'calibration_timestamp': self.calibration.calibration_timestamp
            },
            'limits': {
                'x_max_steps': self.calibration.x_max_steps,
                'y_max_steps': self.calibration.y_max_steps
            }
        }

    def status(self) -> dict:
        return {
            'type': 'tracker',
            'enabled': self.enabled,
            'moving': self.moving,
            'position': {
                'x': self.calibration.x_position,
                'y': self.calibration.y_position,
            },
            'microstep': getattr(self, 'microsteps', None),
            'calibration': {
                'x_steps_per_pixel': self.calibration.x_steps_per_pixel,
                'y_steps_per_pixel': self.calibration.y_steps_per_pixel,
                'dead_zone_pixels': self.calibration.dead_zone_pixels,
                'is_calibrated': self.calibration.is_calibrated,
                'timestamp': self.calibration.calibration_timestamp,
            },
            'limits': {
                'has_switches': getattr(self, 'has_limit_switches', False),
                'pins': {
                    'x_cw': getattr(self, 'x_cw_limit', None) if getattr(self, 'has_limit_switches', False) else None,
                    'x_ccw': getattr(self, 'x_ccw_limit', None) if getattr(self, 'has_limit_switches', False) else None,
                    'y_cw': getattr(self, 'y_cw_limit', None) if getattr(self, 'has_limit_switches', False) else None,
                    'y_ccw': getattr(self, 'y_ccw_limit', None) if getattr(self, 'has_limit_switches', False) else None,
                },
                'max_steps': {
                    'x': self.calibration.x_max_steps,
                    'y': self.calibration.y_max_steps,
                },
            },
            'error': None,
        }
    
    def cleanup(self):
        """Cleanup resources"""
        self.disable()
        try:
            if getattr(self, 'axis_x', None):
                self.axis_x.cleanup()
            if getattr(self, 'axis_y', None):
                self.axis_y.cleanup()
        except Exception:
            pass
        logger.info("StepperController cleanup complete")
