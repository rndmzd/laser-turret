import pigpio
import time

# Initialize pigpio
pi = pigpio.pi()

if not pi.connected:
    print("Failed to connect to pigpio daemon.")
    exit()

# Define GPIO pins
DIR_PIN = 20    # Direction pin
STEP_PIN = 18   # Step pin (PWM-capable)

# Set up GPIO pins
pi.set_mode(DIR_PIN, pigpio.OUTPUT)
pi.set_mode(STEP_PIN, pigpio.OUTPUT)

# Define rotation directions
CW = 1     # Clockwise
CCW = 0    # Counterclockwise

# Set the stepping frequency (in Hz)
frequency = 500  # Adjust as needed (e.g., 500 steps per second)

print("Stepper Motor Test with PWM")
print("Press Ctrl+C to exit")

try:
    # Rotate clockwise
    pi.write(DIR_PIN, CW)
    pi.hardware_PWM(STEP_PIN, frequency, 500000)  # 50% duty cycle

    time.sleep(2)  # Rotate for 2 seconds

    # Stop stepping
    pi.hardware_PWM(STEP_PIN, 0, 0)  # Stop PWM

    time.sleep(1)

    # Rotate counterclockwise
    pi.write(DIR_PIN, CCW)
    pi.hardware_PWM(STEP_PIN, frequency, 500000)

    time.sleep(2)  # Rotate for 2 seconds

    # Stop stepping
    pi.hardware_PWM(STEP_PIN, 0, 0)

except KeyboardInterrupt:
    print("Movement interrupted by user")

finally:
    # Stop all PWM
    pi.hardware_PWM(STEP_PIN, 0, 0)
    pi.stop()
