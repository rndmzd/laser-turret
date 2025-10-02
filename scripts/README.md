# Scripts Directory Documentation

This directory contains testing utilities, calibration tools, and asset generation scripts for the laser turret project.

## Test Scripts

### `calib_test.py`

Motor calibration test script. Initializes X and Y stepper motors, confirms limit switch assignments, and performs full calibration routine. Simple utility for basic calibration verification.

**Usage:**

```bash
python calib_test.py
```

### `steppercontrol_test.py`

Comprehensive stepper motor test suite (584 lines). The primary testing utility for stepper motor functionality.

**Features:**

- Full test framework with `MotorTester` class
- Interactive test mode with menu-driven interface
- Tests for initialization, movement, calibration, limit switches, direction control
- Support for both X and Y axis testing
- pytest-compatible test fixtures

**Usage:**

```bash
# Run automated tests for Y-axis (default)
python steppercontrol_test.py

# Run automated tests for X-axis
python steppercontrol_test.py --x-axis

# Run automated tests for Y-axis
python steppercontrol_test.py --y-axis

# Interactive test mode
python steppercontrol_test.py --interactive
```

**Interactive Test Menu Options:**

1. Move CW (50 steps)
2. Move CCW (50 steps)
3. Check limit switch states
4. Get motor status
5. Perform calibration
6. Test limit switches (manual trigger)
7. Test limit switches (using motor)
8. Test motor direction
9. Test motor response
10. Test A4988 driver settings
11. Exit

### `test_limit_switches.py`

Dedicated limit switch testing utility (306 lines). Comprehensive tool for verifying all four limit switches.

**Features:**

- Real-time switch state monitoring with color-coded terminal output
- Individual switch testing with user prompts
- Wiring verification and diagnostics
- Multiple test modes: `monitor`, `test`, `check`, `all`
- Mock hardware support for development
- Uses configuration manager for pin assignments

**Usage:**

```bash
# Run all tests (default)
python test_limit_switches.py

# Monitor switches in real-time
python test_limit_switches.py --mode monitor

# Test individual switches
python test_limit_switches.py --mode test

# Check wiring only
python test_limit_switches.py --mode check

# Use mock hardware (no Pi required)
python test_limit_switches.py --mock

# Monitor with duration limit
python test_limit_switches.py --mode monitor --duration 60
```

### `laser_control_test.py`

LaserControl class usage examples and documentation. Not a test script but demonstrates proper usage patterns.

**Demonstrates:**

- Basic on/off control
- PWM power level adjustment (0-100%)
- Pulse functionality with duration and power control
- Context manager usage for automatic cleanup
- Different initialization patterns

### `laser_test.py`

Low-level laser GPIO test. Manually controls GPIO pin 18 to activate laser for 1 second on user prompt.

**Features:**

- Interactive prompt-based control
- Safety warnings about goggles and safe pointing direction
- Uses hardware abstraction layer
- Useful for basic laser functionality verification

**Usage:**

```bash
python laser_test.py
# Press Enter when prompted to activate laser
# Ctrl+C to exit
```

### `test_with_mock_hardware.py`

Hardware abstraction layer demonstration (197 lines). Shows how to develop and test without physical Raspberry Pi hardware.

**Tests Include:**

- Laser control with MockGPIO
- Camera simulation with MockCamera
- GPIO event detection simulation
- Pin state reading and writing

**Usage:**

```bash
python test_with_mock_hardware.py
```

**Benefits:**

- Develop and test code without a Raspberry Pi
- Unit test hardware interactions
- Simulate hardware behavior
- Debug logic without physical setup

## Calibration & Measurement

### `measure_ranges.py`

**⚠️ DEPRECATED** - This script uses an outdated StepperMotor API that no longer exists.

Use `test_limit_switches.py` instead for testing limit switches. This file is kept for historical reference only.

### `i2c_scan.py`

I2C bus scanner utility. Continuously scans for I2C devices and displays their addresses.

**Features:**

- Scans custom I2C pins (IO8/IO9)
- Displays device addresses in hexadecimal format
- Continuous monitoring with 2-second intervals
- Based on Adafruit CircuitPython example

**Usage:**

```bash
python i2c_scan.py
# Ctrl+C to stop scanning
```

**Use Cases:**

- Debugging stepper motor drivers
- Verifying I2C device connections
- Troubleshooting communication issues

## Asset Generation

### `generate_crosshair.py`

Generates crosshair overlay image using PIL/Pillow for the web interface.

**Creates:**

- 400x400px PNG image
- Outer circle with configurable radius
- Center dot
- Split crosshair lines (gap in center)
- Tick marks at cardinal directions
- Customizable size and color (default: green)

**Usage:**

```bash
python generate_crosshair.py
# Outputs: crosshair.png
```

### `convert_svg_to_png.py`

Simple converter using CairoSVG to convert SVG crosshair to PNG format.

**Usage:**

```bash
python convert_svg_to_png.py
# Converts crosshair.svg to crosshair.png (400x400)
```

**Requirements:**

- CairoSVG library

### `crosshair.svg`

SVG source file for crosshair graphic. Green (#00ff00) crosshair design with outer circle, center dot, split lines, and tick marks. Used as source for PNG conversion.

## Quick Reference

### Most Common Testing Workflows

**Basic Hardware Verification:**

```bash
# 1. Test limit switches
python test_limit_switches.py --mode all

# 2. Test laser functionality
python laser_test.py

# 3. Run interactive motor tests
python steppercontrol_test.py --interactive
```

**Development Without Hardware:**

```bash
# Test with mock hardware
python test_with_mock_hardware.py
python test_limit_switches.py --mock
```

**Calibration:**

```bash
# Quick calibration test
python calib_test.py

# Full motor calibration (interactive)
python steppercontrol_test.py --interactive
# Then select option 5 for calibration
```

**I2C Troubleshooting:**

```bash
# Scan for I2C devices
python i2c_scan.py
```

## File Organization

- **Production Test Scripts:** `steppercontrol_test.py`, `test_limit_switches.py`
- **Quick Tests:** `calib_test.py`, `laser_test.py`
- **Development Tools:** `test_with_mock_hardware.py`
- **Diagnostics:** `i2c_scan.py`
- **Deprecated:** `measure_ranges.py`
- **Assets:** `generate_crosshair.py`, `convert_svg_to_png.py`, `crosshair.svg`

## Running Scripts from Project Root

All scripts in this directory can be run from the project root:

```bash
# From project root directory
python scripts/steppercontrol_test.py --interactive
python scripts/test_limit_switches.py --mode all
python scripts/laser_test.py
```

Scripts automatically add the parent directory to Python's module search path using:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
```

### Alternative: Install Package in Development Mode

For a cleaner solution, install the package in editable mode:

```bash
# From project root
pip install -e .
```

This makes the `laserturret` module available system-wide in your virtual environment, allowing you to run scripts from any directory without path modifications.

## Notes

- Most scripts require hardware access or mock mode
- Always use safety precautions when testing laser components
- The hardware abstraction layer enables testing without a Raspberry Pi
- Configuration is managed via `laserturret.conf` for production scripts
- Scripts can be run from the project root or from within the `scripts/` directory
