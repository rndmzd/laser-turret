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
TEST_CONFIG_X = {
    'CW_LIMIT_SWITCH_PIN': 27,
    'CCW_LIMIT_SWITCH_PIN': 17,
    'MOTOR_CHANNEL': 2,
    'STEPS_PER_REV': 200,
    'MICROSTEPS': 8,
    'SAFE_DELAY': 0.001,
    'TEST_STEPS': 50,
    'CALIBRATION_TIMEOUT': 30,
    'MOVEMENT_TIMEOUT': 10
}

# Test configuration
TEST_CONFIG_Y = {
    'CW_LIMIT_SWITCH_PIN': 22,
    'CCW_LIMIT_SWITCH_PIN': 23,
    'MOTOR_CHANNEL': 1,
    'STEPS_PER_REV': 200,
    'MICROSTEPS': 8,
    'SAFE_DELAY': 0.001,
    'TEST_STEPS': 50,
    'CALIBRATION_TIMEOUT': 30,
    'MOVEMENT_TIMEOUT': 10
}

TEST_CONFIG = TEST_CONFIG_X

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
        """Test limit switch functionality with proper state management and error handling"""
        logger.info("=== Testing Limit Switches ===")
        
        def wait_for_limit(expected_direction: str, timeout: float = 10.0) -> bool:
            """Wait for specific limit switch to trigger with timeout"""
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = motor.get_status()
                if (status.status == MotorStatus.LIMIT_REACHED and 
                    status.triggered_limit == expected_direction):
                    return True
                time.sleep(0.1)
            return False
        
        test_passed = True
        try:
            # Start monitoring thread
            monitor_thread = Thread(target=self._monitor_motor_status, args=(motor,))
            monitor_thread.start()

            # Test CW limit
            logger.info("Testing CW limit switch...")
            motor.set_direction(CLOCKWISE)
            steps_moved = 0
            
            try:
                steps_moved = motor.step(10000, delay=self.config['SAFE_DELAY'])
                logger.info(f"Moved {steps_moved} steps before CW limit triggered")
                
                if wait_for_limit(CLOCKWISE):
                    logger.info("CW limit successfully triggered and stopped movement")
                else:
                    logger.error("CW limit switch test failed: Movement stopped but limit not triggered")
                    test_passed = False
                    
            except LimitSwitchError as e:
                logger.info(f"CW Movement stopped by limit switch: {e}")
            
            # Clear the triggered state and back off
            time.sleep(0.5)
            motor.set_direction(COUNTER_CLOCKWISE)
            motor.step(10, delay=self.config['SAFE_DELAY'])
            time.sleep(0.5)
            
            # Test CCW limit
            logger.info("Testing CCW limit switch...")
            motor.set_direction(COUNTER_CLOCKWISE)
            steps_moved = 0
            
            try:
                steps_moved = motor.step(10000, delay=self.config['SAFE_DELAY'])
                logger.info(f"Moved {steps_moved} steps before CCW limit triggered")
                
                if wait_for_limit(COUNTER_CLOCKWISE):
                    logger.info("CCW limit successfully triggered and stopped movement")
                else:
                    logger.error("CCW limit switch test failed: Movement stopped but limit not triggered")
                    test_passed = False
                    
            except LimitSwitchError as e:
                logger.info(f"CCW Movement stopped by limit switch: {e}")
            
            # Return to center if test passed
            if test_passed:
                time.sleep(0.5)
                motor.set_direction(CLOCKWISE)
                motor.step(steps_moved // 2, delay=self.config['SAFE_DELAY'])
            
            if not test_passed:
                raise LimitSwitchError("One or more limit switch tests failed")
                
        except Exception as e:
            logger.error(f"Error during limit switch testing: {e}")
            raise
        finally:
            self.stop_event.set()
            monitor_thread.join()
            motor.release()
        
        logger.info("Limit switch tests completed successfully" if test_passed else 
                    "Limit switch tests failed")
        return test_passed

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

def test_motor_direction(motor: StepperMotor) -> None:
    """Test that motor moves in expected direction when commanded"""
    print("\nTesting motor direction...")
    print("This test will move the motor a small amount in each direction.")
    print("Please observe the motor movement and confirm if directions are correct.")
    
    try:
        # Test clockwise
        input("\nPress Enter to test CLOCKWISE movement...")
        print("Moving clockwise...")
        motor.set_direction(CLOCKWISE)
        motor.step(20, delay=TEST_CONFIG['SAFE_DELAY'])
        response = input("Did the motor move clockwise? (y/n): ").lower().strip()
        cw_correct = response == 'y'
        
        time.sleep(0.5)
        
        # Test counter-clockwise
        input("\nPress Enter to test COUNTER-CLOCKWISE movement...")
        print("Moving counter-clockwise...")
        motor.set_direction(COUNTER_CLOCKWISE)
        motor.step(20, delay=TEST_CONFIG['SAFE_DELAY'])
        response = input("Did the motor move counter-clockwise? (y/n): ").lower().strip()
        ccw_correct = response == 'y'
        
        # Report results
        print("\nDirection Test Results:")
        print(f"Clockwise movement: {'CORRECT' if cw_correct else 'INCORRECT'}")
        print(f"Counter-clockwise movement: {'CORRECT' if ccw_correct else 'INCORRECT'}")
        
        if not (cw_correct and ccw_correct):
            print("\nRECOMMENDATION: If directions are reversed, you may need to:")
            print("1. Check motor wiring")
            print("2. Swap motor coil connections")
            print("3. Or update software direction definitions")
    
    except Exception as e:
        print(f"Error during direction test: {e}")
    finally:
        motor.release()

def test_motor_response(motor: StepperMotor) -> None:
    # Test various command values
    test_values = [
        0,    # Deadzone
        10,   # Just above deadzone
        25,   # First threshold
        50,   # Mid-range
        75,   # High threshold
        100,  # Maximum
        -50,  # Negative mid-range
        -100  # Negative maximum
    ]
    
    for value in test_values:
        print(f"\nTesting command value: {value}")
        # Calculate delay
        delay = motor._calculate_step_delay(value)
        if delay:
            print(f"Calculated delay: {delay:.6f} seconds")
            print(f"Steps per second: {1/delay:.1f}")
        else:
            print("In deadzone - no movement.")

def interactive_test_mode() -> None:
    """Interactive testing mode for manual verification"""
    logger.info("=== Starting Interactive Test Mode ===")
    
    try:
        with motor_context(
            motor_channel=TEST_CONFIG['MOTOR_CHANNEL'],
            cw_limit_switch_pin=TEST_CONFIG['CW_LIMIT_SWITCH_PIN'],
            ccw_limit_switch_pin=TEST_CONFIG['CCW_LIMIT_SWITCH_PIN'],
            steps_per_rev=TEST_CONFIG['STEPS_PER_REV'],
            microsteps=TEST_CONFIG['MICROSTEPS'],
            skip_direction_check=True,
            name="TestMotor",
            interactive_test_mode=True
        ) as motor:
            while True:
                print("\nInteractive Test Menu:")
                print("1. Move CW (50 steps)")
                print("2. Move CCW (50 steps)")
                print("3. Check limit switch states")
                print("4. Get motor status")
                print("5. Perform calibration")
                print("6. Test limit switches (manual trigger)")
                print("7. Test limit switches (using motor)")
                print("8. Test motor direction")
                print("9. Test motor response")
                print("10. Exit")
                
                choice = input("Enter choice (1-9): ").strip()
                
                if choice == '1':
                    motor.set_direction(CLOCKWISE)
                    steps = motor.step(TEST_CONFIG['TEST_STEPS'], delay=TEST_CONFIG['SAFE_DELAY'])
                    print(f"\nMoved {steps} steps clockwise.")
                
                elif choice == '2':
                    motor.set_direction(COUNTER_CLOCKWISE)
                    steps = motor.step(TEST_CONFIG['TEST_STEPS'], delay=TEST_CONFIG['SAFE_DELAY'])
                    print(f"\nMoved {steps} steps counter-clockwise.")
                
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
                    except Exception as e:
                        print(f"\nCalibration failed: {e}")
                
                elif choice == '6':
                    try:
                        print("\nStarting manual limit switch test...")
                        motor.confirm_limit_switches()
                        print("\nManual limit switch test completed successfully.")
                    except Exception as e:
                        print(f"\nManual limit switch test failed: {e}")
                
                elif choice == '7':
                    try:
                        print("\nStarting motorized limit switch test...")
                        tester = MotorTester(TEST_CONFIG)
                        tester.test_limit_switches(motor)
                        print("\nMotorized limit switch test completed successfully.")
                    except Exception as e:
                        print(f"\nMotorized limit switch test failed: {e}")
                
                elif choice == '8':
                    test_motor_direction(motor)
                
                elif choice == '9':
                    test_motor_response(motor)
                
                elif choice == '10':
                    break
                
                else:
                    print("\nInvalid choice. Please try again.")
                
                # Give time for status to settle and user to read output
                time.sleep(0.5)
                
    except KeyboardInterrupt:
        logger.info("Interactive test mode terminated by user.")
    except Exception as e:
        logger.error(f"Error during interactive testing: {e}")
        raise
    finally:
        logger.info("Exiting interactive test mode.")

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
