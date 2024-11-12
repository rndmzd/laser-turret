import configparser
import paho.mqtt.client as mqtt
import time
import logging
from laserturret.steppercontrol import StepperMotor, MotorStatus, MotorError
from laserturret.lasercontrol import LaserControl
import RPi.GPIO as GPIO

# Configure logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

config = configparser.ConfigParser()
config.read('laserturret.conf')

# MQTT Configuration
mqtt_broker = config.MQTT_BROKER
mqtt_topic = config.MQTT_TOPIC

# Motor Configuration
x_motor_channel = int(config['Motor']['x_motor_channel'])
y_motor_channel = int(config['Motor']['y_motor_channel'])
x_cw_limit_pin = int(config['GPIO']['x_cw_limit_pin'])
x_ccw_limit_pin = int(config['GPIO']['x_ccw_limit_pin'])
y_cw_limit_pin = int(config['GPIO']['y_cw_limit_pin'])
y_ccw_limit_pin = int(config['GPIO']['y_ccw_limit_pin'])
steps_per_rev = int(config['Motor']['steps_per_rev'])
microsteps = int(config['Motor']['microsteps'])

# Laser
laser_pin = int(config['Laser']['laser_pin'])
laser_max_power = int(config['Laser']['laser_max_power'])

class TurretController:
    def __init__(self, skip_calibration=False, skip_direction_check=False):
        """Initialize the turret controller with two stepper motors."""
        logger.info("Initializing Turret Controller...")
        
        try:
            # Initialize X-axis motor
            self.motor_x = StepperMotor(
                motor_channel=x_motor_channel,
                cw_limit_switch_pin=x_cw_limit_pin,
                ccw_limit_switch_pin=x_ccw_limit_pin,
                steps_per_rev=steps_per_rev,
                microsteps=microsteps,
                name="MotorX",
                perform_calibration=not skip_calibration,
                skip_direction_check=skip_direction_check
            )
            
            # Initialize Y-axis motor
            self.motor_y = StepperMotor(
                motor_channel=y_motor_channel,
                cw_limit_switch_pin=y_cw_limit_pin,
                ccw_limit_switch_pin=y_ccw_limit_pin,
                steps_per_rev=steps_per_rev,
                microsteps=microsteps,
                name="MotorY",
                perform_calibration=not skip_calibration,
                skip_direction_check=skip_direction_check
            )

            self.laser = LaserControl(gpio_pin=laser_pin, initial_power=0)
            
        except Exception as e:
            logger.error(f"Failed to initialize motors: {str(e)}")
            self.cleanup()
            raise
        
        # Initialize MQTT client
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        # Control variables
        self.last_update_time = time.time()
        self.joystic_button_pressed = False
        self.laser_button_pressed = False
        self.laser_power = 100  # Default max power
        
        logger.info("Turret Controller initialized successfully")
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker."""
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
            client.subscribe(mqtt_topic)
        else:
            logger.error(f"Failed to connect to MQTT broker with result code: {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        if rc == 0:
            logger.info("Cleanly disconnected from MQTT broker")
        else:
            logger.warning(f"Unexpected disconnection from MQTT broker. RC: {rc}")
    
    def on_message(self, client, userdata, message):
        """Handle incoming MQTT messages"""
        try:
            # Parse the message (format: "x_val,y_val,joystick_button,laser_button,pot_value")
            parts = message.payload.decode().split(',')
            if len(parts) != 5:
                logger.error(f"Invalid message format. Expected 5 values, got {len(parts)}")
                return

            x_val = float(parts[0])          # Between -100 and +100
            y_val = float(parts[1])          # Between -100 and +100
            self.joystic_button_pressed = parts[2].strip().lower() == 'true'
            self.laser_button_pressed = parts[3].strip().lower() == 'true'
            self.laser_power = float(parts[4])  # Between 0 and 100
            
            # Process commands for each axis
            self.motor_x.process_command(x_val)
            self.motor_y.process_command(y_val)
            
            # Handle laser control with variable power
            if self.joystic_button_pressed:
                logger.debug("Joystick button pressed")
                
            # Handle auxiliary button (you can add custom functionality here)
            if self.laser_button_pressed:
                power_level = min(100, max(0, self.laser_power))
                self.laser.on(power_level=power_level)
            else:
                self.laser.off()
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def calibrate(self):
        """Calibrate both motors"""
        logger.info("Starting calibration sequence...")
        try:
            self.motor_x.calibrate()
            self.motor_y.calibrate()
            logger.info("Calibration completed successfully")
        except Exception as e:
            logger.error(f"Calibration failed: {str(e)}")
            raise
    
    def start(self):
        """Start the controller"""
        try:
            logger.info("Starting Turret Controller...")
            # Connect to MQTT broker
            self.client.connect(mqtt_broker, 1883, keepalive=60)
            
            # Start the MQTT loop
            self.client.loop_forever()
            
        except KeyboardInterrupt:
            logger.info("Shutting down due to keyboard interrupt...")
        except Exception as e:
            logger.error(f"Error during controller operation: {str(e)}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources...")
        try:
            if hasattr(self, 'motor_x'):
                self.motor_x.cleanup()
            if hasattr(self, 'motor_y'):
                self.motor_y.cleanup()
            if hasattr(self, 'laser'):
                self.laser.cleanup()
            if hasattr(self, 'client'):
                self.client.disconnect()
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

if __name__ == "__main__":
    try:
        controller = TurretController(skip_direction_check=True)
        controller.start()
    except Exception as e:
        logger.error(f"Failed to start controller: {str(e)}")
        exit(1)