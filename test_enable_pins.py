#!/usr/bin/env python3
"""
Test script to verify enable pins can be set HIGH and LOW.
This will help diagnose if there's a hardware issue with the enable pins.
"""

import time
from laserturret.hardware_interface import get_gpio_backend
from laserturret.config_manager import get_config

def test_enable_pins():
    print("=== Enable Pin Hardware Test ===\n")
    
    # Get GPIO backend and config
    gpio = get_gpio_backend()
    config = get_config()
    
    # Get enable pins from config
    x_enable = config.get_gpio_pin('x_enable_pin')
    y_enable = config.get_gpio_pin('y_enable_pin')
    
    print(f"X Enable Pin: GPIO {x_enable}")
    print(f"Y Enable Pin: GPIO {y_enable}\n")
    
    # Test X enable pin
    print("Testing X Enable Pin:")
    print("  Setting to LOW (0)...")
    gpio.output(x_enable, 0)
    time.sleep(0.1)
    readback = gpio.input(x_enable)
    print(f"  Readback: {readback} {'✓ PASS' if readback == 0 else '✗ FAIL (expected 0)'}")
    
    print("  Setting to HIGH (1)...")
    gpio.output(x_enable, 1)
    time.sleep(0.1)
    readback = gpio.input(x_enable)
    print(f"  Readback: {readback} {'✓ PASS' if readback == 1 else '✗ FAIL (expected 1)'}")
    
    # Test Y enable pin
    print("\nTesting Y Enable Pin:")
    print("  Setting to LOW (0)...")
    gpio.output(y_enable, 0)
    time.sleep(0.1)
    readback = gpio.input(y_enable)
    print(f"  Readback: {readback} {'✓ PASS' if readback == 0 else '✗ FAIL (expected 0)'}")
    
    print("  Setting to HIGH (1)...")
    gpio.output(y_enable, 1)
    time.sleep(0.1)
    readback = gpio.input(y_enable)
    print(f"  Readback: {readback} {'✓ PASS' if readback == 1 else '✗ FAIL (expected 1)'}")
    
    # Physical test with delays
    print("\n=== Physical Motor Test ===")
    print("Watch the motors and feel for torque changes...\n")
    
    for i in range(3):
        print(f"Cycle {i+1}/3:")
        print("  Setting enable pins to HIGH (1)...")
        gpio.output(x_enable, 1)
        gpio.output(y_enable, 1)
        print("  (Motor should have TORQUE if TMC2209 active-high, or NO TORQUE if active-low)")
        print("  Does motor have torque? ", end='', flush=True)
        time.sleep(3)
        
        print("\n  Setting enable pins to LOW (0)...")
        gpio.output(x_enable, 0)
        gpio.output(y_enable, 0)
        print("  (Motor should have NO TORQUE if TMC2209 active-high, or TORQUE if active-low)")
        print("  Does motor have torque? ", end='', flush=True)
        time.sleep(3)
        print("\n")
    
    print("=== Test Complete ===")
    print("\nConclusions:")
    print("- If readback always shows 0: Enable pins may have hardware pull-downs")
    print("- If torque NEVER changes: Enable pins may not be connected to drivers")
    print("- If torque changes with HIGH: TMC2209 is active-HIGH enable")
    print("- If torque changes with LOW: TMC2209 is active-LOW enable (standard)")
    
    # Cleanup - set to safe state (disabled)
    gpio.output(x_enable, 0)
    gpio.output(y_enable, 0)

if __name__ == '__main__':
    test_enable_pins()
