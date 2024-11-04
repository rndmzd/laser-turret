import paho.mqtt.client as mqtt
import time
from laserturret import StepperMotor
import RPi.GPIO as GPIO

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_TOPIC = "laserturret"

# Motor Configuration
X_MOTOR_CHANNEL = 1
Y_MOTOR_CHANNEL = 2
X_LIMIT_SWITCH_PIN = 17
Y_LIMIT_SWITCH_PIN = 27
STEPS_PER_REV = 200
MICROSTEPS = 8

# Control Parameters
MAX_STEPS_PER_UPDATE = 5  # Maximum steps to move per MQTT message
CONTROL_DEADZONE = 5      # Values between -5 and 5 are ignored
SPEED_SCALING = 0.05      # Adjust this to change movement sensitivity

class TurretController:
    def __init__(self):
        # Initialize stepper motors
        self.motor_x = StepperMotor(
            motor_channel=X_MOTOR_CHANNEL,
            limit_switch_pin=X_LIMIT_SWITCH_PIN,
            limit_switch_direction='CCW',
            steps_per_rev=STEPS_PER_REV,
            microsteps=MICROSTEPS,
            name="MotorX"
        )
        
        self.motor_y = StepperMotor(
            motor_channel=Y_MOTOR_CHANNEL,
            limit_switch_pin=Y_LIMIT_SWITCH_PIN,
            limit_switch_direction='CW',
            steps_per_rev=STEPS_PER_REV,
            microsteps=MICROSTEPS,
            name="MotorY"
        )
        
        # Set microstepping mode for smooth movement
        self.motor_x.set_microstepping('MICROSTEP')
        self.motor_y.set_microstepping('MICROSTEP')
        
        # Initialize MQTT client
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Control variables
        self.last_update_time = time.time()
        self.button_pressed = False
    
    def map_value_to_steps(self, value):
        """
        Map joystick value (-100 to +100) to motor steps
        """
        # Apply deadzone
        if abs(value) < CONTROL_DEADZONE:
            return 0
        
        # Map to steps with speed scaling
        steps = value * SPEED_SCALING * MAX_STEPS_PER_UPDATE
        return int(max(-MAX_STEPS_PER_UPDATE, min(MAX_STEPS_PER_UPDATE, steps)))
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        print("Connected to MQTT broker with result code " + str(rc))
        client.subscribe(MQTT_TOPIC)
    
    def on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            # Parse the message (format: "x_val,y_val,button")
            x_val, y_val, button = msg.payload.decode().split(',')
            x_val = int(x_val)  # Now between -100 and +100
            y_val = int(y_val)  # Now between -100 and +100
            self.button_pressed = button.lower() == 'true'
            
            # Calculate steps for each axis
            x_steps = self.map_value_to_steps(x_val)
            y_steps = self.map_value_to_steps(y_val)
            
            # Set motor directions based on step values
            if x_steps > 0:
                self.motor_x.set_direction('CW')
            elif x_steps < 0:
                self.motor_x.set_direction('CCW')
            
            if y_steps > 0:
                self.motor_y.set_direction('CW')
            elif y_steps < 0:
                self.motor_y.set_direction('CCW')
            
            # Move motors if steps are non-zero
            if x_steps != 0:
                self.motor_x.step(abs(x_steps))
            
            if y_steps != 0:
                self.motor_y.step(abs(y_steps))
            
            # Handle button press (you can customize this behavior)
            if self.button_pressed:
                print("Button pressed!")
                # Add your button action here
            
        except Exception as e:
            print(f"Error processing message: {e}")
    
    def calibrate(self):
        """Calibrate both motors"""
        print("Starting calibration...")
        self.motor_x.calibrate()
        self.motor_y.calibrate()
        print("Calibration complete!")
    
    def start(self):
        """Start the controller"""
        try:
            # Connect to MQTT broker
            self.client.connect(MQTT_BROKER, 1883, 60)
            
            # Start the MQTT loop
            self.client.loop_forever()
            
        except KeyboardInterrupt:
            print("Shutting down...")
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        self.motor_x.release()
        self.motor_y.release()
        self.motor_x.cleanup()
        self.motor_y.cleanup()
        self.client.disconnect()

if __name__ == "__main__":
    controller = TurretController()
    
    # Calibrate on startup (optional)
    # controller.calibrate()
    
    # Start the controller
    controller.start()