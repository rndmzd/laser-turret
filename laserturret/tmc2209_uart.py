import time
from typing import Iterable

try:
    import serial  # type: ignore
except Exception as _:
    serial = None  # Allows importing on systems without pyserial


# -------- CRC-8 (poly 0x07) used by TMC2209 UART --------
def tmc_crc8(bytes_iter: Iterable[int]) -> int:
    crc = 0
    for b in bytes_iter:
        crc ^= b & 0xFF
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


class TMC2209:
    def __init__(self, ser, addr: int):
        self.ser = ser
        self.addr = addr & 0xFF

    def write_reg(self, reg: int, value32: int) -> None:
        reg_w = (reg & 0x7F) | 0x80  # set write bit (bit7=1)
        frame = bytearray([
            0x05,
            self.addr,
            reg_w,
            (value32 >> 24) & 0xFF,
            (value32 >> 16) & 0xFF,
            (value32 >> 8) & 0xFF,
            value32 & 0xFF,
        ])
        frame.append(tmc_crc8(frame))
        self.ser.write(frame)
        self.ser.flush()
        # small inter-frame gap helps on multi-drop
        time.sleep(0.001)

    def read_reg(self, reg: int) -> int:
        reg_r = reg & 0x7F  # read: bit7=0
        hdr = bytearray([0x05, self.addr, reg_r])
        hdr.append(tmc_crc8(hdr))
        self.ser.reset_input_buffer()
        self.ser.write(hdr)
        self.ser.flush()
        # expected response: 0x05, addr, reg_r, data[4], crc
        resp = self.ser.read(8)
        if len(resp) != 8 or resp[0] != 0x05 or resp[1] != self.addr or resp[2] != reg_r:
            raise IOError(f"bad response: {resp.hex() if hasattr(resp, 'hex') else resp}")
        if tmc_crc8(resp[:-1]) != resp[-1]:
            raise IOError("crc mismatch")
        return (resp[3] << 24) | (resp[4] << 16) | (resp[5] << 8) | resp[6]


def open_serial(port: str, baud: int, timeout: float = 0.05):
    if serial is None:
        raise ImportError("pyserial is required for TMC2209 UART (pip install pyserial)")
    return serial.Serial(port, baudrate=baud, bytesize=8, parity="N", stopbits=1, timeout=timeout)


# -------- helper packers for common regs --------
def pack_IHOLD_IRUN(IHOLD: int, IRUN: int, IHOLDDELAY: int) -> int:
    return ((IHOLDDELAY & 0x0F) << 16) | ((IRUN & 0x1F) << 8) | (IHOLD & 0x1F)


def pack_GCONF(pdn_disable: bool = True, mstep_reg_select: bool = True) -> int:
    # GCONF bits: pdn_disable=bit6, mstep_reg_select=bit7
    v = 0
    if pdn_disable:
        v |= (1 << 6)
    if mstep_reg_select:
        v |= (1 << 7)
    return v


def pack_CHOPCONF(mres_bits: int, toff: int, hstrt: int, hend: int, tbl: int) -> int:
    v = 0
    v |= (toff & 0x0F)              # bits 0..3
    v |= ((hstrt & 0x07) << 4)      # bits 4..6
    v |= ((hend & 0x0F) << 7)       # bits 7..10
    v |= ((tbl & 0x03) << 15)       # bits 14..15
    v |= ((mres_bits & 0x0F) << 24) # bits 24..27
    return v


def pack_PWMCONF(pwm_ofs: int, pwm_grad: int, pwm_freq: int = 1, autoscale: bool = True, autograd: bool = True, pwm_lim: int = 12) -> int:
    v = 0
    v |= (pwm_ofs & 0xFF)                # 0..7
    v |= ((pwm_grad & 0xFF) << 8)        # 8..15
    v |= ((pwm_freq & 0x03) << 16)       # 16..17
    if autoscale:
        v |= (1 << 18)
    if autograd:
        v |= (1 << 19)
    v |= ((pwm_lim & 0x0F) << 28)        # 28..31
    return v


# Map microsteps (1,2,4,8,16) to TMC2209 MRES field bits
MRES_FOR_MICROSTEPS = {
    256: 0,
    128: 1,
    64: 2,
    32: 3,
    16: 4,
    8: 5,
    4: 6,
    2: 7,
    1: 8,
}


def mres_bits_for_microsteps(microsteps: int) -> int:
    if microsteps not in MRES_FOR_MICROSTEPS:
        raise ValueError(f"Unsupported microsteps: {microsteps}")
    return MRES_FOR_MICROSTEPS[microsteps]


# Common register addresses
REG = {
    'GCONF': 0x00,
    'GSTAT': 0x01,
    'IFCNT': 0x02,
    'IHOLD_IRUN': 0x10,
    'TPOWERDOWN': 0x11,
    'TPWMTHRS': 0x13,
    'TCOOLTHRS': 0x14,
    'CHOPCONF': 0x6C,
    'DRV_STATUS': 0x6F,
    'PWMCONF': 0x70,
}


def configure_defaults(drv: TMC2209, microsteps: int = 16) -> None:
    """
    Apply a reasonable default configuration for camera pan/tilt steppers.
    """
    ihold_irun = pack_IHOLD_IRUN(IHOLD=0, IRUN=6, IHOLDDELAY=1)
    chopconf = pack_CHOPCONF(mres_bits=mres_bits_for_microsteps(microsteps), toff=3, hstrt=4, hend=0, tbl=2)
    pwmconf = pack_PWMCONF(pwm_ofs=36, pwm_grad=14, pwm_freq=1, autoscale=True, autograd=True, pwm_lim=12)
    #tpwmthrs = 0x00000040
    tpwmthrs = 0x00000000
    tcoolthrs = 0x00000000
    #tpowerdown = 0x00000014
    tpowerdown = 0x00000002

    drv.write_reg(REG['GCONF'], pack_GCONF(pdn_disable=True, mstep_reg_select=True))
    drv.write_reg(REG['IHOLD_IRUN'], ihold_irun)
    drv.write_reg(REG['TPOWERDOWN'], tpowerdown)
    drv.write_reg(REG['TPWMTHRS'], tpwmthrs)
    drv.write_reg(REG['TCOOLTHRS'], tcoolthrs)
    drv.write_reg(REG['CHOPCONF'], chopconf)
    drv.write_reg(REG['PWMCONF'], pwmconf)

    # Touch IFCNT to ensure communication ok
    _ = drv.read_reg(REG['IFCNT'])
