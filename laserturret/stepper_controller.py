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
from typing import Tuple, Optional, Dict
from dataclasses import dataclass, asdict
from laserturret.motion.constants import MICROSTEP_CONFIG, CLOCKWISE, COUNTER_CLOCKWISE

try:
    # Optional UART driver for TMC2209 configuration
    from laserturret.tmc2209_uart import (
        open_serial,
        TMC2209,
        configure_defaults,
        pack_IHOLD_IRUN,
        REG,
    )
except Exception:  # ImportError or pyserial missing
    open_serial = None
    TMC2209 = None  # type: ignore
    configure_defaults = None  # type: ignore
    REG = {}
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
        # Enable polarity: True => HIGH enables, LOW disables; False => LOW enables, HIGH disables
        try:
            self.enable_active_high: bool = bool(self.config.get_enable_active_high())
        except Exception:
            self.enable_active_high = True
        # UART configuration
        self.use_uart: bool = bool(self.config.get_use_uart())
        self.uart_port: Optional[str] = self.config.get_uart_port() if self.use_uart else None
        self.uart_baud: Optional[int] = self.config.get_uart_baud() if self.use_uart else None
        self._serial = None
        self._tmc_x = None
        self._tmc_y = None
        
        # Motor pins
        self.x_step_pin = config_manager.get_motor_pin('x_step_pin')
        self.x_dir_pin = config_manager.get_motor_pin('x_dir_pin')
        self.x_enable_pin = config_manager.get_motor_pin('x_enable_pin')
        
        self.y_step_pin = config_manager.get_motor_pin('y_step_pin')
        self.y_dir_pin = config_manager.get_motor_pin('y_dir_pin')
        self.y_enable_pin = config_manager.get_motor_pin('y_enable_pin')
        
        # Microstepping pins (may be None when UART is used)
        try:
            self.ms1_pin = config_manager.get_motor_pin('ms1_pin') if not self.use_uart else None
            self.ms2_pin = config_manager.get_motor_pin('ms2_pin') if not self.use_uart else None
            self.ms3_pin = config_manager.get_motor_pin('ms3_pin') if not self.use_uart else None
        except Exception:
            self.ms1_pin = None
            self.ms2_pin = None
            self.ms3_pin = None
        
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
        
        # Axis drivers - IMPORTANT: Pass the shared GPIO backend instance
        # so all components control the same physical pins
        try:
            x_cfg = self.config.get_motor_config('x')
            y_cfg = self.config.get_motor_config('y')
            print(f"Creating axis_x with gpio_backend={self.gpio}, enable_pin={x_cfg['enable_pin']}", flush=True)
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
                start_thread=True,
                deadzone=self.config.get_control_deadzone(),
                gpio_backend=self.gpio,  # Share the same GPIO backend!
                enable_active_high=self.enable_active_high,
            )
            print(f"Creating axis_y with gpio_backend={self.gpio}, enable_pin={y_cfg['enable_pin']}", flush=True)
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
                start_thread=True,
                deadzone=self.config.get_control_deadzone(),
                gpio_backend=self.gpio,  # Share the same GPIO backend!
                enable_active_high=self.enable_active_high,
            )
            print(f"Axes created: axis_x.gpio={id(self.axis_x.gpio)}, axis_y.gpio={id(self.axis_y.gpio)}, controller.gpio={id(self.gpio)}", flush=True)
        except Exception as _:
            self.axis_x = None
            self.axis_y = None
        
        # State
        self.enabled = False
        self.moving = False
        self.movement_lock = threading.Lock()
        
        # Initialize GPIO and optionally TMC UART
        self._setup_gpio()
        if self.use_uart:
            self._init_tmc_uart()
        
        # PID defaults (can be overridden by calibration file)
        self.kp = 0.8
        self.ki = 0.0
        self.kd = 0.2
        # Load calibration if available (may override PID)
        self.load_calibration()
        self._ix = 0.0
        self._iy = 0.0
        self._last_pid_time = None
        self._ex_n_last = 0.0
        self._ey_n_last = 0.0
        self._cmd_x_last = 0.0
        self._cmd_y_last = 0.0
        
        # Idle timeout watchdog
        self.idle_timeout = self.config.get_control_idle_timeout()
        self._idle_stop = threading.Event()
        self._active_moves = 0
        self._last_activity = time.time()
        self._idle_thread = threading.Thread(target=self._idle_watchdog, name="idle_watchdog", daemon=True)
        self._idle_thread.start()

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
        
        # Only set up MS pins when not using UART-based microstepping
        if not self.use_uart:
            if self.ms1_pin is not None:
                self.gpio.setup(self.ms1_pin, PinMode.OUTPUT)
            if self.ms2_pin is not None:
                self.gpio.setup(self.ms2_pin, PinMode.OUTPUT)
            if self.ms3_pin is not None:
                self.gpio.setup(self.ms3_pin, PinMode.OUTPUT)
        
        # Setup limit switches if available
        if self.has_limit_switches:
            self.gpio.setup(self.x_cw_limit, PinMode.INPUT, PullMode.UP)
            self.gpio.setup(self.x_ccw_limit, PinMode.INPUT, PullMode.UP)
            self.gpio.setup(self.y_cw_limit, PinMode.INPUT, PullMode.UP)
            self.gpio.setup(self.y_ccw_limit, PinMode.INPUT, PullMode.UP)
        
        # Set microstepping via pins when not using UART
        microsteps = self.config.get_motor_microsteps()
        self.microsteps = microsteps
        if not self.use_uart:
            self._set_microstepping(microsteps)
        
        # Disable motors initially
        disabled_level = 0 if self.enable_active_high else 1
        self.gpio.output(self.x_enable_pin, disabled_level)
        self.gpio.output(self.y_enable_pin, disabled_level)
        logger.info(f"Startup: set enable pins to disabled level={disabled_level} (active_high={self.enable_active_high})")
        
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

    def _init_tmc_uart(self) -> None:
        """Initialize TMC2209 drivers over UART if enabled in config."""
        if not self.use_uart:
            return
        if TMC2209 is None or open_serial is None:
            logger.error("TMC2209 UART requested but pyserial/driver not available")
            return
        try:
            # Open shared UART
            self._serial = open_serial(self.uart_port, int(self.uart_baud or 115200), timeout=0.05)
            x_addr = int(self.config.get_uart_address('x'))
            y_addr = int(self.config.get_uart_address('y'))
            self._tmc_x = TMC2209(self._serial, x_addr)
            self._tmc_y = TMC2209(self._serial, y_addr)
            # Apply defaults based on configured microsteps
            if configure_defaults is not None:
                configure_defaults(self._tmc_x, microsteps=self.microsteps)
                configure_defaults(self._tmc_y, microsteps=self.microsteps)
            # Touch IFCNT to verify comms
            if REG:
                _ = self._tmc_x.read_reg(REG.get('IFCNT', 0x02))
                _ = self._tmc_y.read_reg(REG.get('IFCNT', 0x02))
            logger.info("TMC2209 UART initialized on %s @ %s bps", self.uart_port, self.uart_baud)
        except Exception as e:
            logger.error(f"Failed to initialize TMC2209 over UART: {e}")

    def get_tmc_registers(self) -> Optional[Dict[str, Dict[str, int]]]:
        """Return a snapshot of common TMC2209 registers for X/Y if UART is active."""
        if not self.use_uart or self._tmc_x is None or self._tmc_y is None or not REG:
            return None
        regs = ['GCONF', 'GSTAT', 'IFCNT', 'IHOLD_IRUN', 'TPOWERDOWN', 'TPWMTHRS', 'TCOOLTHRS', 'CHOPCONF', 'DRV_STATUS', 'PWMCONF']
        out: Dict[str, Dict[str, int]] = {'x': {}, 'y': {}}
        for name in regs:
            addr = REG.get(name)
            if addr is None:
                continue
            try:
                out['x'][name] = int(self._tmc_x.read_reg(addr))
            except Exception:
                out['x'][name] = -1
            try:
                out['y'][name] = int(self._tmc_y.read_reg(addr))
            except Exception:
                out['y'][name] = -1
        return out

    def tmc_apply_defaults(self, microsteps: Optional[int] = None) -> bool:
        """Re-apply default TMC2209 settings over UART for both drivers."""
        if not self.use_uart or self._tmc_x is None or self._tmc_y is None or configure_defaults is None:
            return False
        try:
            m = int(microsteps) if microsteps is not None else int(self.microsteps)
            configure_defaults(self._tmc_x, microsteps=m)
            configure_defaults(self._tmc_y, microsteps=m)
            return True
        except Exception as e:
            logger.error(f"Failed to apply TMC2209 defaults: {e}")
            return False

    def _get_drv_by_axis(self, axis: str):
        axis = (axis or '').lower()
        if axis == 'x':
            return self._tmc_x
        if axis == 'y':
            return self._tmc_y
        return None

    def tmc_set_ihold_irun(self, axis: str, ihold: int, irun: int, iholddelay: int) -> bool:
        """Set IHOLD_IRUN fields for one axis over UART."""
        if not self.use_uart or REG is None:
            return False
        drv = self._get_drv_by_axis(axis)
        if drv is None:
            return False
        # clamp to field widths
        ihold = max(0, min(31, int(ihold)))
        irun = max(0, min(31, int(irun)))
        iholddelay = max(0, min(15, int(iholddelay)))
        try:
            val = pack_IHOLD_IRUN(IHOLD=ihold, IRUN=irun, IHOLDDELAY=iholddelay)
            drv.write_reg(REG['IHOLD_IRUN'], val)
            # bump IFCNT
            _ = drv.read_reg(REG.get('IFCNT', 0x02))
            return True
        except Exception as e:
            logger.error(f"IHOLD_IRUN write failed on axis {axis}: {e}")
            return False

    def tmc_set_tpowerdown(self, axis: str, tpowerdown: int) -> bool:
        """Set TPOWERDOWN for one axis over UART."""
        if not self.use_uart or REG is None:
            return False
        drv = self._get_drv_by_axis(axis)
        if drv is None:
            return False
        tpd = max(0, min(0xFF, int(tpowerdown)))
        try:
            drv.write_reg(REG['TPOWERDOWN'], tpd)
            _ = drv.read_reg(REG.get('IFCNT', 0x02))
            return True
        except Exception as e:
            logger.error(f"TPOWERDOWN write failed on axis {axis}: {e}")
            return False
    
    def enable(self):
        """Enable stepper motors (drives enable pins to the configured active level)."""
        level = 1 if self.enable_active_high else 0
        print(f"enable(): setting enable pins to {level} (active_high={self.enable_active_high}) x={self.x_enable_pin}, y={self.y_enable_pin}", flush=True)
        self.gpio.output(self.x_enable_pin, level)
        self.gpio.output(self.y_enable_pin, level)
        # Verify the pins were actually set
        try:
            x_state = self.gpio.input(self.x_enable_pin)
            y_state = self.gpio.input(self.y_enable_pin)
            expected = level
            logger.info(f"Enable pins read back: x_enable={x_state}, y_enable={y_state} (expected={expected} for enabled)")
        except Exception:
            pass
        self.enabled = True
        try:
            if getattr(self, 'axis_x', None):
                self.axis_x.set_suspended(False)
            if getattr(self, 'axis_y', None):
                self.axis_y.set_suspended(False)
        except Exception:
            pass
        logger.info("Stepper motors enabled")
    
    def disable(self, invalidate_calibration: bool = True):
        """
        Disable stepper motors (release torque). Drives enable pins to the configured inactive level.
        
        Args:
            invalidate_calibration: If True, mark calibration as invalid.
                                   Set to False for temporary disable (e.g., idle timeout).
        """
        level = 0 if self.enable_active_high else 1
        print(f"disable(): setting enable pins to {level} (active_high={self.enable_active_high}) x={self.x_enable_pin}, y={self.y_enable_pin}", flush=True)
        self.gpio.output(self.x_enable_pin, level)
        self.gpio.output(self.y_enable_pin, level)
        print(f"GPIO outputs set to {level}", flush=True)
        # Verify the pins were actually set
        try:
            x_state = self.gpio.input(self.x_enable_pin)
            y_state = self.gpio.input(self.y_enable_pin)
            expected = level
            print(f"Enable pins read back: x_enable={x_state}, y_enable={y_state} (expected={expected} for disabled)", flush=True)
        except Exception as e:
            print(f"Failed to read back pin states: {e}", flush=True)
        self.enabled = False
        print(f"Controller enabled flag set to {self.enabled}, suspending axes", flush=True)
        try:
            if getattr(self, 'axis_x', None):
                self.axis_x.set_suspended(True)
                print(f"axis_x suspended={self.axis_x.suspended}, enabled={self.axis_x.enabled}", flush=True)
            if getattr(self, 'axis_y', None):
                self.axis_y.set_suspended(True)
                print(f"axis_y suspended={self.axis_y.suspended}, enabled={self.axis_y.enabled}", flush=True)
        except Exception as e:
            print(f"Error suspending axes: {e}", flush=True)
        if invalidate_calibration and self.calibration.is_calibrated:
            self.calibration.is_calibrated = False
            self.calibration.calibration_timestamp = None
            self.save_calibration()
            print("Stepper motors disabled (calibration invalidated)", flush=True)
        else:
            print("Stepper motors disabled (calibration preserved)", flush=True)
    
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
        self._active_moves += 1
        self._mark_activity()
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
                self._mark_activity()
        const_size = total - 2 * accel
        if const_size > 0:
            try:
                moved = motor.step(const_size, delay)
            except (MotorError, LimitSwitchError):
                moved = 0
            moved_total += moved
            self._mark_activity()
        if accel > 0:
            for size, cur in zip(reversed(seg_sizes), reversed(seg_delays)):
                try:
                    moved = motor.step(size, cur)
                except (MotorError, LimitSwitchError):
                    break
                moved_total += moved
                self._mark_activity()
        if axis == 'x':
            self.calibration.x_position += direction_sign * moved_total
        else:
            self.calibration.y_position += direction_sign * moved_total
        self._active_moves -= 1
        self._mark_activity()
        # Don't force enable here - respect user's enable/disable state
        logger.debug(f"Moved {moved_total} steps on {axis} axis, position: ({self.calibration.x_position}, {self.calibration.y_position})")
    
    def update_tracking_with_pid(self, target_x: int, target_y: int, frame_width: int, frame_height: int) -> None:
        if not self.enabled:
            return
        self._mark_activity()
        now = time.time()
        if getattr(self, '_last_pid_time', None) is None:
            dt = 0.0
        else:
            dt = max(0.0, now - self._last_pid_time)
        self._last_pid_time = now
        cx = frame_width // 2
        cy = frame_height // 2
        ex = float(target_x - cx)
        ey = float(target_y - cy)
        # Normalize and clamp error to [-1, 1] to avoid runaway far from center
        ex_n = ex / max(1.0, (frame_width / 2.0))
        ey_n = ey / max(1.0, (frame_height / 2.0))
        ex_n = max(-1.0, min(1.0, ex_n))
        ey_n = max(-1.0, min(1.0, ey_n))
        self._ix += ex_n * dt
        self._iy += ey_n * dt
        self._ix = max(-10.0, min(10.0, self._ix))
        self._iy = max(-10.0, min(10.0, self._iy))
        # Derivative with cap to reduce spikes on large jumps
        dex_n = ((ex_n - self._ex_n_last) / dt) if dt > 0 else 0.0
        dey_n = ((ey_n - self._ey_n_last) / dt) if dt > 0 else 0.0
        dmax = 5.0
        dex_n = max(-dmax, min(dmax, dex_n))
        dey_n = max(-dmax, min(dmax, dey_n))
        # Reduce gains when far from center to avoid overshoot
        k_scale_x = 0.6 + 0.4 * (1.0 - min(1.0, abs(ex_n)))
        k_scale_y = 0.6 + 0.4 * (1.0 - min(1.0, abs(ey_n)))
        kp_x = self.kp * k_scale_x
        kp_y = self.kp * k_scale_y
        kd_x = self.kd * k_scale_x
        kd_y = self.kd * k_scale_y
        ux = (kp_x * ex_n) + (self.ki * self._ix) + (kd_x * dex_n)
        uy = (kp_y * ey_n) + (self.ki * self._iy) + (kd_y * dey_n)
        # Map to command space and clamp max velocity
        cmd_x = ux * 120.0
        cmd_y = -uy * 120.0
        cmd_x = max(-100.0, min(100.0, cmd_x))
        cmd_y = max(-100.0, min(100.0, cmd_y))
        # Output slew rate limiting
        if dt > 0:
            max_delta = 300.0 * dt
            cmd_x = max(self._cmd_x_last - max_delta, min(self._cmd_x_last + max_delta, cmd_x))
            cmd_y = max(self._cmd_y_last - max_delta, min(self._cmd_y_last + max_delta, cmd_y))
        min_cmd = 0.0
        try:
            if getattr(self, 'axis_x', None):
                min_cmd = max(min_cmd, float(getattr(self.axis_x, 'deadzone', 0)))
            if getattr(self, 'axis_y', None):
                min_cmd = max(min_cmd, float(getattr(self.axis_y, 'deadzone', 0)))
        except Exception:
            pass
        min_cmd = min_cmd + 1.5 if min_cmd > 0 else 0.0
        if abs(cmd_x) > 0 and abs(cmd_x) < min_cmd:
            cmd_x = min_cmd if cmd_x >= 0 else -min_cmd
        if abs(cmd_y) > 0 and abs(cmd_y) < min_cmd:
            cmd_y = min_cmd if cmd_y >= 0 else -min_cmd
        try:
            if getattr(self, 'axis_x', None):
                self.axis_x.process_command(cmd_x)
            if getattr(self, 'axis_y', None):
                self.axis_y.process_command(cmd_y)
        finally:
            # Save last values for next iteration
            self._ex_n_last = ex_n
            self._ey_n_last = ey_n
            self._cmd_x_last = cmd_x
            self._cmd_y_last = cmd_y
            self._mark_activity()
    
    def stop_motion(self) -> None:
        """Immediately zero axis commands and reset PID state without disabling motors."""
        if not self.enabled:
            return
        try:
            if getattr(self, 'axis_x', None):
                self.axis_x.process_command(0.0)
            if getattr(self, 'axis_y', None):
                self.axis_y.process_command(0.0)
        except Exception:
            pass
        # Reset PID state to avoid derivative spikes on the next target acquisition
        self._ix = 0.0
        self._iy = 0.0
        self._ex_n_last = 0.0
        self._ey_n_last = 0.0
        self._cmd_x_last = 0.0
        self._cmd_y_last = 0.0
        self._last_pid_time = None
        self._mark_activity()
    
    def recenter_slowly(self, threshold_steps: int = 10, base_speed: float = 20.0, max_speed: float = 60.0) -> None:
        """Nudge camera toward home (0,0) with gentle velocity commands.
        Uses live axis state positions when available; falls back to calibration positions.
        """
        if not self.enabled:
            return
        try:
            cur_x = 0
            cur_y = 0
            try:
                cur_x = int(getattr(self.axis_x.state, 'position', self.calibration.x_position)) if getattr(self, 'axis_x', None) else self.calibration.x_position
            except Exception:
                cur_x = self.calibration.x_position
            try:
                cur_y = int(getattr(self.axis_y.state, 'position', self.calibration.y_position)) if getattr(self, 'axis_y', None) else self.calibration.y_position
            except Exception:
                cur_y = self.calibration.y_position
            # Determine command directions toward zero
            cmd_x = 0.0
            cmd_y = 0.0
            if abs(cur_x) > threshold_steps:
                sign_x = -1.0 if cur_x > 0 else 1.0
                # Scale speed by distance, capped
                mag_x = min(max_speed, base_speed + (abs(cur_x) * 0.01))
                cmd_x = sign_x * mag_x
            if abs(cur_y) > threshold_steps:
                sign_y = -1.0 if cur_y > 0 else 1.0
                mag_y = min(max_speed, base_speed + (abs(cur_y) * 0.01))
                cmd_y = sign_y * mag_y
            if getattr(self, 'axis_x', None):
                self.axis_x.process_command(cmd_x)
            if getattr(self, 'axis_y', None):
                self.axis_y.process_command(cmd_y)
        except Exception:
            pass
        finally:
            self._mark_activity()
    
    def move_linear(self, steps_x: int, steps_y: int, delay: Optional[float] = None, bypass_limits: bool = False) -> None:
        """
        Move both axes in a coordinated, straight-line path using a DDA/Bresenham approach.
        
        Args:
            steps_x: Signed step delta for X axis
            steps_y: Signed step delta for Y axis
            delay: Optional base delay between steps (uses calibration default if None)
            bypass_limits: If True, bypass software limits (e.g., during calibration)
        """
        if not self.enabled:
            logger.warning("Cannot move - motors not enabled")
            return
        
        if steps_x == 0 and steps_y == 0:
            return
        
        # Constrain to software limits while preserving the movement ratio
        if not bypass_limits:
            req_x, req_y = steps_x, steps_y
            lim_x = self.check_software_limits('x', req_x)
            lim_y = self.check_software_limits('y', req_y)
            rx = (abs(lim_x) / abs(req_x)) if req_x != 0 else 1.0
            ry = (abs(lim_y) / abs(req_y)) if req_y != 0 else 1.0
            r = min(rx, ry)
            # Scale both to maintain slope, then clamp again to be safe
            steps_x = int(round(req_x * r)) if req_x != 0 else 0
            steps_y = int(round(req_y * r)) if req_y != 0 else 0
            steps_x = self.check_software_limits('x', steps_x)
            steps_y = self.check_software_limits('y', steps_y)
            if steps_x == 0 and steps_y == 0:
                logger.debug("Movement constrained entirely by software limits")
                return
        
        # If movement is purely along a single axis, defer to axis step with accel
        if steps_y == 0:
            self.step('x', steps_x, delay=delay, bypass_limits=bypass_limits)
            return
        if steps_x == 0:
            self.step('y', steps_y, delay=delay, bypass_limits=bypass_limits)
            return
        
        # Prepare motors and directions
        motor_x = self.axis_x
        motor_y = self.axis_y
        if motor_x is None or motor_y is None:
            logger.error("Axis drivers not initialized")
            return
        
        dx_sign = 1 if steps_x > 0 else -1
        dy_sign = 1 if steps_y > 0 else -1
        try:
            x_dir_const = CLOCKWISE if dx_sign > 0 else COUNTER_CLOCKWISE
            # Y direction is inverted relative to logical positive
            y_dir_const = COUNTER_CLOCKWISE if dy_sign > 0 else CLOCKWISE
            motor_x.set_direction(x_dir_const)
            motor_y.set_direction(y_dir_const)
        except LimitSwitchError:
            return
        self._active_moves += 1
        self._mark_activity()
        
        # Determine major/minor axes for DDA
        ax = abs(steps_x)
        ay = abs(steps_y)
        major_is_x = ax >= ay
        major = ax if major_is_x else ay
        minor = ay if major_is_x else ax
        
        if delay is None:
            delay = self.calibration.step_delay
        
        # Simple accel/decel around the major axis count
        accel = min(self.calibration.acceleration_steps, max(1, major // 2)) if self.calibration.acceleration_steps > 0 else 0
        
        def compute_delay(i: int) -> float:
            # i in [0, major)
            if accel <= 0:
                return delay
            if i < accel:
                ratio = (i + 0.5) / accel
                return delay + (delay * 2 * (1 - ratio))
            if i >= major - accel:
                j = (major - i - 0.5)
                ratio = j / accel
                return delay + (delay * 2 * (1 - ratio))
            return delay
        
        error_acc = 0
        moved_x = 0
        moved_y = 0
        
        # Don't force enable - motors should already be enabled if needed
        
        for i in range(major):
            cur = compute_delay(i)
            try:
                if major_is_x:
                    moved = motor_x.step(1, cur)
                    if moved <= 0:
                        break
                    moved_x += moved
                    self.calibration.x_position += dx_sign * moved
                else:
                    moved = motor_y.step(1, cur)
                    if moved <= 0:
                        break
                    moved_y += moved
                    self.calibration.y_position += dy_sign * moved
            except (MotorError, LimitSwitchError):
                break
            self._mark_activity()
            
            error_acc += minor
            if error_acc >= major:
                error_acc -= major
                try:
                    if major_is_x:
                        moved = motor_y.step(1, cur)
                        if moved > 0:
                            moved_y += moved
                            self.calibration.y_position += dy_sign * moved
                    else:
                        moved = motor_x.step(1, cur)
                        if moved > 0:
                            moved_x += moved
                            self.calibration.x_position += dx_sign * moved
                except (MotorError, LimitSwitchError):
                    break
                self._mark_activity()
        
        logger.debug(
            f"Linear move complete. Requested=({steps_x}, {steps_y}), Moved=({dx_sign * moved_x}, {dy_sign * moved_y}), "
            f"Final pos=({self.calibration.x_position}, {self.calibration.y_position})"
        )
        self._active_moves -= 1
        self._mark_activity()
    
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
                # Coordinated straight-line motion
                self.move_linear(steps_x, steps_y)
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
            # Determine current positions from live axis state if available
            try:
                cur_x = int(getattr(self.axis_x.state, 'position', self.calibration.x_position)) if getattr(self, 'axis_x', None) else self.calibration.x_position
            except Exception:
                cur_x = self.calibration.x_position
            try:
                cur_y = int(getattr(self.axis_y.state, 'position', self.calibration.y_position)) if getattr(self, 'axis_y', None) else self.calibration.y_position
            except Exception:
                cur_y = self.calibration.y_position
            # Move back to zero position
            self.step('x', -cur_x)
            self.step('y', -cur_y)
        
        logger.info("Camera homed to center position")
        # Don't force enable - respect user's enable/disable state
    
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

                # Calculate total travel range discovered during calibration
                x_total_range = x_range['max'] - x_range['min']
                y_total_range = y_range['max'] - y_range['min']

                if x_total_range <= 0 or y_total_range <= 0:
                    raise ValueError('Unable to determine axis travel (invalid range discovered)')

                if x_total_range % 2:
                    report('warning',
                           'X axis travel range is not even - centering will favor the negative side by one step')
                if y_total_range % 2:
                    report('warning',
                           'Y axis travel range is not even - centering will favor the negative side by one step')

                # After _find_axis_limits both axes are resting at the minimum limit (negative range)
                # Move forward by half the discovered range to reach the center point
                x_steps_to_center = x_total_range // 2
                y_steps_to_center = y_total_range // 2

                report('info',
                       f'Moving to center position from negative limits: X=+{x_steps_to_center} steps, '
                       f'Y=+{y_steps_to_center} steps')

                self.step('x', x_steps_to_center, bypass_limits=True)
                self.step('y', y_steps_to_center, bypass_limits=True)
                
                # Set this as home (0, 0)
                self.calibration.x_position = 0
                self.calibration.y_position = 0
                
                # Update max limits based on discovered range
                x_half_range = x_total_range // 2
                y_half_range = y_total_range // 2
                
                self.calibration.x_max_steps = x_half_range
                self.calibration.y_max_steps = y_half_range
                
                # Mark as calibrated and save timestamp
                from datetime import datetime
                self.calibration.is_calibrated = True
                self.calibration.calibration_timestamp = datetime.now().isoformat()
                
                # Save calibration to file
                self.save_calibration()
                # Don't auto-enable after calibration - let user control enable state
                
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
            # Include PID settings
            cal_data['pid'] = {'kp': self.kp, 'ki': self.ki, 'kd': self.kd}
            
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
                # Load PID if present
                try:
                    pid = cal_data.get('pid', None)
                    if pid:
                        self.kp = float(pid.get('kp', self.kp))
                        self.ki = float(pid.get('ki', self.ki))
                        self.kd = float(pid.get('kd', self.kd))
                except Exception:
                    pass
                
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
        # Compute idle remaining seconds (best-effort)
        try:
            idle_remaining = None
            if getattr(self, 'idle_timeout', None):
                last = float(getattr(self, '_last_activity', time.time()))
                idle_remaining = max(0.0, float(self.idle_timeout) - (time.time() - last))
        except Exception:
            idle_remaining = None

        # Read limit switch pressed states (active low)
        limits_pressed = None
        if getattr(self, 'has_limit_switches', False):
            try:
                limits_pressed = {
                    'x_cw': (self.gpio.input(self.x_cw_limit) == 0),
                    'x_ccw': (self.gpio.input(self.x_ccw_limit) == 0),
                    'y_cw': (self.gpio.input(self.y_cw_limit) == 0),
                    'y_ccw': (self.gpio.input(self.y_ccw_limit) == 0),
                }
            except Exception:
                limits_pressed = None

        try:
            pos_x = int(getattr(self.axis_x.state, 'position', self.calibration.x_position)) if getattr(self, 'axis_x', None) else self.calibration.x_position
        except Exception:
            pos_x = self.calibration.x_position
        try:
            pos_y = int(getattr(self.axis_y.state, 'position', self.calibration.y_position)) if getattr(self, 'axis_y', None) else self.calibration.y_position
        except Exception:
            pos_y = self.calibration.y_position
        # Keep calibration positions aligned with live axis positions when available
        try:
            self.calibration.x_position = int(pos_x)
            self.calibration.y_position = int(pos_y)
        except Exception:
            pass

        return {
            'enabled': self.enabled,
            'moving': self.moving,
            'position': {
                'x': pos_x,
                'y': pos_y
            },
            'microsteps': int(getattr(self, 'microsteps', 0) or 0),
            'calibration': {
                'x_steps_per_pixel': self.calibration.x_steps_per_pixel,
                'y_steps_per_pixel': self.calibration.y_steps_per_pixel,
                'dead_zone_pixels': self.calibration.dead_zone_pixels,
                'step_delay': self.calibration.step_delay,
                'is_calibrated': self.calibration.is_calibrated,
                'calibration_timestamp': self.calibration.calibration_timestamp
            },
            'limits': {
                'x_max_steps': self.calibration.x_max_steps,
                'y_max_steps': self.calibration.y_max_steps
            },
            'limit_switches': {
                'available': bool(getattr(self, 'has_limit_switches', False)),
                'pressed': limits_pressed,
            },
            'idle': {
                'timeout_sec': float(self.idle_timeout) if getattr(self, 'idle_timeout', None) else 0.0,
                'seconds_remaining': idle_remaining,
                'active_moves': int(getattr(self, '_active_moves', 0) or 0),
            },
            'motors': {
                'x': {
                    'available': bool(getattr(self, 'axis_x', None) is not None),
                    'enabled': bool(getattr(getattr(self, 'axis_x', None), 'enabled', False)),
                },
                'y': {
                    'available': bool(getattr(self, 'axis_y', None) is not None),
                    'enabled': bool(getattr(getattr(self, 'axis_y', None), 'enabled', False)),
                },
                'uart': {
                    'enabled': bool(getattr(self, 'use_uart', False)),
                    'link_ok': bool(getattr(self, '_tmc_x', None) is not None and getattr(self, '_tmc_y', None) is not None),
                }
            }
        }

    def get_pid(self) -> dict:
        return {
            'kp': float(self.kp),
            'ki': float(self.ki),
            'kd': float(self.kd),
        }

    def set_pid(self, kp: Optional[float] = None, ki: Optional[float] = None, kd: Optional[float] = None) -> dict:
        if kp is not None:
            self.kp = float(kp)
        if ki is not None:
            self.ki = float(ki)
        if kd is not None:
            self.kd = float(kd)
        return self.get_pid()

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
        try:
            if hasattr(self, '_idle_stop'):
                self._idle_stop.set()
            if hasattr(self, '_idle_thread'):
                self._idle_thread.join(timeout=1.0)
        except Exception:
            pass
        self.disable()
        try:
            if getattr(self, 'axis_x', None):
                self.axis_x.cleanup()
            if getattr(self, 'axis_y', None):
                self.axis_y.cleanup()
        except Exception:
            pass
        logger.info("StepperController cleanup complete")

    def _mark_activity(self) -> None:
        self._last_activity = time.time()

    def _idle_watchdog(self) -> None:
        """
        Watchdog thread that automatically disables motors after idle timeout.
        Invalidates calibration to ensure motors are re-calibrated after cooling.
        """
        logger.info(f"Idle watchdog started. Timeout: {self.idle_timeout}s")
        while not self._idle_stop.is_set():
            try:
                if self.enabled and self.idle_timeout and self.idle_timeout > 0:
                    if self._active_moves == 0:
                        idle_time = time.time() - self._last_activity
                        if idle_time >= self.idle_timeout:
                            try:
                                # Disable motors and invalidate calibration
                                logger.info(f"Idle timeout reached ({idle_time:.1f}s >= {self.idle_timeout}s), disabling motors")
                                self.disable(invalidate_calibration=True)
                                logger.info(f"Motors auto-disabled after {self.idle_timeout:.0f}s idle timeout (calibration invalidated)")
                            except Exception as e:
                                logger.error(f"Error in idle watchdog: {e}")
                            time.sleep(0.1)
                            continue
                        elif idle_time > self.idle_timeout * 0.9:
                            # Log when approaching timeout (90%)
                            logger.debug(f"Approaching idle timeout: {idle_time:.1f}s / {self.idle_timeout}s")
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"Exception in idle watchdog loop: {e}")
                time.sleep(0.1)
