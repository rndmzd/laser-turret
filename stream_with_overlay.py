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
            transform=Transform(hflip=1, vflip=1)  # Flip image if needed
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
        """Apply the overlay to a frame with current opacity and position."""
        # Create a copy of the frame
        result = frame.copy()
        
        # Get the dimensions
        frame_h, frame_w = frame.shape[:2]
        overlay_h, overlay_w = self.overlay_image.shape[:2]
        
        # Calculate ROI coordinates
        x, y = self.overlay_position
        roi_y = min(max(y, 0), frame_h - overlay_h)
        roi_x = min(max(x, 0), frame_w - overlay_w)
        
        # Get ROI from the frame
        roi = result[roi_y:roi_y + overlay_h, roi_x:roi_x + overlay_w]
        
        # Apply overlay with alpha channel if available
        if self.overlay_image.shape[2] == 4:
            # Extract alpha channel
            alpha = self.overlay_image[:, :, 3] / 255.0 * self.overlay_opacity
            alpha = np.expand_dims(alpha, axis=-1)
            
            # Extract BGR channels
            overlay_colors = self.overlay_image[:, :, :3]
            
            # Blend overlay and ROI
            blended = (overlay_colors * alpha) + (roi * (1 - alpha))
            result[roi_y:roi_y + overlay_h, roi_x:roi_x + overlay_w] = blended
        else:
            # No alpha channel, use simple blending
            cv2.addWeighted(
                self.overlay_image, self.overlay_opacity,
                roi, 1 - self.overlay_opacity,
                0, roi
            )
            result[roi_y:roi_y + overlay_h, roi_x:roi_x + overlay_w] = roi
        
        return result

    def set_opacity(self, opacity):
        """Set the overlay opacity (0.0 to 1.0)."""
        self.overlay_opacity = max(0.0, min(1.0, opacity))

    def set_position(self, x, y):
        """Set the overlay position."""
        self.overlay_position = (int(x), int(y))

    def start_streaming(self):
        """Start the camera and streaming server."""
        global output
        output = StreamingOutput()
        
        def process_frames(self):
            while True:
                buffer = self.picam2.capture_array()
                
                # Convert buffer to BGR format if it's not already
                if len(buffer.shape) == 2:
                    buffer = cv2.cvtColor(buffer, cv2.COLOR_GRAY2BGR)
                elif buffer.shape[2] == 4:
                    buffer = cv2.cvtColor(buffer, cv2.COLOR_RGBA2BGR)
                
                # Apply overlay
                frame = self.apply_overlay(buffer)
                
                # Convert to JPEG
                ret, jpeg = cv2.imencode('.jpg', frame)
                if ret:
                    output.write(jpeg.tobytes())
        
        # Start camera
        self.picam2.start()
        
        # Start frame processing thread
        processing_thread = threading.Thread(target=process_frames, args=(self,))
        processing_thread.daemon = True
        processing_thread.start()
        
        # Start streaming server
        address = ('', self.port)
        server = StreamingServer(address, StreamingHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        print(f"Stream started at http://{socket.gethostname()}:{self.port}/stream.mjpg")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping stream...")
            self.picam2.stop()
            server.shutdown()

if __name__ == '__main__':
    # Example usage
    overlay = CameraOverlay(
        overlay_path='crosshair.png',  # Path to your overlay image (should have transparency)
        port=8000
    )
    
    # Set initial opacity
    overlay.set_opacity(0.5)
    
    # Set initial position (centered)
    overlay.set_position(860, 440)  # Centered for 1920x1080
    
    # Start streaming
    overlay.start_streaming()