#!/usr/bin/env python3
"""
DEPRECATED: This script uses an old StepperMotor API that no longer exists.
Use scripts/test_limit_switches.py instead for testing limit switches.

This script is kept for historical reference only and will not run with the current codebase.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
# This import will fail - the old API no longer exists
# from laserturret import StepperMotor

# Calibration Script (OUTDATED)
def calibrate_motor(motor):
    input(f"Press any key to start calibration for {motor.name}.")

    # Move the motor 5 steps and ask the user for confirmation
    # motor.set_direction('CW')
    motor.step(5, delay=0.05)

    motor.set_microstepping('MICROSTEP')
    
    user_response = input("Was this the direction towards the limit switch? (yes/no): ").strip().lower()

    print(f"motor.motor_direction: {motor.motor_direction}")
    print(f"motor.limit_switch_direction: {motor.limit_switch_direction}")

    if user_response == 'yes':
        limit_direction_confirm = False
        if motor.limit_switch_direction == 'CW' and motor.motor_direction == 1:
            limit_direction_confirm = True
        elif motor.limit_switch_direction == 'CCW' and motor.motor_direction == 2:
            limit_direction_confirm = True
        
        if limit_direction_confirm:
            print(f"{motor.name}: Direction confirmed. Proceeding.")
        else:
            print(f"{motor.name}: Limit switch direction in init arguments must be changed.")
            exit(1)
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
    motor.stop_flag = False
    motor.step(10000)#, delay=0.005)  # Move until the limit switch is triggered

    print(f"{motor.name}: {motor.position} steps taken to reach the limit switch.")

try:
    # Initialize two motors for calibration using the steppercontrol module
    motor_x = StepperMotor(motor_channel=1, limit_switch_pin=17, limit_switch_direction='CCW', name='MotorX')
    motor_y = StepperMotor(motor_channel=2, limit_switch_pin=27, limit_switch_direction='CW', name='MotorY')

    # Calibrate both motors
    calibrate_motor(motor_x)
    calibrate_motor(motor_y)
    print("Calibration complete for all motors.") 

except KeyboardInterrupt:
        print("Calibration process interrupted by user.")

except Exception as e:
    print(f"An error occurred during calibration: {e}")

finally:
    if motor_x:
        motor_x.release()
        motor_x.cleanup()
    if motor_y:
        motor_y.release()
        motor_y.cleanup()
    print("GPIO cleanup complete.")