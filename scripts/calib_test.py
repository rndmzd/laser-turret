import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from laserturret.motion import StepperAxis as StepperMotor
from laserturret import get_config

if __name__ == "__main__":
    # Load configuration
    config = get_config()
    
    motor_x = None
    motor_y = None
    
    try:
        # Initialize two motors for calibration using the steppercontrol module
        motor_x = StepperMotor(
            step_pin=config.get_motor_pin('x_step_pin'),
            dir_pin=config.get_motor_pin('x_dir_pin'),
            enable_pin=config.get_motor_pin('x_enable_pin'),
            ms1_pin=config.get_motor_pin('ms1_pin'),
            ms2_pin=config.get_motor_pin('ms2_pin'),
            ms3_pin=config.get_motor_pin('ms3_pin'),
            cw_limit_switch_pin=config.get_gpio_pin('x_cw_limit_pin'),
            ccw_limit_switch_pin=config.get_gpio_pin('x_ccw_limit_pin'),
            steps_per_rev=config.get_motor_steps_per_rev(),
            microsteps=config.get_motor_microsteps(),
            skip_direction_check=False,
            perform_calibration=False,
            name='MotorX'
        )
        
        motor_y = StepperMotor(
            step_pin=config.get_motor_pin('y_step_pin'),
            dir_pin=config.get_motor_pin('y_dir_pin'),
            enable_pin=config.get_motor_pin('y_enable_pin'),
            ms1_pin=config.get_motor_pin('ms1_pin'),
            ms2_pin=config.get_motor_pin('ms2_pin'),
            ms3_pin=config.get_motor_pin('ms3_pin'),
            cw_limit_switch_pin=config.get_gpio_pin('y_cw_limit_pin'),
            ccw_limit_switch_pin=config.get_gpio_pin('y_ccw_limit_pin'),
            steps_per_rev=config.get_motor_steps_per_rev(),
            microsteps=config.get_motor_microsteps(),
            skip_direction_check=False,
            perform_calibration=False,
            name='MotorY'
        )

        # Confirm limit switch assignment
        print("\n" + "="*60)
        print("STEP 1: VERIFYING LIMIT SWITCHES")
        print("="*60)
        print("You will be asked to manually trigger each limit switch.")
        print("This ensures the switches are correctly connected.\n")
        
        motor_x.confirm_limit_switches()
        motor_y.confirm_limit_switches()

        # Calibrate both motors
        print("\n" + "="*60)
        print("STEP 2: AUTO-CALIBRATION")
        print("="*60)
        print("Motors will now automatically find their range limits")
        print("and return to center position.\n")
        
        motor_x.calibrate()
        motor_y.calibrate()
        
        print("\n" + "="*60)
        print("CALIBRATION COMPLETE!")
        print("="*60)
        print("Both motors have been calibrated successfully.")
        
    except KeyboardInterrupt:
        print("\nCalibration interrupted.")
    except Exception as e:
        print(f"An error occurred during calibration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up GPIO settings
        if motor_x:
            motor_x.cleanup()
        if motor_y:
            motor_y.cleanup()
        print("GPIO cleanup complete.")