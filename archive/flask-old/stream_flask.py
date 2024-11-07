from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, MJPEGEncoder
from picamera2.outputs import FileOutput
import cv2
import numpy as np
from libcamera import Transform
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import io
import socket

from flask import Flask, Response

class StreamingOutput:
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = threading.Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

class StreamingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/stream.mjpg')
            self.end_headers()
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                print(f"Removed streaming client {self.client_address}: {str(e)}")
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(HTTPServer):
    allow_reuse_address = True

class CameraOverlay:
    def __init__(self, overlay_path, port=8000):
        self.port = port
        self.overlay_image = cv2.imread(overlay_path, cv2.IMREAD_UNCHANGED)
        if self.overlay_image is None:
            raise ValueError(f"Could not load overlay image: {overlay_path}")
        
        # Initialize camera
        self.picam2 = Picamera2()
        
        # Configure camera
        preview_config = self.picam2.create_preview_configuration(
            main={"size": (1920, 1080)},
            transform=Transform(hflip=0, vflip=0)  # Flip image if needed
        )
        self.picam2.configure(preview_config)
        
        # Create MJPEG encoder
        self.encoder = MJPEGEncoder()
        
        # Initialize overlay properties
        self.overlay_opacity = 0.5
        self.overlay_position = (0, 0)  # (x, y) position
        
        # Resize overlay to match some percentage of the video size
        video_height = 1080
        video_width = 1920
        overlay_height = int(video_height * 0.2)  # 20% of video height
        aspect_ratio = self.overlay_image.shape[1] / self.overlay_image.shape[0]
        overlay_width = int(overlay_height * aspect_ratio)
        self.overlay_image = cv2.resize(self.overlay_image, (overlay_width, overlay_height))

    def apply_overlay(self, frame):
        # Ensure frame has 3 channels
        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        x, y = self.overlay_position
        overlay_h, overlay_w = self.overlay_image.shape[:2]
        frame_h, frame_w = frame.shape[:2]

        # Check if the overlay fits within the frame
        if x + overlay_w > frame_w or y + overlay_h > frame_h:
            print("Overlay does not fit within the frame at the given position.")
            return

        # Extract the region of interest from the frame
        roi = frame[y:y+overlay_h, x:x+overlay_w]

        # Check if the overlay image has an alpha channel
        if self.overlay_image.shape[2] == 4:
            # Separate the color and alpha channels
            overlay_rgb = self.overlay_image[:, :, :3]
            overlay_alpha = self.overlay_image[:, :, 3] / 255.0

            # Create an alpha mask
            alpha_mask = np.dstack((overlay_alpha, overlay_alpha, overlay_alpha))

            # Blend the overlay with the ROI
            blended = (alpha_mask * overlay_rgb + (1 - alpha_mask) * roi).astype(np.uint8)
        else:
            # If no alpha channel, use simple blending
            blended = cv2.addWeighted(self.overlay_image, self.overlay_opacity,
                                    roi, 1 - self.overlay_opacity, 0)

        # Replace the ROI on the frame with the blended image
        frame[y:y+overlay_h, x:x+overlay_w] = blended

    def set_opacity(self, opacity):
        """Set the overlay opacity (0.0 to 1.0)."""
        self.overlay_opacity = max(0.0, min(1.0, opacity))

    def set_position(self, x, y):
        """Set the overlay position."""
        self.overlay_position = (int(x), int(y))

    def start_streaming(self):
        # Start camera
        self.picam2.start()

        # Initialize Flask app
        app = Flask(__name__)

        def gen_frames():
            while True:
                frame = self.picam2.capture_array()
                if frame is not None:
                    # Apply overlay
                    self.apply_overlay(frame)
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                time.sleep(0.01)

        @app.route('/stream')
        def stream():
            return Response(gen_frames(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

        print(f"Stream started at http://{socket.gethostname()}:{self.port}/stream")

        # Run Flask app in a separate thread
        threading.Thread(target=app.run, kwargs={
            'host': '0.0.0.0', 'port': self.port, 'threaded': True}).start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping stream...")
            self.picam2.stop()

if __name__ == '__main__':
    # Example usage
    overlay = CameraOverlay(
        overlay_path='crosshair.png',  # Path to your overlay image
        port=8000
    )

    # Set initial opacity
    overlay.set_opacity(0.5)

    # Set initial position (centered)
    overlay.set_position(860, 440)  # Adjust as needed

    # Start streaming
    overlay.start_streaming()