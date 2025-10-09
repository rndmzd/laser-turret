# Laser Turret

![degen_lasagna_cat](media/degen_lasagna_cat.gif)

A Raspberry Pi-powered laser turret with remote control, camera streaming, and precision stepper motor control.

## Features

- **Modern Control Panel** – Flask + Socket.IO dashboard with overlay toolbars, tabbed controls, and live telemetry for motors, optics, and detection states.
- **Advanced Targeting** – Crosshair steering or physical camera tracking with PID tuning, preset slots, repeating patterns, and automatic re-centering.
- **Object & Motion Detection** – Switch between Haar cascades, TensorFlow Lite (auto model download), Roboflow Inference, or balloon detection heuristics; optionally auto-track or auto-fire.
- **Precision Motion Hardware** – Dual stepper axes, microstepping configuration, limit switch safety, and idle watchdog to disable motors when inactive.
- **Laser Safety & Effects** – PWM power control, burst fire, cooldown enforcement, and remote enable/disable toggles.
- **Recording & Capture** – Start/stop MP4 recordings and snapshot captures directly from the UI while streaming in real time.
- **Remote & Local Control** – MQTT joystick transmitter, REST/Socket endpoints, and mock hardware mode for development without a Raspberry Pi.

## Hardware Requirements

### Raspberry Pi Setup

- Raspberry Pi 4/5 (recommended) or Pi 3B+
- Picamera2 compatible camera module
- MicroSD card (16GB+ recommended)

### Motor Control

- 2x NEMA 17 stepper motors (or similar)
- 2x A4988 stepper motor drivers
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
docker compose -f compose.inference_server.yaml up -d
```

Defaults:

- Server will listen on port 9001
- Compose file mounts `${HOME}/.inference/cache` (Linux/macOS) or `${USERPROFILE}/.inference/cache` (Windows) for model caching
- Set your Roboflow API key and model in `laserturret.conf`

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

#### Optional: Develop Without Hardware

Need to explore the UI or test logic on your laptop? The hardware abstraction layer automatically falls back to mock GPIO/camera backends when Raspberry Pi libraries are unavailable. You can also exercise the mocks directly:

```bash
# Exercise the abstraction layer directly
python scripts/test_with_mock_hardware.py
```

Mock mode disables real GPIO access, simulates laser power state, and feeds synthetic camera frames so you can test workflows safely.

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

```
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

### Limit Switch Connections

```
Raspberry Pi          Limit Switch
GPIO 18 ------------ X CW Limit (NO)
GPIO 21 ------------ X CCW Limit (NO)
GPIO 20 ------------ Y CW Limit (NO)
GPIO 4  ------------ Y CCW Limit (NO)
GND ---------------- Common Ground
```

All limit switches use internal pull-up resistors and trigger on FALLING edge.

### Laser Connection

```
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

- **Overlay Toolbars** – Toggle movement/object/laser panels directly on the video feed, adjust manual step size, and fire the laser without leaving the stream.
- **Tabbed Control Center** – Status, tracking, laser, presets, motion, object detection, exposure, image tuning, and capture tools grouped into dedicated tabs.
- **Crosshair Calibration** – Enable per-session offsets, save/reset calibration, and instantly center the reticle.
- **Camera Tracking Console** – Switch between crosshair and motor tracking, tune PID gains, set steps-per-pixel, dead zones, and enable re-center-on-loss.
- **Presets & Patterns** – Store up to 10 labeled preset angles, recall them instantly, and run looping sequences with adjustable delays.
- **Motion/Object Dashboards** – Configure motion sensitivity/area, toggle auto-track, change detection models, update confidence thresholds, and review recent detections.
- **Laser Safety Controls** – Enable/disable the laser system, configure burst count, pulse duration, cooldowns, and toggle auto-fire with readiness indicators.
- **Capture & Recording** – Start/stop MP4 recordings, download snapshots, and monitor elapsed recording time live.

## MQTT Message Format

Messages are sent to topic `laserturret` in CSV format:

```
x_axis,y_axis,joystick_button,laser_button,laser_power
```

Example: `50,-30,false,true,75`

- X axis: 50 (right)
- Y axis: -30 (down)
- Joystick button: not pressed
- Laser button: pressed
- Laser power: 75%

## Configuration

For a full list of configuration keys, defaults, and validation rules, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### Motor Settings

- **steps_per_rev**: Steps per revolution (typically 200 for 1.8° motors)
- **microsteps**: Microstepping resolution (1, 2, 4, 8, or 16)
- **deadzone**: Input values below this are ignored (reduce jitter)
- **step_delay**: Delay between steps (lower = faster, but may skip)

### Control Tuning

Edit `laserturret.conf`:

```ini
[Control]
max_steps_per_update = 50
deadzone = 5
speed_scaling = 0.10
step_delay = 0.0005
idle_timeout_sec = 120.0
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
```

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

See [scripts/README.md](scripts/README.md) for detailed walkthroughs, usage examples, and additional utilities such as mock hardware demos and benchmarking tools.

## Additional Documentation

- [docs/CAMERA_TRACKING_QUICKSTART.md](docs/CAMERA_TRACKING_QUICKSTART.md) – Enable and tune stepper-based camera tracking in minutes.
- [docs/CAMERA_TRACKING.md](docs/CAMERA_TRACKING.md) – Deep-dive into calibration, PID tuning, and troubleshooting.
- [docs/TENSORFLOW_QUICKSTART.md](docs/TENSORFLOW_QUICKSTART.md) – Switch to TensorFlow Lite and benchmark detection performance.
- [docs/RASPBERRY_PI_5.md](docs/RASPBERRY_PI_5.md) – Understand GPIO backend selection across Pi generations.
- [docs/WEBSOCKET_MIGRATION.md](docs/WEBSOCKET_MIGRATION.md) – Review the Socket.IO architecture powering the live UI.

### Code Structure

```
laser-turret/
├── app.py                          # Flask web server
├── remote_control_rx.py            # MQTT receiver (runs on Pi)
├── remote_control_tx.py            # MQTT transmitter (CircuitPython)
├── compose.inference_server.yaml   # Roboflow Inference Server (Docker Compose)
├── laserturret/
│   ├── config_manager.py           # Validated configuration loader with defaults
│   ├── hardware_interface.py       # GPIO/camera abstraction (lgpio, RPi.GPIO, mocks)
│   ├── lasercontrol.py             # Laser PWM control
│   ├── steppercontrol.py           # Low-level stepper motor implementation
│   ├── stepper_controller.py       # Camera tracking controller (used by app)
│   ├── tflite_detector.py          # TensorFlow Lite object detection wrapper
│   ├── roboflow_detector.py        # Roboflow HTTP client wrapper
│   └── motion/                     # Standardized motion API
│       ├── axis.py                 # StepperAxis alias + constants
│       ├── tracker.py              # CameraTracker alias of StepperController
│       └── constants.py
├── templates/
│   └── index.html                  # Web UI
└── scripts/                        # Test and utility scripts
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
