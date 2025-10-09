#!/usr/bin/env python3
"""
Axis direction and limit switch diagnostic for the laser turret.

Usage:
    python scripts/axis_direction_diagnostic.py [--steps N] [--delay SEC]

This utility reads the configured limit switches and issues small jog moves
(default 50 microsteps per command) on each axis so you can verify that wiring
and motor direction match expectations. The script pauses between jogs so you
can observe motion and stop the test if something looks unsafe.
"""

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import laserturret.motion  # ensure package initialises without circular import
from laserturret.config_manager import get_config
from laserturret.hardware_interface import (
    get_gpio_backend,
    PinMode,
    PullMode,
)
from laserturret.motion.constants import CLOCKWISE, COUNTER_CLOCKWISE
from laserturret.steppercontrol import (
    StepperMotor,
    LimitSwitchError,
    MotorError,
)

LOG = logging.getLogger("axis_diagnostic")


def read_limit_states(gpio, pins):
    """Return active-low limit switch states."""
    states = {}
    for name, pin in pins.items():
        if pin is None:
            states[name] = None
            continue
        try:
            # Ensure pin is configured as input with pull-up before reading.
            gpio.setup(pin, PinMode.INPUT, PullMode.UP)
            states[name] = gpio.input(pin) == 0
        except Exception as err:  # pragma: no cover - hardware specific
            LOG.error("Failed to read %s (pin %s): %s", name, pin, err)
            states[name] = None
    return states


def format_states(states):
    """Human-readable summary of switch states."""
    parts = []
    for name, active in states.items():
        if active is None:
            parts.append(f"{name}: unavailable")
        else:
            parts.append(f"{name}: {'PRESSED' if active else 'released'}")
    return ", ".join(parts)


class AxisTester:
    """Encapsulates jog and limit switch tests for a single axis."""

    def __init__(self, axis, config, gpio, steps, delay):
        self.axis = axis
        self.steps = steps
        self.delay = delay
        pins = config.get_motor_config(axis)
        cw_pin = pins.get("cw_limit_pin")
        ccw_pin = pins.get("ccw_limit_pin")

        self.limit_pins = {
            f"{axis.upper()}_CW": cw_pin,
            f"{axis.upper()}_CCW": ccw_pin,
        }

        try:
            self.motor = StepperMotor(
                step_pin=pins["step_pin"],
                dir_pin=pins["dir_pin"],
                enable_pin=pins["enable_pin"],
                ms1_pin=pins["ms1_pin"],
                ms2_pin=pins["ms2_pin"],
                ms3_pin=pins["ms3_pin"],
                cw_limit_switch_pin=cw_pin,
                ccw_limit_switch_pin=ccw_pin,
                steps_per_rev=pins["steps_per_rev"],
                microsteps=pins["microsteps"],
                skip_direction_check=True,
                perform_calibration=False,
                limit_backoff_steps=1,
                name=f"{axis.upper()}Axis",
                calibration_timeout=5,
                movement_timeout=5,
                deadzone=0,
                interactive_test_mode=True,
                start_thread=False,
                gpio_backend=gpio,
            )
        except Exception as err:  # pragma: no cover - hardware specific
            LOG.error("Failed to initialise %s axis motor: %s", axis, err)
            raise

    def enable(self):
        self.motor.enable()
        # Allow driver to wake before stepping.
        time.sleep(0.05)

    def disable(self):
        self.motor.disable()
        time.sleep(0.05)

    def jog(self, direction_name, direction_const, expected_switch):
        """Perform a small move and report limit switch state."""
        LOG.info(
            "[%s] Jogging %s (%s). Expect approach toward %s.",
            self.axis.upper(),
            direction_name,
            "CLOCKWISE" if direction_const == CLOCKWISE else "COUNTER_CLOCKWISE",
            expected_switch,
        )
        try:
            self.motor.set_direction(direction_const)
        except LimitSwitchError as err:
            LOG.warning(
                "[%s] Limit already active when setting direction %s: %s",
                self.axis.upper(),
                direction_name,
                err,
            )
            return

        try:
            moved = self.motor.step(self.steps, self.delay)
            LOG.info("[%s] Requested %d steps, moved %d.", self.axis.upper(), self.steps, moved)
        except LimitSwitchError as err:
            LOG.warning(
                "[%s] Movement stopped by limit switch while jogging %s: %s",
                self.axis.upper(),
                direction_name,
                err,
            )
        except MotorError as err:
            LOG.error(
                "[%s] Motor error during jog %s: %s",
                self.axis.upper(),
                direction_name,
                err,
            )
        finally:
            # Give the motor driver time to settle with holding torque.
            time.sleep(0.05)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Diagnose axis direction and limit switch wiring."
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=50,
        help="Number of microsteps per jog (default: 50).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.001,
        help="Delay between steps in seconds (default: 0.001).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock GPIO backend (no real hardware).",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Skip interactive confirmations and run straight through.",
    )
    return parser.parse_args(argv)


def wait_for_ack(prompt, skip):
    if skip:
        return
    try:
        input(prompt)
    except KeyboardInterrupt:
        raise SystemExit("Aborted by user.")


def main(argv):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    config = get_config()
    gpio = get_gpio_backend(mock=args.mock)

    pin_summary = {
        "x_cw_limit_pin": config.get_gpio_pin("x_cw_limit_pin"),
        "x_ccw_limit_pin": config.get_gpio_pin("x_ccw_limit_pin"),
        "y_cw_limit_pin": config.get_gpio_pin("y_cw_limit_pin"),
        "y_ccw_limit_pin": config.get_gpio_pin("y_ccw_limit_pin"),
    }

    LOG.info("Limit pin assignments: %s", pin_summary)

    x_tester = AxisTester("x", config, gpio, args.steps, args.delay)
    y_tester = AxisTester("y", config, gpio, args.steps, args.delay)

    testers = {"x": x_tester, "y": y_tester}

    try:
        for axis, tester in testers.items():
            LOG.info("=== Testing %s axis ===", axis.upper())
            states = read_limit_states(gpio, tester.limit_pins)
            LOG.info("[%s] Initial states: %s", axis.upper(), format_states(states))

            wait_for_ack(
                f"Ensure {axis.upper()} axis can move freely. Press Enter to jog positive...",
                args.no_prompt,
            )
            tester.enable()
            if axis == "x":
                tester.jog("positive", CLOCKWISE, "X_CW limit")
            else:
                tester.jog("positive", CLOCKWISE, "Y_CW limit")
            states = read_limit_states(gpio, tester.limit_pins)
            LOG.info("[%s] States after positive jog: %s", axis.upper(), format_states(states))

            wait_for_ack(
                f"Ready for {axis.upper()} negative jog? Press Enter to continue...",
                args.no_prompt,
            )
            if axis == "x":
                tester.jog("negative", COUNTER_CLOCKWISE, "X_CCW limit")
            else:
                tester.jog("negative", COUNTER_CLOCKWISE, "Y_CCW limit")
            states = read_limit_states(gpio, tester.limit_pins)
            LOG.info("[%s] States after negative jog: %s", axis.upper(), format_states(states))

            tester.disable()
            LOG.info("=== %s axis complete ===", axis.upper())

    finally:
        try:
            x_tester.disable()
            y_tester.disable()
        except Exception:
            pass
        try:
            gpio.cleanup()
        except Exception:
            pass

    LOG.info("Diagnostics finished. If motion moved opposite to expectation, swap coil wiring or adjust limit mapping.")


if __name__ == "__main__":
    main(sys.argv[1:])
