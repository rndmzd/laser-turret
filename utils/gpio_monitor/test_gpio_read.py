#!/usr/bin/env python3
"""
Test script to verify GPIO reading with gpiod v2.x
"""

import gpiod
from gpiod.line import Direction, Value
import time

# Test pins (your limit switches and laser)
TEST_PINS = [17, 22, 27, 23, 18]

print("Opening GPIO chip...")
chip = gpiod.Chip('/dev/gpiochip0')

print("Requesting GPIO lines...")
request = chip.request_lines(
    consumer="gpio-test",
    config={
        pin: gpiod.LineSettings(direction=Direction.INPUT)
        for pin in TEST_PINS
    }
)

print("\nReading GPIO values every 500ms. Press Ctrl+C to stop.")
print("Pull pins to ground to see changes.\n")

try:
    previous_values = {}
    while True:
        # Read all values
        values = request.get_values(TEST_PINS)
        
        # Display current values
        for pin in TEST_PINS:
            value = values[pin]
            value_int = 1 if value == Value.ACTIVE else 0
            
            # Detect and highlight changes
            if pin not in previous_values:
                previous_values[pin] = value_int
            
            if previous_values[pin] != value_int:
                print(f"GPIO {pin:2d}: {value_int} *** CHANGED from {previous_values[pin]}")
                previous_values[pin] = value_int
            else:
                print(f"GPIO {pin:2d}: {value_int}")
        
        print("-" * 30)
        time.sleep(0.5)
        
except KeyboardInterrupt:
    print("\n\nCleaning up...")
    request.release()
    chip.close()
    print("Done!")
