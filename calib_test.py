from laserturret import StepperMotor

if __name__ == "__main__":
    try:
        # Initialize two motors for calibration using the steppercontrol module
        motor_x = StepperMotor(motor_channel=1, limit_switch_pin=17, limit_switch_direction='CCW', name='MotorX')
        motor_y = StepperMotor(motor_channel=2, limit_switch_pin=27, limit_switch_direction='CW', name='MotorY')

        # Confirm limit switch assignment
        motor_x.confirm_limit_switch()
        motor_y.confirm_limit_switch()

        # Calibrate both motors
        motor_x.calibrate()
        motor_y.calibrate()
    except KeyboardInterrupt:
        print("Calibration interrupted.")
    except Exception as e:
        print(f"An error occurred during calibration: {e}")
    finally:
        # Clean up GPIO settings
        motor_x.cleanup()
        motor_y.cleanup()