from flask import Flask, render_template, Response, request
import cv2
import threading
import numpy as np

app = Flask(__name__)

camera = cv2.VideoCapture(0)
overlay_position = (0, 0)
overlay_image = cv2.imread('crosshair.png', cv2.IMREAD_UNCHANGED)
overlay_opacity = 1.0

def gen_frames():
    global overlay_position
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            result = frame.copy()
            frame_h, frame_w = frame.shape[:2]
            overlay_h, overlay_w = overlay_image.shape[:2]
            x, y = overlay_position
            roi_y = min(max(y - overlay_h // 2, 0), frame_h - overlay_h)
            roi_x = min(max(x - overlay_w // 2, 0), frame_w - overlay_w)
            roi = result[roi_y:roi_y + overlay_h, roi_x:roi_x + overlay_w]

            if overlay_image.shape[2] == 4:
                alpha = overlay_image[:, :, 3] / 255.0 * overlay_opacity
                alpha = np.expand_dims(alpha, axis=-1)
                overlay_colors = overlay_image[:, :, :3]
                blended = (overlay_colors * alpha) + (roi * (1 - alpha))
                result[roi_y:roi_y + overlay_h, roi_x:roi_x + overlay_w] = blended.astype(np.uint8)
            else:
                pass

            ret, buffer = cv2.imencode('.jpg', result)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calibrate')
def calibrate():
    return render_template('calibrate.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/click', methods=['POST'])
def click():
    global overlay_position
    x = int(float(request.form.get('x')))
    y = int(float(request.form.get('y')))
    overlay_position = (x, y)
    return ('', 204)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)