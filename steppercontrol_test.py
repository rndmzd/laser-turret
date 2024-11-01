import logging
import time

# Import the StepperMotor class from your module
# Assuming the class code is saved in a file named stepper_motor.py
from laserturret import StepperMotor

# Define GPIO pins for limit switches
CW_LIMIT_SWITCH_PIN = 23#27 # or 22
CCW_LIMIT_SWITCH_PIN = 22#17 # or 23

# Configure logging to display outputs from the StepperMotor module
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def main():
    try:
        # Instantiate the StepperMotor class
        motor = StepperMotor(
            motor_channel=2,
            cw_limit_switch_pin=CW_LIMIT_SWITCH_PIN,
            ccw_limit_switch_pin=CCW_LIMIT_SWITCH_PIN,
            steps_per_rev=200,
            microsteps=8,
            skip_direction_check=False,
            perform_calibration=True,
            limit_backoff_steps=5,
            name="TestMotor"
        )

        logger.info("StepperMotor instance created successfully.")

        # Test basic movement in clockwise direction
        logger.info("Testing clockwise movement...")
        motor.set_direction('CW')
        steps_moved = motor.step(100, delay=0.005)
        logger.info(f"Moved {steps_moved} steps clockwise.")

        # Pause for a moment
        time.sleep(1)

        # Test basic movement in counter-clockwise direction
        logger.info("Testing counter-clockwise movement...")
        motor.set_direction('CCW')
        steps_moved = motor.step(100, delay=0.005)
        logger.info(f"Moved {steps_moved} steps counter-clockwise.")

        # Pause for a moment
        time.sleep(1)

        # Move to a specific position
        target_position = 500  # Example target position
        logger.info(f"Moving to position {target_position}...")
        steps_needed = target_position - motor.position
        if steps_needed > 0:
            motor.set_direction('CW')
        else:
            motor.set_direction('CCW')
            steps_needed = -steps_needed

        steps_moved = motor.step(steps_needed, delay=0.005)
        logger.info(f"Moved {steps_moved} steps to reach position {motor.position}.")

        # Pause for a moment
        time.sleep(1)

        # Attempt to move beyond the limit switch to test limit handling
        logger.info("Attempting to move beyond the limit switch...")
        try:
            motor.set_direction('CW')
            motor.step(10000, delay=0.005)  # Large number to ensure hitting the limit
        except RuntimeError as e:
            logger.error(f"Caught an exception: {e}")

        logger.info("Test completed successfully.")

    except Exception as e:
        logger.error(f"An error occurred during testing: {e}")
    finally:
        # Ensure resources are cleaned up properly
        motor.release()
        motor.cleanup()
        logger.info("Motor released and GPIO cleaned up.")

if __name__ == "__main__":
    main()
