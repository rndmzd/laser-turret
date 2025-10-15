# Laser Turret

![degen_lasagna_cat](media/degen_lasagna_cat.gif)

A Raspberry Pi-powered laser turret with remote control, camera streaming, and precision stepper motor control.

## Features

- **Remote Control** - Wireless joystick control via MQTT (CircuitPython transmitter)
- **Video Streaming** - Real-time camera feed with crosshair overlay and telemetry
- **Precision Control** - A4988 stepper motor drivers with limit switches and calibration
- **PWM Laser Control** - Variable power laser with safety features
- **Web Interface** - Flask-based UI with WebSocket real-time updates
- **Camera Tracking (Stepper Motors)** - Hardware camera movement with PID tuning
- **Flexible Detection** - Haar cascades, TensorFlow Lite, or Roboflow Inference (remote)
- **Motion Package API** - Standardized `laserturret.motion` module for stepper control
- **Real-time PID Tuning** - Adjust tracking PID gains via UI or REST API
- **TMC2209 UART Support (Optional)** - Motor tab with live register viewer and on-the-fly tuning (IHOLD/IRUN/IHOLDDELAY/TPOWERDOWN)

## Hardware Requirements

### Raspberry Pi Setup

- Raspberry Pi 4/5 (recommended) or Pi 3B+
- Picamera2 compatible camera module
- MicroSD card (16GB+ recommended)

### Motor Control

- 2x NEMA 17 stepper motors (or similar)
- 2x stepper drivers: A4988/DRV8825 (pin mode) or TMC2209 (UART)
- 4x Limit switches (2 per axis)
- 12V power supply for motors

### Laser

- Laser diode module (compatible with PWM control)
- MOSFET or driver circuit for laser
- Appropriate safety equipment

### Remote Control (Optional)

- CircuitPython-compatible board (e.g., Adafruit QT Py ESP32-S3)
- Analog joystick module
- Potentiometer (for laser power control)
- Push button

## Software Installation

### On Raspberry Pi

#### 1. Install System Dependencies

**For Raspberry Pi 5:**

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-opencv python3-numpy \
    python3-picamera2 python3-libcamera python3-lgpio
```

**For Raspberry Pi 4 and earlier:**

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-opencv python3-numpy \
    python3-picamera2 python3-libcamera python3-rpi.gpio
```

> **Note:** Raspberry Pi 5 requires `lgpio` instead of `RPi.GPIO`. The software will automatically detect and use the correct library.

#### 2. Install Python Dependencies

```bash
cd ~/laser-turret
pip3 install -r requirements.txt
```

#### Optional: Roboflow Remote Inference

If you want to run detection via a Roboflow Inference Server (remote or local):

1. Ensure Docker is installed and running
2. From the repository root, start the server:

```bash
cd inference_server
docker compose up -d
```

Defaults:

- Server will listen on port 9001
- GPU image is configured in `inference_server/compose.yaml`
- Cache path is mounted at `${USERPROFILE}/.inference/cache` on Windows

Then set `detection_method = roboflow` and configure the Roboflow fields in `laserturret.conf` (see Configuration below).

#### 3. Configure Hardware

Edit `laserturret.conf` to match your GPIO pin connections:

```ini
[GPIO]
x_ccw_limit_pin = 21
x_cw_limit_pin = 18
y_ccw_limit_pin = 4
y_cw_limit_pin = 20

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

[Laser]
laser_pin = 12
laser_max_power = 100
```

> Note: UART features rely on `pyserial` (already included in `requirements.txt`).

### On Remote Control (CircuitPython)

#### 1. Install CircuitPython Libraries

Copy these libraries to your CircuitPython device's `lib/` folder:

- `adafruit_minimqtt`
- `adafruit_neopixel` (built-in on most boards)

#### 2. Create secrets.py

```python
# secrets.py
WIFI_SSID = "your_wifi_name"
WIFI_PASSWORD = "your_wifi_password"
MQTT_BROKER = "192.168.1.xxx"  # Your Pi's IP address
MQTT_TOPIC = "laserturret"
```

#### 3. Upload Code

Copy `remote_control_tx.py` to your CircuitPython device as `code.py`

## Wiring Diagram

### Stepper Motor Connections (A4988)

```text
Raspberry Pi          A4988 Driver
GPIO 23 (X_STEP) --> STEP
GPIO 19 (X_DIR)  --> DIR
GPIO 5 (X_EN)    --> ENABLE
GPIO 17 (MS1)    --> MS1
GPIO 27 (MS2)    --> MS2
GPIO 22 (MS3)    --> MS3
                     VDD --> 3.3V
                     GND --> GND
                     VMOT --> 12V
                     GND --> GND
```

### TMC2209 (UART) Setup

For wiring, configuration, and on-the-fly tuning of the TMC2209 drivers, see `docs/TMC2209_UART.md`.

### Limit Switch Connections

```text
Raspberry Pi          Limit Switch
GPIO 18 ------------ X CW Limit (NO)
GPIO 21 ------------ X CCW Limit (NO)
GPIO 20 ------------ Y CW Limit (NO)
GPIO 4  ------------ Y CCW Limit (NO)
GND ---------------- Common Ground
```

All limit switches use internal pull-up resistors and trigger on FALLING edge.

### Laser Connection

```text
Raspberry Pi          MOSFET/Driver
GPIO 12 (PWM) ------- Gate
GND ----------------- Source
                      Drain --> Laser +
                      Laser - --> GND
```

## Usage

### Initial Setup and Calibration

#### 1. Start the MQTT Receiver

```bash
cd ~/laser-turret
python3 remote_control_rx.py
```

On first run, the system will:

- Verify all limit switches
- Calibrate both axes by finding limits
- Center the turret

**Note:** Follow on-screen prompts to trigger each limit switch manually for verification.

#### 2. Start the Web Interface

```bash
python3 app.py
```

Access the camera feed at: `http://<raspberry-pi-ip>:5000`

#### 3. Calibrate Remote Control (First Time)

Hold the joystick button during power-on to enter calibration mode. Follow the LED color indicators:

- **Orange** - Connecting to WiFi
- **Green** - WiFi connected
- **Light Blue** - MQTT connected
- **Purple** - Calibration mode
- **White** - Button pressed / Laser active

### Normal Operation

1. **Power on remote control** - Should connect automatically (blue LED)
2. **Control turret** - Move joystick to pan/tilt
3. **Fire laser** - Press the laser button (adjustable power via potentiometer)
4. **View camera** - Open web browser to Pi's IP on port 5000

### Web Interface Features

- **Live video stream** with FPS counter
- **Crosshair overlay** - Click to reposition
- **Exposure stats** - Real-time camera telemetry
- **Responsive design** - Works on mobile devices
- **Camera tracking controls** - Enable camera movement, home to center, manual nudge
- **PID tuning** - Adjust Kp, Ki, Kd gains at runtime via UI sliders or REST API
- **WebSocket updates** - Real-time status push (2Hz) replaces HTTP polling
- **Motor tab (UART)** - Live TMC2209 register viewer and runtime tuning (IHOLD/IRUN/IHOLDDELAY/TPOWERDOWN)

## MQTT Message Format

Messages are sent to topic `laserturret` in CSV format:

```text
x_axis,y_axis,joystick_button,laser_button,laser_power
```

Example: `50,-30,false,true,75`

- X axis: 50 (right)
- Y axis: -30 (down)
- Joystick button: not pressed
- Laser button: pressed
- Laser power: 75%

## Motion Package API (Recommended)

The project now provides a standardized motion API in `laserturret.motion` for cleaner imports:

```python
from laserturret.motion import StepperAxis, CameraTracker

# StepperAxis is an alias of StepperMotor (backward compatible)
# CameraTracker is an alias of StepperController (backward compatible)
```

**Benefits:**

- Cleaner, more semantic imports
- Future-proof API with backward compatibility
- All motion-related classes in one package

**Example Usage:**

```python
# Old imports (still work)
from laserturret.steppercontrol import StepperMotor
from laserturret.stepper_controller import StepperController

# New imports (recommended)
from laserturret.motion import StepperAxis, CameraTracker
```

See `laserturret/motion/__init__.py` for available exports including `MotorStatus`, `CLOCKWISE`, `COUNTER_CLOCKWISE`, and `MICROSTEP_CONFIG`.

## Configuration

### Motor Settings

- **steps_per_rev**: Steps per revolution (typically 200 for 1.8° motors)
- **microsteps**: Microstepping resolution (1, 2, 4, 8, or 16)
- **deadzone**: Input values below this are ignored (reduce jitter)
- **step_delay**: Delay between steps (lower = faster, but may skip)
- **acceleration_steps**: Steps spent ramping speed up/down (higher = smoother)

### Control Tuning

Edit `laserturret.conf`:

```ini
[Control]
max_steps_per_update = 50
deadzone = 5
speed_scaling = 0.10
step_delay = 0.0005
acceleration_steps = 50
```

### Detection Settings

Select the detection backend and tune thresholds in `laserturret.conf`:

```ini
[Detection]
# Options: 'haar', 'tflite', or 'roboflow'
detection_method = haar

# TFLite (local inference)
tflite_model = ssd_mobilenet_v2
use_coral = false
tflite_confidence = 0.5
tflite_filter_classes =

# Roboflow (remote inference server, default port 9001)
roboflow_server_url = http://localhost:9001
roboflow_model_id =            # e.g. workspace/project/1
roboflow_api_key =             # required for private/hosted models
roboflow_confidence = 0.5
roboflow_class_filter =        # e.g. balloon

# Balloon detection (HSV + shape-based, used with Haar method)
balloon_v_threshold = 60
balloon_min_area = 2000
balloon_circularity_min = 0.55
balloon_fill_ratio_min = 0.5
balloon_aspect_ratio_min = 0.6
balloon_aspect_ratio_max = 1.6
```

**Detection Method Comparison:**

| Method | Speed | Accuracy | Hardware | Best For |
|--------|-------|----------|----------|----------|
| **Haar** | Fast | Low | CPU only | Simple shapes, faces |
| **TFLite** | Medium | High | CPU/Coral | 80+ object classes |
| **Roboflow** | Medium | Very High | Remote GPU | Custom trained models |

### PID Tuning Settings

Camera tracking uses PID control for smooth, responsive movement. Tune gains via:

**Web UI:**

- Navigate to "📹 Track" → "Camera Tracking" → "PID Tuning" section
- Adjust sliders: Kp (0-2), Ki (0-1), Kd (0-2)
- Click "Apply PID" to save to `camera_calibration.json`

**REST API:**

```bash
curl -X POST http://localhost:5000/tracking/camera/pid \
  -H "Content-Type: application/json" \
  -d '{"kp": 0.8, "ki": 0.0, "kd": 0.2}'
```

**Recommended Starting Values:**

- **Kp (Proportional):** 0.8 - Primary responsiveness
- **Ki (Integral):** 0.0 - Keep low to avoid drift
- **Kd (Derivative):** 0.2 - Damping to reduce overshoot

Adjust based on mechanical setup, camera weight, and motor characteristics. See `docs/CAMERA_TRACKING.md` for detailed tuning guide.

## Safety

⚠️ **IMPORTANT SAFETY INFORMATION** ⚠️

1. **Never look directly at the laser beam**
2. **Use appropriate laser safety goggles**
3. **Ensure laser power is appropriate for your application**
4. **Keep the laser pointed in a safe direction**
5. **Implement emergency stop procedures**
6. **Follow all local regulations for laser use**

The software includes:

- Limit switches to prevent mechanical damage
- Configurable laser power limits
- Emergency stop capability (Ctrl+C)

## WebSocket Status Updates

The control panel uses WebSocket (Socket.IO) for real-time status updates:

**Before (HTTP Polling):**

- ~10 HTTP requests/second
- 500-1000ms latency
- High overhead

**After (WebSocket):**

- Single persistent connection
- <50ms latency
- 90% less network traffic
- 2Hz status push (500ms intervals)

**Status includes:** FPS, exposure, crosshair position, laser state, object/motion detection, recording status, tracking position, and PID values.

See `docs/WEBSOCKET_MIGRATION.md` for migration details and performance metrics.

### REST API Reference

The control panel exposes a comprehensive REST API for automation and integration:

### Core Endpoints

- `GET /` - Web UI
- `GET /video_feed` - MJPEG video stream
- `GET /get_fps` - Current FPS
- `GET /exposure_stats` - Camera exposure statistics
- `GET /get_camera_settings` - Current camera configuration

### Camera Control

- `POST /set_exposure` - Set exposure mode and parameters
- `POST /set_image_params` - Brightness, contrast, saturation
- `POST /set_white_balance` - White balance mode
- `POST /capture_image` - Capture still image
- `POST /start_recording` - Start video recording
- `POST /stop_recording` - Stop video recording
- `GET /recording_status` - Recording status

### Crosshair Control

- `GET /get_crosshair_position` - Position (relative coordinates)
- `POST /update_crosshair` - Update position
- `POST /reset_crosshair` - Reset to center
- `GET /crosshair/calibration` - Get calibration offset
- `POST /crosshair/calibration/set` - Set calibration offset
- `POST /crosshair/calibration/reset` - Reset calibration

### Tracking Control

- `GET /tracking/mode` - Get current mode (crosshair/camera)
- `POST /tracking/mode` - Set tracking mode
- `GET /tracking/camera/status` - Camera tracking status
- `POST /tracking/camera/toggle` - Enable/disable camera tracking
- `POST /tracking/camera/home` - Home camera to center
- `POST /tracking/camera/settings` - Update tracking settings
- `GET /tracking/camera/pid` - Get PID values
- `POST /tracking/camera/pid` - Set PID values (persisted)
- `POST /tracking/camera/recenter_on_loss` - Re-center behavior

### TMC2209 UART

- `GET /tracking/camera/tmc/registers` - Read common registers for X/Y
- `POST /tracking/camera/tmc/apply_defaults` - Apply safe defaults (uses configured `microsteps`)
- `POST /tracking/camera/tmc/ihold_irun` - Set IHOLD/IRUN/IHOLDDELAY (`{"axis":"x|y|both","ihold":6,"irun":20,"iholddelay":4}`)
- `POST /tracking/camera/tmc/tpowerdown` - Set TPOWERDOWN (`{"axis":"x|y|both","tpowerdown":20}`)

### Object Detection

- `GET /object_detection/status` - Detection status and settings
- `POST /object_detection/toggle` - Enable/disable detection
- `POST /object_detection/auto_track` - Enable/disable auto-tracking
- `POST /object_detection/settings` - Update detection settings
- `GET /detection_method/config` - Current detection method config
- `POST /detection_method/switch` - Switch detection method
- `POST /tflite/settings` - TensorFlow Lite settings
- `POST /roboflow/settings` - Roboflow settings

### Motion Detection

- `GET /motion_detection/status` - Motion detection status
- `POST /motion_detection/toggle` - Enable/disable motion detection
- `POST /motion_detection/auto_track` - Enable/disable auto-tracking
- `POST /motion_detection/settings` - Update sensitivity and thresholds

### Laser Control

- `GET /laser/status` - Laser state and power
- `POST /laser/toggle` - Enable/disable laser
- `POST /laser/power` - Set laser power (0-100%)
- `POST /laser/auto_fire` - Enable/disable auto-fire

**WebSocket Event:**

- `status_update` - Consolidated status (emitted at 2Hz)

For detailed API usage examples, see `docs/CAMERA_TRACKING.md` and `docs/WEBSOCKET_MIGRATION.md`.

## Troubleshooting

### Motors Not Moving

- Check GPIO pin assignments in `laserturret.conf`
- Verify A4988 drivers have power (12V)
- Test with `scripts/steppercontrol_test.py`
- Check limit switch wiring (should be NC or properly pulled up)

### Camera Not Working

- Run `libcamera-hello` to test camera
- Check camera cable connection
- Verify Picamera2 is installed: `python3 -c "from picamera2 import Picamera2"`
- App will show "Camera Not Available" if camera fails

### Remote Control Not Connecting

- Verify WiFi credentials in `secrets.py`
- Check MQTT broker IP address
- Ensure Pi is running `remote_control_rx.py`
- Check CircuitPython serial console for errors

### Limit Switches Not Triggering

- Test with multimeter (should be closed when not pressed)
- Verify GPIO pins in config
- Check pull-up resistors are enabled
- Run calibration in debug mode
- Use `scripts/test_limit_switches.py` for diagnostics

### WebSocket Connection Issues

- Check browser console (F12) for connection errors
- Verify Flask-SocketIO installed: `pip show flask-socketio`
- Firewall must allow port 5000
- Look for "✅ WebSocket connected" in browser console

### Roboflow Inference Server Not Responding

- Verify Docker container running: `docker ps`
- Check server logs: `docker logs inference_server`
- Ensure `roboflow_server_url` in config matches container port
- Test connection: `curl http://localhost:9001/`

## Development

### Running Tests

```bash
cd scripts
python3 steppercontrol_test.py  # Test motor control
python3 laser_test.py           # Test laser PWM
python3 calib_test.py          # Test calibration
```

### Utility Scripts

- `gpio_monitor.py` - Real-time GPIO state monitoring (web interface on port 5001)
- `measure_ranges.py` - Measure joystick calibration ranges
- `i2c_scan.py` - Scan for I2C devices

### Code Structure

```text
laser-turret/
├── app.py                          # Flask web server with WebSocket support
├── remote_control_rx.py            # MQTT receiver (runs on Pi)
├── remote_control_tx.py            # MQTT transmitter (CircuitPython)
├── inference_server/
│   └── compose.yaml                # Roboflow Inference Server (Docker Compose)
├── laserturret/
│   ├── lasercontrol.py             # Laser PWM control
│   ├── steppercontrol.py           # Low-level stepper motor implementation
│   ├── stepper_controller.py       # Camera tracking controller (used by app)
│   ├── roboflow_detector.py        # Roboflow HTTP client wrapper
│   ├── tflite_detector.py          # TensorFlow Lite object detection
│   ├── tmc2209_uart.py             # TMC2209 UART driver helpers
│   ├── hardware_interface.py       # GPIO abstraction (lgpio/RPi.GPIO)
│   ├── config_manager.py           # Configuration file management
│   └── motion/                     # Standardized motion API (recommended)
│       ├── __init__.py             # StepperAxis, CameraTracker exports
│       ├── axis.py                 # StepperAxis (alias of StepperMotor)
│       ├── tracker.py              # CameraTracker (alias of StepperController)
│       └── constants.py            # Microstepping and direction constants
├── templates/
│   └── index.html                  # Web UI with Socket.IO integration
├── static/
│   └── css/index.css               # UI styling
└── scripts/                        # Test and utility scripts
    └── setup_tmc2209_uart.py       # Configure and dump TMC2209 registers via CLI
```

## Contributing

See `docs/REVIEW.md` for:

- Known issues and bugs
- Refactoring opportunities
- Feature enhancement ideas
- Code quality improvements

## License

See LICENSE file for details.

## Acknowledgments

- Built with Raspberry Pi, CircuitPython, and Flask
- Uses A4988 stepper drivers and Picamera2
- MQTT communication via paho-mqtt and Adafruit_MiniMQTT
