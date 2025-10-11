from flask import Flask, Response, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from picamera2 import Picamera2
from picamera2.controls import Controls
from libcamera import ColorSpace, Transform
import cv2
import numpy as np
import threading
import time
from collections import deque
from datetime import datetime
import os
import json

from laserturret.hardware_interface import get_gpio_backend
from laserturret.config_manager import get_config
from laserturret.motion import CameraTracker as StepperController
from laserturret.lasercontrol import LaserControl

# Try to import TFLite detector
try:
    from laserturret.tflite_detector import TFLiteDetector, TFLITE_AVAILABLE
except ImportError:
    TFLITE_AVAILABLE = False
    print("Warning: TFLite detector not available")

# Try to import Roboflow detector client
try:
    from laserturret.roboflow_detector import RoboflowDetector
    ROBOFLOW_AVAILABLE = True
except Exception:
    ROBOFLOW_AVAILABLE = False
    print("Warning: Roboflow inference client not available. Install with: pip install inference-sdk")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'laser-turret-secret-key-change-in-production'
if app.config.get('SECRET_KEY') == 'laser-turret-secret-key-change-in-production':
    print("WARNING: Using default Flask SECRET_KEY; set a unique SECRET_KEY in production.")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global variables
output_frame = None
lock = threading.Lock()
picam2 = None

# Camera resolution
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080

# Crosshair position and calibration offset
crosshair_pos = {'x': CAMERA_WIDTH // 2, 'y': CAMERA_HEIGHT // 2}
crosshair_offset = {'x': 0, 'y': 0}  # Offset from frame center in pixels (image coords)
crosshair_calibration_file = 'crosshair_calibration.json'
crosshair_lock = threading.Lock()

# FPS monitoring
fps_buffer = deque(maxlen=30)
last_frame_time = None
fps_value = 0
fps_lock = threading.Lock()

# Exposure monitoring
exposure_stats = {
    'exposure_time': 0,
    'analog_gain': 0
}
exposure_lock = threading.Lock()

# Video recording
is_recording = False
video_writer = None
recording_filename = None
recording_lock = threading.Lock()
recording_start_time = None

# Motion detection
motion_detection_enabled = False
motion_auto_track = False
motion_sensitivity = 25  # Threshold for motion detection (lower = more sensitive)
motion_min_area = 500    # Minimum area to consider as motion
motion_lock = threading.Lock()
background_subtractor = None
last_motion_center = None

# Object/Face detection
object_detection_enabled = False
object_auto_track = False
detection_mode = 'face'  # 'face', 'eye', 'body', 'smile'
detection_method = 'haar'  # 'haar' or 'tflite' - loaded from config
target_priority = 'largest'  # 'largest', 'closest', 'leftmost', 'rightmost'
object_lock = threading.Lock()
detected_objects = []

# Haar Cascade classifiers (legacy)
face_cascade = None
eye_cascade = None
body_cascade = None
smile_cascade = None

# TensorFlow Lite detector
tflite_detector = None
tflite_filter_classes = []  # Empty = detect all classes

# Roboflow detector
roboflow_detector = None
roboflow_filter_classes = []  # Empty = detect all classes

# Preset positions
preset_positions = {}  # {slot: {'x': int, 'y': int, 'label': str}}
preset_lock = threading.Lock()
pattern_running = False
pattern_thread = None
pattern_sequence = []
pattern_delay = 1.0  # seconds between positions
pattern_loop = False

# Laser fire control
laser_enabled = False
laser_pulse_duration = 0.1  # seconds (100ms default)
laser_burst_count = 1  # Number of pulses in burst mode
laser_burst_delay = 0.1  # Delay between burst pulses
laser_cooldown = 0.5  # Minimum time between fire commands
laser_auto_fire = False  # Auto-fire when object/motion detected
laser_power = 100  # Laser power level (0-100%)
laser_mock_fire_mode = False  # Mock fire mode for visual testing
mock_fire_active = False  # Current mock fire state
mock_fire_time = None  # When mock fire started
laser_lock = threading.Lock()
last_fire_time = None
fire_count = 0  # Track total fires
laser_control = None  # LaserControl instance

# Camera tracking mode (stepper motor control)
tracking_mode = 'crosshair'  # 'crosshair' or 'camera'
camera_tracking_enabled = False
stepper_controller = None
tracking_mode_lock = threading.Lock()
camera_recenter_on_loss = False

tracking_smoothing_alpha = 0.3
target_lock_distance = 150
target_switch_cooldown = 0.25
object_track_smooth_center = None
object_last_switch_time = 0.0
motion_smooth_center = None
crosshair_dead_zone_pixels = 20
motion_bg_history = 500
motion_learning_rate = 0.01
motion_kernel_size = 5

balloon_v_threshold = 60
balloon_min_area = 2000
balloon_circularity_min = 0.55
balloon_fill_ratio_min = 0.5
balloon_aspect_ratio_min = 0.6
balloon_aspect_ratio_max = 1.6

def load_crosshair_calibration():
    """Load crosshair calibration offset from file"""
    global crosshair_offset
    if os.path.exists(crosshair_calibration_file):
        with open(crosshair_calibration_file, 'r') as f:
            data = json.load(f)
            crosshair_offset['x'] = data['x']
            crosshair_offset['y'] = data['y']

def save_crosshair_calibration():
    """Save crosshair calibration offset to file"""
    global crosshair_offset
    with open(crosshair_calibration_file, 'w') as f:
        json.dump(crosshair_offset, f)

def initialize_laser_control():
    """Initialize laser control with PWM"""
    global laser_control, laser_power
    
    try:
        # Get configuration and GPIO backend
        config = get_config()
        gpio = get_gpio_backend(mock=False)  # Set to True for testing without hardware
        
        # Get laser configuration
        laser_pin = config.get_laser_pin()
        laser_max_power = config.get_laser_max_power()
        
        # Initialize laser control
        laser_control = LaserControl(
            gpio_pin=int(laser_pin),
            pwm_frequency=1000,
            initial_power=0,
            name="MainLaser",
            gpio_backend=gpio
        )
        
        # Set initial power from config (capped by max power)
        laser_power = min(laser_power, int(laser_max_power))
        laser_control.set_power(laser_power)
        
        print(f"Laser control initialized successfully on GPIO {laser_pin}")
        print(f"Max power: {laser_max_power}%, Current power: {laser_power}%")
        
    except Exception as e:
        print(f"WARNING: Failed to initialize laser control: {e}")
        print("Laser will operate in simulation mode only.")
        laser_control = None

def initialize_stepper_controller():
    """Initialize stepper motor controller for camera tracking"""
    global stepper_controller
    
    try:
        # Get configuration and GPIO backend
        config = get_config()
        gpio = get_gpio_backend(mock=False)  # Set to True for testing without hardware
        
        # Initialize stepper controller
        stepper_controller = StepperController(gpio, config)
        print("Stepper controller initialized successfully")
        
    except Exception as e:
        print(f"WARNING: Failed to initialize stepper controller: {e}")
        print("Camera tracking mode will not be available.")
        stepper_controller = None

def initialize_camera():
    """Initialize the Pi Camera with compatible auto exposure settings"""
    global picam2, crosshair_pos, last_frame_time
    
    try:
        picam2 = Picamera2()
        
        # Configure camera with supported settings
        config = picam2.create_preview_configuration(
            main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT),
                  "format": "RGB888"},
            buffer_count=2,
            transform=Transform(vflip=0, hflip=0)
        )
        
        picam2.configure(config)
        
        # Get supported controls for debugging
        print("Supported controls:", picam2.camera_controls)
        
        picam2.start()
        
        # Set controls after starting to ensure they apply correctly
        picam2.set_controls({
            # Basic exposure controls
            "AeEnable": True,               # Enable Auto Exposure
            
            # White Balance
            "AwbEnable": True,              # Enable Auto White Balance
            "AwbMode": 1,                   # Auto WB mode
            
            # Basic image adjustments
            "Brightness": 0.0,              # Default brightness
            "Contrast": 1.0,                # Default contrast
            "Saturation": 1.0,              # Default saturation
        })
        
        time.sleep(2)  # Allow time for AE and AWB to settle
        
        # Start exposure monitoring
        threading.Thread(target=monitor_exposure, daemon=True).start()
        
        # Initialize positions using crosshair calibration offset
        load_crosshair_calibration()
        with crosshair_lock:
            crosshair_pos['x'] = (CAMERA_WIDTH // 2) + int(crosshair_offset['x'])
            crosshair_pos['y'] = (CAMERA_HEIGHT // 2) + int(crosshair_offset['y'])
        last_frame_time = datetime.now()
        
        print("Camera initialized successfully")
        
    except Exception as e:
        print(f"ERROR: Failed to initialize camera: {e}")
        print("Camera will not be available. Check hardware connection.")
        picam2 = None

def monitor_exposure():
    """Monitor exposure settings in a separate thread"""
    global exposure_stats
    while True:
        try:
            metadata = picam2.capture_metadata()
            with exposure_lock:
                exposure_stats['exposure_time'] = metadata.get('ExposureTime', 0)
                exposure_stats['analog_gain'] = metadata.get('AnalogueGain', 0)
        except Exception as e:
            print(f"Error monitoring exposure: {e}")
        time.sleep(0.2)

def fire_laser():
    """Fire the laser using LaserControl with PWM power control"""
    global last_fire_time, fire_count, mock_fire_active, mock_fire_time
    
    current_time = time.time()
    
    # Check cooldown
    if last_fire_time and (current_time - last_fire_time) < laser_cooldown:
        return False, 'Laser cooling down'
    
    if not laser_enabled and not laser_mock_fire_mode:
        return False, 'Laser disabled'
    
    try:
        # In mock fire mode, only show visual indicator without firing
        if laser_mock_fire_mode:
            mock_fire_active = True
            mock_fire_time = current_time
            # Calculate total burst duration for visual feedback
            total_duration = (laser_pulse_duration * laser_burst_count) + (laser_burst_delay * (laser_burst_count - 1))
            print(f"🟡 MOCK FIRE! {laser_burst_count} pulse(s) - Power: {laser_power}% - Duration: {laser_pulse_duration}s each")
            
            # Schedule mock fire deactivation
            def deactivate_mock_fire():
                global mock_fire_active
                time.sleep(total_duration)
                mock_fire_active = False
            
            threading.Thread(target=deactivate_mock_fire, daemon=True).start()
            
            fire_count += laser_burst_count
            last_fire_time = current_time
            return True, f'Mock fired {laser_burst_count} pulse(s) at {laser_power}% power'
        
        # Real firing mode
        # Execute burst
        for pulse_num in range(laser_burst_count):
            if laser_control:
                # Real hardware: Use LaserControl with PWM
                print(f"🔴 LASER FIRE! Pulse {pulse_num + 1}/{laser_burst_count} - Power: {laser_power}% - Duration: {laser_pulse_duration}s")
                laser_control.pulse(laser_pulse_duration, power_level=laser_power)
            else:
                # Simulation mode
                print(f"🔴 LASER FIRE (SIM)! Pulse {pulse_num + 1}/{laser_burst_count} - Power: {laser_power}% - Duration: {laser_pulse_duration}s")
                time.sleep(laser_pulse_duration)
            
            fire_count += 1
            
            # Delay between burst pulses (except after last pulse)
            if pulse_num < laser_burst_count - 1:
                time.sleep(laser_burst_delay)
        
        last_fire_time = current_time
        return True, f'Fired {laser_burst_count} pulse(s) at {laser_power}% power'
    
    except Exception as e:
        return False, str(e)

def check_auto_fire():
    """Check if auto-fire conditions are met"""
    if not laser_auto_fire:
        return False
    
    # Auto-fire works with both real laser and mock fire mode
    if not laser_enabled and not laser_mock_fire_mode:
        return False
    
    # Check if object is detected and auto-track is on
    with object_lock:
        if object_auto_track and len(detected_objects) > 0:
            return True
    
    # Check if motion is detected and auto-track is on
    with motion_lock:
        if motion_auto_track and last_motion_center is not None:
            return True
    
    return False

def run_pattern_sequence():
    """Execute a pattern sequence in a separate thread"""
    global pattern_running, pattern_thread

    while pattern_running:
        for slot in pattern_sequence:
            if not pattern_running:
                break

            with preset_lock:
                pos = preset_positions.get(slot)

            if pos is None:
                print(f"Pattern: Slot {slot} missing, skipping")
                continue

            with crosshair_lock:
                crosshair_pos['x'] = pos['x']
                crosshair_pos['y'] = pos['y']

            print(f"Pattern: Moving to preset {slot} - {pos['label']}")

            # Move physical camera if tracking is enabled
            move_camera_to_absolute_position(pos['x'], pos['y'])

            time.sleep(pattern_delay)

        # If not looping, stop after one cycle
        if not pattern_running:
            break

        if not pattern_loop:
            pattern_running = False
            break

    pattern_thread = None


def move_camera_to_absolute_position(abs_x, abs_y, background=False):
    """Move the physical camera so the provided absolute coordinate is centered"""
    try:
        with tracking_mode_lock:
            tracking_active = tracking_mode == 'camera' and camera_tracking_enabled

        controller = stepper_controller
        if not tracking_active or controller is None:
            return False

        with crosshair_lock:
            adj_x = int(abs_x) - int(crosshair_offset['x'])
            adj_y = int(abs_y) - int(crosshair_offset['y'])

        def move():
            moved_local = controller.move_to_center_object(adj_x, adj_y, CAMERA_WIDTH, CAMERA_HEIGHT)
            if moved_local:
                print(f"Camera moved to preset position ({abs_x}, {abs_y})")
            else:
                print(f"Preset ({abs_x}, {abs_y}) within dead zone, no camera movement")
            return moved_local

        if background:
            threading.Thread(target=move, daemon=True).start()
            return True

        return move()
    except Exception as e:
        print(f"Error moving camera to preset position: {e}")
        return False


def halt_stepper_motion(reason: str = ""):
    """Stop ongoing stepper controller motion immediately."""
    global stepper_controller
    if stepper_controller is None:
        return
    try:
        stepper_controller.stop_motion()
        if reason:
            print(f"Stepper motion halted: {reason}")
    except Exception as exc:
        print(f"Warning: failed to halt stepper motion ({reason}): {exc}")

def initialize_tflite_detector():
    """Initialize TensorFlow Lite detector from config"""
    global tflite_detector, tflite_filter_classes, detection_method

    try:
        config = get_config()

        # Respect the current runtime selection; do not override detection_method from config here.
        if not TFLITE_AVAILABLE:
            print("TensorFlow Lite not available. Install with: pip install tflite-runtime")
            return

        model_name = config.get_tflite_model()
        use_coral = config.get_use_coral()
        confidence = config.get_tflite_confidence()
        tflite_filter_classes = config.get_tflite_filter_classes()

        print(f"Initializing TFLite detector: {model_name}")
        print(f"  Coral USB Accelerator: {use_coral}")
        print(f"  Confidence threshold: {confidence}")
        if tflite_filter_classes:
            print(f"  Filter classes: {', '.join(tflite_filter_classes)}")

        tflite_detector = TFLiteDetector(
            model_name=model_name,
            use_coral=use_coral,
            confidence_threshold=confidence
        )

        print("TFLite detector initialized successfully")
        print(f"  Stats: {tflite_detector.get_stats()}")

    except Exception as e:
        print(f"Warning: Failed to initialize TFLite detector: {e}")
        tflite_detector = None

def initialize_roboflow_detector():
    global roboflow_detector, roboflow_filter_classes, detection_method
    if not ROBOFLOW_AVAILABLE:
        print("Roboflow client not available. Using Haar Cascades.")
        detection_method = 'haar'
        return
    try:
        config = get_config()
        server_url = config.get_roboflow_server_url()
        model_id = config.get_roboflow_model_id()
        api_key = config.get_roboflow_api_key()
        confidence = config.get_roboflow_confidence()
        roboflow_filter_classes = config.get_roboflow_class_filter()
        if not model_id:
            raise RuntimeError("Roboflow model_id not set in config")
        print(f"Initializing Roboflow detector: {model_id}")
        print(f"  Server: {server_url}")
        print(f"  Confidence threshold: {confidence}")
        if roboflow_filter_classes:
            print(f"  Filter classes: {', '.join(roboflow_filter_classes)}")
        roboflow_detector = RoboflowDetector(
            server_url=server_url,
            model_id=model_id,
            api_key=api_key if api_key else None,
            confidence=confidence,
            class_filter=roboflow_filter_classes,
        )
        print("Roboflow detector initialized successfully")
        print(f"  Stats: {roboflow_detector.get_stats()}")
    except Exception as e:
        print(f"Warning: Failed to initialize Roboflow detector: {e}")
        print("Falling back to Haar Cascades")
        detection_method = 'haar'
        roboflow_detector = None

def initialize_cascades():
    """Initialize Haar Cascade classifiers for object detection"""
    global face_cascade, eye_cascade, body_cascade, smile_cascade
    
    # List of possible cascade file locations
    possible_paths = [
        # Try cv2.data if available
        (lambda: cv2.data.haarcascades if hasattr(cv2, 'data') else None)(),
        # Common OpenCV installation paths
        '/usr/share/opencv4/haarcascades/',
        '/usr/local/share/opencv4/haarcascades/',
        '/usr/share/opencv/haarcascades/',
        # Relative path (if cascades are in local directory)
        'haarcascades/',
        './',
    ]
    
    cascade_path = None
    for path in possible_paths:
        if path is None:
            continue
        try:
            # Test if path exists by trying to load a cascade
            test_path = path + 'haarcascade_frontalface_default.xml'
            test_cascade = cv2.CascadeClassifier(test_path)
            if not test_cascade.empty():
                cascade_path = path
                break
        except:
            continue
    
    if cascade_path:
        try:
            face_cascade = cv2.CascadeClassifier(cascade_path + 'haarcascade_frontalface_default.xml')
            eye_cascade = cv2.CascadeClassifier(cascade_path + 'haarcascade_eye.xml')
            body_cascade = cv2.CascadeClassifier(cascade_path + 'haarcascade_fullbody.xml')
            smile_cascade = cv2.CascadeClassifier(cascade_path + 'haarcascade_smile.xml')
            print(f"Object detection cascades initialized successfully from: {cascade_path}")
        except Exception as e:
            print(f"Warning: Could not load some cascade classifiers: {e}")
    else:
        print("Warning: Could not find Haar cascade files. Object detection will not work.")
        print("Please install opencv-data package or download cascade files manually.")

def initialize_balloon_settings():
    """Initialize balloon detection thresholds from config"""
    global balloon_v_threshold, balloon_min_area, balloon_circularity_min
    global balloon_fill_ratio_min, balloon_aspect_ratio_min, balloon_aspect_ratio_max
    try:
        config = get_config()
        balloon_v_threshold = int(config.get_balloon_v_threshold())
        balloon_min_area = int(config.get_balloon_min_area())
        balloon_circularity_min = float(config.get_balloon_circularity_min())
        balloon_fill_ratio_min = float(config.get_balloon_fill_ratio_min())
        balloon_aspect_ratio_min = float(config.get_balloon_aspect_ratio_min())
        balloon_aspect_ratio_max = float(config.get_balloon_aspect_ratio_max())
        print("Balloon settings initialized from config")
    except Exception as e:
        print(f"Warning: Failed to initialize balloon settings from config: {e}")

def detect_objects(frame):
    """Detect objects using either Haar Cascades or TensorFlow Lite"""
    global detected_objects, face_cascade, eye_cascade, body_cascade, smile_cascade
    global tflite_detector, tflite_filter_classes, detection_method
    
    objects = []
    
    try:
        # Use TensorFlow Lite detection
        if detection_method == 'tflite':
            if tflite_detector is None:
                initialize_tflite_detector()
            
            if tflite_detector is not None:
                # Run TFLite detection
                detections = tflite_detector.detect(frame)
                
                # Filter by class if specified
                if tflite_filter_classes:
                    detections = [d for d in detections if d['type'] in tflite_filter_classes]
                
                objects = detections
            else:
                # Fall back to Haar if TFLite failed
                detection_method = 'haar'
        
        # Use Roboflow inference server
        if detection_method == 'roboflow':
            if roboflow_detector is None:
                initialize_roboflow_detector()
            if roboflow_detector is not None:
                detections = roboflow_detector.detect(frame)
                if roboflow_filter_classes:
                    detections = [d for d in detections if d['type'] in roboflow_filter_classes]
                objects = detections
            else:
                detection_method = 'haar'
        
        # Use Haar Cascade detection
        if detection_method == 'haar':
            # Initialize cascades if needed
            if face_cascade is None:
                initialize_cascades()
            
            # Convert to grayscale for detection
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            
            if detection_mode == 'face' and face_cascade is not None:
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                objects = [{'type': 'face', 'rect': (x, y, w, h)} for x, y, w, h in faces]
            
            elif detection_mode == 'eye' and eye_cascade is not None:
                eyes = eye_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=10, minSize=(20, 20))
                objects = [{'type': 'eye', 'rect': (x, y, w, h)} for x, y, w, h in eyes]
            
            elif detection_mode == 'body' and body_cascade is not None:
                bodies = body_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(50, 100))
                objects = [{'type': 'body', 'rect': (x, y, w, h)} for x, y, w, h in bodies]
            
            elif detection_mode == 'smile' and smile_cascade is not None:
                smiles = smile_cascade.detectMultiScale(gray, scaleFactor=1.8, minNeighbors=20, minSize=(25, 25))
                objects = [{'type': 'smile', 'rect': (x, y, w, h)} for x, y, w, h in smiles]
            
            elif detection_mode == 'balloon':
                hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
                lower = np.array([0, 0, 0], dtype=np.uint8)
                upper = np.array([179, 255, int(balloon_v_threshold)], dtype=np.uint8)
                mask = cv2.inRange(hsv, lower, upper)
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                detections = []
                for c in contours:
                    area = cv2.contourArea(c)
                    if area < balloon_min_area:
                        continue
                    x, y, w, h = cv2.boundingRect(c)
                    ar = w / float(h) if h > 0 else 0
                    if ar < balloon_aspect_ratio_min or ar > balloon_aspect_ratio_max:
                        continue
                    peri = cv2.arcLength(c, True)
                    if peri <= 0:
                        continue
                    circ = 4.0 * np.pi * area / (peri * peri)
                    if circ < balloon_circularity_min:
                        continue
                    fill = area / float(w * h) if w > 0 and h > 0 else 0
                    if fill < balloon_fill_ratio_min:
                        continue
                    detections.append({'type': 'balloon', 'rect': (x, y, w, h)})
                objects = detections
    
    except Exception as e:
        print(f"Object detection error: {e}")
    
    detected_objects = objects
    return objects

def get_priority_target(objects):
    """Select target based on priority setting"""
    if not objects:
        return None
    
    if target_priority == 'largest':
        # Return object with largest area
        return max(objects, key=lambda obj: obj['rect'][2] * obj['rect'][3])
    
    elif target_priority == 'closest':
        # Return object with largest area (closer objects appear larger)
        return max(objects, key=lambda obj: obj['rect'][2] * obj['rect'][3])
    
    elif target_priority == 'leftmost':
        # Return leftmost object
        return min(objects, key=lambda obj: obj['rect'][0])
    
    elif target_priority == 'rightmost':
        # Return rightmost object
        return max(objects, key=lambda obj: obj['rect'][0])
    
    return objects[0]

def detect_motion(frame):
    """Detect motion in frame and return contours and motion center"""
    global background_subtractor, last_motion_center
    
    if background_subtractor is None:
        background_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=motion_bg_history, varThreshold=motion_sensitivity, detectShadows=False
        )
    
    # Convert to BGR for processing
    bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    bgr_frame = cv2.GaussianBlur(bgr_frame, (5, 5), 0)
    
    # Apply background subtraction
    fg_mask = background_subtractor.apply(bgr_frame, learningRate=motion_learning_rate)
    
    # Apply morphological operations to reduce noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (motion_kernel_size, motion_kernel_size))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
    fg_mask = cv2.dilate(fg_mask, kernel, iterations=1)
    
    # Find contours
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter contours by area and find the largest
    motion_contours = [c for c in contours if cv2.contourArea(c) > motion_min_area]
    
    motion_center = None
    if motion_contours:
        # Find the largest contour
        largest_contour = max(motion_contours, key=cv2.contourArea)
        M = cv2.moments(largest_contour)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            motion_center = (cx, cy)
            last_motion_center = motion_center
    else:
        # Clear last motion center when no motion detected
        last_motion_center = None
    
    return motion_contours, motion_center

def create_crosshair(frame, color=(0, 255, 0), thickness=3, opacity=0.5):
    """Draw crosshair, object detection, motion detection overlay, and exposure information"""
    overlay = np.zeros_like(frame, dtype=np.uint8)
    global object_track_smooth_center, object_last_switch_time, motion_smooth_center
    
    # Object/Face detection overlay
    with object_lock:
        if object_detection_enabled:
            try:
                objects = detect_objects(frame)
                
                # Draw all detected objects
                for obj in objects:
                    x, y, w, h = obj['rect']
                    # Draw rectangle
                    cv2.rectangle(overlay, (x, y), (x + w, y + h), (255, 255, 0), 2)
                    # Draw label
                    label = obj['type'].capitalize()
                    cv2.putText(overlay, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX,
                               0.7, (255, 255, 0), 2, cv2.LINE_AA)
                
                # Auto-track: select priority target
                if object_auto_track and objects:
                    target = get_priority_target(objects)
                    if target:
                        x, y, w, h = target['rect']
                        cx = x + w // 2
                        cy = y + h // 2

                        use_cx, use_cy = cx, cy
                        if object_track_smooth_center is not None and len(objects) > 0:
                            px, py = object_track_smooth_center
                            best_obj = None
                            best_dist = None
                            for obj in objects:
                                ox, oy, ow, oh = obj['rect']
                                ocx = ox + ow // 2
                                ocy = oy + oh // 2
                                d = ((ocx - px) ** 2 + (ocy - py) ** 2) ** 0.5
                                if best_dist is None or d < best_dist:
                                    best_dist = d
                                    best_obj = (ocx, ocy)
                            if best_obj is not None and best_dist is not None:
                                if best_dist < target_lock_distance:
                                    use_cx, use_cy = best_obj
                                else:
                                    if (time.time() - object_last_switch_time) < target_switch_cooldown:
                                        use_cx, use_cy = int(px), int(py)
                                    else:
                                        object_last_switch_time = time.time()

                        if object_track_smooth_center is None:
                            object_track_smooth_center = (float(use_cx), float(use_cy))
                        else:
                            sx = object_track_smooth_center[0] + tracking_smoothing_alpha * (use_cx - object_track_smooth_center[0])
                            sy = object_track_smooth_center[1] + tracking_smoothing_alpha * (use_cy - object_track_smooth_center[1])
                            object_track_smooth_center = (sx, sy)

                        sx_i = int(object_track_smooth_center[0])
                        sy_i = int(object_track_smooth_center[1])

                        cv2.circle(overlay, (sx_i, sy_i), 15, (0, 255, 255), 3)
                        cv2.circle(overlay, (sx_i, sy_i), 5, (0, 255, 255), -1)

                        with tracking_mode_lock:
                            if tracking_mode == 'crosshair':
                                with crosshair_lock:
                                    dx = sx_i - crosshair_pos['x']
                                    dy = sy_i - crosshair_pos['y']
                                    if (dx * dx + dy * dy) ** 0.5 > crosshair_dead_zone_pixels:
                                        crosshair_pos['x'] = sx_i
                                        crosshair_pos['y'] = sy_i
                            elif tracking_mode == 'camera' and camera_tracking_enabled and stepper_controller:
                                if not stepper_controller.moving:
                                    with crosshair_lock:
                                        tx = sx_i - int(crosshair_offset['x'])
                                        ty = sy_i - int(crosshair_offset['y'])
                                    try:
                                        stepper_controller.update_tracking_with_pid(tx, ty, CAMERA_WIDTH, CAMERA_HEIGHT)
                                    except Exception as e:
                                        print(f"PID update error (object tracking): {e}")
                        # If auto-track is enabled but there are no objects, stop motion
                if object_auto_track and not objects:
                    object_track_smooth_center = None
                    with tracking_mode_lock:
                        if tracking_mode == 'camera' and camera_tracking_enabled and stepper_controller:
                            try:
                                if camera_recenter_on_loss:
                                    stepper_controller.recenter_slowly()
                                else:
                                    stepper_controller.stop_motion()
                            except Exception as e:
                                print(f"Stop motion error (object tracking lost): {e}")
            except Exception as e:
                print(f"Object detection error: {e}")
    
    # Motion detection overlay
    with motion_lock:
        if motion_detection_enabled:
            try:
                motion_contours, motion_center = detect_motion(frame)
                
                # Draw motion contours
                if motion_contours:
                    for contour in motion_contours:
                        if cv2.contourArea(contour) > motion_min_area:
                            cv2.drawContours(overlay, [contour], -1, (0, 255, 255), 2)
                
                # Draw motion center
                if motion_center:
                    if motion_smooth_center is None:
                        motion_smooth_center = (float(motion_center[0]), float(motion_center[1]))
                    else:
                        mx = motion_smooth_center[0] + tracking_smoothing_alpha * (motion_center[0] - motion_smooth_center[0])
                        my = motion_smooth_center[1] + tracking_smoothing_alpha * (motion_center[1] - motion_smooth_center[1])
                        motion_smooth_center = (mx, my)

                    msx = int(motion_smooth_center[0])
                    msy = int(motion_smooth_center[1])
                    cv2.circle(overlay, (msx, msy), 10, (255, 0, 255), 2)
                    cv2.circle(overlay, (msx, msy), 3, (255, 0, 255), -1)
                    
                    if motion_auto_track and not object_auto_track:
                        with tracking_mode_lock:
                            if tracking_mode == 'crosshair':
                                with crosshair_lock:
                                    dx = msx - crosshair_pos['x']
                                    dy = msy - crosshair_pos['y']
                                    if (dx * dx + dy * dy) ** 0.5 > crosshair_dead_zone_pixels:
                                        crosshair_pos['x'] = msx
                                        crosshair_pos['y'] = msy
                            elif tracking_mode == 'camera' and camera_tracking_enabled and stepper_controller:
                                if not stepper_controller.moving:
                                    with crosshair_lock:
                                        tx = msx - int(crosshair_offset['x'])
                                        ty = msy - int(crosshair_offset['y'])
                                    try:
                                        stepper_controller.update_tracking_with_pid(tx, ty, CAMERA_WIDTH, CAMERA_HEIGHT)
                                    except Exception as e:
                                        print(f"PID update error (motion tracking): {e}")
                else:
                    motion_smooth_center = None
                    if motion_auto_track and not object_auto_track:
                        with tracking_mode_lock:
                            if tracking_mode == 'camera' and camera_tracking_enabled and stepper_controller:
                                try:
                                    if camera_recenter_on_loss:
                                        stepper_controller.recenter_slowly()
                                    else:
                                        stepper_controller.stop_motion()
                                except Exception as e:
                                    print(f"Stop motion error (motion tracking lost): {e}")
            except Exception as e:
                print(f"Motion detection error: {e}")
    
    # Determine crosshair position based on tracking mode
    with tracking_mode_lock:
        if tracking_mode == 'camera' and camera_tracking_enabled:
            with crosshair_lock:
                center_x = (CAMERA_WIDTH // 2) + int(crosshair_offset['x'])
                center_y = (CAMERA_HEIGHT // 2) + int(crosshair_offset['y'])
        else:
            with crosshair_lock:
                center_x = crosshair_pos['x']
                center_y = crosshair_pos['y']
    
    # Change crosshair color if mock firing is active
    crosshair_color = color
    with laser_lock:
        if mock_fire_active and laser_mock_fire_mode:
            crosshair_color = (0, 165, 255)  # Orange/red color for firing
    
    # Draw crosshair
    line_length = 40
    cv2.line(overlay, (center_x - line_length, center_y),
             (center_x + line_length, center_y),
             crosshair_color, thickness)
    cv2.line(overlay, (center_x, center_y - line_length),
             (center_x, center_y + line_length),
             crosshair_color, thickness)
    cv2.circle(overlay, (center_x, center_y), 6, crosshair_color, thickness)
    
    # Draw fire indicator icon when mock firing
    with laser_lock:
        if mock_fire_active and laser_mock_fire_mode:
            # Draw a pulsing fire indicator icon near crosshair
            icon_offset_y = -70
            icon_center_x = center_x
            icon_center_y = center_y + icon_offset_y
            
            # Draw a filled circle with "FIRE" text
            cv2.circle(overlay, (icon_center_x, icon_center_y), 35, (0, 165, 255), -1)
            cv2.circle(overlay, (icon_center_x, icon_center_y), 35, (0, 100, 255), 3)
            cv2.putText(overlay, "FIRE", (icon_center_x - 30, icon_center_y + 8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2, cv2.LINE_AA)
    
    # Add stats overlay
    with fps_lock:
        fps_text = f"FPS: {fps_value}"
    with exposure_lock:
        exp_text = f"Exp: {exposure_stats['exposure_time']/1000:.1f}ms"
        gain_text = f"Gain: {exposure_stats['analog_gain']:.1f}x"
    
    y_offset = 40
    texts = [fps_text, exp_text, gain_text]
    
    # Add object detection status
    with object_lock:
        if object_detection_enabled:
            if detection_method == 'haar':
                obj_text = f"Detect: {detection_mode.upper()} ({len(detected_objects)})"
            elif detection_method == 'tflite':
                obj_text = f"Detect: TFLITE ({len(detected_objects)})"
            elif detection_method == 'roboflow':
                obj_text = f"Detect: ROBOFLOW ({len(detected_objects)})"
            else:
                obj_text = f"Detect: {detection_method.upper()} ({len(detected_objects)})"
            if object_auto_track:
                obj_text += " [TRACK]"
            texts.append(obj_text)
    
    # Add motion detection status
    with motion_lock:
        if motion_detection_enabled:
            motion_text = "Motion: ON"
            if motion_auto_track:
                motion_text += " [TRACK]"
            texts.append(motion_text)
    
    # Add laser status
    with laser_lock:
        if laser_enabled:
            laser_text = f"Laser: ON [{fire_count}]"
            if laser_auto_fire:
                laser_text += " [AUTO]"
            texts.append(laser_text)
    
    # Add camera tracking mode status
    with tracking_mode_lock:
        if tracking_mode == 'camera':
            cam_track_text = "Track: CAMERA"
            if camera_tracking_enabled:
                cam_track_text += " [ON]"
            texts.append(cam_track_text)
    
    # Check and trigger auto-fire if conditions met
    if check_auto_fire():
        threading.Thread(target=fire_laser, daemon=True).start()
    
    for text in texts:
        cv2.putText(overlay, text, (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX,
                    1, color, 2, cv2.LINE_AA)
        y_offset += 40
    
    return cv2.addWeighted(frame, 1.0, overlay, opacity, 0)

def generate_frames():
    """Generate frames with crosshair overlay and FPS monitoring"""
    global output_frame, lock, last_frame_time, video_writer, is_recording
    
    # Check if camera is available
    if picam2 is None:
        # Return a placeholder frame if camera failed to initialize
        placeholder = np.zeros((CAMERA_HEIGHT, CAMERA_WIDTH, 3), dtype=np.uint8)
        cv2.putText(placeholder, "Camera Not Available", (CAMERA_WIDTH//2 - 300, CAMERA_HEIGHT//2), 
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3, cv2.LINE_AA)
        _, encoded_frame = cv2.imencode('.jpg', placeholder)
        placeholder_bytes = encoded_frame.tobytes()
        while True:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + placeholder_bytes + b'\r\n')
            time.sleep(1)
    
    while True:
        try:
            # Calculate frame time and FPS
            current_time = datetime.now()
            if last_frame_time is not None:
                frame_time = (current_time - last_frame_time).total_seconds()
                fps_buffer.append(frame_time)
                update_fps()
            last_frame_time = current_time
            
            # Capture frame - already in RGB format
            frame = picam2.capture_array()
            
            # Add crosshair
            frame = create_crosshair(frame, opacity=0.5)
            
            # Write frame to video file if recording
            with recording_lock:
                if is_recording and video_writer is not None:
                    try:
                        # Convert RGB to BGR for OpenCV
                        bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        video_writer.write(bgr_frame)
                    except Exception as e:
                        print(f"Error writing video frame: {e}")
            
            # Encode with high quality
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
            with lock:
                _, encoded_frame = cv2.imencode('.jpg', frame, encode_param)
                output_frame = encoded_frame.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + output_frame + b'\r\n')
            
        except Exception as e:
            print(f"Error in generate_frames: {e}")
            time.sleep(0.1)

def update_fps():
    """Calculate current FPS using rolling average"""
    global fps_value
    if len(fps_buffer) >= 2:
        # Calculate average FPS from the buffer
        fps = len(fps_buffer) / sum(fps_buffer)
        with fps_lock:
            fps_value = round(fps, 1)

@app.route('/')
def index():
    """Video streaming home page"""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/update_crosshair', methods=['POST'])
def update_crosshair():
    """Update crosshair position based on click coordinates"""
    data = request.get_json()
    with crosshair_lock:
        crosshair_pos['x'] = int(data['x'])
        crosshair_pos['y'] = int(data['y'])
    return jsonify({'status': 'success'})

@app.route('/reset_crosshair', methods=['POST'])
def reset_crosshair():
    """Reset crosshair to center position"""
    with crosshair_lock:
        # Reset to calibrated default (center + offset)
        crosshair_pos['x'] = (CAMERA_WIDTH // 2) + int(crosshair_offset['x'])
        crosshair_pos['y'] = (CAMERA_HEIGHT // 2) + int(crosshair_offset['y'])
    return jsonify({
        'status': 'success',
        'x': crosshair_pos['x'],
        'y': crosshair_pos['y']
    })

@app.route('/get_crosshair_position')
def get_crosshair_position():
    """Get crosshair position in relative coordinates (centered at 0,0)"""
    with tracking_mode_lock:
        if tracking_mode == 'camera' and camera_tracking_enabled:
            # In camera tracking mode, crosshair shown at center + offset
            with crosshair_lock:
                abs_x = (CAMERA_WIDTH // 2) + int(crosshair_offset['x'])
                abs_y = (CAMERA_HEIGHT // 2) + int(crosshair_offset['y'])
                rel_x = int(crosshair_offset['x'])
                rel_y = -int(crosshair_offset['y'])  # Invert Y axis for relative coords
            return jsonify({
                'status': 'success',
                'absolute_x': abs_x,
                'absolute_y': abs_y,
                'relative_x': rel_x,
                'relative_y': rel_y
            })
        else:
            # In crosshair mode, calculate actual crosshair position
            with crosshair_lock:
                # Calculate relative position from center
                # Center of frame is (0, 0)
                # X increases to the right, Y increases upward (inverted from image coordinates)
                center_x = CAMERA_WIDTH // 2
                center_y = CAMERA_HEIGHT // 2
                
                relative_x = crosshair_pos['x'] - center_x
                relative_y = center_y - crosshair_pos['y']  # Invert Y axis
                
                return jsonify({
                    'status': 'success',
                    'absolute_x': crosshair_pos['x'],
                    'absolute_y': crosshair_pos['y'],
                    'relative_x': relative_x,
                    'relative_y': relative_y
                })

@app.route('/crosshair/calibration', methods=['GET'])
def get_crosshair_calibration():
    with crosshair_lock:
        center_x = CAMERA_WIDTH // 2
        center_y = CAMERA_HEIGHT // 2
        abs_x = center_x + int(crosshair_offset['x'])
        abs_y = center_y + int(crosshair_offset['y'])
        return jsonify({
            'status': 'success',
            'offset': {'x': int(crosshair_offset['x']), 'y': int(crosshair_offset['y'])},
            'absolute': {'x': abs_x, 'y': abs_y}
        })

@app.route('/crosshair/calibration/set', methods=['POST'])
def set_crosshair_calibration():
    try:
        data = request.get_json()
        x = int(data.get('x'))
        y = int(data.get('y'))
        x = max(0, min(CAMERA_WIDTH - 1, x))
        y = max(0, min(CAMERA_HEIGHT - 1, y))
        cx = CAMERA_WIDTH // 2
        cy = CAMERA_HEIGHT // 2
        with crosshair_lock:
            crosshair_offset['x'] = int(x - cx)
            crosshair_offset['y'] = int(y - cy)
            save_crosshair_calibration()
            crosshair_pos['x'] = cx + int(crosshair_offset['x'])
            crosshair_pos['y'] = cy + int(crosshair_offset['y'])
            return jsonify({
                'status': 'success',
                'offset': {'x': int(crosshair_offset['x']), 'y': int(crosshair_offset['y'])},
                'absolute': {'x': crosshair_pos['x'], 'y': crosshair_pos['y']}
            })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/crosshair/calibration/reset', methods=['POST'])
def reset_crosshair_calibration():
    with crosshair_lock:
        crosshair_offset['x'] = 0
        crosshair_offset['y'] = 0
        save_crosshair_calibration()
        crosshair_pos['x'] = CAMERA_WIDTH // 2
        crosshair_pos['y'] = CAMERA_HEIGHT // 2
        return jsonify({
            'status': 'success',
            'offset': {'x': 0, 'y': 0},
            'absolute': {'x': crosshair_pos['x'], 'y': crosshair_pos['y']}
        })

@app.route('/get_fps')
def get_fps():
    """Return current FPS value"""
    with fps_lock:
        return jsonify({'fps': fps_value})

@app.route('/exposure_stats')
def get_exposure_stats():
    """Return current exposure statistics"""
    with exposure_lock:
        return jsonify(exposure_stats)

@app.route('/set_exposure', methods=['POST'])
def set_exposure():
    """Set exposure mode and parameters"""
    if picam2 is None:
        return jsonify({'status': 'error', 'message': 'Camera not available'}), 503
    
    try:
        data = request.get_json()
        controls = {}
        
        if 'auto' in data:
            controls['AeEnable'] = bool(data['auto'])
        
        if 'exposure_time' in data and data['exposure_time'] is not None and not data.get('auto', True):
            # Only set manual exposure if auto is disabled
            controls['ExposureTime'] = int(data['exposure_time'])
        
        if 'analog_gain' in data and data['analog_gain'] is not None and not data.get('auto', True):
            controls['AnalogueGain'] = float(data['analog_gain'])
        
        if 'digital_gain' in data and data['digital_gain'] is not None and not data.get('auto', True):
            controls['DigitalGain'] = float(data['digital_gain'])
        
        if controls:
            picam2.set_controls(controls)
            return jsonify({'status': 'success', 'controls': controls})
        
        return jsonify({'status': 'success', 'message': 'No changes'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/set_image_params', methods=['POST'])
def set_image_params():
    """Set image parameters like brightness, contrast, saturation"""
    if picam2 is None:
        return jsonify({'status': 'error', 'message': 'Camera not available'}), 503
    
    try:
        data = request.get_json()
        controls = {}
        
        if 'brightness' in data and data['brightness'] is not None:
            controls['Brightness'] = float(data['brightness'])
        
        if 'contrast' in data and data['contrast'] is not None:
            controls['Contrast'] = float(data['contrast'])
        
        if 'saturation' in data and data['saturation'] is not None:
            controls['Saturation'] = float(data['saturation'])
        
        if controls:
            picam2.set_controls(controls)
            return jsonify({'status': 'success', 'controls': controls})
        
        return jsonify({'status': 'success', 'message': 'No changes'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/set_white_balance', methods=['POST'])
def set_white_balance():
    """Set white balance mode"""
    if picam2 is None:
        return jsonify({'status': 'error', 'message': 'Camera not available'}), 503
    
    try:
        data = request.get_json()
        controls = {}
        
        if 'auto' in data:
            controls['AwbEnable'] = bool(data['auto'])
        
        if 'mode' in data and data['mode'] is not None:
            controls['AwbMode'] = int(data['mode'])
        
        if controls:
            picam2.set_controls(controls)
            return jsonify({'status': 'success', 'controls': controls})
        
        return jsonify({'status': 'success', 'message': 'No changes'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/capture_image', methods=['POST'])
def capture_image():
    """Capture and save a still image"""
    if picam2 is None:
        return jsonify({'status': 'error', 'message': 'Camera not available'}), 503
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"capture_{timestamp}.jpg"
        
        # Capture high quality image
        picam2.capture_file(filename)
        
        return jsonify({
            'status': 'success',
            'filename': filename,
            'message': f'Image saved as {filename}'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_camera_settings')
def get_camera_settings():
    """Get current camera settings"""
    if picam2 is None:
        return jsonify({'status': 'error', 'message': 'Camera not available'}), 503
    
    try:
        metadata = picam2.capture_metadata()
        return jsonify({
            'status': 'success',
            'settings': {
                'exposure_time': metadata.get('ExposureTime', 0),
                'analog_gain': metadata.get('AnalogueGain', 0),
                'digital_gain': metadata.get('DigitalGain', 0),
                'color_gains': metadata.get('ColourGains', [0, 0]),
                'lux': metadata.get('Lux', 0)
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/start_recording', methods=['POST'])
def start_recording():
    """Start recording video to file"""
    global is_recording, video_writer, recording_filename, recording_start_time
    
    if picam2 is None:
        return jsonify({'status': 'error', 'message': 'Camera not available'}), 503
    
    with recording_lock:
        if is_recording:
            return jsonify({'status': 'error', 'message': 'Already recording'}), 400
        
        try:
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            recording_filename = f"video_{timestamp}.mp4"
            
            # Initialize video writer
            # Using mp4v codec for MP4 container
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            
            # Get actual FPS or use default
            actual_fps = fps_value if fps_value > 0 else 30.0
            
            video_writer = cv2.VideoWriter(
                recording_filename,
                fourcc,
                actual_fps,
                (CAMERA_WIDTH, CAMERA_HEIGHT)
            )
            
            if not video_writer.isOpened():
                video_writer = None
                return jsonify({'status': 'error', 'message': 'Failed to open video writer'}), 500
            
            is_recording = True
            recording_start_time = datetime.now()
            
            return jsonify({
                'status': 'success',
                'filename': recording_filename,
                'message': 'Recording started'
            })
        except Exception as e:
            is_recording = False
            video_writer = None
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    """Stop recording video"""
    global is_recording, video_writer, recording_filename, recording_start_time
    
    with recording_lock:
        if not is_recording:
            return jsonify({'status': 'error', 'message': 'Not currently recording'}), 400
        
        try:
            filename = recording_filename
            duration = None
            
            if recording_start_time:
                duration = (datetime.now() - recording_start_time).total_seconds()
            
            # Release video writer
            if video_writer is not None:
                video_writer.release()
                video_writer = None
            
            is_recording = False
            recording_start_time = None
            
            return jsonify({
                'status': 'success',
                'filename': filename,
                'duration': duration,
                'message': f'Recording stopped. Saved as {filename}'
            })
        except Exception as e:
            is_recording = False
            video_writer = None
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/recording_status')
def recording_status():
    """Get current recording status"""
    with recording_lock:
        if is_recording and recording_start_time:
            duration = (datetime.now() - recording_start_time).total_seconds()
            return jsonify({
                'status': 'success',
                'is_recording': True,
                'filename': recording_filename,
                'duration': duration
            })
        else:
            return jsonify({
                'status': 'success',
                'is_recording': False
            })

@app.route('/motion_detection/toggle', methods=['POST'])
def toggle_motion_detection():
    """Toggle motion detection on/off"""
    global motion_detection_enabled, background_subtractor
    
    try:
        data = request.get_json()
        with motion_lock:
            motion_detection_enabled = bool(data.get('enabled', not motion_detection_enabled))
            
            # Reset background subtractor when toggling
            if not motion_detection_enabled:
                background_subtractor = None
        
        return jsonify({
            'status': 'success',
            'enabled': motion_detection_enabled
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/motion_detection/auto_track', methods=['POST'])
def toggle_auto_track():
    """Toggle auto-tracking on/off"""
    global motion_auto_track, motion_smooth_center
    
    try:
        data = request.get_json()
        with motion_lock:
            new_state = bool(data.get('enabled', not motion_auto_track))
            motion_auto_track = new_state
            if not motion_auto_track:
                motion_smooth_center = None
        if not motion_auto_track:
            halt_stepper_motion("motion auto-track disabled")
        
        return jsonify({
            'status': 'success',
            'enabled': motion_auto_track
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/motion_detection/settings', methods=['POST'])
def update_motion_settings():
    """Update motion detection settings"""
    global motion_sensitivity, motion_min_area, background_subtractor
    
    try:
        data = request.get_json()
        with motion_lock:
            if 'sensitivity' in data:
                motion_sensitivity = int(data['sensitivity'])
                # Reset background subtractor to apply new sensitivity
                background_subtractor = None
            
            if 'min_area' in data:
                motion_min_area = int(data['min_area'])
        
        return jsonify({
            'status': 'success',
            'sensitivity': motion_sensitivity,
            'min_area': motion_min_area
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/motion_detection/status')
def motion_detection_status():
    """Get current motion detection status and settings"""
    with motion_lock:
        return jsonify({
            'status': 'success',
            'enabled': motion_detection_enabled,
            'auto_track': motion_auto_track,
            'sensitivity': motion_sensitivity,
            'min_area': motion_min_area,
            'motion_detected': last_motion_center is not None,
            'motion_center': last_motion_center
        })

@app.route('/object_detection/toggle', methods=['POST'])
def toggle_object_detection():
    """Toggle object/face detection on/off"""
    global object_detection_enabled
    
    try:
        data = request.get_json()
        with object_lock:
            object_detection_enabled = bool(data.get('enabled', not object_detection_enabled))
        
        return jsonify({
            'status': 'success',
            'enabled': object_detection_enabled
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/object_detection/auto_track', methods=['POST'])
def toggle_object_auto_track():
    """Toggle object auto-tracking on/off"""
    global object_auto_track, object_track_smooth_center
    
    try:
        data = request.get_json()
        with object_lock:
            new_state = bool(data.get('enabled', not object_auto_track))
            object_auto_track = new_state
            if not object_auto_track:
                object_track_smooth_center = None
        if not object_auto_track:
            halt_stepper_motion("object auto-track disabled")
        
        return jsonify({
            'status': 'success',
            'enabled': object_auto_track
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/object_detection/settings', methods=['POST'])
def update_object_settings():
    """Update object detection settings"""
    global detection_mode, target_priority
    
    try:
        data = request.get_json()
        with object_lock:
            if 'mode' in data:
                detection_mode = data['mode']
            
            if 'priority' in data:
                target_priority = data['priority']
        
        return jsonify({
            'status': 'success',
            'mode': detection_mode,
            'priority': target_priority
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/object_detection/status')
def object_detection_status():
    """Get current object detection status and settings"""
    with object_lock:
        # Get TFLite/Roboflow stats if available
        tflite_stats = None
        if detection_method == 'tflite' and tflite_detector is not None:
            tflite_stats = tflite_detector.get_stats()
        roboflow_stats = None
        if detection_method == 'roboflow' and roboflow_detector is not None:
            roboflow_stats = roboflow_detector.get_stats()
        
        return jsonify({
            'status': 'success',
            'enabled': object_detection_enabled,
            'auto_track': object_auto_track,
            'mode': detection_mode,
            'detection_method': detection_method,
            'priority': target_priority,
            'objects_detected': len(detected_objects),
            'objects': [{'type': obj['type'], 'rect': [int(v) for v in obj['rect']]} for obj in detected_objects],
            'tflite_available': TFLITE_AVAILABLE,
            'tflite_stats': tflite_stats,
            'roboflow_available': ROBOFLOW_AVAILABLE,
            'roboflow_stats': roboflow_stats,
            'balloon_settings': {
                'v_threshold': int(balloon_v_threshold),
                'min_area': int(balloon_min_area),
                'circularity_min': float(balloon_circularity_min),
                'fill_ratio_min': float(balloon_fill_ratio_min),
                'aspect_ratio_min': float(balloon_aspect_ratio_min),
                'aspect_ratio_max': float(balloon_aspect_ratio_max),
            }
        })

@app.route('/detection_method/config')
def detection_method_config():
    try:
        config = get_config()
        method = config.get_detection_method()
        return jsonify({'status': 'success', 'method': method})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/detection_method/switch', methods=['POST'])
def switch_detection_method():
    """Switch between Haar Cascades, TensorFlow Lite, and Roboflow"""
    global detection_method, tflite_detector
    
    try:
        data = request.get_json()
        method = data.get('method', 'haar')
        
        if method not in ['haar', 'tflite', 'roboflow']:
            return jsonify({
                'status': 'error',
                'message': 'Invalid method. Must be "haar", "tflite", or "roboflow"'
            }), 400
        
        if method == 'tflite' and not TFLITE_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'TensorFlow Lite is not available. Install with: pip install tflite-runtime'
            }), 400
        if method == 'roboflow' and not ROBOFLOW_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Roboflow inference client is not available. Install with: pip install inference-sdk'
            }), 400
        
        # Switch method
        old_method = detection_method
        detection_method = method
        
        # Initialize TFLite if needed
        if method == 'tflite' and tflite_detector is None:
            initialize_tflite_detector()
            
            if tflite_detector is None:
                detection_method = old_method
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to initialize TFLite detector'
                }), 500
        # Initialize Roboflow if needed
        if method == 'roboflow' and roboflow_detector is None:
            initialize_roboflow_detector()
            if roboflow_detector is None:
                detection_method = old_method
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to initialize Roboflow detector'
                }), 500
        
        return jsonify({
            'status': 'success',
            'message': f'Switched to {method}',
            'detection_method': detection_method,
            'tflite_stats': tflite_detector.get_stats() if tflite_detector else None,
            'roboflow_stats': roboflow_detector.get_stats() if roboflow_detector else None
        })
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tflite/settings', methods=['POST'])
def update_tflite_settings():
    """Update TensorFlow Lite detection settings at runtime"""
    global tflite_detector, tflite_filter_classes
    
    try:
        if detection_method != 'tflite':
            return jsonify({
                'status': 'error',
                'message': 'TensorFlow Lite is not currently active'
            }), 400
        
        if tflite_detector is None:
            return jsonify({
                'status': 'error',
                'message': 'TensorFlow Lite detector not initialized'
            }), 400
        
        data = request.get_json()
        confidence = data.get('confidence')
        filter_classes = data.get('filter_classes', '')
        
        # Update confidence threshold if provided
        if confidence is not None:
            confidence = float(confidence)
            if 0.0 <= confidence <= 1.0:
                tflite_detector.confidence_threshold = confidence
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Confidence must be between 0.0 and 1.0'
                }), 400
        
        # Update class filter if provided
        if filter_classes is not None:
            # Parse comma-separated classes
            if filter_classes.strip():
                tflite_filter_classes = [c.strip() for c in filter_classes.split(',') if c.strip()]
            else:
                tflite_filter_classes = []
        
        return jsonify({
            'status': 'success',
            'message': 'TFLite settings applied',
            'confidence': tflite_detector.confidence_threshold,
            'filter_classes': tflite_filter_classes,
            'stats': tflite_detector.get_stats()
        })
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/roboflow/settings', methods=['POST'])
def update_roboflow_settings():
    global roboflow_detector, roboflow_filter_classes
    try:
        if not ROBOFLOW_AVAILABLE:
            return jsonify({
                'status': 'error',
                'message': 'Roboflow client not available'
            }), 400
        data = request.get_json()
        server_url = data.get('server_url')
        model_id = data.get('model_id')
        api_key = data.get('api_key')
        confidence = data.get('confidence')
        filter_classes = data.get('filter_classes')
        need_reinit = False
        if server_url is not None or model_id is not None or api_key is not None:
            need_reinit = True
        if confidence is not None and roboflow_detector is not None:
            try:
                c = float(confidence)
                if 0.0 <= c <= 1.0:
                    roboflow_detector.confidence = c
                else:
                    return jsonify({'status': 'error', 'message': 'Confidence must be between 0.0 and 1.0'}), 400
            except Exception:
                return jsonify({'status': 'error', 'message': 'Invalid confidence value'}), 400
        if filter_classes is not None:
            if isinstance(filter_classes, str):
                roboflow_filter_classes = [c.strip() for c in filter_classes.split(',') if c.strip()]
            elif isinstance(filter_classes, list):
                roboflow_filter_classes = [str(c).strip() for c in filter_classes if str(c).strip()]
            else:
                roboflow_filter_classes = []
            # Update detector runtime filter as well
            if roboflow_detector is not None:
                roboflow_detector.class_filter = list(roboflow_filter_classes)
        if need_reinit:
            srv = server_url if server_url is not None else (roboflow_detector.server_url if roboflow_detector else 'http://localhost:9001')
            mid = model_id if model_id is not None else (roboflow_detector.model_id if roboflow_detector else '')
            # If API key omitted, reuse existing key (if any)
            key = api_key if api_key is not None else (roboflow_detector.api_key if roboflow_detector else None)
            if not mid:
                return jsonify({'status': 'error', 'message': 'model_id is required'}), 400
            roboflow_detector = RoboflowDetector(
                server_url=srv,
                model_id=mid,
                api_key=key,
                confidence=roboflow_detector.confidence if roboflow_detector else 0.5,
                class_filter=roboflow_filter_classes,
            )
        return jsonify({
            'status': 'success',
            'message': 'Roboflow settings applied',
            'confidence': roboflow_detector.confidence if roboflow_detector else None,
            'filter_classes': roboflow_filter_classes,
            'stats': roboflow_detector.get_stats() if roboflow_detector else None
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/presets/save', methods=['POST'])
def save_preset():
    """Save current crosshair position to a preset slot"""
    try:
        data = request.get_json()
        slot = int(data.get('slot'))
        label = data.get('label', f'Preset {slot}')
        
        if slot < 1 or slot > 10:
            return jsonify({'status': 'error', 'message': 'Slot must be between 1 and 10'}), 400
        
        with crosshair_lock:
            x = crosshair_pos['x']
            y = crosshair_pos['y']
        
        with preset_lock:
            preset_positions[slot] = {
                'x': x,
                'y': y,
                'label': label
            }
        
        return jsonify({
            'status': 'success',
            'slot': slot,
            'position': {'x': x, 'y': y},
            'label': label
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/presets/load/<int:slot>', methods=['POST'])
def load_preset(slot):
    """Load a preset position to the crosshair"""
    try:
        if slot < 1 or slot > 10:
            return jsonify({'status': 'error', 'message': 'Slot must be between 1 and 10'}), 400
        
        with preset_lock:
            if slot not in preset_positions:
                return jsonify({'status': 'error', 'message': f'No preset saved in slot {slot}'}), 404
            
            preset = preset_positions[slot]
        
        with crosshair_lock:
            crosshair_pos['x'] = preset['x']
            crosshair_pos['y'] = preset['y']

        move_started = move_camera_to_absolute_position(preset['x'], preset['y'], background=True)

        return jsonify({
            'status': 'success',
            'slot': slot,
            'position': {'x': preset['x'], 'y': preset['y']},
            'label': preset['label'],
            'camera_move_started': move_started
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/presets/delete/<int:slot>', methods=['POST'])
def delete_preset(slot):
    """Delete a preset position"""
    try:
        if slot < 1 or slot > 10:
            return jsonify({'status': 'error', 'message': 'Slot must be between 1 and 10'}), 400
        
        with preset_lock:
            if slot in preset_positions:
                del preset_positions[slot]
                return jsonify({'status': 'success', 'slot': slot})
            else:
                return jsonify({'status': 'error', 'message': f'No preset in slot {slot}'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/presets/list')
def list_presets():
    """Get all saved presets"""
    with preset_lock:
        presets = {
            slot: {
                'x': pos['x'],
                'y': pos['y'],
                'label': pos['label']
            }
            for slot, pos in preset_positions.items()
        }
    
    return jsonify({
        'status': 'success',
        'presets': presets
    })

@app.route('/presets/pattern/start', methods=['POST'])
def start_pattern():
    """Start executing a pattern sequence"""
    global pattern_running, pattern_thread, pattern_sequence, pattern_delay, pattern_loop
    
    try:
        data = request.get_json()
        sequence = data.get('sequence', [])
        delay = float(data.get('delay', 1.0))
        loop = bool(data.get('loop', True))
        
        if not sequence:
            return jsonify({'status': 'error', 'message': 'Empty sequence'}), 400
        
        # Validate sequence slots
        for slot in sequence:
            if slot < 1 or slot > 10:
                return jsonify({'status': 'error', 'message': f'Invalid slot {slot}'}), 400
            with preset_lock:
                if slot not in preset_positions:
                    return jsonify({'status': 'error', 'message': f'No preset in slot {slot}'}), 404
        
        # Stop existing pattern if running
        if pattern_running:
            pattern_running = False
            if pattern_thread:
                pattern_thread.join(timeout=2)
            pattern_thread = None

        pattern_sequence = sequence
        pattern_delay = delay
        pattern_loop = loop
        pattern_running = True

        # Start pattern thread
        pattern_thread = threading.Thread(target=run_pattern_sequence, daemon=True)
        pattern_thread.start()
        
        return jsonify({
            'status': 'success',
            'sequence': sequence,
            'delay': delay,
            'loop': loop
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/presets/pattern/stop', methods=['POST'])
def stop_pattern():
    """Stop the running pattern sequence"""
    global pattern_running, pattern_loop

    pattern_running = False
    pattern_loop = False

    return jsonify({
        'status': 'success',
        'message': 'Pattern stopped'
    })

@app.route('/presets/pattern/status')
def pattern_status():
    """Get pattern execution status"""
    return jsonify({
        'status': 'success',
        'running': pattern_running,
        'sequence': pattern_sequence,
        'delay': pattern_delay,
        'loop': pattern_loop
    })

@app.route('/laser/toggle', methods=['POST'])
def toggle_laser():
    """Enable/disable laser system"""
    global laser_enabled
    
    try:
        data = request.get_json()
        with laser_lock:
            laser_enabled = bool(data.get('enabled', not laser_enabled))
        
        return jsonify({
            'status': 'success',
            'enabled': laser_enabled
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/laser/fire', methods=['POST'])
def manual_fire():
    """Manually fire the laser"""
    success, message = fire_laser()
    
    if success:
        return jsonify({
            'status': 'success',
            'message': message,
            'fire_count': fire_count
        })
    else:
        return jsonify({
            'status': 'error',
            'message': message
        }), 400

@app.route('/laser/auto_fire', methods=['POST'])
def toggle_auto_fire():
    """Toggle auto-fire mode"""
    global laser_auto_fire
    
    try:
        data = request.get_json()
        with laser_lock:
            laser_auto_fire = bool(data.get('enabled', not laser_auto_fire))
        
        return jsonify({
            'status': 'success',
            'enabled': laser_auto_fire
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/laser/settings', methods=['POST'])
def update_laser_settings():
    """Update laser fire settings"""
    global laser_pulse_duration, laser_burst_count, laser_burst_delay, laser_cooldown, laser_power
    
    try:
        data = request.get_json()
        with laser_lock:
            if 'pulse_duration' in data:
                laser_pulse_duration = float(data['pulse_duration'])
            
            if 'burst_count' in data:
                laser_burst_count = int(data['burst_count'])
            
            if 'burst_delay' in data:
                laser_burst_delay = float(data['burst_delay'])
            
            if 'cooldown' in data:
                laser_cooldown = float(data['cooldown'])
            
            if 'power' in data:
                power = int(data['power'])
                if 0 <= power <= 100:
                    laser_power = power
                    if laser_control:
                        laser_control.set_power(laser_power)
                else:
                    return jsonify({'status': 'error', 'message': 'Power must be 0-100'}), 400
        
        return jsonify({
            'status': 'success',
            'pulse_duration': laser_pulse_duration,
            'burst_count': laser_burst_count,
            'burst_delay': laser_burst_delay,
            'cooldown': laser_cooldown,
            'power': laser_power
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/laser/status')
def laser_status():
    """Get laser system status"""
    with laser_lock:
        cooldown_remaining = 0
        if last_fire_time:
            elapsed = time.time() - last_fire_time
            cooldown_remaining = max(0, laser_cooldown - elapsed)
        
        return jsonify({
            'status': 'success',
            'enabled': laser_enabled,
            'auto_fire': laser_auto_fire,
            'mock_fire_mode': laser_mock_fire_mode,
            'pulse_duration': laser_pulse_duration,
            'burst_count': laser_burst_count,
            'burst_delay': laser_burst_delay,
            'cooldown': laser_cooldown,
            'cooldown_remaining': cooldown_remaining,
            'fire_count': fire_count,
            'ready_to_fire': cooldown_remaining == 0,
            'power': laser_power,
            'hardware_available': laser_control is not None
        })

@app.route('/laser/mock_fire', methods=['POST'])
def toggle_mock_fire():
    """Toggle mock fire mode"""
    global laser_mock_fire_mode
    
    try:
        data = request.get_json()
        with laser_lock:
            laser_mock_fire_mode = bool(data.get('enabled', not laser_mock_fire_mode))
        
        return jsonify({
            'status': 'success',
            'enabled': laser_mock_fire_mode
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/laser/reset_count', methods=['POST'])
def reset_fire_count():
    """Reset fire counter"""
    global fire_count
    
    with laser_lock:
        fire_count = 0
    
    return jsonify({
        'status': 'success',
        'fire_count': 0
    })

@app.route('/balloon/settings', methods=['POST'])
def update_balloon_settings():
    """Update balloon detection thresholds at runtime"""
    global balloon_v_threshold, balloon_min_area, balloon_circularity_min
    global balloon_fill_ratio_min, balloon_aspect_ratio_min, balloon_aspect_ratio_max
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

        if 'v_threshold' in data:
            v = int(data['v_threshold'])
            if 0 <= v <= 255:
                balloon_v_threshold = v
            else:
                return jsonify({'status': 'error', 'message': 'v_threshold must be 0-255'}), 400

        if 'min_area' in data:
            a = int(data['min_area'])
            if a >= 0:
                balloon_min_area = a
            else:
                return jsonify({'status': 'error', 'message': 'min_area must be >= 0'}), 400

        if 'circularity_min' in data:
            c = float(data['circularity_min'])
            if 0.0 <= c <= 1.0:
                balloon_circularity_min = c
            else:
                return jsonify({'status': 'error', 'message': 'circularity_min must be 0.0-1.0'}), 400

        if 'fill_ratio_min' in data:
            f = float(data['fill_ratio_min'])
            if 0.0 <= f <= 1.0:
                balloon_fill_ratio_min = f
            else:
                return jsonify({'status': 'error', 'message': 'fill_ratio_min must be 0.0-1.0'}), 400

        if 'aspect_ratio_min' in data:
            ar_min = float(data['aspect_ratio_min'])
            if ar_min >= 0.0:
                balloon_aspect_ratio_min = ar_min
            else:
                return jsonify({'status': 'error', 'message': 'aspect_ratio_min must be >= 0.0'}), 400

        if 'aspect_ratio_max' in data:
            ar_max = float(data['aspect_ratio_max'])
            if ar_max >= 0.0:
                balloon_aspect_ratio_max = ar_max
            else:
                return jsonify({'status': 'error', 'message': 'aspect_ratio_max must be >= 0.0'}), 400

        return jsonify({
            'status': 'success',
            'balloon_settings': {
                'v_threshold': int(balloon_v_threshold),
                'min_area': int(balloon_min_area),
                'circularity_min': float(balloon_circularity_min),
                'fill_ratio_min': float(balloon_fill_ratio_min),
                'aspect_ratio_min': float(balloon_aspect_ratio_min),
                'aspect_ratio_max': float(balloon_aspect_ratio_max),
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

# Camera tracking mode endpoints
@app.route('/tracking/mode', methods=['POST'])
def set_tracking_mode():
    """Set tracking mode (crosshair or camera)"""
    global tracking_mode, camera_tracking_enabled
    
    try:
        data = request.get_json()
        mode = data.get('mode', 'crosshair')
        
        if mode not in ['crosshair', 'camera']:
            return jsonify({'status': 'error', 'message': 'Invalid mode. Must be "crosshair" or "camera"'}), 400
        
        with tracking_mode_lock:
            # If switching to camera mode, verify stepper controller is available
            if mode == 'camera' and stepper_controller is None:
                return jsonify({
                    'status': 'error',
                    'message': 'Camera tracking not available. Stepper controller not initialized.'
                }), 503
            
            # Disable camera tracking when switching to crosshair mode
            if mode == 'crosshair':
                camera_tracking_enabled = False
                if stepper_controller:
                    stepper_controller.disable()
            
            tracking_mode = mode
        
        return jsonify({
            'status': 'success',
            'mode': tracking_mode
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/toggle', methods=['POST'])
def toggle_camera_tracking():
    """Enable/disable camera tracking"""
    global camera_tracking_enabled
    
    try:
        if stepper_controller is None:
            return jsonify({
                'status': 'error',
                'message': 'Stepper controller not available'
            }), 503
        
        data = request.get_json()
        enabled = bool(data.get('enabled', not camera_tracking_enabled))
        
        with tracking_mode_lock:
            if tracking_mode != 'camera':
                return jsonify({
                    'status': 'error',
                    'message': 'Must be in camera tracking mode first'
                }), 400
            
            # Check calibration requirement before enabling
            if enabled and not stepper_controller.is_calibrated():
                return jsonify({
                    'status': 'error',
                    'message': 'Calibration required before enabling camera movement. Please run Auto-Calibrate first.'
                }), 400
            
            camera_tracking_enabled = enabled
            
            if enabled:
                stepper_controller.enable()
            else:
                stepper_controller.disable()
        
        return jsonify({
            'status': 'success',
            'enabled': camera_tracking_enabled
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/home', methods=['POST'])
def home_camera():
    """Home the camera to center position"""
    try:
        if stepper_controller is None:
            return jsonify({'status': 'error', 'message': 'Stepper controller not available'}), 503
        
        if not camera_tracking_enabled:
            return jsonify({'status': 'error', 'message': 'Camera tracking not enabled'}), 400
        
        # Home in background thread
        threading.Thread(target=stepper_controller.home, daemon=True).start()
        
        return jsonify({
            'status': 'success',
            'message': 'Homing camera to center position'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/calibrate', methods=['POST'])
def calibrate_camera_tracking():
    """Calibrate camera tracking steps-per-pixel"""
    try:
        if stepper_controller is None:
            return jsonify({'status': 'error', 'message': 'Stepper controller not available'}), 503
        
        data = request.get_json()
        axis = data.get('axis')  # 'x' or 'y'
        pixels_moved = float(data.get('pixels_moved'))
        steps_executed = int(data.get('steps_executed'))
        
        if axis not in ['x', 'y']:
            return jsonify({'status': 'error', 'message': 'Invalid axis'}), 400
        
        stepper_controller.calibrate_steps_per_pixel(axis, pixels_moved, steps_executed)
        
        return jsonify({
            'status': 'success',
            'message': f'{axis.upper()} axis calibrated',
            'calibration': stepper_controller.get_status()['calibration']
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/settings', methods=['POST'])
def update_camera_tracking_settings():
    """Update camera tracking settings"""
    try:
        if stepper_controller is None:
            return jsonify({'status': 'error', 'message': 'Stepper controller not available'}), 503
        
        data = request.get_json()
        
        if 'dead_zone_pixels' in data:
            stepper_controller.calibration.dead_zone_pixels = int(data['dead_zone_pixels'])
        
        if 'step_delay' in data:
            stepper_controller.calibration.step_delay = float(data['step_delay'])
        
        if 'x_max_steps' in data:
            stepper_controller.calibration.x_max_steps = int(data['x_max_steps'])
        
        if 'y_max_steps' in data:
            stepper_controller.calibration.y_max_steps = int(data['y_max_steps'])
        
        if 'x_steps_per_pixel' in data:
            stepper_controller.calibration.x_steps_per_pixel = float(data['x_steps_per_pixel'])
        
        if 'y_steps_per_pixel' in data:
            stepper_controller.calibration.y_steps_per_pixel = float(data['y_steps_per_pixel'])
        
        return jsonify({
            'status': 'success',
            'settings': stepper_controller.get_status()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/pid', methods=['GET', 'POST'])
def tracking_camera_pid():
    """Get or set PID values for camera tracking (kp, ki, kd)"""
    try:
        if stepper_controller is None:
            return jsonify({'status': 'error', 'message': 'Stepper controller not available'}), 503
        if request.method == 'GET':
            vals = stepper_controller.get_pid()
            return jsonify({'status': 'success', 'pid': vals})
        data = request.get_json() or {}
        kp = data.get('kp')
        ki = data.get('ki')
        kd = data.get('kd')
        def cast(v):
            return float(v) if v is not None else None
        vals = stepper_controller.set_pid(cast(kp), cast(ki), cast(kd))
        try:
            stepper_controller.save_calibration()
        except Exception:
            pass
        return jsonify({'status': 'success', 'pid': vals})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/recenter_on_loss', methods=['POST'])
def set_recenter_on_loss():
    """Enable/disable slow re-centering when target is lost."""
    global camera_recenter_on_loss
    try:
        data = request.get_json() or {}
        enabled = bool(data.get('enabled', not camera_recenter_on_loss))
        with tracking_mode_lock:
            camera_recenter_on_loss = enabled
        return jsonify({'status': 'success', 'enabled': camera_recenter_on_loss})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/status')
def camera_tracking_status():
    """Get camera tracking status"""
    with tracking_mode_lock:
        if stepper_controller is None:
            return jsonify({
                'status': 'success',
                'available': False,
                'mode': tracking_mode,
                'enabled': False
            })
        
        return jsonify({
            'status': 'success',
            'available': True,
            'mode': tracking_mode,
            'enabled': camera_tracking_enabled,
            'recenter_on_loss': camera_recenter_on_loss,
            'controller_status': stepper_controller.get_status()
        })

@app.route('/tracking/status')
def tracking_status():
    """Get overall tracking status"""
    with tracking_mode_lock:
        return jsonify({
            'status': 'success',
            'mode': tracking_mode,
            'camera_tracking': {
                'available': stepper_controller is not None,
                'enabled': camera_tracking_enabled
            },
            'object_tracking': {
                'enabled': object_detection_enabled,
                'auto_track': object_auto_track
            },
            'motion_tracking': {
                'enabled': motion_detection_enabled,
                'auto_track': motion_auto_track
            }
        })

@app.route('/tracking/camera/move_to_position', methods=['POST'])
def move_camera_to_position():
    """
    Move camera to recenter a clicked position.
    User clicks on video at position (x, y), and camera moves to bring that point to center.
    """
    try:
        if stepper_controller is None:
            return jsonify({'status': 'error', 'message': 'Stepper controller not available'}), 503
        
        if not camera_tracking_enabled:
            return jsonify({'status': 'error', 'message': 'Camera tracking not enabled'}), 400
        
        data = request.get_json()
        click_x = int(data.get('x'))
        click_y = int(data.get('y'))
        # Adjust click position by crosshair offset so that camera recenters to crosshair location
        with crosshair_lock:
            adj_x = click_x - int(crosshair_offset['x'])
            adj_y = click_y - int(crosshair_offset['y'])
        
        # In camera tracking mode, crosshair stays centered - don't update it
        # Only the camera moves to recenter the clicked position
        
        # Move camera to recenter the clicked position in background thread
        def move_camera():
            moved = stepper_controller.move_to_center_object(
                adj_x, adj_y, CAMERA_WIDTH, CAMERA_HEIGHT
            )
            if moved:
                print(f"Camera moved to recenter position ({click_x}, {click_y}) with offset ({crosshair_offset['x']}, {crosshair_offset['y']})")
            else:
                print(f"Click at ({click_x}, {click_y}) within dead zone, no movement needed")
        
        threading.Thread(target=move_camera, daemon=True).start()
        
        return jsonify({
            'status': 'success',
            'message': 'Camera moving to recenter clicked position',
            'position': {'x': click_x, 'y': click_y}
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/manual_move', methods=['POST'])
def manual_move_camera():
    """Manually move camera by specified steps"""
    try:
        if stepper_controller is None:
            return jsonify({'status': 'error', 'message': 'Stepper controller not available'}), 503
        
        if not camera_tracking_enabled:
            return jsonify({'status': 'error', 'message': 'Camera tracking not enabled'}), 400
        
        data = request.get_json()
        axis = data.get('axis')  # 'x' or 'y'
        steps = int(data.get('steps'))
        
        if axis not in ['x', 'y']:
            return jsonify({'status': 'error', 'message': 'Invalid axis'}), 400
        
        # Move in background thread
        def move():
            stepper_controller.manual_move(axis, steps)
        
        threading.Thread(target=move, daemon=True).start()
        
        return jsonify({
            'status': 'success',
            'message': f'Moving {axis} axis by {steps} steps'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/set_home', methods=['POST'])
def set_home_position():
    """Set current position as home (0, 0)"""
    try:
        if stepper_controller is None:
            return jsonify({'status': 'error', 'message': 'Stepper controller not available'}), 503
        
        if not stepper_controller.is_calibrated():
            return jsonify({
                'status': 'error',
                'message': 'Calibration required before setting home position. Please run Auto-Calibrate first.'
            }), 400
        
        success = stepper_controller.set_home_position()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Home position set to current location'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to set home position'
            }), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/tracking/camera/auto_calibrate', methods=['POST'])
def auto_calibrate_camera():
    """Run automatic calibration sequence"""
    try:
        if stepper_controller is None:
            return jsonify({'status': 'error', 'message': 'Stepper controller not available'}), 503
        
        # Auto-calibration can run independently to establish initial calibration values
        # No need to check if camera_tracking_enabled - calibration comes first!
        
        # Run calibration in background thread
        def calibrate():
            # Enable motors for calibration if not already enabled
            if not stepper_controller.enabled:
                print("Enabling motors for auto-calibration")
                stepper_controller.enable()
            
            try:
                result = stepper_controller.auto_calibrate()
                print(f"Auto-calibration completed: {result}")
                # Keep motors enabled after calibration to prevent drift
                print("Motors remain enabled after calibration to maintain position")
            except Exception as e:
                print(f"Auto-calibration error: {e}")
                # Keep motors enabled even on error to maintain position
                raise
        
        threading.Thread(target=calibrate, daemon=True).start()
        
        return jsonify({
            'status': 'success',
            'message': 'Auto-calibration started. This may take several minutes.'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

def get_consolidated_status():
    """Get all system status in a single consolidated update"""
    status = {}
    
    # FPS
    with fps_lock:
        status['fps'] = fps_value
    
    # Exposure stats
    with exposure_lock:
        status['exposure'] = {
            'exposure_time': exposure_stats['exposure_time'],
            'analog_gain': exposure_stats['analog_gain']
        }
    
    # Crosshair position
    with tracking_mode_lock:
        if tracking_mode == 'camera' and camera_tracking_enabled:
            with crosshair_lock:
                abs_x = (CAMERA_WIDTH // 2) + int(crosshair_offset['x'])
                abs_y = (CAMERA_HEIGHT // 2) + int(crosshair_offset['y'])
                rel_x = int(crosshair_offset['x'])
                rel_y = -int(crosshair_offset['y'])
        else:
            with crosshair_lock:
                center_x = CAMERA_WIDTH // 2
                center_y = CAMERA_HEIGHT // 2
                abs_x = crosshair_pos['x']
                abs_y = crosshair_pos['y']
                rel_x = crosshair_pos['x'] - center_x
                rel_y = center_y - crosshair_pos['y']
    
    status['crosshair'] = {
        'absolute_x': abs_x,
        'absolute_y': abs_y,
        'relative_x': rel_x,
        'relative_y': rel_y
    }
    
    # Crosshair calibration
    with crosshair_lock:
        status['crosshair_calibration'] = {
            'x': int(crosshair_offset['x']),
            'y': int(crosshair_offset['y'])
        }
    
    # Laser status
    with laser_lock:
        cooldown_remaining = 0
        if last_fire_time:
            elapsed = time.time() - last_fire_time
            cooldown_remaining = max(0, laser_cooldown - elapsed)
        
        status['laser'] = {
            'enabled': laser_enabled,
            'auto_fire': laser_auto_fire,
            'mock_fire_mode': laser_mock_fire_mode,
            'pulse_duration': laser_pulse_duration,
            'burst_count': laser_burst_count,
            'burst_delay': laser_burst_delay,
            'cooldown': laser_cooldown,
            'cooldown_remaining': cooldown_remaining,
            'fire_count': fire_count,
            'ready_to_fire': cooldown_remaining == 0,
            'power': laser_power,
            'hardware_available': laser_control is not None
        }
    
    # Object detection status
    with object_lock:
        status['object_detection'] = {
            'enabled': object_detection_enabled,
            'auto_track': object_auto_track,
            'mode': detection_mode,
            'method': detection_method,
            'count': len(detected_objects),
            'priority': target_priority
        }
    
    # Motion detection status
    with motion_lock:
        status['motion_detection'] = {
            'enabled': motion_detection_enabled,
            'auto_track': motion_auto_track,
            'sensitivity': motion_sensitivity,
            'min_area': motion_min_area,
            'has_motion': last_motion_center is not None
        }
    
    # Recording status
    with recording_lock:
        status['recording'] = {
            'is_recording': is_recording,
            'filename': recording_filename,
            'duration': (time.time() - recording_start_time) if is_recording and recording_start_time else 0
        }
    
    # Pattern status
    status['pattern'] = {
        'running': pattern_running,
        'loop': pattern_loop
    }
    
    # Camera tracking status
    with tracking_mode_lock:
        status['tracking'] = {
            'mode': tracking_mode,
            'camera_enabled': camera_tracking_enabled,
            'recenter_on_loss': camera_recenter_on_loss
        }
    
    # Stepper controller status (if available)
    if stepper_controller:
        try:
            controller_status = stepper_controller.get_status()
            # Add PID values to controller status
            try:
                controller_status['pid'] = stepper_controller.get_pid()
            except Exception:
                pass
            status['controller'] = controller_status
        except Exception as e:
            print(f"Error getting controller status: {e}")
            status['controller'] = None
    else:
        status['controller'] = None
    
    # Add digital gain from camera
    try:
        if picam2:
            metadata = picam2.capture_metadata()
            status['exposure']['digital_gain'] = metadata.get('DigitalGain', 1.0)
    except Exception:
        status['exposure']['digital_gain'] = 1.0
    
    return status

def status_emitter_thread():
    """Background thread that emits consolidated status updates via WebSocket"""
    print("Starting WebSocket status emitter thread...")
    while True:
        try:
            status = get_consolidated_status()
            socketio.emit('status_update', status, namespace='/')
            socketio.sleep(0.5)  # Emit updates twice per second
        except Exception as e:
            print(f"Error in status emitter: {e}")
            time.sleep(1)

if __name__ == '__main__':
    initialize_camera()
    initialize_laser_control()  # Initialize laser control with PWM
    initialize_stepper_controller()  # Initialize stepper controller
    initialize_tflite_detector()  # Loads detection_method from config and initializes TFLite if requested
    # If configuration requests Roboflow, initialize it now
    if detection_method == 'roboflow':
        initialize_roboflow_detector()
    initialize_balloon_settings()  # Initialize balloon settings from config
    
    # Start the status emitter background thread
    socketio.start_background_task(status_emitter_thread)
    
    # Run with SocketIO
    print("Starting Laser Turret Control Panel with WebSocket support...")
    print("Access the control panel at http://<your-ip>:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
