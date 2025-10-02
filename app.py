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
    'analogue_gain': 0
}
exposure_lock = threading.Lock()

# Video recording
is_recording = False
video_writer = None
recording_filename = None
recording_lock = threading.Lock()
recording_start_time = None

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
                exposure_stats['analogue_gain'] = metadata.get('AnalogueGain', 0)
        except Exception as e:
            print(f"Error monitoring exposure: {e}")
        time.sleep(0.2)

def create_crosshair(frame, color=(0, 255, 0), thickness=3, opacity=0.5):
    """Draw crosshair and exposure information"""
    overlay = np.zeros_like(frame, dtype=np.uint8)
    
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
        gain_text = f"Gain: {exposure_stats['analogue_gain']:.1f}x"
    
    y_offset = 40
    for text in [fps_text, exp_text, gain_text]:
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

if __name__ == '__main__':
    initialize_camera()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)