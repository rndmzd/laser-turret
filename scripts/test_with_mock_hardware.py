"""
Example script demonstrating hardware abstraction with mock implementations.

This shows how to test laser turret components without physical hardware.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from laserturret.lasercontrol import LaserControl
from laserturret.hardware_interface import MockGPIO, MockCamera
import time


def test_laser_control():
    """Test laser control with mock GPIO"""
    print("=" * 60)
    print("Testing LaserControl with Mock GPIO")
    print("=" * 60)
    
    # Create mock GPIO backend
    mock_gpio = MockGPIO()
    
    # Create laser control with mock backend
    laser = LaserControl(
        gpio_pin=12,
        pwm_frequency=1000,
        gpio_backend=mock_gpio
    )
    
    print("\n1. Testing power level setting...")
    laser.set_power(50)
    print(f"   Power level: {laser.power_level}%")
    
    print("\n2. Testing laser on/off...")
    laser.on()
    print(f"   Laser is on: {laser.is_on}")
    time.sleep(0.5)
    
    laser.off()
    print(f"   Laser is on: {laser.is_on}")
    
    print("\n3. Testing laser pulse...")
    laser.pulse(duration=0.2, power_level=75)
    print("   Pulse complete")
    
    print("\n4. Testing variable power...")
    for power in [25, 50, 75, 100]:
        laser.on(power_level=power)
        print(f"   Set to {power}% power")
        time.sleep(0.1)
    
    laser.cleanup()
    print("\n✅ LaserControl test complete\n")


def test_mock_camera():
    """Test camera with mock implementation"""
    print("=" * 60)
    print("Testing MockCamera")
    print("=" * 60)
    
    # Create mock camera
    camera = MockCamera(width=640, height=480)
    
    print("\n1. Configuring camera...")
    camera.configure({
        'format': 'RGB888',
        'size': (640, 480)
    })
    
    print("\n2. Starting camera...")
    camera.start()
    
    print("\n3. Capturing frames...")
    for i in range(5):
        frame = camera.capture_array()
        metadata = camera.capture_metadata()
        print(f"   Frame {i+1}: Shape={frame.shape}, "
              f"Exposure={metadata['ExposureTime']}µs, "
              f"Gain={metadata['AnalogueGain']}x")
        time.sleep(0.1)
    
    print("\n4. Getting camera controls...")
    controls = camera.camera_controls
    print(f"   Available controls: {list(controls.keys())}")
    
    camera.stop()
    print("\n✅ MockCamera test complete\n")


def test_gpio_events():
    """Test GPIO event detection with mock"""
    print("=" * 60)
    print("Testing GPIO Event Detection")
    print("=" * 60)
    
    mock_gpio = MockGPIO()
    
    # Track callback invocations
    events_triggered = []
    
    def limit_switch_callback(pin):
        events_triggered.append(pin)
        print(f"   Callback triggered for pin {pin}")
    
    print("\n1. Setting up event detection...")
    from laserturret.hardware_interface import PinMode, PullMode, Edge
    
    # Setup pins
    mock_gpio.setup(18, PinMode.INPUT, pull_up_down=PullMode.UP)
    mock_gpio.setup(21, PinMode.INPUT, pull_up_down=PullMode.UP)
    
    # Add event detection
    mock_gpio.add_event_detect(18, Edge.FALLING, callback=limit_switch_callback)
    mock_gpio.add_event_detect(21, Edge.FALLING, callback=limit_switch_callback)
    
    print("\n2. Simulating limit switch triggers...")
    print("   Triggering pin 18 (falling edge)...")
    mock_gpio.trigger_event(18, 0)  # High to low
    
    print("   Triggering pin 21 (falling edge)...")
    mock_gpio.trigger_event(21, 0)  # High to low
    
    print(f"\n3. Total events triggered: {len(events_triggered)}")
    print(f"   Event pins: {events_triggered}")
    
    mock_gpio.cleanup()
    print("\n✅ GPIO Event Detection test complete\n")


def test_pin_states():
    """Test reading and writing GPIO pin states"""
    print("=" * 60)
    print("Testing GPIO Pin States")
    print("=" * 60)
    
    mock_gpio = MockGPIO()
    from laserturret.hardware_interface import PinMode
    
    print("\n1. Setting up output pins...")
    mock_gpio.setup(23, PinMode.OUTPUT)  # STEP pin
    mock_gpio.setup(19, PinMode.OUTPUT)  # DIR pin
    
    print("\n2. Writing to output pins...")
    mock_gpio.output(23, 1)
    mock_gpio.output(19, 0)
    
    print("\n3. Reading pin states...")
    step_val = mock_gpio.input(23)
    dir_val = mock_gpio.input(19)
    print(f"   STEP pin (23): {step_val}")
    print(f"   DIR pin (19): {dir_val}")
    
    print("\n4. Toggling pins...")
    for _ in range(3):
        mock_gpio.output(23, 1)
        print(f"   STEP high")
        time.sleep(0.05)
        mock_gpio.output(23, 0)
        print(f"   STEP low")
        time.sleep(0.05)
    
    mock_gpio.cleanup()
    print("\n✅ GPIO Pin States test complete\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" HARDWARE ABSTRACTION LAYER TEST SUITE")
    print(" Running tests with MOCK hardware (no Pi required)")
    print("=" * 60 + "\n")
    
    try:
        test_laser_control()
        test_mock_camera()
        test_gpio_events()
        test_pin_states()
        
        print("=" * 60)
        print(" ALL TESTS PASSED ✅")
        print("=" * 60)
        print("\nThe hardware abstraction layer allows you to:")
        print("  • Develop and test code without a Raspberry Pi")
        print("  • Unit test hardware interactions")
        print("  • Simulate hardware behavior")
        print("  • Debug logic without physical setup")
        print("\nTo use real hardware, simply omit the gpio_backend parameter")
        print("or set it to get_gpio_backend() which auto-detects.")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
