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

# Pin configurations for each axis
X_AXIS_PINS = {
    'STEP_PIN': 13,
    'DIR_PIN': 19,
    'ENABLE_PIN': 26,
    'MS1_PIN': 6,
    'MS2_PIN': 5,
    'MS3_PIN': 11,
}

Y_AXIS_PINS = {
    'STEP_PIN': 18,
    'DIR_PIN': 4,
    'ENABLE_PIN': 12,
    'MS1_PIN': 21,
    'MS2_PIN': 20,
    'MS3_PIN': 16,
}

# Test configuration for X-axis
TEST_CONFIG_X = {
    **X_AXIS_PINS,  # Unpack pin configurations
    'CW_LIMIT_SWITCH_PIN': 27,
    'CCW_LIMIT_SWITCH_PIN': 17,
    'STEPS_PER_REV': 200,
    'MICROSTEPS': 8,
    'SAFE_DELAY': 0.001,
    'TEST_STEPS': 50,
    'CALIBRATION_TIMEOUT': 30,
    'MOVEMENT_TIMEOUT': 10
}

# Test configuration for Y-axis
TEST_CONFIG_Y = {
    **Y_AXIS_PINS,  # Unpack pin configurations
    'CW_LIMIT_SWITCH_PIN': 22,
    'CCW_LIMIT_SWITCH_PIN': 23,
    'STEPS_PER_REV': 200,
    'MICROSTEPS': 8,
    'SAFE_DELAY': 0.001,
    'TEST_STEPS': 50,
    'CALIBRATION_TIMEOUT': 30,
    'MOVEMENT_TIMEOUT': 10
}

# Default to Y-axis configuration for testing
TEST_CONFIG = TEST_CONFIG_Y

@contextmanager
def motor_context(**kwargs) -> Generator[StepperMotor, None, None]:
    """Context manager for proper motor cleanup"""
    motor = None
    try:
        # Create motor with correct pin assignments
        motor = StepperMotor(
            step_pin=kwargs['STEP_PIN'],
            dir_pin=kwargs['DIR_PIN'],
            enable_pin=kwargs['ENABLE_PIN'],
            ms1_pin=kwargs['MS1_PIN'],
            ms2_pin=kwargs['MS2_PIN'],
            ms3_pin=kwargs['MS3_PIN'],
            cw_limit_switch_pin=kwargs.get('CW_LIMIT_SWITCH_PIN'),
            ccw_limit_switch_pin=kwargs.get('CCW_LIMIT_SWITCH_PIN'),
            steps_per_rev=kwargs.get('STEPS_PER_REV', 200),
            microsteps=kwargs.get('MICROSTEPS', 8),
            skip_direction_check=kwargs.get('skip_direction_check', False),
            perform_calibration=kwargs.get('perform_calibration', True),
            calibration_timeout=kwargs.get('CALIBRATION_TIMEOUT', 30),
            movement_timeout=kwargs.get('MOVEMENT_TIMEOUT', 10),
            name=kwargs.get('name', "TestMotor"),
            interactive_test_mode=kwargs.get('interactive_test_mode', False)
        )
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
        
        # Test invalid GPIO pin
        with pytest.raises(ConfigurationError):
            StepperMotor(
                step_pin=self.config['STEP_PIN'],
                dir_pin=self.config['DIR_PIN'],
                enable_pin=self.config['ENABLE_PIN'],
                ms1_pin=self.config['MS1_PIN'],
                ms2_pin=self.config['MS2_PIN'],
                ms3_pin=self.config['MS3_PIN'],
                cw_limit_switch_pin=100  # Invalid pin
            )
        
        # Test duplicate GPIO pins
        with pytest.raises(ConfigurationError):
            StepperMotor(
                step_pin=self.config['STEP_PIN'],
                dir_pin=self.config['DIR_PIN'],
                enable_pin=self.config['ENABLE_PIN'],
                ms1_pin=self.config['MS1_PIN'],
                ms2_pin=self.config['MS2_PIN'],
                ms3_pin=self.config['MS3_PIN'],
                cw_limit_switch_pin=23,
                ccw_limit_switch_pin=23  # Duplicate pin
            )
        
        # Test invalid microstep configuration
        with pytest.raises(ConfigurationError):
            StepperMotor(
                step_pin=self.config['STEP_PIN'],
                dir_pin=self.config['DIR_PIN'],
                enable_pin=self.config['ENABLE_PIN'],
                ms1_pin=self.config['MS1_PIN'],
                ms2_pin=self.config['MS2_PIN'],
                ms3_pin=self.config['MS3_PIN'],
                microsteps=3  # Invalid microstep value
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
        
        def wait_for_limit(expected_direction: str, timeout: float = 10.0) -> bool:
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
                    logger.info("CW limit successfully triggered")
                else:
                    logger.error("CW limit switch test failed")
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
                    logger.info("CCW limit successfully triggered")
                else:
                    logger.error("CCW limit switch test failed")
                    test_passed = False
                    
            except LimitSwitchError as e:
                logger.info(f"CCW Movement stopped by limit switch: {e}")
            
            # Return to center
            if test_passed:
                time.sleep(0.5)
                motor.set_direction(CLOCKWISE)
                motor.step(steps_moved // 2, delay=self.config['SAFE_DELAY'])
            
            if not test_passed:
                raise LimitSwitchError("Limit switch tests failed")
                
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
            self.test_configuration()
            
            with motor_context(**self.config) as motor:
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
    """Interactive test for motor direction"""
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
            print("3. Update DIR pin logic in software")
            print("4. Or check A4988 driver configuration")
    
    except Exception as e:
        print(f"Error during direction test: {e}")
    finally:
        motor.release()

def test_motor_response(motor: StepperMotor) -> None:
    """Test motor response to different command values"""
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
        with motor_context(**TEST_CONFIG, skip_direction_check=True, 
                         interactive_test_mode=True) as motor:
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
                print("10. Test A4988 driver settings")
                print("11. Exit")
                
                choice = input("Enter choice (1-11): ").strip()
                
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
                        print("Please manually trigger each limit switch when prompted.")
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
                    print("\nA4988 Driver Settings:")
                    print(f"Microsteps: {TEST_CONFIG['MICROSTEPS']}")
                    print(f"Step Pin: {TEST_CONFIG['STEP_PIN']}")
                    print(f"Direction Pin: {TEST_CONFIG['DIR_PIN']}")
                    print(f"Enable Pin: {TEST_CONFIG['ENABLE_PIN']}")
                    print(f"MS1 Pin: {TEST_CONFIG['MS1_PIN']}")
                    print(f"MS2 Pin: {TEST_CONFIG['MS2_PIN']}")
                    print(f"MS3 Pin: {TEST_CONFIG['MS3_PIN']}")
                    print("\nPlease verify these match your physical connections.")
                
                elif choice == '11':
                    break
                
                else:
                    print("\nInvalid choice. Please try again.")
                
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
    try:
        if len(sys.argv) > 1:
            if sys.argv[1] == '--interactive':
                interactive_test_mode()
            elif sys.argv[1] == '--x-axis':
                tester = MotorTester(TEST_CONFIG_X)
                tester.run_all_tests()
            elif sys.argv[1] == '--y-axis':
                tester = MotorTester(TEST_CONFIG_Y)
                tester.run_all_tests()
            elif sys.argv[1] == '--help':
                print("\nUsage:")
                print("  python steppercontrol_test.py [option]")
                print("\nOptions:")
                print("  --interactive  Run interactive test mode")
                print("  --x-axis      Test X-axis motor")
                print("  --y-axis      Test Y-axis motor")
                print("  --help        Show this help message")
            else:
                print("Invalid argument. Use --help for usage information.")
                sys.exit(1)
        else:
            # Default to Y-axis test
            tester = MotorTester(TEST_CONFIG)
            tester.run_all_tests()
            
    except KeyboardInterrupt:
        print("\nTests interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest suite failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()