# Camera Tracking Mode

## Overview

Camera tracking mode is a major feature that enables physical camera movement using stepper motors to track objects. Instead of moving a crosshair on screen (software tracking), the camera itself moves to keep tracked objects centered under a fixed crosshair (hardware tracking).

## Key Concepts

### Tracking Modes

The system supports two mutually exclusive tracking modes:

1. **Crosshair Tracking (Default)**
   - Software-based tracking
   - Moves the crosshair overlay to follow detected objects
   - Camera remains stationary
   - No hardware requirements beyond the camera
   - Lower latency, immediate response

2. **Camera Tracking (New Feature)**
   - Hardware-based tracking  
   - Moves the camera physically using stepper motors
   - Crosshair remains fixed at center of frame
   - Requires stepper motor hardware and proper calibration
   - Physical precision tracking

### How It Works

When camera tracking is enabled:

1. Object detection or motion detection identifies a target
2. System calculates the pixel offset between target center and frame center
3. Offset is converted to stepper motor steps using calibrated steps-per-pixel ratio
4. Stepper motors move the camera to center the target under the fixed crosshair
5. Dead zone prevents jitter from small movements

## Hardware Requirements

### Required Components

- **Stepper Motors**: 2x NEMA 17 or similar (X and Y axes)
- **Stepper Drivers**: 2x A4988 or DRV8825 drivers
- **Power Supply**: 12V/24V suitable for your motors
- **Mounting Hardware**: Pan/tilt mechanism for camera mounting
- **GPIO Pins**: Configured in `laserturret.conf`

### Wiring

Configure pins in `laserturret.conf`:

```ini
[Motor]
x_step_pin = 23
x_dir_pin = 19
x_enable_pin = 5
y_step_pin = 24
y_dir_pin = 26
y_enable_pin = 6
ms1_pin = 17
ms2_pin = 27
ms3_pin = 22
microsteps = 8
steps_per_rev = 200

[GPIO]
x_cw_limit_pin = 18
x_ccw_limit_pin = 21
y_cw_limit_pin = 20
y_ccw_limit_pin = 4
```

## Setup and Calibration

### Initial Setup

1. **Hardware Assembly**
   - Mount camera on pan/tilt mechanism
   - Connect stepper motors to drivers
   - Wire drivers to Raspberry Pi GPIO pins
   - Install limit switches (optional but recommended)

2. **Configuration**
   - Copy `laserturret.conf.example` to `laserturret.conf`
   - Set correct GPIO pin numbers
   - Configure microstepping (typically 8 or 16)
   - Set steps per revolution for your motors

3. **Software Installation**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Stepper controller initializes automatically on app startup

### Calibration Process

Calibration establishes the steps-per-pixel ratio for accurate tracking:

1. **Access Tracking Tab**
   - Open web interface
   - Navigate to "📹 Track" tab
   - Select "Camera Tracking (Stepper Motors)" mode

2. **Enable Camera Tracking**
   - Toggle "Enable Camera Movement"
   - Motors should engage (you may hear a slight click)

3. **Calibrate X-Axis**
   - Enable object or motion detection
   - Place a target object in frame
   - Note object's pixel position
   - Manually adjust "X-Axis Steps/Pixel" slider
   - Enable auto-tracking and observe movement
   - Fine-tune until object centers correctly
   - Typical range: 0.05 - 0.20 steps/pixel

4. **Calibrate Y-Axis**
   - Repeat process for Y-axis
   - Move object vertically in frame
   - Adjust "Y-Axis Steps/Pixel" slider
   - Test and refine

5. **Set Dead Zone**
   - Adjust "Dead Zone" to prevent jitter
   - Too small: camera oscillates
   - Too large: tracking less precise
   - Recommended: 15-30 pixels

6. **Save Calibration**
   - Click "Save Calibration" to persist settings
   - Test with various objects and distances

### Advanced Calibration

For precise calibration:

1. Use a ruler or known distance marker
2. Measure pixel distance object moves in frame
3. Count motor steps executed
4. Calculate: `steps_per_pixel = steps / pixels_moved`
5. Use API endpoint for programmatic calibration:

```bash
curl -X POST http://localhost:5000/tracking/camera/calibrate \
  -H "Content-Type: application/json" \
  -d '{
    "axis": "x",
    "pixels_moved": 100,
    "steps_executed": 50
  }'
```

## Usage

### Basic Operation

1. **Select Tracking Mode**
   - Go to "📹 Track" tab
   - Choose "Camera Tracking" from dropdown
   - Camera tracking controls appear

2. **Enable Camera Movement**
   - Toggle "Enable Camera Movement"
   - Status indicator shows "Camera Enabled: Yes"

3. **Enable Object/Motion Tracking**
   - Navigate to "👤 Objects" or "🎯 Motion" tab
   - Enable detection
   - Enable auto-tracking
   - Camera will automatically follow detected targets

4. **Home Camera**
   - Click "🏠 Home Camera to Center" to return to zero position
   - Useful after extensive movement or when starting a session

### Settings

**Dead Zone (pixels)**: Minimum offset before camera moves

- Range: 5-100 pixels
- Lower = more responsive but may oscillate
- Higher = smoother but less precise
- Default: 20 pixels

**Movement Speed**: Step delay between motor steps

- Range: 0.5-5.0 ms
- Lower = faster movement
- Higher = smoother, more controlled
- Default: 1.0 ms

**Steps Per Pixel**: Calibration ratio for each axis

- Depends on motor, gearing, and camera FOV
- Requires manual calibration
- Save after calibration

**Max Steps**: Software limits to prevent overextension

- Default: 2000 steps per axis from center
- Adjust based on physical constraints
- Acts as safety limit if limit switches fail

## Safety Features

### Software Limits

- Maximum step count per axis from center position
- Prevents camera from moving beyond safe range
- Configurable via settings or API

### Hardware Limit Switches

- Optional but recommended
- Immediately stops movement when triggered
- Active-low configuration (triggered when pin reads LOW)
- Configured in GPIO section of config file

### Movement Lock

- Thread-safe movement control
- Prevents simultaneous movements from conflicting
- Only one movement command executes at a time

### Auto-Disable

- Motors disable when switching to crosshair mode
- Prevents accidental movement
- Must explicitly enable in camera mode

## API Reference

### Set Tracking Mode

```bash
POST /tracking/mode
Content-Type: application/json

{
  "mode": "camera"  # or "crosshair"
}
```

### Toggle Camera Tracking

```bash
POST /tracking/camera/toggle
Content-Type: application/json

{
  "enabled": true
}
```

### Home Camera

```bash
POST /tracking/camera/home
```

### Update Settings

```bash
POST /tracking/camera/settings
Content-Type: application/json

{
  "dead_zone_pixels": 20,
  "step_delay": 0.001,
  "x_steps_per_pixel": 0.15,
  "y_steps_per_pixel": 0.12,
  "x_max_steps": 2000,
  "y_max_steps": 2000
}
```

### Get Status

```bash
GET /tracking/camera/status
```

Response:

```json
{
  "status": "success",
  "available": true,
  "mode": "camera",
  "enabled": true,
  "controller_status": {
    "enabled": true,
    "moving": false,
    "position": {"x": 150, "y": -75},
    "calibration": {
      "x_steps_per_pixel": 0.15,
      "y_steps_per_pixel": 0.12,
      "dead_zone_pixels": 20
    },
    "limits": {
      "x_max_steps": 2000,
      "y_max_steps": 2000
    }
  }
}
```

## Troubleshooting

### Camera Not Moving

**Check:**

- Is camera tracking mode selected?
- Is "Enable Camera Movement" toggled on?
- Are motors physically connected and powered?
- Check GPIO pin configuration in `laserturret.conf`
- Verify stepper controller initialized (check console logs)

**Solution:**

```bash
# Check logs
python app.py
# Look for "Stepper controller initialized successfully"
```

### Erratic Movement / Oscillation

**Symptoms:** Camera rapidly moves back and forth

**Causes:**

- Dead zone too small
- Steps-per-pixel ratio too high
- Object detection unstable

**Solution:**

- Increase dead zone to 30-40 pixels
- Reduce steps-per-pixel calibration values
- Improve lighting for better object detection

### Movement in Wrong Direction

**Cause:** Stepper motor direction inverted

**Solution:**

- Swap motor direction pin wiring, or
- Modify direction logic in code (invert HIGH/LOW in `step()` method)

### Camera Doesn't Return to Center

**Cause:** Position tracking lost or accumulated error

**Solution:**

- Click "Home Camera to Center"
- Check limit switches if equipped
- Recalibrate if issue persists

### Limit Switch Triggered Unexpectedly

**Check:**

- Limit switch wiring (should be normally open, active low)
- Pull-up resistors enabled in GPIO configuration
- Physical alignment of switches

**Solution:**

```python
# In stepper_controller.py, verify:
self.gpio.setup(self.x_cw_limit, PinMode.INPUT, PullMode.UP)
```

### Stepper Controller Not Available

**Message:** "Camera tracking not available. Stepper controller not initialized."

**Causes:**

- Hardware not connected
- Missing configuration file
- GPIO initialization failed

**Solution:**

1. Check `laserturret.conf` exists
2. Verify GPIO library installed (lgpio or RPi.GPIO)
3. Run with mock mode for testing:

   ```python
   # In app.py, line 103:
   gpio = get_gpio_backend(mock=True)
   ```

## Performance Considerations

### Latency

- Object detection: ~30-50ms
- Step calculation: <1ms
- Motor movement: Depends on distance and speed
- Total latency: 50-500ms depending on distance

### Accuracy

- Positioning accuracy: ±5-10 pixels with proper calibration
- Repeatability: High (stepper motors don't lose steps under normal load)
- Drift: Minimal if motors maintain position hold

### Object Tracking Compatibility

- Works with face detection
- Works with eye detection
- Works with body detection
- Works with motion detection
- Only one tracking source at a time (object takes priority over motion)

## Integration with Existing Features

### Compatible Features

- ✅ Object detection (face, eye, body, smile)
- ✅ Motion detection
- ✅ Laser fire control
- ✅ Auto-fire on detection
- ✅ Video recording
- ✅ Image capture
- ✅ FPS monitoring

### Incompatible Features

- ❌ Preset positions (designed for crosshair mode)
- ❌ Pattern sequences (designed for crosshair mode)
- ❌ Manual crosshair click (no effect in camera mode)

### Mode Switching

- Switching modes automatically disables incompatible features
- Camera returns to center when switching to crosshair mode
- Previous tracking settings preserved

## Architecture

### Code Structure

```
laserturret/
├── stepper_controller.py    # Stepper motor control
├── hardware_interface.py    # GPIO abstraction layer
└── config_manager.py         # Configuration management

app.py                        # Main application with tracking integration
templates/
└── index.html               # UI with camera tracking tab
```

### Key Classes

**StepperController**: Main controller for stepper motors

- `enable()` / `disable()`: Control motor power
- `step()`: Execute steps on an axis with acceleration
- `move_to_center_object()`: Calculate and execute tracking movement
- `home()`: Return to center position
- `calibrate_steps_per_pixel()`: Update calibration

**StepperCalibration**: Configuration data class

- Steps-per-pixel ratios
- Current position tracking
- Movement limits
- Speed and dead zone settings

### Threading Model

- Main thread: Flask app and frame generation
- Movement threads: Spawned for each tracking movement
- Thread-safe with locks on shared state
- Non-blocking design prevents UI freezing

## Future Enhancements

### Planned Features

- [ ] Auto-calibration routine using known markers
- [ ] Saved calibration profiles for different setups
- [ ] Velocity-based tracking (predict object movement)
- [ ] Zone-based tracking (divide frame into regions)
- [ ] Integration with preset positions in camera mode
- [ ] Emergency stop button
- [ ] Movement logging and replay

### Hardware Improvements

- Support for servo motors as alternative to steppers
- Closed-loop stepper control with encoders
- Multi-camera support
- Gimbal stabilization integration

## License

This camera tracking feature is part of the laser-turret project and follows the same license terms.

## Support

For issues, questions, or contributions:

- Check existing issues on GitHub
- Review this documentation thoroughly
- Test with mock mode before hardware deployment
- Calibrate carefully for best results

---

**Last Updated**: 2025-10-02
**Version**: 1.0.0
