#!/usr/bin/env python3
"""
Limit Switch Test Script

Tests the functionality of all four limit switches (end stops) for the laser turret.
Displays real-time switch states and verifies proper wiring and pull-up configuration.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
import logging
from laserturret.config_manager import get_config
from laserturret.hardware_interface import get_gpio_backend, PinMode, PullMode, Edge

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


class LimitSwitchTester:
    """Test utility for limit switches"""
    
    def __init__(self, use_mock=False):
        """Initialize the tester"""
        logger.info("Initializing Limit Switch Tester...")
        
        # Load configuration
        self.config = get_config()
        
        # Get GPIO backend
        self.gpio = get_gpio_backend(mock=use_mock)
        
        # Get pin assignments from config
        self.switches = {
            'X_CW': self.config.get_gpio_pin('x_cw_limit_pin'),
            'X_CCW': self.config.get_gpio_pin('x_ccw_limit_pin'),
            'Y_CW': self.config.get_gpio_pin('y_cw_limit_pin'),
            'Y_CCW': self.config.get_gpio_pin('y_ccw_limit_pin'),
        }
        
        # Track trigger counts
        self.trigger_counts = {name: 0 for name in self.switches.keys()}
        
        # Setup GPIO pins
        self._setup_pins()
        
        logger.info("Limit Switch Tester initialized")
        logger.info(f"Pin assignments: {self.switches}")
    
    def _setup_pins(self):
        """Setup GPIO pins with pull-up resistors"""
        for name, pin in self.switches.items():
            self.gpio.setup(pin, PinMode.INPUT, pull_up_down=PullMode.UP)
            logger.debug(f"Setup {name} on pin {pin} with pull-up")
    
    def read_switch_state(self, switch_name):
        """
        Read current state of a switch.
        
        Returns:
            bool: True if pressed (LOW), False if released (HIGH)
        """
        pin = self.switches[switch_name]
        # Switch is pressed when pin reads LOW (0)
        return self.gpio.input(pin) == 0
    
    def read_all_states(self):
        """Read states of all switches"""
        return {name: self.read_switch_state(name) for name in self.switches.keys()}
    
    def print_status(self, states=None):
        """Print current status of all switches"""
        if states is None:
            states = self.read_all_states()
        
        print(f"\n{Colors.BOLD}╔════════════════════════════════════════════════╗{Colors.END}")
        print(f"{Colors.BOLD}║         LIMIT SWITCH STATUS                    ║{Colors.END}")
        print(f"{Colors.BOLD}╠════════════════════════════════════════════════╣{Colors.END}")
        
        for name, pressed in states.items():
            pin = self.switches[name]
            count = self.trigger_counts[name]
            
            if pressed:
                status = f"{Colors.RED}{Colors.BOLD}PRESSED {Colors.END}"
                icon = "●"
            else:
                status = f"{Colors.GREEN}RELEASED{Colors.END}"
                icon = "○"
            
            print(f"{Colors.BOLD}║{Colors.END} {icon} {name:8} (Pin {pin:2}) - {status}  [Triggers: {count:3}] {Colors.BOLD}║{Colors.END}")
        
        print(f"{Colors.BOLD}╚════════════════════════════════════════════════╝{Colors.END}")
    
    def monitor_switches(self, interval=0.1, duration=None):
        """
        Monitor switches in real-time.
        
        Args:
            interval: Polling interval in seconds
            duration: Duration to monitor (None = forever)
        """
        print(f"\n{Colors.CYAN}{Colors.BOLD}Starting real-time monitoring...{Colors.END}")
        print(f"{Colors.YELLOW}Press Ctrl+C to stop{Colors.END}\n")
        
        start_time = time.time()
        last_states = self.read_all_states()
        
        try:
            while True:
                # Check duration
                if duration and (time.time() - start_time) > duration:
                    break
                
                # Read current states
                current_states = self.read_all_states()
                
                # Check for state changes
                changed = False
                for name in self.switches.keys():
                    if current_states[name] != last_states[name]:
                        changed = True
                        if current_states[name]:  # Pressed
                            self.trigger_counts[name] += 1
                            logger.info(f"{name} PRESSED (Pin {self.switches[name]})")
                        else:  # Released
                            logger.info(f"{name} RELEASED")
                
                # Update display if state changed
                if changed:
                    # Clear screen (optional)
                    # print("\033[2J\033[H", end='')
                    self.print_status(current_states)
                    last_states = current_states
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Monitoring stopped by user{Colors.END}")
    
    def test_individual_switches(self, timeout=30):
        """
        Test each switch individually with user prompts.
        
        Args:
            timeout: Timeout for each switch test in seconds
        """
        print(f"\n{Colors.CYAN}{Colors.BOLD}═══════════════════════════════════════════{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}  INDIVIDUAL LIMIT SWITCH TEST{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}═══════════════════════════════════════════{Colors.END}\n")
        
        results = {}
        
        for name, pin in self.switches.items():
            print(f"\n{Colors.BOLD}Testing {name} (Pin {pin}):{Colors.END}")
            print(f"{Colors.YELLOW}Please trigger the {name} limit switch...{Colors.END}")
            print(f"Waiting up to {timeout} seconds...")
            
            start_time = time.time()
            triggered = False
            
            # Wait for switch to be pressed
            while (time.time() - start_time) < timeout:
                if self.read_switch_state(name):
                    triggered = True
                    elapsed = time.time() - start_time
                    print(f"{Colors.GREEN}✓ {name} triggered! (after {elapsed:.1f}s){Colors.END}")
                    self.trigger_counts[name] += 1
                    
                    # Wait for release
                    print(f"{Colors.YELLOW}Release the switch...{Colors.END}")
                    while self.read_switch_state(name):
                        time.sleep(0.1)
                    print(f"{Colors.GREEN}✓ {name} released{Colors.END}")
                    break
                
                time.sleep(0.1)
            
            if not triggered:
                print(f"{Colors.RED}✗ {name} test FAILED - timeout{Colors.END}")
            
            results[name] = triggered
        
        # Print summary
        print(f"\n{Colors.CYAN}{Colors.BOLD}═══════════════════════════════════════════{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}  TEST SUMMARY{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}═══════════════════════════════════════════{Colors.END}\n")
        
        passed = sum(results.values())
        total = len(results)
        
        for name, success in results.items():
            status = f"{Colors.GREEN}PASS{Colors.END}" if success else f"{Colors.RED}FAIL{Colors.END}"
            icon = "✓" if success else "✗"
            print(f"{icon} {name:8} - {status}")
        
        print(f"\n{Colors.BOLD}Result: {passed}/{total} switches working{Colors.END}")
        
        if passed == total:
            print(f"{Colors.GREEN}{Colors.BOLD}All limit switches functioning correctly!{Colors.END}\n")
        else:
            print(f"{Colors.RED}{Colors.BOLD}Some limit switches failed. Check wiring.{Colors.END}\n")
        
        return results
    
    def check_wiring(self):
        """Check for potential wiring issues"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}═══════════════════════════════════════════{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}  WIRING DIAGNOSTIC{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}═══════════════════════════════════════════{Colors.END}\n")
        
        states = self.read_all_states()
        issues = []
        
        # Check if any switches are constantly pressed
        for name, pressed in states.items():
            if pressed:
                issues.append(f"{Colors.YELLOW}⚠ {name} is reading as PRESSED - check if switch is stuck or mis-wired{Colors.END}")
        
        # Check if all switches are released (normal state)
        all_released = all(not pressed for pressed in states.values())
        
        if all_released:
            print(f"{Colors.GREEN}✓ All switches in normal state (released){Colors.END}")
            print(f"{Colors.GREEN}✓ Pull-up resistors appear to be working{Colors.END}")
        else:
            print(f"{Colors.RED}✗ Some switches are not in normal state{Colors.END}")
            for issue in issues:
                print(f"  {issue}")
        
        # Check for duplicate pin assignments (shouldn't happen with config validation)
        pins = list(self.switches.values())
        if len(pins) != len(set(pins)):
            print(f"{Colors.RED}✗ CRITICAL: Duplicate pin assignments detected!{Colors.END}")
        else:
            print(f"{Colors.GREEN}✓ No duplicate pin assignments{Colors.END}")
        
        print()
    
    def cleanup(self):
        """Clean up GPIO resources"""
        logger.info("Cleaning up GPIO...")
        self.gpio.cleanup(list(self.switches.values()))
        logger.info("Cleanup complete")


def main():
    """Main test program"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test laser turret limit switches')
    parser.add_argument('--mock', action='store_true', help='Use mock GPIO for testing')
    parser.add_argument('--mode', choices=['monitor', 'test', 'check', 'all'], 
                       default='all', help='Test mode')
    parser.add_argument('--duration', type=int, help='Duration for monitoring (seconds)')
    
    args = parser.parse_args()
    
    print(f"\n{Colors.BLUE}{Colors.BOLD}╔════════════════════════════════════════════════╗{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}║   LASER TURRET LIMIT SWITCH TEST UTILITY       ║{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}╚════════════════════════════════════════════════╝{Colors.END}")
    
    if args.mock:
        print(f"\n{Colors.YELLOW}Running in MOCK mode (no hardware required){Colors.END}")
    
    try:
        tester = LimitSwitchTester(use_mock=args.mock)
        
        if args.mode == 'check' or args.mode == 'all':
            tester.check_wiring()
        
        if args.mode == 'test' or args.mode == 'all':
            tester.test_individual_switches()
        
        if args.mode == 'monitor' or args.mode == 'all':
            tester.monitor_switches(duration=args.duration)
        
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Error: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
    finally:
        if 'tester' in locals():
            tester.cleanup()
    
    print(f"\n{Colors.CYAN}Test complete.{Colors.END}\n")


if __name__ == "__main__":
    main()
