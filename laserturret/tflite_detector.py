"""
TensorFlow Lite Object Detection Module

Provides efficient object detection using TensorFlow Lite models optimized for edge devices.
Supports CPU inference and optional Coral USB Accelerator.
"""

import os
import numpy as np
import cv2
from pathlib import Path
import urllib.request
import time

# Try to import TensorFlow Lite runtime
try:
    import tflite_runtime.interpreter as tflite
    TFLITE_AVAILABLE = True
except ImportError:
    try:
        import tensorflow.lite as tflite
        TFLITE_AVAILABLE = True
    except ImportError:
        TFLITE_AVAILABLE = False
        print("Warning: TensorFlow Lite not available. Install with: pip install tflite-runtime")

# Try to import Coral support
try:
    from pycoral.utils import edgetpu
    from pycoral.adapters import common
    from pycoral.adapters import detect
    CORAL_AVAILABLE = True
except ImportError:
    CORAL_AVAILABLE = False


# COCO dataset labels (80 classes)
COCO_LABELS = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
    'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
    'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
    'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair',
    'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator',
    'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]


# Available models with download URLs
AVAILABLE_MODELS = {
    'ssd_mobilenet_v2': {
        'name': 'SSD MobileNet V2',
        'url': 'https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip',
        'file': 'detect.tflite',
        'input_size': (300, 300),
        'labels': COCO_LABELS,
        'description': 'Fast general object detection (80 classes)',
        'fps_estimate': '20-25 FPS on Pi 5'
    },
    'efficientdet_lite0': {
        'name': 'EfficientDet Lite0',
        'url': 'https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/object_detection/rpi/lite-model_efficientdet_lite0_detection_metadata_1.tflite',
        'file': 'efficientdet_lite0.tflite',
        'input_size': (320, 320),
        'labels': COCO_LABELS,
        'description': 'Better accuracy, slightly slower (80 classes)',
        'fps_estimate': '15-20 FPS on Pi 5'
    },
    'balloon_lite0': {
        'name': 'Balloon Detector (EfficientDet-Lite0)',
        'url': 'local',
        'file': 'balloon_lite0.tflite',
        'input_size': (320, 320),
        'labels': ['balloon'],
        'description': 'Custom trained balloon detector',
        'fps_estimate': '15-25 FPS on Pi 5'
    }
}


class TFLiteDetector:
    """TensorFlow Lite Object Detector"""
    
    def __init__(self, model_name='ssd_mobilenet_v2', use_coral=False, confidence_threshold=0.5):
        """
        Initialize TFLite detector
        
        Args:
            model_name: Name of model to use (see AVAILABLE_MODELS)
            use_coral: Whether to use Coral USB Accelerator if available
            confidence_threshold: Minimum confidence for detections (0.0-1.0)
        """
        if not TFLITE_AVAILABLE:
            raise RuntimeError("TensorFlow Lite is not available. Install with: pip install tflite-runtime")
        
        self.model_name = model_name
        self.use_coral = use_coral and CORAL_AVAILABLE
        self.confidence_threshold = confidence_threshold
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        self.input_size = (300, 300)
        self.labels = COCO_LABELS
        
        # Performance metrics
        self.inference_times = []
        self.frame_count = 0
        
        # Load model
        self._load_model()
    
    def _get_model_dir(self):
        """Get directory for storing downloaded models"""
        model_dir = Path(__file__).parent.parent / 'models' / 'tflite'
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir
    
    def _download_model(self, model_info):
        """Download model if not already cached"""
        model_dir = self._get_model_dir()
        model_path = model_dir / model_info['file']
        
        if model_path.exists():
            print(f"Using cached model: {model_path}")
            return model_path
        
        if model_info.get('url') == 'local':
            raise FileNotFoundError(f"Local model not found: {model_path}. Place your TFLite file at this path.")

        print(f"Downloading {model_info['name']}...")
        print(f"URL: {model_info['url']}")
        
        try:
            # Handle different URL formats
            if model_info['url'].endswith('.zip'):
                # Download and extract zip
                import zipfile
                import tempfile
                
                zip_path = model_dir / f"{model_info['file']}.zip"
                urllib.request.urlretrieve(model_info['url'], zip_path)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(model_dir)
                
                zip_path.unlink()  # Delete zip file
                
                # Find the .tflite file
                tflite_files = list(model_dir.glob('*.tflite'))
                if tflite_files:
                    tflite_files[0].rename(model_path)
            else:
                # Direct download
                urllib.request.urlretrieve(model_info['url'], model_path)
            
            print(f"Model downloaded: {model_path}")
            return model_path
        
        except Exception as e:
            print(f"Error downloading model: {e}")
            raise
    
    def _load_model(self):
        """Load TFLite model and initialize interpreter"""
        if self.model_name not in AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {self.model_name}. Available: {list(AVAILABLE_MODELS.keys())}")
        
        model_info = AVAILABLE_MODELS[self.model_name]
        model_path = self._download_model(model_info)
        
        self.input_size = model_info['input_size']
        self.labels = model_info['labels']
        
        # Initialize interpreter
        if self.use_coral:
            print("Initializing Coral USB Accelerator...")
            self.interpreter = tflite.Interpreter(
                model_path=str(model_path),
                experimental_delegates=[edgetpu.load_edgetpu_delegate()]
            )
            print("Coral accelerator loaded successfully")
        else:
            print("Initializing CPU inference...")
            self.interpreter = tflite.Interpreter(model_path=str(model_path))
        
        self.interpreter.allocate_tensors()
        
        # Get input and output details
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        
        print(f"Model loaded: {model_info['name']}")
        print(f"Input size: {self.input_size}")
        print(f"Expected performance: {model_info['fps_estimate']}")
    
    def detect(self, frame):
        """
        Detect objects in frame
        
        Args:
            frame: RGB image as numpy array (H, W, 3)
        
        Returns:
            List of detections: [{'type': str, 'rect': (x, y, w, h), 'confidence': float}]
        """
        if self.interpreter is None:
            return []
        
        start_time = time.time()
        
        # Get original dimensions
        orig_h, orig_w = frame.shape[:2]
        
        # Preprocess frame
        input_data = cv2.resize(frame, self.input_size)
        input_data = np.expand_dims(input_data, axis=0)
        
        # Check if model expects uint8 or float32
        if self.input_details[0]['dtype'] == np.uint8:
            input_data = input_data.astype(np.uint8)
        else:
            input_data = (input_data.astype(np.float32) - 127.5) / 127.5
        
        # Run inference
        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()
        
        # Get outputs
        # Standard TFLite detection model outputs:
        # [0] = locations (bounding boxes)
        # [1] = classes
        # [2] = scores
        # [3] = number of detections
        boxes = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
        classes = self.interpreter.get_tensor(self.output_details[1]['index'])[0]
        scores = self.interpreter.get_tensor(self.output_details[2]['index'])[0]
        
        # Process detections
        detections = []
        for i in range(len(scores)):
            if scores[i] >= self.confidence_threshold:
                # Get bounding box (normalized coordinates)
                ymin, xmin, ymax, xmax = boxes[i]
                
                # Convert to pixel coordinates
                x = int(xmin * orig_w)
                y = int(ymin * orig_h)
                w = int((xmax - xmin) * orig_w)
                h = int((ymax - ymin) * orig_h)
                
                # Get class label
                class_id = int(classes[i])
                if class_id < len(self.labels):
                    label = self.labels[class_id]
                else:
                    label = f"class_{class_id}"
                
                detections.append({
                    'type': label,
                    'rect': (x, y, w, h),
                    'confidence': float(scores[i])
                })
        
        # Track performance
        inference_time = time.time() - start_time
        self.inference_times.append(inference_time)
        if len(self.inference_times) > 30:
            self.inference_times.pop(0)
        self.frame_count += 1
        
        return detections
    
    def get_avg_inference_time(self):
        """Get average inference time in milliseconds"""
        if not self.inference_times:
            return 0
        return (sum(self.inference_times) / len(self.inference_times)) * 1000
    
    def get_fps(self):
        """Get estimated FPS based on inference time"""
        avg_time = self.get_avg_inference_time()
        if avg_time > 0:
            return 1000 / avg_time
        return 0
    
    def get_stats(self):
        """Get performance statistics"""
        return {
            'model': self.model_name,
            'accelerator': 'Coral' if self.use_coral else 'CPU',
            'avg_inference_ms': round(self.get_avg_inference_time(), 2),
            'estimated_fps': round(self.get_fps(), 1),
            'frame_count': self.frame_count,
            'confidence_threshold': self.confidence_threshold
        }


def list_available_models():
    """List all available models with descriptions"""
    print("\nAvailable TensorFlow Lite Models:")
    print("=" * 80)
    for key, info in AVAILABLE_MODELS.items():
        print(f"\n{key}:")
        print(f"  Name: {info['name']}")
        print(f"  Description: {info['description']}")
        print(f"  Performance: {info['fps_estimate']}")
        print(f"  Input Size: {info['input_size']}")
        print(f"  Classes: {len(info['labels'])}")


# Test/Demo code
if __name__ == '__main__':
    print("TensorFlow Lite Detector Module")
    print(f"TensorFlow Lite Available: {TFLITE_AVAILABLE}")
    print(f"Coral Support Available: {CORAL_AVAILABLE}")
    
    list_available_models()
    
    if TFLITE_AVAILABLE:
        print("\nTest: Creating detector...")
        try:
            detector = TFLiteDetector(model_name='ssd_mobilenet_v2', confidence_threshold=0.5)
            print("Detector created successfully!")
            print(f"Stats: {detector.get_stats()}")
        except Exception as e:
            print(f"Error creating detector: {e}")
