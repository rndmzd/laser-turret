# GPIO Monitor - System Architecture

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Web Browser                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │            GPIO Monitor Frontend (HTML/JS)            │  │
│  │  • Visual GPIO Pinout Display                         │  │
│  │  • Socket.IO Client                                   │  │
│  │  • Real-time State Updates                            │  │
│  │  • Color-coded Pin Visualization                      │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕ WebSocket (Socket.IO)
┌─────────────────────────────────────────────────────────────┐
│              Flask Web Server (Port 5001)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Flask-SocketIO Application               │  │
│  │  • HTTP Routes (/,  /api/pinout)                      │  │
│  │  • WebSocket Events (connect, disconnect, update)     │  │
│  │  • Real-time Event Broadcasting                       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                   GPIOMonitor Class                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           Background Monitoring Thread                │  │
│  │  • Continuous GPIO State Reading                      │  │
│  │  • 10Hz Update Rate (100ms interval)                  │  │
│  │  • State Change Detection                             │  │
│  │  • WebSocket Event Emission                           │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Pin State Management                     │  │
│  │  • Track 40 Physical Pins                             │  │
│  │  • GPIO/Power/Ground Pin Types                        │  │
│  │  • Direction & Value Tracking                         │  │
│  │  • Pin Function Mapping                               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                  libgpiod (gpiod library)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         Modern GPIO Interface for Pi 5                │  │
│  │  • Direct Hardware Access                             │  │
│  │  • Line Request/Release Management                    │  │
│  │  • Read Pin Values                                    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│              Linux Kernel GPIO Subsystem                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              gpiochip4 (54 lines)                     │  │
│  │  • Hardware GPIO Controller                           │  │
│  │  • Raspberry Pi 5 GPIO Chip                           │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│          Raspberry Pi 5 Hardware GPIO Pins (40)              │
│                   Physical Connectors                        │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Data Flow

### Initialization Flow

```
1. Application Start
   └─→ GPIOMonitor.__init__()
       ├─→ Open gpiochip4
       ├─→ Request GPIO lines (input mode)
       └─→ Initialize pin state dictionary

2. Flask Application Setup
   └─→ Initialize Flask + SocketIO
       ├─→ Register routes
       ├─→ Setup WebSocket handlers
       └─→ Start monitoring thread

3. Background Monitoring Thread
   └─→ Continuous loop (10Hz)
       ├─→ Read all GPIO pin values
       ├─→ Update internal state
       └─→ Broadcast via WebSocket
```

### Real-time Update Flow

```
GPIO Hardware
    ↓ (100ms interval)
gpiod.line.get_value()
    ↓
Pin State Updated
    ↓
SocketIO.emit('gpio_update')
    ↓ (WebSocket)
Browser Socket.IO Client
    ↓
JavaScript Event Handler
    ↓
Update DOM Elements
    ↓
Visual Display Updated
```

## 🔄 Component Interactions

### Backend Components

```python
# Main Application Thread
Flask App
  └─→ SocketIO Server
      ├─→ Handle client connections
      ├─→ Serve static content
      └─→ Broadcast updates

# Background Thread
GPIOMonitor Thread
  └─→ While running:
      ├─→ Read GPIO states
      ├─→ Format data
      └─→ Emit to all clients
```

### Frontend Components

```javascript
// Socket.IO Client
socket.on('connect')
  └─→ Request initial update

socket.on('gpio_update')
  └─→ updateGPIODisplay(data)
      ├─→ Parse pin data
      ├─→ Apply color coding
      ├─→ Update DOM elements
      └─→ Animate changes
```

## 🗂️ Data Structures

### Pin State Object

```python
{
    'physical': 7,           # Physical pin number (1-40)
    'bcm': 4,                # BCM GPIO number
    'type': 'GPIO',          # Pin type: GPIO/3V3/5V/GND
    'value': 0,              # Current value: 0 (LOW) or 1 (HIGH)
    'direction': 'input',    # Direction: input/output/unknown
    'function': 'GPIO4',     # Pin function name
    'pull': 'down'           # Pull resistor: up/down/none
}
```

### Complete Pinout Data

```python
{
    1: {'physical': 1, 'type': '3V3', ...},
    2: {'physical': 2, 'type': '5V', ...},
    3: {'physical': 3, 'bcm': 2, 'type': 'GPIO', ...},
    # ... all 40 pins
}
```

## 🧵 Threading Model

```
Main Thread (Flask/SocketIO)
  │
  ├─→ HTTP Request Handler Thread(s)
  │   └─→ Serve HTML/API requests
  │
  ├─→ WebSocket Handler Thread(s)
  │   └─→ Handle client connections
  │
  └─→ GPIO Monitor Thread (Daemon)
      └─→ Continuous GPIO polling
          └─→ Emit updates to all clients
```

## 🎨 Frontend Architecture

### HTML Structure

```html
<body>
  <container>
    <header>
      ├─→ Title
      └─→ Status Indicator
    </header>
    <gpio-board>
      ├─→ pin-container (Grid)
      │   ├─→ left-column (Pins 1,3,5...39)
      │   └─→ right-column (Pins 2,4,6...40)
      ├─→ legend (Color guide)
      └─→ update-time
    </gpio-board>
  </container>
</body>
```

### CSS Layout

```css
Grid Layout
  ├─→ Two columns (left/right pins)
  ├─→ Responsive design
  ├─→ Color-coded backgrounds
  ├─→ Hover effects
  └─→ Smooth animations
```

### JavaScript Modules

```javascript
// Core Functions
├─→ Socket.IO connection management
├─→ updateGPIODisplay(data)
├─→ getPinClass(pin)
├─→ formatPinInfo(pin)
└─→ Event handlers (connect/disconnect/update)
```

## 🔐 Security Considerations

### Current Implementation

- ✅ **Read-only access** - No write operations
- ✅ **Input mode only** - All GPIO requested as inputs
- ✅ **No authentication** - Suitable for local network
- ✅ **No PIN control** - Cannot change configurations

### Recommendations for Production

- 🔒 Add user authentication (Flask-Login)
- 🔒 Implement HTTPS/TLS
- 🔒 Rate limiting for API endpoints
- 🔒 CORS configuration
- 🔒 Input validation for future write operations

## ⚡ Performance Optimization

### Current Optimizations

1. **Efficient Polling**: 100ms interval balances responsiveness and CPU usage
2. **Batch Updates**: Single WebSocket message for all pins
3. **Daemon Thread**: Non-blocking background monitoring
4. **Minimal DOM Updates**: Only update changed elements
5. **CSS Animations**: Hardware-accelerated transitions

### Potential Improvements

- Implement change detection (only send updates on state changes)
- Add client-side caching
- Compress WebSocket messages
- Lazy load pin history data

## 📈 Scalability

### Current Limitations

- Single GPIO chip (gpiochip4)
- Single Raspberry Pi
- WebSocket per client

### Future Scalability Options

- Multi-chip support
- Multiple Pi monitoring from one interface
- Aggregated dashboard for fleet monitoring
- Database storage for historical data

## 🐛 Error Handling

```
Error Detection Points:

1. GPIO Chip Access
   └─→ Fallback to simulation mode

2. Line Request Failure
   └─→ Mark pin as unknown state

3. Read Value Error
   └─→ Keep last known value

4. WebSocket Disconnect
   └─→ Auto-reconnect with status indicator

5. Network Issues
   └─→ Connection status display
```

## 🔧 Configuration Points

| Component | Configuration | Location |
|-----------|--------------|----------|
| Web Server | Port (5001) | `gpio_monitor.py:264` |
| Update Rate | 100ms | `gpio_monitor.py:184` |
| GPIO Chip | gpiochip4 | `gpio_monitor.py:71` |
| Pin Mapping | PI5_PINOUT | `gpio_monitor.py:24-61` |
| Colors | CSS classes | `gpio_monitor.html:50-100` |

## 📚 Dependencies Graph

```
Application
  ├─→ Flask (Web framework)
  │   └─→ Werkzeug (WSGI)
  ├─→ Flask-SocketIO (WebSocket support)
  │   ├─→ python-socketio (Server implementation)
  │   └─→ eventlet (Async I/O)
  └─→ gpiod (GPIO access)
      └─→ libgpiod (System library)
          └─→ Linux kernel GPIO subsystem
```

## 🎯 Design Principles

1. **Simplicity**: Minimal dependencies, straightforward code
2. **Reliability**: Graceful degradation, error handling
3. **Real-time**: Low latency updates via WebSocket
4. **Safety**: Read-only operations prevent damage
5. **Usability**: Intuitive visual interface
6. **Portability**: Simulation mode for development

## 📝 Code Organization

```
gpio_monitor.py (8KB)
  ├─→ Constants (PI5_PINOUT, GPIO_PINS)
  ├─→ GPIOMonitor Class (250 lines)
  │   ├─→ __init__: Setup GPIO
  │   ├─→ initialize_pins: Pin configuration
  │   ├─→ read_pin_states: GPIO reading
  │   ├─→ get_pinout_data: Data formatting
  │   ├─→ start_monitoring: Thread management
  │   └─→ _monitor_loop: Background polling
  ├─→ Flask Routes (3 routes)
  └─→ SocketIO Handlers (3 events)

gpio_monitor.html (12KB)
  ├─→ HTML Structure (100 lines)
  ├─→ CSS Styles (300 lines)
  └─→ JavaScript Logic (150 lines)
```

---

**Last Updated**: 2025-09-29
**Architecture Version**: 1.0
**Target Platform**: Raspberry Pi 5
