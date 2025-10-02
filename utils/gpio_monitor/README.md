# GPIO Monitor - Raspberry Pi 5 Web Application

A real-time web application for monitoring GPIO pin states on Raspberry Pi 5 with a beautiful visual interface.

## Features

- 🎨 **Visual GPIO Pinout Diagram** - Interactive display of all 40 GPIO pins
- 🔴 **Color-Coded Pin States** - Easy-to-read color scheme for pin types and states
- ⚡ **Real-Time Updates** - WebSocket-based live updates (10Hz refresh rate)
- 📊 **Pin Information** - Shows BCM number, physical pin number, function, direction, and state
- 🔌 **Complete Pin Coverage** - Displays all GPIO, power (3.3V/5V), and ground pins

## Color Scheme

- **Orange** - 3.3V Power pins
- **Red** - 5V Power pins
- **Dark Gray** - Ground pins
- **Blue** - GPIO Input pins (LOW state)
- **Green** - GPIO Input pins (HIGH state)
- **Purple** - GPIO Output pins (LOW state)
- **Pink** - GPIO Output pins (HIGH state)

## Installation

### 1. Install System Dependencies

On Raspberry Pi 5, install the required system packages:

```bash
sudo apt-get update
sudo apt-get install python3-pip python3-libgpiod gpiod libgpiod-dev
```

### 2. Install Python Dependencies

```bash
cd utils
pip3 install -r requirements.txt
```

### 3. Run the Application

```bash
python3 gpio_monitor.py
```

The application will start on port 5001. Access it by navigating to:

```
http://<raspberry-pi-ip>:5001
```

Or if running locally on the Pi:

```
http://localhost:5001
```

## Usage

1. **View Pin States** - The interface shows all 40 pins arranged in two columns matching the physical layout
2. **Real-Time Monitoring** - Pin states update automatically every 100ms
3. **Pin Details** - Each pin displays:
   - Physical pin number
   - BCM GPIO number (for GPIO pins)
   - Pin function/name
   - Direction (input/output)
   - Current value (HIGH/LOW)

## Technical Details

### GPIO Library

This application uses `gpiod` (libgpiod), which is the modern GPIO library for Raspberry Pi 5. The older `RPi.GPIO` library is not compatible with Pi 5.

### Pin Mapping

The application uses the BCM (Broadcom) pin numbering scheme and maps it to physical pin positions. The Raspberry Pi 5 uses `gpiochip4` for GPIO access.

### Architecture

- **Backend**: Flask + Flask-SocketIO
- **Frontend**: Vanilla JavaScript with Socket.IO client
- **GPIO Interface**: libgpiod (gpiod Python bindings)
- **Update Mechanism**: WebSocket for real-time bidirectional communication

### Simulation Mode

If `gpiod` is not available (e.g., running on a non-Pi system for development), the application runs in simulation mode with mock data.

## Configuration

### Change Port

Edit `gpio_monitor.py` and modify the port number:

```python
socketio.run(app, host='0.0.0.0', port=5001, debug=False)
```

### Adjust Update Rate

Modify the sleep time in the monitoring loop (in seconds):

```python
time.sleep(0.1)  # Update every 100ms (10Hz)
```

## Troubleshooting

### Permission Issues

If you get permission errors accessing GPIO:

```bash
# Add your user to the gpio group
sudo usermod -a -G gpio $USER

# Log out and back in for changes to take effect
```

### Port Already in Use

If port 5001 is already in use, either:

1. Change the port in `gpio_monitor.py`
2. Stop the conflicting service
3. Use a different port: `python3 gpio_monitor.py --port 5002` (requires code modification)

### GPIO Chip Not Found

The Raspberry Pi 5 typically uses `gpiochip0` (pinctrl-rp1). If you get an error, verify the chip exists:

```bash
gpiodetect
```

If the chip has a different name, update it in `gpio_monitor.py`:

```python
self.chip = gpiod.Chip('gpiochip0')  # Change if needed
```

## Safety Notes

⚠️ **Important**: This application monitors GPIO pins in INPUT mode by default to prevent accidental damage. Changing pin directions or writing values requires code modifications.

- Never connect inputs directly between power and ground
- Be careful with 5V pins - they can damage 3.3V components
- Always check your wiring before connecting external components

## Development

### Project Structure

```
utils/
├── gpio_monitor.py          # Flask application & GPIO monitoring
├── templates/
│   └── gpio_monitor.html    # Frontend interface
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

### Extending the Application

To add features:

1. **Add GPIO Control**: Implement write functionality in `GPIOMonitor` class
2. **Export Data**: Add endpoints to export pin states as JSON/CSV
3. **Alerts**: Add notification system for pin state changes
4. **History**: Store and display historical pin state data

## License

This project is part of the laser-turret repository. See the main LICENSE file for details.

## Credits

Created for Raspberry Pi 5 GPIO monitoring and visualization.
