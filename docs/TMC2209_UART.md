# TMC2209 UART Configuration & Tuning

This document explains how to configure and tune Trinamic TMC2209 stepper drivers via UART in the Laser Turret project.

## Overview

When `use_uart = true`, the app configures both X and Y TMC2209 drivers over a shared UART bus. You can:

- Read live driver registers from the web UI (Motor tab)
- Apply safe default tuning at startup and on demand
- Change IHOLD/IRUN/IHOLDDELAY and TPOWERDOWN at runtime (per-axis or both)

The classic MS1/MS2/MS3 pins are not required in UART mode. Microstepping is set via the `MRES` field in `CHOPCONF` based on your configured `microsteps`.

## Wiring (High-level)

- Connect the Raspberry Pi UART to the TMC2209 UART bus as per the datasheet (shared RX/TX, PDN/UART pin). Multiple drivers share the same UART (multi-drop).
- Ensure proper power and grounds are common between drivers and Pi.
- Keep inter-frame delay (app already adds a short gap) and ensure drivers are powered before the app starts.

Refer to the TMC2209 datasheet and your driver board schematic for the exact UART/PDN wiring and addressing jumpers/straps.

## Configuration

Set these keys in `laserturret.conf` under `[Motor]`:

```ini
# Enable UART mode for TMC2209
use_uart = true

# Serial port and baudrate
uart_port = /dev/serial0
uart_baud = 115200

# Per-axis UART addresses (0-3)
x_uart_address = 2
y_uart_address = 1

# Microstepping resolution (affects CHOPCONF.MRES in UART mode)
microsteps = 8  # 1,2,4,8,16
```

Notes:

- When `use_uart = true`, the MS1/MS2/MS3 pins in config are ignored and not driven.
- Addresses must match your hardware straps/jumpers per TMC2209 addressing scheme (0–3). See datasheet for details.

## Web UI: Motor Tab

Open the Control Center → Hardware → Motor.

- "TMC2209 Driver Registers": Click Refresh to read `GCONF, GSTAT, IFCNT, IHOLD_IRUN, TPOWERDOWN, TPWMTHRS, TCOOLTHRS, CHOPCONF, DRV_STATUS, PWMCONF` for X and Y. Values are shown in hex.
- "UART Tuning":
  - Axis selector: `X`, `Y`, or `Both`
  - Set `IHOLD`, `IRUN`, `IHOLDDELAY`, `TPOWERDOWN`
  - Apply buttons will write registers over UART and refresh the register table

## REST API

- Read registers:

```bash
curl http://<pi>:5000/tracking/camera/tmc/registers
```

- Apply default tuning (uses configured `microsteps` to set CHOPCONF.MRES):

```bash
curl -X POST http://<pi>:5000/tracking/camera/tmc/apply_defaults -H 'Content-Type: application/json' -d '{}'
```

- Write IHOLD/IRUN/IHOLDDELAY:

```bash
curl -X POST http://<pi>:5000/tracking/camera/tmc/ihold_irun \
  -H 'Content-Type: application/json' \
  -d '{"axis":"x","ihold":6,"irun":20,"iholddelay":4}'
```

- Write TPOWERDOWN:

```bash
curl -X POST http://<pi>:5000/tracking/camera/tmc/tpowerdown \
  -H 'Content-Type: application/json' \
  -d '{"axis":"both","tpowerdown":20}'
```

## CLI Setup Script

A helper script can apply defaults and dump registers from the console:

```bash
python scripts/setup_tmc2209_uart.py --dump-only
python scripts/setup_tmc2209_uart.py --microsteps 16
python scripts/setup_tmc2209_uart.py --port /dev/serial0 --baud 115200 --x-addr 2 --y-addr 1 --dump-only
```

## Troubleshooting

- **No registers / errors**: Ensure `use_uart = true`, port/baud are correct, and drivers are powered.
- **IFCNT not incrementing**: Check wiring and addressing (X/Y addresses unique and match software config).
- **UI shows errors**: The Motor tab will display a banner if UART is disabled or the driver is unreachable.
- **Microstepping not changing**: In UART mode, MS pins are ignored. `microsteps` is applied via `CHOPCONF.MRES`.

## Safety

Always power down the system before changing wiring. Ensure proper current/thermal settings for your motors and heatsinking for the driver ICs.
