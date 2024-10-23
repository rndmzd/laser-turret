import time
import board
import busio
import digitalio
import wifi
import socketpool
import adafruit_requests
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
import adafruit_minimqtt.adafruit_minimqtt as MQTT

#SSID = '***REMOVED***'
#PASSWORD = '***REMOVED***'

#print("Connecting to Wi-Fi...")
#wifi.radio.connect(SSID, PASSWORD)
#print(f"Connected to {SSID}")

# Create a socket pool
#pool = socketpool.SocketPool(wifi.radio)

# Set up ADS1115 and Joystick
i2c = busio.I2C(board.IO8, board.IO9)
while not i2c.try_lock():
    pass
print([hex(da) for da in i2c.scan()])
ads = ADS.ADS1115(i2c)
joystick_x = AnalogIn(ads, ADS.P0)
joystick_y = AnalogIn(ads, ADS.P1)

# MQTT setup
broker = 'laserturret'
topic = 'joystick'

def connected(client, userdata, flags, rc):
    print("Connected to MQTT broker!")

def disconnected(client, userdata, rc):
    print("Disconnected from MQTT broker!")

def publish(client, userdata, topic, pid):
    print(f"Published to {topic} with PID {pid}")

# Create MQTT client
#mqtt_client = MQTT.MQTT(
#    broker=broker,
#    socket_pool=pool,
#    is_ssl=False
#)

# Setup MQTT callbacks
#mqtt_client.on_connect = connected
#mqtt_client.on_disconnect = disconnected
#mqtt_client.on_publish = publish

# Connect to the broker
#mqtt_client.connect()

# Main loop
while True:
    x_val = joystick_x.value
    y_val = joystick_y.value
    payload = f"{x_val},{y_val}"
    
    #mqtt_client.publish(topic, payload)
    print(payload)
    time.sleep(0.1)

