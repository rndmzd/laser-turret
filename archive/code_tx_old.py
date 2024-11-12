import time
import board
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from analogio import AnalogIn
from digitalio import DigitalInOut, Pull
import json
import microcontroller
import neopixel

import secrets

# Neopixel setup
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.3)  # Set initial brightness to 30%

# Colors for different states
COLOR_OFF = (0, 0, 0)
COLOR_WIFI_CONNECTING = (255, 165, 0)  # Orange
COLOR_WIFI_CONNECTED = (0, 255, 0)     # Green
COLOR_MQTT_CONNECTED = (0, 128, 255)   # Light blue
COLOR_CALIBRATING = (255, 0, 255)      # Purple
COLOR_ERROR = (255, 0, 0)              # Red
COLOR_ACTIVE = (255, 255, 255)         # White

# Wi-Fi setup
SSID = secrets.WIFI_SSID
PASSWORD = secrets.WIFI_PASSWORD

# Max size of NVM data (255 bytes)
NVM_SIZE = 255

# Default calibration data
calibration = {
    'left': 0,
    'right': 65535,
    'up': 65535,
    'down': 0,
    'x_center': 32767,
    'y_center': 32767
}

# Save calibration data to NVM
def save_calibration(calibration_data):
    try:
        # Convert calibration dict to JSON string
        calibration_string = json.dumps(calibration_data)
        
        # Check if data will fit in NVM
        if len(calibration_string) > NVM_SIZE:
            print("Calibration data too large to save.")
            return
        
        # Clear NVM first by writing zeros
        for i in range(NVM_SIZE):
            microcontroller.nvm[i] = 0
            
        # Write the data to NVM
        nvm_bytes = bytes(calibration_string, "utf-8")
        for i, b in enumerate(nvm_bytes):
            microcontroller.nvm[i] = b
            
        print("Calibration saved successfully!")
        
    except Exception as e:
        print(f"Failed to save calibration: {e}")

# Load calibration data from NVM
def load_calibration():
    try:
        # Read data until we hit a null byte
        nvm_data = ""
        for i in range(NVM_SIZE):
            if microcontroller.nvm[i] == 0:
                break
            nvm_data += chr(microcontroller.nvm[i])
        
        if nvm_data:
            # Parse JSON and update calibration
            loaded_cal = json.loads(nvm_data)
            calibration.update(loaded_cal)
            print("Calibration loaded successfully!")
            print(f"Loaded values: {calibration}")
            return calibration
        else:
            print("No calibration data found, using defaults.")
            return calibration
            
    except Exception as e:
        print(f"Failed to load calibration data: {e}")
        print("Using default calibration values.")
        return calibration

# Function to connect to Wi-Fi
def connect_to_wifi():
    print("Connecting to Wi-Fi...")
    pixel.fill(COLOR_WIFI_CONNECTING)
    try:
        wifi.radio.connect(SSID, PASSWORD)
        print(f"Connected to {SSID}")
        pixel.fill(COLOR_WIFI_CONNECTED)
    except Exception as e:
        print(f"Failed to connect to Wi-Fi: {e}")
        pixel.fill(COLOR_ERROR)
        time.sleep(5)
        connect_to_wifi()

# Function to handle MQTT connection
def connect_to_mqtt():
    try:
        mqtt_client.connect()
        print("Connected to MQTT broker!")
        pixel.fill(COLOR_MQTT_CONNECTED)
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        pixel.fill(COLOR_ERROR)
        time.sleep(5)
        connect_to_mqtt()

# MQTT callback functions
def connected(client, userdata, flags, rc):
    print("Connected to MQTT broker!")

def disconnected(client, userdata, rc):
    print("Disconnected from MQTT broker!")

def publish(client, userdata, topic, pid):
    print(f"Published to {topic} with PID {pid}")

# Wait for joystick button press and release
def wait_for_button_press():
    while button.value:
        time.sleep(0.1)  # Wait until the button is pressed
    while not button.value:
        time.sleep(0.1)  # Wait until the button is released
    time.sleep(1)  # 1-second delay after button release

# Modified calibration function with LED feedback
def calibrate_joystick():
    print("Joystick calibration started! Press button to proceed.")
    pixel.fill(COLOR_CALIBRATING)
    wait_for_button_press()
    
    # X-Minimum
    print("Press the button then move joystick to the farthest LEFT position within 5 seconds.")
    wait_for_button_press()
    print("Reading values...")
    start_time = time.time()
    x_min = 30000
    while (time.time() - start_time) < 5:
        val = joystick_x.value
        if val < x_min:
            x_min = val
        time.sleep(0.1)
    print("Complete.")
    calibration['left'] = x_min
    print(f"X-Minimum: {calibration['left']}")
    
    # Farthest Up
    print("Press the button then move joystick to the farthest UP position within 5 seconds.")
    wait_for_button_press()
    print("Reading values...")
    start_time = time.time()
    y_max = 30000
    while (time.time() - start_time) < 5:
        val = joystick_y.value
        if val > y_max:
            y_max = val
        time.sleep(0.1)
    print("Complete.")
    calibration['up'] = y_max
    print(f"Y-Maximum: {calibration['up']}")
    
    # Farthest Right
    print("Press the button then move joystick to the farthest RIGHT position within 5 seconds.")
    wait_for_button_press()
    print("Reading values...")
    start_time = time.time()
    x_max = 30000
    while (time.time() - start_time) < 5:
        val = joystick_x.value
        if val > x_max:
            x_max = val
        time.sleep(0.1)
    print("Complete.")
    calibration['right'] = x_max
    print(f"X-Maximum: {calibration['right']}")
    
    # Farthest Down
    print("Press the button then move joystick to the farthest DOWN position within 5 seconds.")
    wait_for_button_press()
    print("Reading values...")
    start_time = time.time()
    y_min = 30000
    while (time.time() - start_time) < 5:
        val = joystick_y.value
        if val < y_min:
            y_min = val
        time.sleep(0.1)
    print("Complete.")
    calibration['down'] = y_min
    print(f"Y-Minimum: {calibration['down']}")

    # Center
    print("Press the button then leave it at its CENTER position for 5 seconds.")
    wait_for_button_press()
    time.sleep(3)
    print("Reading values...")
    start_time = time.time()
    x_center = joystick_x.value
    y_center = joystick_y.value
    print("Complete.")
    calibration['x_center'] = x_center
    calibration['y_center'] = y_center
    print(f"Center: {calibration['x_center']}, {calibration['y_center']}")
    
    print("Calibration complete!")
    save_calibration(calibration)
    pixel.fill(COLOR_MQTT_CONNECTED)  # Return to normal operation color

def map_joystick_values(x_val, y_val):
    # Use stored center values
    x_center = calibration['x_center']
    y_center = calibration['y_center']
    
    # Map X-axis values (-100 to +100)
    if x_val < x_center:
        # Left side (negative values)
        x_mapped = (x_val - x_center) / (x_center - calibration['left']) * 100
    else:
        # Right side (positive values)
        x_mapped = (x_val - x_center) / (calibration['right'] - x_center) * 100
    
    # Map Y-axis values (-100 to +100)
    if y_val < y_center:
        # Down side (negative values)
        y_mapped = (y_val - y_center) / (y_center - calibration['down']) * 100
    else:
        # Up side (positive values)
        y_mapped = (y_val - y_center) / (calibration['up'] - y_center) * 100
    
    # Clamp values between -100 and 100
    x_mapped = max(-100, min(100, x_mapped))
    y_mapped = max(-100, min(100, y_mapped))
    
    return int(x_mapped), int(y_mapped)

# Function to update LED based on joystick movement
def update_led_from_movement(x_mapped, y_mapped):
    # Calculate intensity based on movement magnitude
    magnitude = min(100, max(abs(x_mapped), abs(y_mapped)))
    intensity = magnitude / 100.0
    
    # Create color based on direction
    if abs(x_mapped) > abs(y_mapped):
        # More horizontal movement
        if x_mapped > 0:
            color = (int(255 * intensity), int(128 * intensity), 0)  # Yellow-orange for right
        else:
            color = (0, int(255 * intensity), int(128 * intensity))  # Cyan for left
    else:
        # More vertical movement
        if y_mapped > 0:
            color = (int(128 * intensity), int(255 * intensity), 0)  # Green-yellow for up
        else:
            color = (int(255 * intensity), 0, int(128 * intensity))  # Purple for down
    
    pixel.fill(color)

# Initialize hardware and connections
pool = socketpool.SocketPool(wifi.radio)

joystick_x = AnalogIn(board.IO8)  # X-axis pin
joystick_y = AnalogIn(board.IO9)  # Y-axis pin

button = DigitalInOut(board.IO7)  # Button pin
button.switch_to_input(pull=Pull.UP)

broker = '192.168.1.182'
topic = 'laserturret'

# Connect to Wi-Fi
connect_to_wifi()

# Setup MQTT
mqtt_client = MQTT.MQTT(
    broker=broker,
    socket_pool=pool,
    is_ssl=False
)

mqtt_client.on_connect = connected
mqtt_client.on_disconnect = disconnected
mqtt_client.on_publish = publish

connect_to_mqtt()

# Load calibration data
calibration = load_calibration()

# Check if joystick button is pressed during startup
if not button.value:
    calibrate_joystick()

# Main loop
while True:
    try:
        x_val = joystick_x.value
        y_val = joystick_y.value
        button_pressed = not button.value
        
        # Map joystick values using the calibration
        x_mapped, y_mapped = map_joystick_values(x_val, y_val)

        # Update LED based on movement
        update_led_from_movement(x_mapped, y_mapped)
        
        # Create payload to send
        payload = f"{x_mapped},{y_mapped},{button_pressed}"
        mqtt_client.publish(topic, payload)

        # Show button press with white flash
        if button_pressed:
            pixel.fill(COLOR_ACTIVE)
        
        time.sleep(0.25)
        
    except Exception as e:
        print(f"Error in main loop: {e}")
        pixel.fill(COLOR_ERROR)
        time.sleep(1)
