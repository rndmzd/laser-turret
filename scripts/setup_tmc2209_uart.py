import argparse
import sys

from laserturret.config_manager import get_config
from laserturret.tmc2209_uart import open_serial, TMC2209, configure_defaults, REG


def dump_regs(label: str, drv: TMC2209) -> None:
    regs = [
        'GCONF', 'GSTAT', 'IFCNT', 'IHOLD_IRUN', 'TPOWERDOWN',
        'TPWMTHRS', 'TCOOLTHRS', 'CHOPCONF', 'DRV_STATUS', 'PWMCONF'
    ]
    for name in regs:
        addr = REG.get(name)
        if addr is None:
            continue
        try:
            val = drv.read_reg(addr)
            print(f"{label}.{name} = 0x{val:08X}")
        except Exception as e:
            print(f"{label}.{name} read error: {e}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Configure TMC2209 over UART")
    p.add_argument("--config", default="laserturret.conf")
    p.add_argument("--port")
    p.add_argument("--baud", type=int)
    p.add_argument("--x-addr", type=int)
    p.add_argument("--y-addr", type=int)
    p.add_argument("--microsteps", type=int)
    p.add_argument("--no-apply", action="store_true")
    p.add_argument("--dump-only", action="store_true")
    args = p.parse_args(argv)

    cfg = get_config(args.config)

    port = args.port or cfg.get_uart_port()
    baud = args.baud or cfg.get_uart_baud()
    x_addr = args.x_addr if getattr(args, "x_addr", None) is not None else cfg.get_uart_address('x')
    y_addr = args.y_addr if getattr(args, "y_addr", None) is not None else cfg.get_uart_address('y')
    micro = args.microsteps if getattr(args, "microsteps", None) is not None else cfg.get_motor_microsteps()

    ser = open_serial(port, baud, timeout=0.05)
    try:
        x = TMC2209(ser, int(x_addr))
        y = TMC2209(ser, int(y_addr))

        if not args.dump_only and not args.no_apply:
            configure_defaults(x, microsteps=micro)
            configure_defaults(y, microsteps=micro)
            print(f"Applied defaults (microsteps={micro}) to X(addr={x_addr}) and Y(addr={y_addr})")

        print("X driver registers:")
        dump_regs("X", x)
        print("Y driver registers:")
        dump_regs("Y", y)
        return 0
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
