# Configuration Reference

The laser turret ships with a type-checked configuration manager (`laserturret/config_manager.py`) that merges your `laserturret.conf` file with safe defaults, validates pin assignments, and exposes convenient helper methods throughout the application.

## Getting Started

1. Copy `laserturret.conf.example` to `laserturret.conf`.
2. Edit only the values that differ from your hardware — anything you omit falls back to the defaults listed below.
3. The configuration is loaded once via `laserturret.get_config()` and cached globally. Call `get_config().reload()` if you need to re-read the file at runtime.

> **Tip:** Missing files are not fatal. When `laserturret.conf` is absent, the application logs a warning and continues using the defaults defined in `ConfigManager.DEFAULTS`.

## Validation Rules

The configuration manager enforces several safety checks when the file is loaded:

- **Unique GPIO pins:** Every pin (limit switches, motor control, laser) must be unique or a `ConfigurationError` is raised.
- **Valid pin range:** Pins must fall within BCM 2–27.
- **Supported microsteps:** Only 1, 2, 4, 8, or 16 microstepping values are accepted.
- **MQTT ports:** Ports must be between 1 and 65535.

Any violation prevents the application from starting, protecting your hardware from shorted or conflicting assignments.

## Configuration Sections & Defaults

### `[GPIO]`

| Key | Default | Purpose |
| --- | --- | --- |
| `x_ccw_limit_pin` | `21` | Counter-clockwise limit for X axis |
| `x_cw_limit_pin` | `18` | Clockwise limit for X axis |
| `y_ccw_limit_pin` | `4` | Counter-clockwise limit for Y axis |
| `y_cw_limit_pin` | `20` | Clockwise limit for Y axis |

### `[MQTT]`

| Key | Default | Purpose |
| --- | --- | --- |
| `broker` | `localhost` | MQTT broker hostname/IP for the joystick transmitter |
| `port` | `1883` | MQTT broker port |
| `topic` | `laserturret` | Topic used by `remote_control_rx.py` and `remote_control_tx.py` |

### `[Motor]`

| Key | Default | Purpose |
| --- | --- | --- |
| `x_dir_pin` | `19` | Direction pin for X axis |
| `x_step_pin` | `23` | Step pin for X axis |
| `x_enable_pin` | `5` | Enable pin for X axis |
| `y_dir_pin` | `26` | Direction pin for Y axis |
| `y_step_pin` | `24` | Step pin for Y axis |
| `y_enable_pin` | `6` | Enable pin for Y axis |
| `ms1_pin` | `17` | Microstep select 1 (shared) |
| `ms2_pin` | `27` | Microstep select 2 (shared) |
| `ms3_pin` | `22` | Microstep select 3 (shared) |
| `microsteps` | `8` | Microstepping setting (1/8 step default) |
| `steps_per_rev` | `200` | Full steps per motor revolution |

### `[Control]`

| Key | Default | Purpose |
| --- | --- | --- |
| `max_steps_per_update` | `50` | Clamp on steps processed per joystick message |
| `deadzone` | `5` | Ignore small joystick deltas to avoid jitter |
| `speed_scaling` | `0.10` | Multiplier applied to joystick input before stepping |
| `step_delay` | `0.0005` | Delay between steps (seconds) |
| `idle_timeout_sec` | `120.0` | Automatically disables motors after inactivity |

### `[Laser]`

| Key | Default | Purpose |
| --- | --- | --- |
| `laser_pin` | `12` | PWM output controlling the MOSFET/driver |
| `laser_max_power` | `5` | Upper bound (%) enforced when arming the laser |

> The UI lets you request up to 100% power, but the laser controller clamps values above `laser_max_power`. Increase this limit only after validating your driver and safety procedures.

### `[Camera]`

| Key | Default | Purpose |
| --- | --- | --- |
| `width` | `1920` | Capture width for Picamera2 |
| `height` | `1080` | Capture height |
| `format` | `RGB888` | Output pixel format |
| `buffer_count` | `2` | Number of camera buffers retained |

### `[Detection]`

| Key | Default | Purpose |
| --- | --- | --- |
| `detection_method` | `haar` | `haar`, `tflite`, or `roboflow` |
| `tflite_model` | `ssd_mobilenet_v2` | Model name downloaded automatically |
| `use_coral` | `False` | Enable Coral USB accelerator delegate |
| `tflite_confidence` | `0.5` | Confidence threshold for TensorFlow Lite detections |
| `tflite_filter_classes` | `` (empty) | Comma-delimited allowlist of COCO classes |
| `balloon_v_threshold` | `60` | HSV V threshold for balloon heuristic |
| `balloon_min_area` | `4000` | Minimum contour area (pixels) |
| `balloon_circularity_min` | `0.55` | Minimum acceptable circularity |
| `balloon_fill_ratio_min` | `0.5` | Minimum fill ratio (area vs. bounding box) |
| `balloon_aspect_ratio_min` | `0.6` | Lower aspect ratio bound |
| `balloon_aspect_ratio_max` | `1.6` | Upper aspect ratio bound |
| `roboflow_server_url` | `http://localhost:9001` | Remote inference endpoint |
| `roboflow_model_id` | `` (empty) | Target Roboflow workspace/project/version |
| `roboflow_api_key` | `` (empty) | API key for hosted/private models |
| `roboflow_confidence` | `0.5` | Confidence threshold for Roboflow detections |
| `roboflow_class_filter` | `` (empty) | Comma-delimited allowlist of Roboflow classes |

## Runtime Helpers

The configuration manager exposes helper methods for every key, simplifying downstream code. A few commonly used examples:

```python
from laserturret import get_config

config = get_config()
laser_pin = config.get_laser_pin()
max_power = config.get_laser_max_power()
mqtt_topic = config.get_mqtt_topic()
```

Call `config.get_all_config()` to inspect the merged configuration (defaults plus overrides) or `config.reload()` after editing the file on disk while the app is running.

## Troubleshooting

- **"Configuration file not found"** – Copy `laserturret.conf.example` and adjust values for your wiring.
- **"Pin X is assigned to multiple functions"** – Ensure each pin in the `[GPIO]`, `[Motor]`, and `[Laser]` sections is unique.
- **"Invalid microsteps value"** – Limit settings to 1, 2, 4, 8, or 16. Most A4988 drivers ship with jumpers for these increments.
- **Unexpected laser power clamp** – Verify `laser_max_power`; the UI cannot exceed this safety limit.

Keeping configuration centralized in one validated file reduces setup errors, makes it easy to switch between hardware profiles, and enables safe fallbacks for development machines that lack GPIO access.
