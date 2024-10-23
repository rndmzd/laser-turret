import time
import board
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from analogio import AnalogIn
from digitalio import DigitalInOut, Pull
import json
import microcontroller

# Wi-Fi setup
SSID = "***REMOVED***"
PASSWORD = "***REMOVED***"

# Max size of NVM data (255 bytes)
NVM_SIZE = 255

# Default calibration data
calibration = {
    'left': 0,
    'right': 65535,
    'up': 0,
    'down': 65535
}

# Function to connect to Wi-Fi
def connect_to_wifi():
    print("Connecting to Wi-Fi...")
    try:
        wifi.radio.connect(SSID, PASSWORD)
        print(f"Connected to {SSID}")
    except Exception as e:
        print(f"Failed to connect to Wi-Fi: {e}")
        time.sleep(5)
        connect_to_wifi()

# Connect to Wi-Fi
connect_to_wifi()

# Create a socket pool
pool = socketpool.SocketPool(wifi.radio)

# Set up analog inputs for joystick (powered by 3.3V)
joystick_x = AnalogIn(board.IO8)  # X-axis pin
joystick_y = AnalogIn(board.IO9)  # Y-axis pin

# Set up digital input for the button (with pull-up resistor)
button = DigitalInOut(board.IO7)  # Button pin
button.switch_to_input(pull=Pull.UP)

# MQTT setup
broker = '192.168.1.182'
topic = 'laserturret'

# Function to handle MQTT connection
def connect_to_mqtt():
    try:
        mqtt_client.connect()
        print("Connected to MQTT broker!")
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        time.sleep(5)
        connect_to_mqtt()

# MQTT callback functions
def connected(client, userdata, flags, rc):
    print("Connected to MQTT broker!")

def disconnected(client, userdata, rc):
    print("Disconnected from MQTT broker!")

def publish(client, userdata, topic, pid):
    print(f"Published to {topic} with PID {pid}")

# Create MQTT client
mqtt_client = MQTT.MQTT(
    broker=broker,
    socket_pool=pool,
    is_ssl=False
)

# Setup MQTT callbacks
mqtt_client.on_connect = connected
mqtt_client.on_disconnect = disconnected
mqtt_client.on_publish = publish

# Connect to MQTT broker
connect_to_mqtt()

# Save calibration data to NVM
def save_calibration():
    try:
        calibration_data = json.dumps(calibration)
        if len(calibration_data) > NVM_SIZE:
            print("Calibration data too large to save.")
            return
        # Convert string to bytes and save in non-volatile memory
        microcontroller.nvm[0:len(calibration_data)] = bytes(calibration_data, "utf-8")
        print("Calibration data saved!")
    except Exception as e:
        print(f"Failed to save calibration: {e}")

# Load calibration data from NVM
def load_calibration():
    try:
        # Read bytes from non-volatile memory and convert to string
        nvm_data = bytes(microcontroller.nvm).decode("utf-8").strip('\x00')
        if nvm_data:
            global calibration
            calibration = json.loads(nvm_data)
            print("Calibration data loaded!")
        else:
            print("No calibration data found, using defaults.")
    except Exception as e:
        print("Failed to load calibration data, using defaults.")

# Calibration function
def calibrate_joystick():
    print("Joystick calibration started! Press button to proceed.")
    wait_for_button_press()
    
    # Farthest Left
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
    print(f"Farthest LEFT recorded: {calibration['left']}")
    
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
    print(f"Farthest UP recorded: {calibration['up']}")
    
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
    print(f"Farthest RIGHT recorded: {calibration['right']}")
    
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
    print(f"Farthest DOWN recorded: {calibration['down']}")
    
    print("Calibration complete!")
    save_calibration()  # Save calibration data after completing

# Wait for joystick button press and release, with a delay after release
def wait_for_button_press():
    while button.value:
        time.sleep(0.1)  # Wait until the button is pressed
    while not button.value:
        time.sleep(0.1)  # Wait until the button is released
    time.sleep(1)  # 1-second delay after button release

# Mapping function to map joystick values to the usable range
def map_joystick_values(x_val, y_val):
    # Map X-axis values
    x_mapped = (x_val - calibration['left']) / (calibration['right'] - calibration['left']) * 65535
    x_mapped = max(0, min(65535, x_mapped))  # Ensure value stays in range
    
    # Map Y-axis values
    y_mapped = (y_val - calibration['down']) / (calibration['up'] - calibration['down']) * 65535
    y_mapped = max(0, min(65535, y_mapped))  # Ensure value stays in range
    
    return int(x_mapped), int(y_mapped)

# Load calibration data from NVM at startup
load_calibration()

# Check if joystick button is pressed during startup
if not button.value:
    calibrate_joystick()

# Main loop
while True:
    try:
        x_val = joystick_x.value  # Read X-axis (0-65535 range)
        y_val = joystick_y.value  # Read Y-axis (0-65535 range)
        button_pressed = not button.value  # Button is pressed when value is False (due to pull-up)
        
        # Map joystick values using the calibration
        x_mapped, y_mapped = map_joystick_values(x_val, y_val)
        
        # Create payload to send
        payload = f"{x_mapped},{y_mapped},{button_pressed}"
        mqtt_client.publish(topic, payload)
        
        time.sleep(0.1)
        
    except Exception as e:
        print(f"Error in main loop: {e}")
        time.sleep(1)
