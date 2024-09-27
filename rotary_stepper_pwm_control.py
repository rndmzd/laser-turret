import pigpio
import time

# Initialize pigpio
pi = pigpio.pi()

if not pi.connected:
    print("Failed to connect to pigpio daemon.")
    exit()

# Define GPIO pins
DIR_PIN = 20       # Direction pin for stepper motor
STEP_PIN = 18      # STEP pin (using hardware PWM-capable GPIO18)

ENCODER_CLK = 5    # Rotary encoder CLK pin
ENCODER_DT = 6     # Rotary encoder DT pin

# Set up GPIO pins
pi.set_mode(DIR_PIN, pigpio.OUTPUT)
pi.set_mode(STEP_PIN, pigpio.OUTPUT)

pi.set_mode(ENCODER_CLK, pigpio.INPUT)
pi.set_pull_up_down(ENCODER_CLK, pigpio.PUD_UP)

pi.set_mode(ENCODER_DT, pigpio.INPUT)
pi.set_pull_up_down(ENCODER_DT, pigpio.PUD_UP)

# Initialize variables
current_direction = 0  # 0 for CCW, 1 for CW
clkLastState = pi.read(ENCODER_CLK)

print("Rotary Encoder to Stepper Motor Control with Hardware PWM")
print("Rotate the encoder to move the motor.")
print("Press Ctrl+C to exit.")

try:
    while True:
        clkState = pi.read(ENCODER_CLK)
        dtState = pi.read(ENCODER_DT)

        if clkState != clkLastState:
            if dtState != clkState:
                # Clockwise rotation
                current_direction = 1  # Set direction to clockwise
            else:
                # Counterclockwise rotation
                current_direction = 0  # Set direction to counterclockwise

            pi.write(DIR_PIN, current_direction)

            # Generate a single step pulse using waveform
            # Create a waveform with a single pulse on STEP_PIN
            pulse_length = 5  # Pulse length in microseconds (minimum 2us for A4988)
            wf = []

            # Set STEP_PIN high
            wf.append(pigpio.pulse(1 << STEP_PIN, 0, pulse_length))
            # Set STEP_PIN low
            wf.append(pigpio.pulse(0, 1 << STEP_PIN, pulse_length))

            # Clear any existing waveforms
            pi.wave_clear()
            # Add the waveform pulses
            pi.wave_add_generic(wf)
            # Create a waveform ID
            wid = pi.wave_create()
            if wid >= 0:
                pi.wave_send_once(wid)
                # Wait for the waveform to finish
                while pi.wave_tx_busy():
                    time.sleep(0.001)
                # Delete the waveform
                pi.wave_delete(wid)
            else:
                print("Failed to create waveform.")

            print(f"Moved one step {'CW' if current_direction == 1 else 'CCW'}")

            clkLastState = clkState

        # Small delay to debounce the encoder signal
        time.sleep(0.001)

except KeyboardInterrupt:
    print("\nProgram exited by user")
finally:
    pi.wave_clear()
    pi.stop()
