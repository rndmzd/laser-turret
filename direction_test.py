from laserturret import StepperMotor

# Define GPIO pins for Motor X (X-axis)
ms_pins_X = {'MS1': 17, 'MS2': 27, 'MS3': 22}
dir_pin_X = 23
step_pin_X = 24

# Define GPIO pins for Motor Y (Y-axis)
ms_pins_Y = {'MS1': 5, 'MS2': 6, 'MS3': 13}
dir_pin_Y = 19
step_pin_Y = 26

try:
    # Initialize motors
    motor_X = StepperMotor(ms_pins_X, dir_pin_X, step_pin_X, name="Motor X")
    motor_Y = StepperMotor(ms_pins_Y, dir_pin_Y, step_pin_Y, name="Motor Y")

    # Set microstepping mode if desired
    motor_X.set_microstepping('FULL')
    motor_Y.set_microstepping('FULL')

    # Define the sequence for each motor
    def run_sequence(motor):
        input(f"Ensure {motor.name} is at the center position. Press Enter to begin.")
        
        # Move in CW direction
        print(f"{motor.name}: Moving in CW direction.")
        motor.set_direction('CW')
        motor.step(5, delay=0.1)

        input(f"{motor.name}: Press Enter to switch direction.")
        
        # Move in CCW direction
        print(f"{motor.name}: Moving in CCW direction.")
        motor.set_direction('CCW')
        motor.step(5, delay=0.1)

        input(f"{motor.name}: Sequence complete. Press Enter to continue.")

    # Run the sequence for Motor X
    print("\nStarting sequence for Motor X (X-axis)...")
    run_sequence(motor_X)

    # Run the sequence for Motor Y
    print("\nStarting sequence for Motor Y (Y-axis)...")
    run_sequence(motor_Y)

finally:
    # Clean up GPIO settings
    motor_X.cleanup()
    motor_Y.cleanup()
    print("GPIO cleanup complete.")