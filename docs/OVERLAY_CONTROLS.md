# Video Overlay Controls

## Overview

The UI now features **collapsible overlay controls** directly on the video feed. These overlays provide quick access to critical functions without leaving the video view.

## Features

### 1. Toggle Buttons (Top Right)

Three semi-transparent buttons float in the top-right corner of the video:

- **⚡ Motors: ON/OFF** - Instantly enable/disable camera tracking motors
- **🎮 Movement** - Show/hide movement control overlay
- **🔴 Laser** - Show/hide laser control overlay

Buttons highlight when their corresponding overlay is open or when motors are active.

### 2. Movement Control Overlay (Top Left)

Collapsible panel with:
- **3x3 Directional Pad** - Arrow buttons (▲▼◄►) for precise camera control
- **🏠 Center Button** - Sets current position as home
- **Step Size Slider** - Adjust movement increment (10-500 steps)
- **Return to Home Button** - Quick navigation back to center

**Usage:**
1. Click "🎮 Movement" button to open
2. Use arrow buttons to move camera
3. Adjust step size for finer/coarser control
4. Click × to close overlay

### 3. Laser Control Overlay (Bottom Right)

Collapsible panel with:
- **🔴 FIRE LASER Button** - Large, prominent fire button
- **Laser System Toggle** - Enable/disable laser
- **Auto-Fire Toggle** - Enable automatic firing
- **Status Display** - Shows laser status, fire count, and ready state

**Usage:**
1. Click "🔴 Laser" button to open
2. Enable laser system with toggle
3. Fire laser with button
4. Click × to close overlay

### 4. Motors Quick Toggle

The **⚡ Motors** button provides instant motor control:
- Click to toggle camera tracking motors ON/OFF
- Button turns green when motors are active
- Status text shows current state
- Syncs with detailed settings in Camera Tracking tab

## Design Philosophy

### Minimal Interference
- Overlays are hidden by default
- Semi-transparent backgrounds (rgba(0, 0, 0, 0.9))
- Backdrop blur for improved readability
- Can be closed with × button for full video view

### Context Awareness
- Controls appear where needed (movement top-left, laser bottom-right)
- Toggle buttons always visible but unobtrusive
- Active states clearly indicated with color changes

### Synchronization
- All overlay controls sync with detailed settings tabs
- WebSocket updates keep all UI elements current
- Changes in overlays reflect in main control panel and vice versa

## Implementation Details

### CSS Classes

```css
.control-overlay - Base overlay styling (hidden by default)
.control-overlay.hidden - Hide overlay
.movement-overlay - Position for movement controls (top-left)
.laser-overlay - Position for laser controls (bottom-right)
.toggle-overlay-btn - Toggle button styling
.motor-toggle-btn - Motor button with active state
```

### JavaScript Functions

```javascript
toggleOverlay(type) - Show/hide overlay ('movement' or 'laser')
closeOverlay(type) - Close specific overlay
toggleMotors() - Toggle camera tracking motors
```

### WebSocket Integration

Overlays receive real-time updates for:
- Laser status (enabled, ready, fire count)
- Motor status (ON/OFF)
- Fire button enabled state
- Toggle switch states

## User Benefits

1. **Faster Operation** - No tab switching to fire laser or move camera
2. **Better Spatial Awareness** - Control camera while watching target
3. **Clean View** - Close overlays for unobstructed video
4. **Quick Motor Control** - Toggle motors without navigating to settings
5. **Consistent Experience** - Same controls work everywhere

## Keyboard Workflow (Future Enhancement)

Potential additions:
- Hotkeys to toggle overlays (M for movement, L for laser)
- WASD for movement controls
- Spacebar to fire laser
- ESC to close all overlays
