import time
import RPi.GPIO as GPIO
from laserturret import StepperMotor

# Calibration Script
def calibrate_motor(motor):
    input(f"Press any key to start calibration for {motor.name}.")

    # Move the motor 5 steps and ask the user for confirmation
    motor.set_direction('CCW')
    motor.step(5, delay=0.05)
    user_response = input("Was this the direction towards the limit switch? (yes/no): ").strip().lower()

    print(f"motor.motor_direction: {motor.motor_direction}")
    print(f"motor.limit_switch_direction: {motor.limit_switch_direction}")

    if user_response == 'yes' and motor.motor_direction == motor.limit_switch_direction:
        print(f"{motor.name}: Direction confirmed. Proceeding.")
    else:
        print(f"{motor.name}: Limit switch direction in init arguments must be changed.")
        exit(1)

    motor.release()

    # Ask user to manually trigger the limit switch and confirm
    input(f"Manually move {motor.name} until the limit switch is triggered. Press any key when ready.")
    user_response = input(f"Did {motor.name} trigger the correct limit switch? (yes/no): ").strip().lower()

    if user_response == 'yes':
        print(f"{motor.name}: Limit switch assignment confirmed.")
    else:
        print(f"{motor.name}: Limit switch error. Please check the wiring or configuration.")
        exit(1)
    
    input(f"Manually move {motor.name} to the furthest travel limit opposite of the limit switch. Press any key when ready.")

    # Move towards the limit switch and count steps
    motor.set_direction(motor.limit_switch_direction)
    motor.step(10000, delay=0.05)  # Move until the limit switch is triggered

    print(f"{motor.name}: {motor.step_count} steps taken to reach the limit switch.")

# Initialize two motors for calibration using the steppercontrol module
motor_1 = StepperMotor(motor_channel=1, limit_switch_pin=18, limit_switch_direction='CW', name='Motor 1')
motor_2 = StepperMotor(motor_channel=2, limit_switch_pin=25, limit_switch_direction='CW', name='Motor 2')

# Calibrate both motors
calibrate_motor(motor_1)
calibrate_motor(motor_2)

print("Calibration complete for all motors.")
