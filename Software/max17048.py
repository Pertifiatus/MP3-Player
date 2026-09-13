"""MAX17048 Li+ fuel gauge driver (raw I2C), VCELL/SOC only.

Register map verified against Adafruit's CircuitPython MAX1704x driver
(github.com/adafruit/Adafruit_CircuitPython_MAX1704x/blob/main/adafruit_max1704x.py) -
the rest of the chip (alerts, hibernate, quick-start) is unused here.
"""
from smbus2 import SMBus, i2c_msg

ADDR = 0x36
BUS = 1

REG_VCELL = 0x02
REG_SOC = 0x04


class MAX17048:
    def __init__(self, bus=BUS, address=ADDR):
        self._bus = SMBus(bus)
        self._addr = address

    def _read_word(self, reg):
        write = i2c_msg.write(self._addr, [reg])
        read = i2c_msg.read(self._addr, 2)
        self._bus.i2c_rdwr(write, read)
        data = list(read)
        return (data[0] << 8) | data[1]

    def read_vcell(self):
        """Returns cell voltage in volts."""
        return self._read_word(REG_VCELL) * 78.125 / 1_000_000

    def read_soc_pct(self):
        """Returns state of charge in percent (can read slightly outside 0-100)."""
        return self._read_word(REG_SOC) / 256.0


def demo():
    """Self-check: print live VCELL/SOC for 10s. Requires real hardware."""
    import time

    gauge = MAX17048()
    end = time.monotonic() + 10
    while time.monotonic() < end:
        print(f"VCELL={gauge.read_vcell():.3f}V SOC={gauge.read_soc_pct():.1f}%")
        time.sleep(1)


if __name__ == "__main__":
    demo()
