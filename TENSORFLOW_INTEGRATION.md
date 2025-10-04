# TensorFlow Lite Integration Guide

This document explains how to use TensorFlow Lite for advanced object detection in the laser turret project.

## Overview

The laser turret now supports **two detection methods**:

1. **Haar Cascades** (OpenCV) - Legacy method
   - Fast and simple
   - Limited to faces, eyes, bodies, smiles
   - Lower accuracy (~60-70%)
   - Good for basic face tracking

2. **TensorFlow Lite** - Modern deep learning
   - More accurate (~85-90%)
   - Detects 80+ object classes (COCO dataset)
   - Slightly slower (but still real-time capable)
   - Extensible and future-proof

## Benefits of TensorFlow Lite

### ✅ What You Gain

1. **More Object Classes**
   - People, cats, dogs, birds, vehicles
   - Sports equipment (balls, frisbees, etc.)
   - Household objects
   - [See full COCO label list](laserturret/tflite_detector.py)

2. **Better Accuracy**
   - Fewer false positives
   - Works with varied lighting, angles, occlusions
   - Confidence scores for each detection

3. **Future-Proof**
   - Easy to swap models
   - Can train custom models
   - Active development and support

### ⚠️ Trade-offs

1. **Slightly Slower**
   - Haar: 30+ FPS on Pi 5
   - TFLite (CPU): 15-25 FPS on Pi 5
   - TFLite (Coral): 30+ FPS on Pi 5

2. **Larger Dependencies**
   - ~10MB for tflite-runtime
   - Models download automatically (~4-10MB each)

3. **More Complex**
   - Additional configuration options
   - Model management

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `tflite-runtime` - TensorFlow Lite runtime (~10MB)

### 2. Optional: Coral USB Accelerator

For maximum performance (30+ FPS), use a Coral USB Accelerator:

```bash
# Install Coral support
pip install pycoral

# Plug in Coral USB Accelerator
# Update config: use_coral = true
```

**Coral Device**: $60 USD, provides 4 TOPS of inference performance

## Configuration

### Basic Setup

Edit `laserturret.conf`:

```ini
[Detection]
# Choose detection method
detection_method = tflite  # or 'haar' for legacy

# TFLite model (only used if detection_method = tflite)
tflite_model = ssd_mobilenet_v2

# Use Coral USB Accelerator (requires hardware)
use_coral = false

# Confidence threshold (0.0-1.0)
# Higher = fewer false positives, lower = more detections
tflite_confidence = 0.5

# Filter to specific classes (comma-separated, empty = all)
# Example: person,cat,dog
tflite_filter_classes =
```

### Available Models

#### ssd_mobilenet_v2 (Recommended)
- **Speed**: 20-25 FPS on Pi 5
- **Accuracy**: Good
- **Classes**: 80 (COCO dataset)
- **Best for**: General-purpose detection

#### efficientdet_lite0
- **Speed**: 15-20 FPS on Pi 5
- **Accuracy**: Better
- **Classes**: 80 (COCO dataset)
- **Best for**: When accuracy > speed

### Class Filtering

Detect only specific objects:

```ini
# Only detect people
tflite_filter_classes = person

# Detect pets
tflite_filter_classes = cat,dog,bird

# Detect vehicles
tflite_filter_classes = car,truck,bus,motorcycle
```

**Full class list** (80 classes):
person, bicycle, car, motorcycle, airplane, bus, train, truck, boat, traffic light, fire hydrant, stop sign, parking meter, bench, bird, **cat**, **dog**, horse, sheep, cow, elephant, bear, zebra, giraffe, backpack, umbrella, handbag, tie, suitcase, frisbee, skis, snowboard, sports ball, kite, baseball bat, baseball glove, skateboard, surfboard, tennis racket, bottle, wine glass, cup, fork, knife, spoon, bowl, banana, apple, sandwich, orange, broccoli, carrot, hot dog, pizza, donut, cake, chair, couch, potted plant, bed, dining table, toilet, tv, laptop, mouse, remote, keyboard, cell phone, microwave, oven, toaster, sink, refrigerator, book, clock, vase, scissors, teddy bear, hair drier, toothbrush

## Usage

### Starting the Application

```bash
python app.py
```

The application will:
1. Load configuration from `laserturret.conf`
2. Initialize the selected detection method
3. Download TFLite model if needed (first run only)
4. Start the web interface

Console output:
```
Initializing TFLite detector: ssd_mobilenet_v2
  Coral accelerator: False
  Confidence threshold: 0.5
Using cached model: models/tflite/detect.tflite
Model loaded: SSD MobileNet V2
Input size: (300, 300)
Expected performance: 20-25 FPS on Pi 5
TFLite detector initialized successfully
```

### Switching Detection Methods

**Method 1: Configuration File**

Edit `laserturret.conf`:
```ini
detection_method = haar  # or 'tflite'
```

Restart the application.

**Method 2: Runtime (Future)**

Web UI controls coming soon to switch methods without restart.

## Benchmarking

Compare detection methods on your hardware:

```bash
# Run 10-second camera benchmark with live preview
python scripts/benchmark_detection.py

# Longer benchmark
python scripts/benchmark_detection.py --duration 30

# No preview (faster)
python scripts/benchmark_detection.py --no-preview

# Test images only (no camera needed)
python scripts/benchmark_detection.py --test-images
```

**Example Output:**
```
BENCHMARK RESULTS
================================================================================

HAAR:
  Model: Haar Cascade
  Accelerator: CPU
  Avg Inference Time: 8.52 ms
  Estimated FPS: 117.4
  Frames Processed: 1174
  Avg Detections: 1.2

TFLITE:
  Model: SSD MobileNet V2
  Accelerator: CPU
  Avg Inference Time: 42.18 ms
  Estimated FPS: 23.7
  Frames Processed: 237
  Avg Detections: 2.8

COMPARISON
================================================================================
Haar Cascade is 4.95x FASTER than TFLite

Recommendation:
✓ TFLite provides good performance (>=20 FPS)
  Use TFLite for better accuracy and more object classes
```

## Performance Optimization

### 1. Lower Resolution

Edit camera configuration:
```python
CAMERA_WIDTH = 1280  # Instead of 1920
CAMERA_HEIGHT = 720  # Instead of 1080
```

**Impact**: 2-3x faster inference

### 2. Increase Confidence Threshold

```ini
tflite_confidence = 0.7  # Instead of 0.5
```

**Impact**: Fewer detections to process, slightly faster

### 3. Use Coral USB Accelerator

```ini
use_coral = true
```

**Impact**: 2-3x faster inference (requires $60 hardware)

### 4. Filter Classes

```ini
tflite_filter_classes = person,cat,dog
```

**Impact**: Faster post-processing, fewer false triggers

## Troubleshooting

### TFLite Not Loading

**Error**: `TensorFlow Lite not available`

**Solution**:
```bash
pip install tflite-runtime
# or
pip install tensorflow-lite
```

### Model Download Fails

**Error**: `Error downloading model`

**Solution**: Download manually and place in `models/tflite/`:
- [SSD MobileNet V2](https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip)

### Low FPS

**Symptoms**: < 15 FPS on Pi 5

**Solutions**:
1. Use lower camera resolution
2. Switch to faster model (`ssd_mobilenet_v2`)
3. Consider Coral USB Accelerator
4. Fall back to Haar Cascades

### Coral Not Detected

**Error**: `Could not open any GPIO chip` (wrong error, should be Coral-specific)

**Solution**:
```bash
# Check Coral is connected
lsusb | grep "Global Unichip"

# Install/reinstall Coral support
pip install --upgrade pycoral
```

## Advanced: Custom Models

### Using Your Own TFLite Model

1. Train or download a TFLite model
2. Place it in `models/tflite/my_model.tflite`
3. Add to `AVAILABLE_MODELS` in `laserturret/tflite_detector.py`:

```python
AVAILABLE_MODELS = {
    'my_model': {
        'name': 'My Custom Model',
        'url': 'file:///models/tflite/my_model.tflite',
        'file': 'my_model.tflite',
        'input_size': (320, 320),
        'labels': ['class1', 'class2', 'class3'],
        'description': 'Custom trained model',
        'fps_estimate': '20 FPS on Pi 5'
    }
}
```

4. Update config:
```ini
tflite_model = my_model
```

## API Reference

### TFLiteDetector Class

```python
from laserturret.tflite_detector import TFLiteDetector

# Initialize
detector = TFLiteDetector(
    model_name='ssd_mobilenet_v2',
    use_coral=False,
    confidence_threshold=0.5
)

# Detect objects in frame (RGB numpy array)
detections = detector.detect(frame)
# Returns: [{'type': 'person', 'rect': (x, y, w, h), 'confidence': 0.95}, ...]

# Get performance stats
stats = detector.get_stats()
# Returns: {'model': '...', 'avg_inference_ms': 42.5, 'estimated_fps': 23.5, ...}
```

## Comparison Table

| Feature | Haar Cascades | TFLite (CPU) | TFLite (Coral) |
|---------|---------------|--------------|----------------|
| **Speed (Pi 5)** | 30+ FPS | 15-25 FPS | 30+ FPS |
| **Accuracy** | 60-70% | 85-90% | 85-90% |
| **Object Classes** | 4 | 80+ | 80+ |
| **Setup Complexity** | Simple | Medium | Medium |
| **Hardware Cost** | $0 | $0 | $60 |
| **Memory Usage** | Low | Medium | Medium |
| **False Positives** | High | Low | Low |
| **Lighting Robustness** | Poor | Good | Good |
| **Occlusion Handling** | Poor | Good | Good |

## Recommendations

### Use Haar Cascades If:
- ✅ You only need face detection
- ✅ You prioritize simplicity
- ✅ You need 30+ FPS guaranteed
- ✅ You have no budget for Coral

### Use TFLite (CPU) If:
- ✅ You need multiple object classes
- ✅ You want better accuracy
- ✅ 15-25 FPS is acceptable
- ✅ You want to future-proof your system

### Use TFLite (Coral) If:
- ✅ You need both speed AND accuracy
- ✅ You can invest $60 in hardware
- ✅ You want 30+ FPS with 80+ classes
- ✅ You want the best of both worlds

## Conclusion

TensorFlow Lite provides a significant upgrade in detection capability while maintaining acceptable real-time performance on Raspberry Pi 5. For $60, a Coral USB Accelerator eliminates the performance penalty entirely.

**Recommended Setup**: TFLite + Coral USB Accelerator

## Further Reading

- [TensorFlow Lite Documentation](https://www.tensorflow.org/lite)
- [Coral USB Accelerator](https://coral.ai/products/accelerator)
- [COCO Dataset](https://cocodataset.org/)
- [Model Zoo](https://www.tensorflow.org/lite/models)

## Support

Issues or questions? Check:
- Configuration: `laserturret.conf.example`
- Source code: `laserturret/tflite_detector.py`
- Benchmark: `scripts/benchmark_detection.py`
- Examples: `app.py` (detection integration)
