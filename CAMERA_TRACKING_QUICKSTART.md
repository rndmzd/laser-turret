# Camera Tracking Quick Start Guide

## What Is Camera Tracking?

Camera tracking mode physically moves your camera using stepper motors to keep objects centered under a fixed crosshair. This is the opposite of traditional crosshair tracking where the camera stays fixed and the crosshair moves on screen.

## Quick Setup (5 Minutes)

### 1. Hardware Check
- ✅ 2x Stepper motors (NEMA 17 recommended)
- ✅ 2x Stepper drivers (A4988 or DRV8825)
- ✅ 12V power supply
- ✅ Pan/tilt mount for camera
- ✅ All wired according to `laserturret.conf`

### 2. Enable Camera Tracking
1. Start the app: `python app.py`
2. Open web UI: `http://localhost:5000`
3. Click **📹 Track** tab
4. Select **"Camera Tracking (Stepper Motors)"**
5. Toggle **"Enable Camera Movement"** ON

### 3. Quick Calibration
1. Enable object detection (👤 Objects tab)
2. Place a target in frame
3. Adjust **X-Axis Steps/Pixel** slider until horizontal tracking works
4. Adjust **Y-Axis Steps/Pixel** slider until vertical tracking works
5. Click **Save Calibration**

### 4. Start Tracking
1. Enable **Auto-Track Objects**
2. Watch the camera follow your target!

## Safety First ⚠️

- **Always test movement manually before enabling auto-tracking**
- Use the **Home Camera** button to return to center
- Set appropriate **Dead Zone** (20px recommended) to prevent oscillation
- Install limit switches for additional safety

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Camera doesn't move | Check power, wiring, and GPIO pins |
| Moves wrong direction | Swap motor wiring or invert direction in code |
| Oscillates back/forth | Increase dead zone to 30-40 pixels |
| Not available message | Check `laserturret.conf` exists and is valid |

## Key Settings

- **Dead Zone**: 20 pixels (prevents jitter)
- **Movement Speed**: 1.0ms (balance between speed and smoothness)
- **Steps/Pixel**: 0.1 default (adjust during calibration)
- **Max Steps**: 2000 (prevents over-extension)

## When to Use Each Mode

**Crosshair Tracking (Default)**
- ✅ No hardware needed
- ✅ Instant response
- ✅ Good for viewing/monitoring
- ❌ Laser must aim at crosshair position

**Camera Tracking (New)**
- ✅ Physical precision
- ✅ Laser always aims at center
- ✅ Better for active targeting
- ❌ Requires calibration
- ❌ Slight movement delay

## Next Steps

- Read full documentation: `CAMERA_TRACKING.md`
- Fine-tune calibration for your setup
- Integrate with laser auto-fire
- Experiment with different detection modes

---

**Need Help?** Check `CAMERA_TRACKING.md` for detailed troubleshooting and advanced configuration.
