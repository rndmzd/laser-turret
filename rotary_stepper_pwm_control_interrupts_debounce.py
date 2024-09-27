import pigpio
import time
import threading

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

last_callback_time = 0

# Set up GPIO pins
pi.set_mode(DIR_PIN, pigpio.OUTPUT)
pi.set_mode(STEP_PIN, pigpio.OUTPUT)

pi.set_mode(ENCODER_CLK, pigpio.INPUT)
pi.set_pull_up_down(ENCODER_CLK, pigpio.PUD_UP)

pi.set_mode(ENCODER_DT, pigpio.INPUT)
pi.set_pull_up_down(ENCODER_DT, pigpio.PUD_UP)

# Initialize variables
current_direction = 0  # 0 for CCW, 1 for CW

# Global variable for thread safety
clkLastState = pi.read(ENCODER_CLK)
lock = threading.Lock()

print("Rotary Encoder to Stepper Motor Control with Hardware PWM and Interrupts")
print("Rotate the encoder to move the motor.")
print("Press Ctrl+C to exit.")

def move_stepper(direction):
    """
    Moves the stepper motor one step in the specified direction.
    """
    pi.write(DIR_PIN, direction)

    # Generate a single step pulse using waveform
    pulse_length = 5  # Pulse length in microseconds (minimum 2us for A4988)
    wf = []

    # Set STEP_PIN high
    wf.append(pigpio.pulse(1 << STEP_PIN, 0, pulse_length))
    # Set STEP_PIN low
    wf.append(pigpio.pulse(0, 1 << STEP_PIN, pulse_length))

    # Lock to prevent concurrent access to waveforms
    with lock:
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

def encoder_callback(gpio, level, tick):
    """
    Callback function for encoder events with debouncing.
    """
    global clkLastState, current_direction, last_callback_time

    # Minimum time between callbacks in microseconds (e.g., 5000us = 5ms)
    debounce_time = 5000

    current_time = tick  # 'tick' is the timestamp in microseconds

    if (current_time - last_callback_time) > debounce_time:
        clkState = pi.read(ENCODER_CLK)
        dtState = pi.read(ENCODER_DT)

        if clkState != clkLastState:
            if dtState != clkState:
                current_direction = 1  # Clockwise
            else:
                current_direction = 0  # Counterclockwise

            threading.Thread(target=move_stepper, args=(current_direction,)).start()

            # print(f"Moved one step {'CW' if current_direction == 1 else 'CCW'}")

        clkLastState = clkState
        last_callback_time = current_time

try:
    # Set up interrupts
    pi.callback(ENCODER_CLK, pigpio.EITHER_EDGE, encoder_callback)

    # Keep the program running
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\nProgram exited by user")
finally:
    pi.wave_clear()
    pi.stop()
