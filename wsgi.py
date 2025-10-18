import atexit
from app import (
    app,
    socketio,
    initialize_camera,
    initialize_laser_control,
    initialize_stepper_controller,
    initialize_tflite_detector,
    initialize_roboflow_detector,
    initialize_balloon_settings,
    status_emitter_thread,
    detection_method,
    cleanup_on_exit,
)

initialize_camera()
initialize_laser_control()
initialize_stepper_controller()
initialize_tflite_detector()
if detection_method == 'roboflow':
    initialize_roboflow_detector()
initialize_balloon_settings()

socketio.start_background_task(status_emitter_thread)

try:
    atexit.register(cleanup_on_exit)
except Exception:
    pass
