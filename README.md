# Laser Turret

![degen_lasagna_cat](media/degen_lasagna_cat.gif)

A Raspberry Pi-powered laser turret with remote control, live video streaming, hardware camera tracking, and configurable laser safety controls.

## Highlights

- **Raspberry Pi ready** – Automatically selects the right GPIO backend (`lgpio` on Pi 5, `RPi.GPIO` on older boards) with a mock driver for off-device development.
- **Dual tracking modes** – Keep the crosshair fixed in software or physically move the camera with stepper motors, limit switches, and calibration tools.
- **Multiple detection backends** – Switch between Haar cascades, TensorFlow Lite, and Roboflow inference at runtime and filter detections by class.
- **Motion analytics** – Background subtraction, motion targets, and smoothing with optional auto-track and laser auto-fire.
- **Video workflow** – Live MJPEG stream with crosshair overlay, still capture, rolling exposure stats, and MP4 recording from the browser.
- **Laser management** – PWM power control, burst/pulse modes, cooldown enforcement, software toggles, and optional remote potentiometer input.
- **Presets & patterns** – Save crosshair positions, recall them later, or run repeating motion patterns for demos and balloon popping routines.

## Hardware Requirements

### Raspberry Pi

- Raspberry Pi 4/5 (recommended) or Pi 3B+
- Picamera2-compatible camera module
- MicroSD card (16GB+ recommended)

### Motor Control

- 2 × NEMA 17 stepper motors (or similar)
- 2 × A4988 stepper motor drivers
- 4 × Limit switches (2 per axis)
- 12V motor power supply

### Laser Assembly

- PWM-controllable laser diode module
- MOSFET or driver circuit for laser power switching
- Proper laser safety eyewear

### Optional Remote Control

- CircuitPython-compatible microcontroller (e.g., Adafruit QT Py ESP32-S3)
- Analog joystick module
- Potentiometer (laser power input)
- Momentary push button

Wiring diagrams for motors, switches, and the laser are included later in this document.

## Software Setup

### 1. System Packages (Raspberry Pi)

Use the provided `apt_requirements.txt` as a reference or install manually:

```bash
sudo apt-get update
sudo xargs -a apt_requirements.txt apt-get install -y
```

- Raspberry Pi 5 installs `python3-lgpio`
- Raspberry Pi 4 and earlier install `python3-rpi.gpio`

> **Note:** The software auto-detects the correct GPIO library and falls back to a mock backend when neither is available.

### 2. Python Environment

```bash
cd ~/laser-turret
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Re-run the `pip install` step after updating dependencies.

### 3. Optional: Roboflow Inference Server

To run detections using a Roboflow Inference Server (local or remote):

```bash
docker compose -f compose.inference_server.yaml up -d
```

Defaults:

- Server listens on port `9001`
- GPU image (`roboflow/roboflow-inference-server-gpu:latest`) by default
- Cache is mounted to `${USERPROFILE}/.inference/cache`

Set `detection_method = roboflow` in `laserturret.conf` and populate the Roboflow fields to activate remote inference.

## Configuration

Copy `laserturret.conf.example` to `laserturret.conf` and adjust for your build. The configuration manager validates pins and provides sane defaults.

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
idle_timeout_sec = 120.0

[Laser]
laser_pin = 12
laser_max_power = 100

[Camera]
width = 1920
height = 1080
format = RGB888
buffer_count = 2

[Detection]
# Options: haar, tflite, roboflow
detection_method = haar

# TensorFlow Lite
tflite_model = ssd_mobilenet_v2
use_coral = false
tflite_confidence = 0.5
tflite_filter_classes =

# Roboflow Inference Server
roboflow_server_url = http://localhost:9001
roboflow_model_id =
roboflow_api_key =
roboflow_confidence = 0.5
roboflow_class_filter =

# Balloon heuristics (Haar/balloon detection mode)
balloon_v_threshold = 60
balloon_min_area = 2000
balloon_circularity_min = 0.55
balloon_fill_ratio_min = 0.5
balloon_aspect_ratio_min = 0.6
balloon_aspect_ratio_max = 1.6
```

Additional settings (PID gains, tracking ratios, etc.) are configured live from the UI and persisted in calibration files.

## Running the System

1. **Start the MQTT receiver** (motor + laser controller):
   ```bash
   python remote_control_rx.py
   ```
   On first run the controller verifies limit switches, calibrates both axes, and centers the turret. Use `Ctrl+C` to perform an emergency stop.

2. **Launch the web interface**:
   ```bash
   python app.py
   ```
   Visit `http://<raspberry-pi-ip>:5000` to open the control panel. Set `FLASK_ENV=development` for verbose logging during debugging.

3. **Optional hardware joystick**: Power the CircuitPython remote. It publishes joystick values, button states, and potentiometer readings to the MQTT topic defined in `laserturret.conf`.

4. **Calibrate the crosshair**: Use the calibration controls in the UI. Offsets are stored in `crosshair_calibration.json` and automatically loaded at startup.

5. **Camera tracking**: Enable hardware tracking from the **Track** tab once homing is complete. See `docs/CAMERA_TRACKING_QUICKSTART.md` for a detailed walkthrough of PID tuning, automatic calibration, and safety checks.

## Web Interface Overview

### Dashboard

- MJPEG stream with crosshair overlay, FPS counter, and exposure telemetry.
- Adjust exposure, white balance, and camera parameters on the fly.
- Capture still images or start/stop MP4 recordings (filename and elapsed time are displayed).

### Detect Tab

- Toggle motion detection, set sensitivity/min area, and enable motion-based auto-track.
- Enable object detection using Haar cascades, TensorFlow Lite, or Roboflow without restarting the server.
- Choose detection targets (faces, eyes, full body, smile, balloon, or custom classes) and prioritize largest/closest detections.
- Activate object auto-track and optional laser auto-fire when a target is locked.
- Configure TFLite and Roboflow parameters directly from the browser.

### Track Tab

- Switch between **Crosshair** (software) and **Camera** (hardware) tracking modes.
- Toggle camera tracking, home the rig, or run full calibration routines.
- Tune step delay, steps-per-pixel ratios, dead zones, PID gains, and loss recovery behavior.
- Manually jog axes, move to absolute coordinates, set the current pose as home, or auto-calibrate the camera alignment.

### Presets & Patterns

- Save crosshair positions to labeled preset slots.
- Recall presets on demand or schedule them in a looping pattern with adjustable delays.

### Laser Controls

- Arm/disarm the laser, trigger manual fire, or fire pulse/burst sequences with configurable durations and cooldown.
- Display live status, total fire counts, and cooldown timers.

### Status Feed

- The Socket.IO status thread broadcasts consolidated telemetry (laser state, tracking mode, motion/object status, camera stats) for heads-up displays or automation scripts.

## Remote Control (CircuitPython)

1. **Libraries** – Copy `adafruit_minimqtt` and `adafruit_neopixel` to the device `lib/` directory.
2. **Wi-Fi and MQTT secrets** – Create `secrets.py`:
   ```python
   WIFI_SSID = "your_wifi_name"
   WIFI_PASSWORD = "your_wifi_password"
   MQTT_BROKER = "192.168.1.xxx"  # Raspberry Pi IP
   MQTT_TOPIC = "laserturret"
   ```
3. **Upload code** – Copy `remote_control_tx.py` to the board as `code.py`. Hold the joystick button while powering on to enter calibration mode. LED color codes: orange (Wi-Fi connecting), green (Wi-Fi connected), light blue (MQTT connected), purple (calibration), white (button pressed/laser active).

## Wiring Reference

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

All limit switches use internal pull-ups and trigger on a falling edge.

### Laser Connection

```
Raspberry Pi          MOSFET/Driver
GPIO 12 (PWM) ------- Gate
GND ----------------- Source
                      Drain --> Laser +
                      Laser - --> GND
```

## Utility Scripts

Most helper scripts live in `scripts/` (see `scripts/README.md` for detailed descriptions). Highlights include:

- `steppercontrol_test.py` – Automated and interactive motor test suite.
- `test_limit_switches.py` – Live diagnostics and wiring verification for all limit switches.
- `laser_control_test.py` – Examples of using the `LaserControl` class safely.
- `test_with_mock_hardware.py` – Demonstrates the mock GPIO and camera interfaces for development on non-Pi hardware.
- `benchmark_detection.py` – Compare Haar vs. TFLite performance.

## Troubleshooting

### Motors Not Moving

- Verify GPIO pin assignments and wiring in `laserturret.conf`.
- Confirm A4988 drivers have power (12V) and the enable pin is low.
- Use `scripts/steppercontrol_test.py` or `scripts/test_limit_switches.py --mode monitor` to diagnose hardware issues.

### Camera Not Working

- Test with `libcamera-hello` to ensure the OS sees the camera.
- Check the ribbon cable connection and Picamera2 installation (`python3 -c "from picamera2 import Picamera2"`).
- The UI will display "Camera Not Available" if initialization fails.

### Remote Control Not Connecting

- Confirm Wi-Fi credentials and MQTT broker IP in `secrets.py`.
- Ensure `remote_control_rx.py` is running on the Raspberry Pi.
- Check the CircuitPython serial console for errors.

### Limit Switches Not Triggering

- Test continuity with a multimeter (closed when not pressed).
- Confirm GPIO pins and pull-ups in configuration.
- Run `python scripts/test_limit_switches.py --mode test` and trigger each switch manually.

## Safety

⚠️ **Important Safety Information** ⚠️

1. Never look directly at the laser beam.
2. Always wear appropriate laser safety goggles.
3. Set `laser_max_power` to a safe value for your hardware.
4. Keep the laser pointed away from people and reflective surfaces.
5. Provide an emergency stop mechanism (Ctrl+C on the receiver, kill switch on hardware).
6. Follow all local regulations for laser usage.

The software includes limit switch protection, configurable power limits, cooldown timers, and manual overrides to help mitigate risk.

## Additional Documentation

The `docs/` directory contains in-depth guides:

- `CAMERA_TRACKING.md` & `CAMERA_TRACKING_QUICKSTART.md` – Hardware tracking setup and calibration.
- `CAMERA_TRACKING_DIAGRAM.txt` – Wiring reference for the tracking subsystem.
- `TENSORFLOW_QUICKSTART.md` & `TENSORFLOW_INTEGRATION.md` – TensorFlow Lite setup.
- `RASPBERRY_PI_5.md` – Notes on Pi 5 GPIO support.
- `SECURITY_SCANNING.md` – Guidance for running dependency and container scans.
- `WEBSOCKET_MIGRATION.md` – Socket.IO migration details for the web UI.

## Project Structure

```
laser-turret/
├── app.py                         # Flask + Socket.IO control panel
├── laserturret/
│   ├── hardware_interface.py      # GPIO & camera abstraction layer
│   ├── config_manager.py          # Typed configuration loader/validator
│   ├── steppercontrol.py          # Low-level stepper driver
│   ├── stepper_controller.py      # High-level tracking controller
│   ├── lasercontrol.py            # PWM laser control helpers
│   ├── roboflow_detector.py       # Roboflow HTTP client
│   ├── tflite_detector.py         # TensorFlow Lite wrapper
│   └── motion/                    # Motion aliases and helpers
├── remote_control_rx.py           # MQTT receiver for motors + laser
├── remote_control_tx.py           # CircuitPython transmitter example
├── static/ and templates/         # Web assets and HTML templates
├── scripts/                       # Tests, diagnostics, and utilities
└── docs/                          # Extended documentation and diagrams
```

## Contributing

See `docs/REVIEW.md` for known issues, refactoring opportunities, feature ideas, and code quality notes. Pull requests should include relevant hardware setup details, configuration changes, and test evidence.

## License

See `LICENSE` for licensing information.

## Acknowledgments

- Built with Raspberry Pi, CircuitPython, Flask, and Picamera2.
- Uses A4988 stepper drivers, MQTT (paho-mqtt / Adafruit MiniMQTT), and Roboflow/TFLite for detection.
- Animated cat courtesy of the community that inspired this project.
