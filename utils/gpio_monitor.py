"""
GPIO Monitor Web Application for Raspberry Pi 5
Displays real-time GPIO pin states with visual pinout diagram
"""

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import threading
import time
import os

# Try to import gpiod (modern library for Pi 5)
try:
    import gpiod
    from gpiod.line import Direction, Value
    GPIO_AVAILABLE = True
except ImportError:
    print("Warning: gpiod not available. Running in simulation mode.")
    GPIO_AVAILABLE = False

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gpio-monitor-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Raspberry Pi 5 GPIO Pin mapping (BCM numbers)
# Physical pin number -> BCM GPIO number mapping
PI5_PINOUT = {
    # Left side (odd numbers)
    1: None,    # 3.3V
    3: 2,       # GPIO 2 (SDA)
    5: 3,       # GPIO 3 (SCL)
    7: 4,       # GPIO 4
    9: None,    # Ground
    11: 17,     # GPIO 17
    13: 27,     # GPIO 27
    15: 22,     # GPIO 22
    17: None,   # 3.3V
    19: 10,     # GPIO 10 (MOSI)
    21: 9,      # GPIO 9 (MISO)
    23: 11,     # GPIO 11 (SCLK)
    25: None,   # Ground
    27: 0,      # GPIO 0 (ID_SD)
    29: 5,      # GPIO 5
    31: 6,      # GPIO 6
    33: 13,     # GPIO 13
    35: 19,     # GPIO 19
    37: 26,     # GPIO 26
    39: None,   # Ground
    
    # Right side (even numbers)
    2: None,    # 5V
    4: None,    # 5V
    6: None,    # Ground
    8: 14,      # GPIO 14 (TXD)
    10: 15,     # GPIO 15 (RXD)
    12: 18,     # GPIO 18
    14: None,   # Ground
    16: 23,     # GPIO 23
    18: 24,     # GPIO 24
    20: None,   # Ground
    22: 25,     # GPIO 25
    24: 8,      # GPIO 8 (CE0)
    26: 7,      # GPIO 7 (CE1)
    28: 1,      # GPIO 1 (ID_SC)
    30: None,   # Ground
    32: 12,     # GPIO 12
    34: None,   # Ground
    36: 16,     # GPIO 16
    38: 20,     # GPIO 20
    40: 21,     # GPIO 21
}

# Get all GPIO BCM numbers (excluding None/power/ground pins)
GPIO_PINS = sorted([bcm for bcm in PI5_PINOUT.values() if bcm is not None])

class GPIOMonitor:
    """Monitor GPIO pin states"""
    
    def __init__(self):
        self.chip = None
        self.request = None
        self.pin_states = {}
        self.running = False
        
        if GPIO_AVAILABLE:
            try:
                # Open GPIO chip (gpiochip0 for Pi 5 - pinctrl-rp1)
                # gpiod v2.x API
                self.chip = gpiod.Chip('/dev/gpiochip0')
                
                # Request all GPIO lines as inputs
                line_config = {
                    line: gpiod.LineSettings(direction=Direction.INPUT)
                    for line in GPIO_PINS
                }
                
                self.request = self.chip.request_lines(
                    consumer="gpio-monitor",
                    config=line_config
                )
                print("GPIO chip opened successfully")
            except Exception as e:
                print(f"Error opening GPIO chip: {e}")
                print("Running in simulation mode")
                self.chip = None
                self.request = None
        
        self.initialize_pins()
    
    def initialize_pins(self):
        """Initialize all GPIO pins for monitoring"""
        for bcm in GPIO_PINS:
            # Initialize state
            self.pin_states[bcm] = {
                'bcm': bcm,
                'value': 0,
                'direction': 'input',
                'function': self.get_pin_function(bcm),
                'pull': 'none'
            }
    
    def get_pin_function(self, bcm):
        """Get the special function name for a BCM pin"""
        functions = {
            0: 'ID_SD', 1: 'ID_SC',
            2: 'SDA1', 3: 'SCL1',
            4: 'GPCLK0', 
            7: 'CE1', 8: 'CE0',
            9: 'MISO', 10: 'MOSI', 11: 'SCLK',
            14: 'TXD', 15: 'RXD',
            18: 'PCM_CLK', 19: 'PCM_FS', 20: 'PCM_DIN', 21: 'PCM_DOUT',
        }
        return functions.get(bcm, f'GPIO{bcm}')
    
    def read_pin_states(self):
        """Read current state of all GPIO pins"""
        if self.request:
            # Real GPIO reading with gpiod v2.x API
            try:
                for bcm in GPIO_PINS:
                    value = self.request.get_value(bcm)
                    # Convert Value enum to int (0 or 1)
                    self.pin_states[bcm]['value'] = 1 if value == Value.ACTIVE else 0
            except Exception as e:
                print(f"Error reading GPIO: {e}")
        else:
            # Simulation mode - generate random states
            import random
            for bcm in GPIO_PINS:
                if random.random() > 0.95:  # Occasionally change state
                    self.pin_states[bcm]['value'] = 1 - self.pin_states[bcm]['value']
        
        return self.pin_states
    
    def get_pinout_data(self):
        """Get complete pinout data including power/ground pins"""
        pinout = {}
        for physical_pin, bcm in PI5_PINOUT.items():
            if bcm is None:
                # Determine pin type
                if physical_pin in [1, 17]:
                    pin_type = '3V3'
                elif physical_pin in [2, 4]:
                    pin_type = '5V'
                else:
                    pin_type = 'GND'
                
                pinout[physical_pin] = {
                    'physical': physical_pin,
                    'bcm': None,
                    'type': pin_type,
                    'value': None,
                    'direction': None,
                    'function': pin_type
                }
            else:
                state = self.pin_states.get(bcm, {})
                pinout[physical_pin] = {
                    'physical': physical_pin,
                    'bcm': bcm,
                    'type': 'GPIO',
                    'value': state.get('value', 0),
                    'direction': state.get('direction', 'unknown'),
                    'function': state.get('function', f'GPIO{bcm}'),
                    'pull': state.get('pull', 'none')
                }
        
        return pinout
    
    def start_monitoring(self):
        """Start continuous monitoring in background thread"""
        self.running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.running:
            self.read_pin_states()
            pinout_data = self.get_pinout_data()
            
            # Emit update via SocketIO
            socketio.emit('gpio_update', pinout_data)
            
            time.sleep(0.1)  # Update every 100ms
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
        
        # Release GPIO request (gpiod v2.x)
        if self.request:
            try:
                self.request.release()
            except:
                pass
        
        if self.chip:
            try:
                self.chip.close()
            except:
                pass

# Global monitor instance
gpio_monitor = GPIOMonitor()

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('gpio_monitor.html')

@app.route('/api/pinout')
def get_pinout():
    """Get current pinout data"""
    return jsonify(gpio_monitor.get_pinout_data())

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    # Send initial state
    emit('gpio_update', gpio_monitor.get_pinout_data())

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

@socketio.on('request_update')
def handle_update_request():
    """Handle manual update request"""
    emit('gpio_update', gpio_monitor.get_pinout_data())

if __name__ == '__main__':
    print("Starting GPIO Monitor Web Application")
    print(f"GPIO Available: {GPIO_AVAILABLE}")
    
    # Start monitoring
    gpio_monitor.start_monitoring()
    
    try:
        # Run the Flask app with SocketIO
        socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)
    finally:
        gpio_monitor.stop_monitoring()
