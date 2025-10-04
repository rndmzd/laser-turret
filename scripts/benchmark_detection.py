#!/usr/bin/env python3
"""
Benchmark script to compare Haar Cascade vs TensorFlow Lite detection methods.

This script tests both detection methods on sample images or live camera feed
and provides performance metrics including:
- Detection accuracy
- Inference time
- FPS
- Memory usage
"""

import sys
import os
import time
import cv2
import numpy as np
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from laserturret.tflite_detector import TFLiteDetector, TFLITE_AVAILABLE
except ImportError:
    TFLITE_AVAILABLE = False
    print("Warning: TFLite detector not available")


class HaarDetector:
    """Haar Cascade detector wrapper for benchmarking"""
    
    def __init__(self):
        """Initialize Haar Cascade classifiers"""
        self.face_cascade = None
        self.inference_times = []
        self.frame_count = 0
        self._load_cascades()
    
    def _load_cascades(self):
        """Load Haar Cascade classifiers"""
        cascade_path = None
        possible_paths = [
            (lambda: cv2.data.haarcascades if hasattr(cv2, 'data') else None)(),
            '/usr/share/opencv4/haarcascades/',
            '/usr/local/share/opencv4/haarcascades/',
            '/usr/share/opencv/haarcascades/',
        ]
        
        for path in possible_paths:
            if path is None:
                continue
            try:
                test_path = path + 'haarcascade_frontalface_default.xml'
                test_cascade = cv2.CascadeClassifier(test_path)
                if not test_cascade.empty():
                    cascade_path = path
                    break
            except:
                continue
        
        if cascade_path:
            self.face_cascade = cv2.CascadeClassifier(
                cascade_path + 'haarcascade_frontalface_default.xml'
            )
            print(f"Loaded Haar Cascades from: {cascade_path}")
        else:
            raise RuntimeError("Could not find Haar Cascade files")
    
    def detect(self, frame):
        """Detect faces in frame"""
        start_time = time.time()
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        
        # Detect faces
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )
        
        # Convert to standard format
        detections = [
            {'type': 'face', 'rect': (int(x), int(y), int(w), int(h)), 'confidence': 1.0}
            for x, y, w, h in faces
        ]
        
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
        """Get estimated FPS"""
        avg_time = self.get_avg_inference_time()
        if avg_time > 0:
            return 1000 / avg_time
        return 0
    
    def get_stats(self):
        """Get performance statistics"""
        return {
            'model': 'Haar Cascade',
            'accelerator': 'CPU',
            'avg_inference_ms': round(self.get_avg_inference_time(), 2),
            'estimated_fps': round(self.get_fps(), 1),
            'frame_count': self.frame_count,
            'confidence_threshold': 'N/A'
        }


def draw_detections(frame, detections, color=(0, 255, 0)):
    """Draw detection boxes on frame"""
    output = frame.copy()
    
    for det in detections:
        x, y, w, h = det['rect']
        label = det['type']
        confidence = det.get('confidence', 1.0)
        
        # Draw rectangle
        cv2.rectangle(output, (x, y), (x + w, y + h), color, 2)
        
        # Draw label with confidence
        text = f"{label}: {confidence:.2f}"
        cv2.putText(output, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX,
                   0.5, color, 2, cv2.LINE_AA)
    
    return output


def benchmark_camera(duration_seconds=10, show_preview=True):
    """Benchmark detection methods using live camera"""
    print("\n" + "=" * 80)
    print("CAMERA BENCHMARK")
    print("=" * 80)
    
    # Initialize camera
    try:
        from picamera2 import Picamera2
        print("Initializing Pi Camera...")
        camera = Picamera2()
        config = camera.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        camera.configure(config)
        camera.start()
        time.sleep(2)  # Camera warm-up
        print("Camera initialized")
    except Exception as e:
        print(f"Error initializing camera: {e}")
        print("Using test image instead...")
        return benchmark_test_images()
    
    # Initialize detectors
    detectors = {}
    
    # Haar Cascade
    try:
        print("\nInitializing Haar Cascade detector...")
        detectors['haar'] = HaarDetector()
        print("✓ Haar Cascade ready")
    except Exception as e:
        print(f"✗ Haar Cascade failed: {e}")
    
    # TensorFlow Lite
    if TFLITE_AVAILABLE:
        try:
            print("\nInitializing TFLite detector...")
            detectors['tflite'] = TFLiteDetector(
                model_name='ssd_mobilenet_v2',
                confidence_threshold=0.5
            )
            print("✓ TFLite ready")
        except Exception as e:
            print(f"✗ TFLite failed: {e}")
    else:
        print("\n✗ TFLite not available")
    
    if not detectors:
        print("No detectors available!")
        return
    
    # Run benchmark
    print(f"\nRunning benchmark for {duration_seconds} seconds...")
    print("Press 'q' to quit early\n")
    
    results = {name: [] for name in detectors.keys()}
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration_seconds:
            # Capture frame
            frame = camera.capture_array()
            
            # Test each detector
            for name, detector in detectors.items():
                detections = detector.detect(frame)
                results[name].append(len(detections))
                
                # Show preview if requested
                if show_preview:
                    display_frame = draw_detections(frame, detections)
                    cv2.putText(display_frame, f"{name.upper()}: {detector.get_stats()['estimated_fps']:.1f} FPS",
                              (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.imshow(f'{name.capitalize()} Detection', display_frame)
            
            if show_preview and cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    finally:
        camera.stop()
        if show_preview:
            cv2.destroyAllWindows()
    
    # Print results
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)
    
    for name, detector in detectors.items():
        stats = detector.get_stats()
        avg_detections = np.mean(results[name]) if results[name] else 0
        
        print(f"\n{name.upper()}:")
        print(f"  Model: {stats['model']}")
        print(f"  Accelerator: {stats['accelerator']}")
        print(f"  Avg Inference Time: {stats['avg_inference_ms']:.2f} ms")
        print(f"  Estimated FPS: {stats['estimated_fps']:.1f}")
        print(f"  Frames Processed: {stats['frame_count']}")
        print(f"  Avg Detections: {avg_detections:.1f}")
    
    # Comparison
    if 'haar' in detectors and 'tflite' in detectors:
        haar_fps = detectors['haar'].get_fps()
        tflite_fps = detectors['tflite'].get_fps()
        
        print(f"\n{'=' * 80}")
        print("COMPARISON")
        print("=" * 80)
        
        if haar_fps > tflite_fps:
            speedup = haar_fps / tflite_fps
            print(f"Haar Cascade is {speedup:.2f}x FASTER than TFLite")
        else:
            speedup = tflite_fps / haar_fps
            print(f"TFLite is {speedup:.2f}x FASTER than Haar Cascade")
        
        print(f"\nRecommendation:")
        if tflite_fps >= 20:
            print("✓ TFLite provides good performance (>=20 FPS)")
            print("  Use TFLite for better accuracy and more object classes")
        elif haar_fps >= 25:
            print("✓ Haar Cascade provides better performance")
            print("  Stick with Haar for real-time face detection")
        else:
            print("⚠ Both methods may be too slow for real-time tracking")
            print("  Consider using Coral USB Accelerator for TFLite")


def benchmark_test_images():
    """Benchmark using test images (when camera not available)"""
    print("\n" + "=" * 80)
    print("TEST IMAGE BENCHMARK")
    print("=" * 80)
    print("Note: Camera benchmark provides more realistic results")
    
    # Create test image with simple shapes
    test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    # Initialize detectors
    detectors = {}
    
    try:
        detectors['haar'] = HaarDetector()
        print("✓ Haar Cascade ready")
    except Exception as e:
        print(f"✗ Haar Cascade failed: {e}")
    
    if TFLITE_AVAILABLE:
        try:
            detectors['tflite'] = TFLiteDetector(
                model_name='ssd_mobilenet_v2',
                confidence_threshold=0.5
            )
            print("✓ TFLite ready")
        except Exception as e:
            print(f"✗ TFLite failed: {e}")
    
    # Run benchmark
    iterations = 100
    print(f"\nRunning {iterations} iterations on test image...\n")
    
    for name, detector in detectors.items():
        for i in range(iterations):
            detector.detect(test_image)
            if (i + 1) % 25 == 0:
                print(f"{name}: {i + 1}/{iterations} iterations")
        
        stats = detector.get_stats()
        print(f"\n{name.upper()} Results:")
        print(f"  Avg Inference Time: {stats['avg_inference_ms']:.2f} ms")
        print(f"  Estimated FPS: {stats['estimated_fps']:.1f}")


def main():
    """Main benchmark function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Benchmark object detection methods')
    parser.add_argument('--duration', type=int, default=10,
                       help='Benchmark duration in seconds (default: 10)')
    parser.add_argument('--no-preview', action='store_true',
                       help='Disable preview windows')
    parser.add_argument('--test-images', action='store_true',
                       help='Use test images instead of camera')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("OBJECT DETECTION BENCHMARK")
    print("=" * 80)
    print("\nThis script compares Haar Cascade vs TensorFlow Lite detection methods.")
    print("It measures inference time, FPS, and detection performance.\n")
    
    if args.test_images:
        benchmark_test_images()
    else:
        benchmark_camera(
            duration_seconds=args.duration,
            show_preview=not args.no_preview
        )
    
    print("\n" + "=" * 80)
    print("Benchmark complete!")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()
