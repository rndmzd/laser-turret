import logging
import time
import sys
from contextlib import contextmanager
from typing import Generator, Optional
import pytest
from threading import Thread, Event

from laserturret.steppercontrol import (
    StepperMotor,
    MotorStatus,
    MotorError,
    LimitSwitchError,
    CalibrationError,
    ConfigurationError,
    CLOCKWISE,
    COUNTER_CLOCKWISE
)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test configuration
TEST_CONFIG = {
    'CW_LIMIT_SWITCH_PIN': 27,
    'CCW_LIMIT_SWITCH_PIN': 17,
    'MOTOR_CHANNEL': 2,
    'STEPS_PER_REV': 200,
    'MICROSTEPS': 8,
    'SAFE_DELAY': 0.01,
    'TEST_STEPS': 50,
    'CALIBRATION_TIMEOUT': 30,
    'MOVEMENT_TIMEOUT': 10
}

@contextmanager
def motor_context(**kwargs) -> Generator[StepperMotor, None, None]:
    """Context manager for proper motor cleanup"""
    motor = None
    try:
        motor = StepperMotor(**kwargs)
        yield motor
    except Exception as e:
        logger.error(f"Error during motor operation: {e}")
        raise
    finally:
        if motor:
            logger.info("Cleaning up motor...")
            motor.release()
            motor.cleanup()

class MotorTester:
    """Class to manage motor testing"""
    
    def __init__(self, config: dict):
        self.config = config
        self.stop_event = Event()

    def test_configuration(self) -> None:
        """Test configuration validation"""
        logger.info("=== Testing Configuration Validation ===")
        
        # Test invalid motor channel
        with pytest.raises(ConfigurationError):
            StepperMotor(motor_channel=3)
        
        # Test invalid GPIO pin
        with pytest.raises(ConfigurationError):
            StepperMotor(
                motor_channel=1,
                cw_limit_switch_pin=100
            )
        
        # Test duplicate GPIO pins
        with pytest.raises(ConfigurationError):
            StepperMotor(
                motor_channel=1,
                cw_limit_switch_pin=23,
                ccw_limit_switch_pin=23
            )
        
        logger.info("Configuration validation tests passed")

    def test_basic_movement(self, motor: StepperMotor) -> None:
        """Test basic movement functionality"""
        logger.info("=== Testing Basic Movement ===")
        
        # Test CW movement
        logger.info("Testing clockwise movement...")
        motor.set_direction(CLOCKWISE)
        initial_pos = motor.get_status().position
        steps_moved = motor.step(self.config['TEST_STEPS'], 
                               delay=self.config['SAFE_DELAY'])
        
        current_status = motor.get_status()
        assert steps_moved == self.config['TEST_STEPS'], \
            f"Expected {self.config['TEST_STEPS']} steps, got {steps_moved}"
        assert current_status.position == initial_pos + self.config['TEST_STEPS'], \
            "Position tracking error"
        
        time.sleep(0.5)
        
        # Test CCW movement
        logger.info("Testing counter-clockwise movement...")
        motor.set_direction(COUNTER_CLOCKWISE)
        initial_pos = motor.get_status().position
        steps_moved = motor.step(self.config['TEST_STEPS'], 
                               delay=self.config['SAFE_DELAY'])
        
        current_status = motor.get_status()
        assert steps_moved == self.config['TEST_STEPS'], \
            f"Expected {self.config['TEST_STEPS']} steps, got {steps_moved}"
        assert current_status.position == initial_pos - self.config['TEST_STEPS'], \
            "Position tracking error"
        
        logger.info("Basic movement tests passed.")

    def test_limit_switches(self, motor: StepperMotor) -> None:
        """Test limit switch functionality"""
        logger.info("=== Testing Limit Switches ===")
        
        # Test limit switch states
        cw_limit, ccw_limit = motor.get_limit_switch_states()
        logger.info(f"Initial limit switch states - CW: {cw_limit}, CCW: {ccw_limit}")
        
        # Start monitoring thread
        monitor_thread = Thread(target=self._monitor_motor_status, args=(motor,))
        monitor_thread.start()
        
        try:
            # Test CW limit
            logger.info("Testing CW limit approach...")
            motor.set_direction(CLOCKWISE)
            steps_moved = motor.step(1000, delay=self.config['SAFE_DELAY'])
            logger.info(f"Moved {steps_moved} steps toward CW limit.")
            
            # Check if limit was reached
            status = motor.get_status()
            if status.status == MotorStatus.LIMIT_REACHED:
                logger.info("CW limit successfully reached.")
            
            time.sleep(0.5)
            
            # Test CCW limit
            logger.info("Testing CCW limit approach...")
            motor.set_direction(COUNTER_CLOCKWISE)
            steps_moved = motor.step(1000, delay=self.config['SAFE_DELAY'])
            logger.info(f"Moved {steps_moved} steps toward CCW limit.")
            
            # Check if limit was reached
            status = motor.get_status()
            if status.status == MotorStatus.LIMIT_REACHED:
                logger.info("CCW limit successfully reached.")
                
        finally:
            self.stop_event.set()
            monitor_thread.join()
        
        logger.info("Limit switch tests completed.")

    def test_movement_timeout(self, motor: StepperMotor) -> None:
        """Test movement timeout functionality"""
        logger.info("=== Testing Movement Timeout ===")
        
        # Set a very short timeout temporarily
        original_timeout = motor.movement_timeout
        motor.movement_timeout = 0.1
        
        try:
            motor.set_direction(CLOCKWISE)
            with pytest.raises(MotorError):
                motor.step(1000, delay=0.2)  # Delay > timeout
            logger.info("Movement timeout test passed.")
        finally:
            motor.movement_timeout = original_timeout

    def _monitor_motor_status(self, motor: StepperMotor) -> None:
        """Monitor and log motor status changes"""
        last_status = None
        while not self.stop_event.is_set():
            current_status = motor.get_status()
            if current_status != last_status:
                logger.info(f"Motor status changed to: {current_status}")
                last_status = current_status
            time.sleep(0.1)

    def run_all_tests(self) -> None:
        """Run all motor tests"""
        logger.info("Starting comprehensive motor tests...")
        
        try:
            # Test configuration validation
            self.test_configuration()
            
            # Test motor operations
            with motor_context(
                motor_channel=self.config['MOTOR_CHANNEL'],
                cw_limit_switch_pin=self.config['CW_LIMIT_SWITCH_PIN'],
                ccw_limit_switch_pin=self.config['CCW_LIMIT_SWITCH_PIN'],
                steps_per_rev=self.config['STEPS_PER_REV'],
                microsteps=self.config['MICROSTEPS'],
                skip_direction_check=False,
                perform_calibration=True,
                calibration_timeout=self.config['CALIBRATION_TIMEOUT'],
                movement_timeout=self.config['MOVEMENT_TIMEOUT'],
                name="TestMotor"
            ) as motor:
                # Run tests
                self.test_basic_movement(motor)
                time.sleep(1)
                self.test_movement_timeout(motor)
                time.sleep(1)
                self.test_limit_switches(motor)
                
                logger.info("All tests completed successfully!")
                
        except AssertionError as e:
            logger.error(f"Test assertion failed: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error during testing: {e}")
            sys.exit(1)

def interactive_test_mode() -> None:
    """Interactive testing mode for manual verification"""
    logger.info("=== Starting Interactive Test Mode ===")
    motor = None
    
    try:
        motor = StepperMotor(
            motor_channel=TEST_CONFIG['MOTOR_CHANNEL'],
            cw_limit_switch_pin=TEST_CONFIG['CW_LIMIT_SWITCH_PIN'],
            ccw_limit_switch_pin=TEST_CONFIG['CCW_LIMIT_SWITCH_PIN'],
            steps_per_rev=TEST_CONFIG['STEPS_PER_REV'],
            microsteps=TEST_CONFIG['MICROSTEPS'],
            name="TestMotor",
            interactive_test_mode=True
        )
        
        while True:
            print("\nInteractive Test Menu:")
            print("1. Move CW (50 steps)")
            print("2. Move CCW (50 steps)")
            print("3. Check limit switch states")
            print("4. Get motor status")
            print("5. Perform calibration")
            print("6. Test motor direction")
            print("7. Test limit switches")
            print("8. Exit")
            print("Press Ctrl+C at any time to stop motor movement or exit.")
            
            choice = input("Enter choice (1-8): ").strip()
            
            if choice == '1':
                motor.set_direction(CLOCKWISE)
                try:
                    steps = motor.step(50, delay=TEST_CONFIG['SAFE_DELAY'])
                    print(f"\nMoved {steps} steps clockwise.")
                except KeyboardInterrupt:
                    print("\nMovement stopped by user.")
            
            elif choice == '2':
                motor.set_direction(COUNTER_CLOCKWISE)
                try:
                    steps = motor.step(50, delay=TEST_CONFIG['SAFE_DELAY'])
                    print(f"\nMoved {steps} steps counter-clockwise.")
                except KeyboardInterrupt:
                    print("\nMovement stopped by user.")
            
            elif choice == '3':
                cw_limit, ccw_limit = motor.get_limit_switch_states()
                print(f"\nCW Limit: {cw_limit}, CCW Limit: {ccw_limit}")
            
            elif choice == '4':
                status = motor.get_status()
                print(f"\nMotor Status: {status}")
            
            elif choice == '5':
                try:
                    motor.calibrate()
                    print("\nCalibration complete.")
                except KeyboardInterrupt:
                    print("\nCalibration stopped by user.")
                except Exception as e:
                    print(f"\nCalibration failed: {e}")
            
            elif choice == '6':
                try:
                    motor.confirm_motor_direction(timeout=TEST_CONFIG['MOVEMENT_TIMEOUT'])
                    print("\nMotor direction confirmed correct.")
                except KeyboardInterrupt:
                    print("\nDirection test interrupted by user.")
                except Exception as e:
                    print(f"\nDirection test failed: {e}")
            
            elif choice == '7':
                try:
                    motor.confirm_limit_switches(
                        skip_direction_check=True,
                        timeout=TEST_CONFIG['MOVEMENT_TIMEOUT']
                    )
                    print("\nLimit switches confirmed working correctly.")
                except KeyboardInterrupt:
                    print("\nLimit switch test interrupted by user.")
                except Exception as e:
                    print(f"\nLimit switch test failed: {e}")
            
            elif choice == '8':
                break
            
            else:
                print("\nInvalid choice. Please enter a number from 1-8.")
                
    except KeyboardInterrupt:
        print("\nExiting interactive test mode...")
    except Exception as e:
        logger.error(f"Error during interactive testing: {e}")
    finally:
        if motor:
            logger.info("Releasing motor...")
            try:
                motor.release()
                motor.cleanup()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")

def main():
    """Main entry point"""
    # Parse command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
        interactive_test_mode()
    else:
        # Run automated tests
        tester = MotorTester(TEST_CONFIG)
        tester.run_all_tests()

if __name__ == "__main__":
    main()