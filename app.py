from flask import Flask, Response, render_template, jsonify, request
from picamera2 import Picamera2
from picamera2.controls import Controls
from libcamera import ColorSpace, Transform
import cv2
import numpy as np
import threading
import time
from collections import deque
from datetime import datetime
from laserturret.hardware_interface import get_gpio_backend
from laserturret.config_manager import get_config
from laserturret.stepper_controller import StepperController

app = Flask(__name__)

# Global variables
output_frame = None
lock = threading.Lock()
picam2 = None

# Camera resolution
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080

# Crosshair position
crosshair_pos = {'x': CAMERA_WIDTH // 2, 'y': CAMERA_HEIGHT // 2}
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
target_priority = 'largest'  # 'largest', 'closest', 'leftmost', 'rightmost'
object_lock = threading.Lock()
detected_objects = []
face_cascade = None
eye_cascade = None
body_cascade = None
smile_cascade = None

# Preset positions
preset_positions = {}  # {slot: {'x': int, 'y': int, 'label': str}}
preset_lock = threading.Lock()
pattern_running = False
pattern_thread = None
pattern_sequence = []
pattern_delay = 1.0  # seconds between positions

# Laser fire control
laser_enabled = False
laser_pulse_duration = 0.1  # seconds (100ms default)
laser_burst_count = 1  # Number of pulses in burst mode
laser_burst_delay = 0.1  # Delay between burst pulses
laser_cooldown = 0.5  # Minimum time between fire commands
laser_auto_fire = False  # Auto-fire when object/motion detected
laser_lock = threading.Lock()
last_fire_time = None
fire_count = 0  # Track total fires

# Camera tracking mode (stepper motor control)
tracking_mode = 'crosshair'  # 'crosshair' or 'camera'
camera_tracking_enabled = False
stepper_controller = None
tracking_mode_lock = threading.Lock()

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
            transform=Transform(vflip=0, hflip=0),
            controls={
                # Basic exposure controls
                "AeEnable": True,               # Enable Auto Exposure
                "ExposureTime": 20000,          # Initial exposure time (microseconds)
                "AnalogueGain": 1.0,            # Initial gain
                
                # White Balance
                "AwbEnable": True,              # Enable Auto White Balance
                "AwbMode": 1,                   # Auto WB mode
                
                # Basic image adjustments
                "Brightness": 0.0,              # Default brightness
                "Contrast": 1.0,                # Default contrast
                "Saturation": 1.0,              # Default saturation
            }
        )
        
        picam2.configure(config)
        
        # Get supported controls for debugging
        print("Supported controls:", picam2.camera_controls)
        
        picam2.start()
        time.sleep(2)  # Allow time for AE and AWB to settle
        
        # Start exposure monitoring
        threading.Thread(target=monitor_exposure, daemon=True).start()
        
        # Initialize positions
        crosshair_pos['x'] = CAMERA_WIDTH // 2
        crosshair_pos['y'] = CAMERA_HEIGHT // 2
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
    """Fire the laser (simulate pulse - integrate with GPIO for actual hardware)"""
    global last_fire_time, fire_count
    
    current_time = time.time()
    
    # Check cooldown
    if last_fire_time and (current_time - last_fire_time) < laser_cooldown:
        return False, 'Laser cooling down'
    
    if not laser_enabled:
        return False, 'Laser disabled'
    
    try:
        # Execute burst
        for pulse_num in range(laser_burst_count):
            # Simulate laser pulse (replace with GPIO control for real hardware)
            print(f"🔴 LASER FIRE! Pulse {pulse_num + 1}/{laser_burst_count} - Duration: {laser_pulse_duration}s")
            
            # In real implementation, turn GPIO pin HIGH here
            # GPIO.output(LASER_PIN, GPIO.HIGH)
            
            time.sleep(laser_pulse_duration)
            
            # In real implementation, turn GPIO pin LOW here
            # GPIO.output(LASER_PIN, GPIO.LOW)
            
            fire_count += 1
            
            # Delay between burst pulses (except after last pulse)
            if pulse_num < laser_burst_count - 1:
                time.sleep(laser_burst_delay)
        
        last_fire_time = current_time
        return True, f'Fired {laser_burst_count} pulse(s)'
    
    except Exception as e:
        return False, str(e)

def check_auto_fire():
    """Check if auto-fire conditions are met"""
    if not laser_auto_fire or not laser_enabled:
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
    global pattern_running
    
    while pattern_running:
        for slot in pattern_sequence:
            if not pattern_running:
                break
            
            with preset_lock:
                if slot in preset_positions:
                    pos = preset_positions[slot]
                    with crosshair_lock:
                        crosshair_pos['x'] = pos['x']
                        crosshair_pos['y'] = pos['y']
                    print(f"Pattern: Moving to preset {slot} - {pos['label']}")
            
            time.sleep(pattern_delay)
        
        # If not looping, stop after one cycle
        if not pattern_running:
            break

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

def detect_objects(frame):
    """Detect objects (faces, eyes, bodies) in frame"""
    global detected_objects, face_cascade, eye_cascade, body_cascade, smile_cascade
    
    # Initialize cascades if needed
    if face_cascade is None:
        initialize_cascades()
    
    # Convert to grayscale for detection
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    
    objects = []
    
    try:
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
            history=500, varThreshold=motion_sensitivity, detectShadows=False
        )
    
    # Convert to BGR for processing
    bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    
    # Apply background subtraction
    fg_mask = background_subtractor.apply(bgr_frame)
    
    # Apply morphological operations to reduce noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
    
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
                        # Calculate center
                        center_x = x + w // 2
                        center_y = y + h // 2
                        
                        # Draw target indicator
                        cv2.circle(overlay, (center_x, center_y), 15, (0, 255, 255), 3)
                        cv2.circle(overlay, (center_x, center_y), 5, (0, 255, 255), -1)
                        
                        # Update tracking based on mode
                        with tracking_mode_lock:
                            if tracking_mode == 'crosshair':
                                # Traditional mode: move crosshair to object
                                with crosshair_lock:
                                    crosshair_pos['x'] = center_x
                                    crosshair_pos['y'] = center_y
                            elif tracking_mode == 'camera' and camera_tracking_enabled and stepper_controller:
                                # Camera tracking mode: move camera to center object
                                threading.Thread(
                                    target=lambda: stepper_controller.move_to_center_object(
                                        center_x, center_y, CAMERA_WIDTH, CAMERA_HEIGHT
                                    ),
                                    daemon=True
                                ).start()
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
                    cv2.circle(overlay, motion_center, 10, (255, 0, 255), 2)
                    cv2.circle(overlay, motion_center, 3, (255, 0, 255), -1)
                    
                    # Auto-track: update tracking based on mode (only if object tracking is off)
                    if motion_auto_track and not object_auto_track:
                        with tracking_mode_lock:
                            if tracking_mode == 'crosshair':
                                # Traditional mode: move crosshair to motion
                                with crosshair_lock:
                                    crosshair_pos['x'] = motion_center[0]
                                    crosshair_pos['y'] = motion_center[1]
                            elif tracking_mode == 'camera' and camera_tracking_enabled and stepper_controller:
                                # Camera tracking mode: move camera to center motion
                                threading.Thread(
                                    target=lambda: stepper_controller.move_to_center_object(
                                        motion_center[0], motion_center[1], CAMERA_WIDTH, CAMERA_HEIGHT
                                    ),
                                    daemon=True
                                ).start()
            except Exception as e:
                print(f"Motion detection error: {e}")
    
    with crosshair_lock:
        center_x = crosshair_pos['x']
        center_y = crosshair_pos['y']
    
    # Draw crosshair
    line_length = 40
    cv2.line(overlay, (center_x - line_length, center_y),
             (center_x + line_length, center_y),
             color, thickness)
    cv2.line(overlay, (center_x, center_y - line_length),
             (center_x, center_y + line_length),
             color, thickness)
    cv2.circle(overlay, (center_x, center_y), 6, color, thickness)
    
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
            obj_text = f"Detect: {detection_mode.upper()} ({len(detected_objects)})"
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
        crosshair_pos['x'] = CAMERA_WIDTH // 2
        crosshair_pos['y'] = CAMERA_HEIGHT // 2
    return jsonify({
        'status': 'success',
        'x': crosshair_pos['x'],
        'y': crosshair_pos['y']
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
        
        if 'exposure_time' in data and not data.get('auto', True):
            # Only set manual exposure if auto is disabled
            controls['ExposureTime'] = int(data['exposure_time'])
        
        if 'analog_gain' in data and not data.get('auto', True):
            controls['AnalogueGain'] = float(data['analog_gain'])
        
        if 'digital_gain' in data and not data.get('auto', True):
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
        
        if 'brightness' in data:
            controls['Brightness'] = float(data['brightness'])
        
        if 'contrast' in data:
            controls['Contrast'] = float(data['contrast'])
        
        if 'saturation' in data:
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
        
        if 'mode' in data:
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
    global motion_auto_track
    
    try:
        data = request.get_json()
        with motion_lock:
            motion_auto_track = bool(data.get('enabled', not motion_auto_track))
        
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
    global object_auto_track
    
    try:
        data = request.get_json()
        with object_lock:
            object_auto_track = bool(data.get('enabled', not object_auto_track))
        
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
        return jsonify({
            'status': 'success',
            'enabled': object_detection_enabled,
            'auto_track': object_auto_track,
            'mode': detection_mode,
            'priority': target_priority,
            'objects_detected': len(detected_objects),
            'objects': [{'type': obj['type'], 'rect': [int(v) for v in obj['rect']]} for obj in detected_objects]
        })

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
        
        return jsonify({
            'status': 'success',
            'slot': slot,
            'position': {'x': preset['x'], 'y': preset['y']},
            'label': preset['label']
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
    global pattern_running, pattern_thread, pattern_sequence, pattern_delay
    
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
        
        pattern_sequence = sequence
        pattern_delay = delay
        pattern_running = loop  # Only keep running if looping
        
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
    global pattern_running
    
    pattern_running = False
    
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
        'delay': pattern_delay
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
    global laser_pulse_duration, laser_burst_count, laser_burst_delay, laser_cooldown
    
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
        
        return jsonify({
            'status': 'success',
            'pulse_duration': laser_pulse_duration,
            'burst_count': laser_burst_count,
            'burst_delay': laser_burst_delay,
            'cooldown': laser_cooldown
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
            'pulse_duration': laser_pulse_duration,
            'burst_count': laser_burst_count,
            'burst_delay': laser_burst_delay,
            'cooldown': laser_cooldown,
            'cooldown_remaining': cooldown_remaining,
            'fire_count': fire_count,
            'ready_to_fire': cooldown_remaining == 0
        })

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

if __name__ == '__main__':
    initialize_camera()
    initialize_stepper_controller()  # Initialize stepper controller
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)