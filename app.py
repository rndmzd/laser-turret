from flask import Flask, Response, render_template, jsonify, request
from picamera2 import Picamera2
import cv2
import numpy as np
import threading
import time

app = Flask(__name__)

# Global variables
output_frame = None
lock = threading.Lock()
picam2 = None

# Crosshair position (default to center)
crosshair_pos = {'x': 320, 'y': 240}  # Will be updated when camera initializes
crosshair_lock = threading.Lock()

def initialize_camera(width=640, height=480):
    """Initialize the Pi Camera with specified resolution"""
    global picam2, crosshair_pos
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (width, height), "format": "RGB888"}
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(2)  # Give camera time to warm up
    
    # Initialize crosshair at center
    crosshair_pos['x'] = width // 2
    crosshair_pos['y'] = height // 2

def create_crosshair(frame, color=(0, 255, 0), thickness=2, opacity=0.5):
    """
    Draw a semi-transparent crosshair on the frame at the specified position
    """
    height, width = frame.shape[:2]
    
    # Create a transparent overlay
    overlay = np.zeros_like(frame, dtype=np.uint8)
    
    with crosshair_lock:
        center_x = crosshair_pos['x']
        center_y = crosshair_pos['y']
    
    # Draw crosshair on overlay
    # Draw horizontal line
    cv2.line(overlay, (center_x - 20, center_y), (center_x + 20, center_y),
             color, thickness)
    # Draw vertical line
    cv2.line(overlay, (center_x, center_y - 20), (center_x, center_y + 20),
             color, thickness)
    # Add circle at center
    cv2.circle(overlay, (center_x, center_y), 4, color, thickness)
    
    # Blend the overlay with the original frame
    blended = cv2.addWeighted(frame, 1.0, overlay, opacity, 0)
    
    return blended

def generate_frames():
    """Generate frames with crosshair overlay"""
    global output_frame, lock
    
    while True:
        # Capture frame from camera
        frame = picam2.capture_array()
        
        # Convert from BGR to RGB if necessary
        if frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Add crosshair with 50% opacity
        frame = create_crosshair(frame, opacity=0.5)
        
        # Encode the frame in JPEG format
        with lock:
            _, encoded_frame = cv2.imencode('.jpg', frame)
            output_frame = encoded_frame.tobytes()
        
        # Yield the frame in byte format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + output_frame + b'\r\n')

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

if __name__ == '__main__':
    # Initialize camera
    initialize_camera()
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)