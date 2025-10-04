# TensorFlow Lite Quick Start

## What's New?

Your laser turret now supports **TensorFlow Lite** for advanced object detection! This gives you:

- ✅ **80+ object classes** (people, pets, vehicles, etc.) instead of just faces
- ✅ **85-90% accuracy** vs 60-70% with Haar Cascades
- ✅ **Real-time performance** (15-25 FPS on Raspberry Pi 5)
- ✅ **Optional Coral USB Accelerator** for 30+ FPS

## Quick Setup (3 Steps)

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs `tflite-runtime` (~10MB).

### 2. Configure Detection Method

Edit `laserturret.conf` (or copy from `laserturret.conf.example`):

```ini
[Detection]
detection_method = tflite  # Changed from 'haar'
tflite_model = ssd_mobilenet_v2
use_coral = false
tflite_confidence = 0.5
tflite_filter_classes =  # Empty = all 80 classes
```

### 3. Start the Application

```bash
python app.py
```

The first run will download the model (~4MB). Subsequent runs are instant.

## Example Configurations

### Track People Only
```ini
detection_method = tflite
tflite_filter_classes = person
```

### Track Pets
```ini
detection_method = tflite
tflite_filter_classes = cat,dog,bird
```

### Track Everything (Default)
```ini
detection_method = tflite
tflite_filter_classes =
```

### Use Old Method (Faces Only)
```ini
detection_method = haar
```

## Benchmarking

Compare performance on your hardware:

```bash
python scripts/benchmark_detection.py
```

Example output:
```
HAAR:        117.4 FPS, Avg Detections: 1.2
TFLITE:       23.7 FPS, Avg Detections: 2.8

Recommendation: TFLite provides good performance (>=20 FPS)
```

## API Usage

Switch detection methods at runtime (no restart needed):

```bash
# Switch to TensorFlow Lite
curl -X POST http://localhost:5000/detection_method/switch \
  -H "Content-Type: application/json" \
  -d '{"method": "tflite"}'

# Switch back to Haar Cascades
curl -X POST http://localhost:5000/detection_method/switch \
  -H "Content-Type: application/json" \
  -d '{"method": "haar"}'

# Get current status
curl http://localhost:5000/object_detection/status
```

## Available Object Classes

**People & Animals:** person, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe, bird

**Vehicles:** bicycle, car, motorcycle, airplane, bus, train, truck, boat

**Sports:** sports ball, frisbee, skis, snowboard, kite, baseball bat, surfboard, tennis racket

**Indoor Objects:** chair, couch, bed, dining table, tv, laptop, book, clock

**All 80 classes:** See `COCO_LABELS` in `laserturret/tflite_detector.py`

## Performance Tips

1. **Lower camera resolution** for faster inference:
   ```python
   CAMERA_WIDTH = 1280  # Instead of 1920
   CAMERA_HEIGHT = 720  # Instead of 1080
   ```

2. **Filter to specific classes**:
   ```ini
   tflite_filter_classes = person,cat,dog
   ```

3. **Increase confidence threshold** (fewer false positives):
   ```ini
   tflite_confidence = 0.7  # Instead of 0.5
   ```

4. **Use Coral USB Accelerator** ($60, 2-3x speedup):
   ```ini
   use_coral = true
   ```

## Troubleshooting

**Problem:** `TensorFlow Lite not available`

**Solution:**
```bash
pip install tflite-runtime
```

---

**Problem:** Low FPS (< 15)

**Solutions:**
- Lower camera resolution
- Increase confidence threshold
- Switch to `ssd_mobilenet_v2` (faster model)
- Consider Coral USB Accelerator
- Fall back to Haar Cascades

---

**Problem:** Too many false detections

**Solutions:**
- Increase confidence: `tflite_confidence = 0.7`
- Filter classes: `tflite_filter_classes = person`

## Full Documentation

For complete details, see:
- **[TENSORFLOW_INTEGRATION.md](TENSORFLOW_INTEGRATION.md)** - Complete guide
- **[laserturret.conf.example](laserturret.conf.example)** - Configuration options
- **[scripts/benchmark_detection.py](scripts/benchmark_detection.py)** - Benchmark tool
- **[laserturret/tflite_detector.py](laserturret/tflite_detector.py)** - Source code

## Comparison

| Feature | Haar Cascades | TFLite |
|---------|---------------|--------|
| **Classes** | 4 (face, eye, body, smile) | 80+ (COCO dataset) |
| **Accuracy** | 60-70% | 85-90% |
| **Speed (Pi 5)** | 30+ FPS | 15-25 FPS |
| **With Coral** | N/A | 30+ FPS |
| **Setup** | Simple | Medium |

## Recommendation

**Use TFLite** if you want:
- Multiple object types (pets, toys, people, etc.)
- Better accuracy and fewer false positives
- Future-proof solution

**Use Haar** if you:
- Only need face detection
- Want maximum simplicity
- Need guaranteed 30+ FPS without extra hardware

**Best of Both Worlds**: TFLite + Coral USB Accelerator ($60)

---

**Questions?** Check the full documentation or open an issue on GitHub.
