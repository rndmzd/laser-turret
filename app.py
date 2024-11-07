from flask import Flask, Response, render_template, jsonify, request
from picamera2 import Picamera2
from picamera2.controls import Controls
from libcamera import ColorSpace
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

# Crosshair position (default to center)
crosshair_pos = {'x': CAMERA_WIDTH // 2, 'y': CAMERA_HEIGHT // 2}
crosshair_lock = threading.Lock()

# FPS monitoring
fps_buffer = deque(maxlen=30)  # Store last 30 frame times
last_frame_time = None
fps_value = 0
fps_lock = threading.Lock()

def initialize_camera():
    """Initialize the Pi Camera with 1080p resolution and proper color settings"""
    global picam2, crosshair_pos, last_frame_time
    picam2 = Picamera2()
    
    # Configure camera for 1080p with specific color settings
    """
    AwbMode values:
    0 = Manual
    1 = Auto (default)
    2 = Incandescent
    3 = Tungsten
    4 = Fluorescent
    5 = Indoor
    6 = Daylight
    7 = Cloudy
    """
    config = picam2.create_preview_configuration(
        main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT),
              "format": "RGB888"},
        buffer_count=2,
        controls={
            "AwbEnable": True,          # Enable Auto White Balance
            "AwbMode": 1,               # Auto mode (you can try other modes: 0=Manual, 1=Auto, 2=Incandescent, 3=Tungsten, 4=Fluorescent, 5=Indoor, 6=Daylight, 7=Cloudy)
            "Brightness": 0.0,          # Default brightness (0.0 is normal)
            "Contrast": 1.0,            # Default contrast (1.0 is normal)
            "Saturation": 1.0,          # Default saturation (1.0 is normal)
            "Sharpness": 1.0,           # Default sharpness (1.0 is normal)
            "ExposureTime": 20000,      # Auto exposure (in microseconds)
            "AnalogueGain": 1.0,        # Default gain (1.0 is normal)
            "AeEnable": True,           # Enable Auto Exposure
            "ColourGains": (1.0, 1.0),  # RGB gains (red, blue) for manual white balance
        },
        colour_space=ColorSpace.Rec709() # Use standard RGB color space
    )
    
    picam2.configure(config)
    picam2.start()
    
    # Allow time for AWB to settle
    time.sleep(2)
    
    # Optional: Fine-tune white balance after auto-adjustment
    controls = Controls(picam2)
    controls.AwbEnable = True
    controls.AeEnable = True
    
    # Initialize crosshair at center
    crosshair_pos['x'] = CAMERA_WIDTH // 2
    crosshair_pos['y'] = CAMERA_HEIGHT // 2
    
    # Initialize FPS tracking
    last_frame_time = datetime.now()

def update_fps():
    """Calculate current FPS using rolling average"""
    global fps_value
    if len(fps_buffer) >= 2:
        # Calculate average FPS from the buffer
        fps = len(fps_buffer) / sum(fps_buffer)
        with fps_lock:
            fps_value = round(fps, 1)

def create_crosshair(frame, color=(0, 255, 0), thickness=3, opacity=0.5):
    """Draw a semi-transparent crosshair on the frame"""
    # No color conversion needed as we're already in RGB format
    overlay = np.zeros_like(frame, dtype=np.uint8)
    
    with crosshair_lock:
        center_x = crosshair_pos['x']
        center_y = crosshair_pos['y']
    
    line_length = 40
    
    # Draw crosshair
    cv2.line(overlay, (center_x - line_length, center_y),
             (center_x + line_length, center_y),
             color, thickness)
    cv2.line(overlay, (center_x, center_y - line_length),
             (center_x, center_y + line_length),
             color, thickness)
    cv2.circle(overlay, (center_x, center_y), 6, color, thickness)
    
    # Add FPS counter to frame
    with fps_lock:
        fps_text = f"FPS: {fps_value}"
    cv2.putText(overlay, fps_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                1, color, 2, cv2.LINE_AA)
    
    return cv2.addWeighted(frame, 1.0, overlay, opacity, 0)

def generate_frames():
    """Generate frames with crosshair overlay and FPS monitoring"""
    global output_frame, lock, last_frame_time
    
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

if __name__ == '__main__':
    initialize_camera()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)