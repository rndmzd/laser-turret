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
mqtt_broker = config['MQTT']['broker']
mqtt_topic = config['MQTT']['topic']

# Motor Configuration
x_motor_channel = int(config['Motor']['x_motor_channel'])
y_motor_channel = int(config['Motor']['y_motor_channel'])
x_cw_limit_pin = int(config['GPIO']['x_cw_limit_pin'])
x_ccw_limit_pin = int(config['GPIO']['x_ccw_limit_pin'])
y_cw_limit_pin = int(config['GPIO']['y_cw_limit_pin'])
y_ccw_limit_pin = int(config['GPIO']['y_ccw_limit_pin'])
steps_per_rev = int(config['Motor']['steps_per_rev'])
microsteps = int(config['Motor']['microsteps'])

# Control Parameters
max_steps_per_update = int(config['Control']['max_steps_per_update'])
control_deadzone = int(config['Control']['deadzone'])
speed_scaling = float(config['Control']['speed_scaling'])
step_delay = float(config['Control']['step_delay'])

# Laser
laser_pin = int(config['Laser']['laser_pin'])
laser_max_power = int(config['Laser']['laser_max_power'])

class TurretController:
    def __init__(self, skip_calibration=False, skip_direction_check=False):
        """
        Initialize the turret controller with two stepper motors.
        
        Args:
            skip_calibration: If True, skips the initial motor calibration
        """
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
        
        # Initialize MQTT client with protocol version 5 and modern callbacks
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        # Control variables
        self.last_update_time = time.time()
        self.button_pressed = False
        
        logger.info("Turret Controller initialized successfully")
    
    '''def map_value_to_steps(self, value):
        """
        Map joystick value (-100 to +100) to motor steps with deadzone handling.
        
        Args:
            value: Input value from joystick (-100 to +100)
            
        Returns:
            Number of steps to move (-max_steps_per_update to +max_steps_per_update)
        """
        # Apply deadzone
        if abs(value) < control_deadzone:
            return 0
        
        # Map to steps with speed scaling
        steps = value * speed_scaling * max_steps_per_update
        return int(max(-max_steps_per_update, min(max_steps_per_update, steps)))'''
    
    
    def on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback when connected to MQTT broker."""
        if rc == 0:
            logger.info("Connected to MQTT broker successfully")
            client.subscribe(mqtt_topic, qos=1)
        else:
            logger.error(f"Failed to connect to MQTT broker with result code: {rc}")
    
    def on_disconnect(self, client, userdata, disconnect_flags, rc, properties=None, *args):
        """Callback for when the client disconnects from the broker."""
        if rc == 0:
            logger.info("Cleanly disconnected from MQTT broker")
        else:
            logger.warning(f"Unexpected disconnection from MQTT broker. RC: {rc}")
    
    def move_motor(self, motor, steps):
        """
        Move a motor safely with error handling.
        
        Args:
            motor: StepperMotor instance to move
            steps: Number of steps (negative for CCW, positive for CW)
        """
        try:
            if steps == 0:
                return
                
            # Set direction based on steps sign
            direction = 'CW' if steps > 0 else 'CCW'
            motor.set_direction(direction)
            
            # Get motor status before moving
            status = motor.get_status()
            if status.status == MotorStatus.ERROR:
                logger.error(f"Motor error: {status.error_message}")
                return
                
            # Move the motor
            motor.step(abs(steps), delay=step_delay)
            
        except MotorError as e:
            logger.error(f"Motor movement error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during motor movement: {str(e)}")
    
    def on_message(self, client, userdata, message, properties=None):
        """Handle incoming MQTT messages"""
        try:
            # Parse the message (format: "x_val,y_val,button")
            x_val, y_val, button = message.payload.decode().split(',')
            x_val = float(x_val)    # Now between -100 and +100
            y_val = float(y_val)    # Now between -100 and +100
            self.button_pressed = button.strip().lower() == 'true'  # Convert 'True'/'False' string to boolean
            
            # Process commands for each axis
            self.motor_x.process_command(x_val)
            self.motor_y.process_command(y_val)
            
            # Handle button press
            if self.button_pressed:
                self.laser.on(power_level=laser_max_power)
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
                self.motor_x.release()
                self.motor_x.cleanup()
            if hasattr(self, 'motor_y'):
                self.motor_y.release()
                self.motor_y.cleanup()
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