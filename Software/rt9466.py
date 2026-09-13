"""RT9466 single-cell Li-ion switching charger driver (raw I2C).

Register map taken from the official Richtek datasheet (DS9466-04, May 2021,
https://www.richtek.com/assets/product_file/RT9466/DS9466-04.pdf) - not guessed,
since a wrong register write here can set the wrong charge voltage/current and
damage the battery.
"""
from smbus2 import SMBus

ADDR = 0x53
BUS = 1

REG_CHG_CTRL2 = 0x02
REG_CHG_CTRL4 = 0x04
REG_CHG_CTRL7 = 0x07
REG_CHG_CTRL16 = 0x10
REG_CHG_STAT = 0x42
REG_CHG_FAULT = 0x51
REG_DEVICE_ID = 0x40

DEVICE_ID_EXPECTED = 0x84  # VENDOR[3:0]=1000, CHIP_REV[3:0]=0100 (datasheet reset value)

VOREG_MIN_V = 3.9
VOREG_MAX_CODE = 0b1010001  # 4.71V - codes above this clamp to 4.71V too (datasheet table)
ICHG_MAX_CODE = 0b110001  # 5A - codes above this clamp to 5A too (datasheet table)

CHG_STAT_TEXT = {0b00: "ready", 0b01: "charging", 0b10: "done", 0b11: "fault"}


def _voreg_code(voltage_v):
    """CHG_CTRL4 VOREG[6:0]: 0000000=3.9V, +10mV/step, clamps at 4.71V."""
    code = round((voltage_v - VOREG_MIN_V) / 0.01)
    return max(0, min(code, VOREG_MAX_CODE))


def _ichg_code(current_a):
    """CHG_CTRL7 ICHG[5:0]: 000000=0.1A, +0.1A/step, clamps at 5A."""
    code = round(current_a * 10) - 1
    return max(0, min(code, ICHG_MAX_CODE))


class RT9466:
    def __init__(self, bus=BUS, address=ADDR):
        self._bus = SMBus(bus)
        self._addr = address
        device_id = self._bus.read_byte_data(self._addr, REG_DEVICE_ID)
        if device_id != DEVICE_ID_EXPECTED:
            raise RuntimeError(
                f"RT9466 DEVICE_ID mismatch: got 0x{device_id:02x}, expected 0x{DEVICE_ID_EXPECTED:02x}"
            )

    def _rmw(self, reg, mask, value):
        current = self._bus.read_byte_data(self._addr, reg)
        self._bus.write_byte_data(self._addr, reg, (current & ~mask & 0xFF) | (value & mask))

    def configure(self, charge_current_ma, charge_voltage_v=4.2):
        """Set charge voltage/current and put the charger + JEITA in a known state.

        JEITA is disabled: CLAUDE.md documents the TS pin as a fixed-resistor workaround
        (no real NTC), so leaving JEITA on risks the chip reading that fixed divider as an
        out-of-range temperature and silently refusing to charge.
        """
        self._rmw(REG_CHG_CTRL4, 0xFE, _voreg_code(charge_voltage_v) << 1)
        self.set_charge_current(charge_current_ma)
        self._rmw(REG_CHG_CTRL2, 0b00000011, 0b00000011)  # CHG_EN + CFO_EN
        self._rmw(REG_CHG_CTRL16, 0b00010000, 0b00000000)  # JEITA_EN = 0

    def set_charge_current(self, charge_current_ma):
        self._rmw(REG_CHG_CTRL7, 0xFC, _ichg_code(charge_current_ma / 1000.0) << 2)

    def read_status(self):
        stat = self._bus.read_byte_data(self._addr, REG_CHG_STAT)
        return CHG_STAT_TEXT[(stat >> 6) & 0b11]

    def read_fault(self):
        fault = self._bus.read_byte_data(self._addr, REG_CHG_FAULT)
        return {
            "vbus_ov": bool(fault & (1 << 7)),
            "vbat_ov": bool(fault & (1 << 6)),
            "vsys_ov": bool(fault & (1 << 5)),
            "vsys_uv": bool(fault & (1 << 4)),
        }


def demo():
    """Self-check: verify encoding against the datasheet table, then (on real hardware)
    configure the charger at a conservative default and print status/fault."""
    assert _voreg_code(4.2) == 0b0011110
    assert _voreg_code(3.9) == 0
    assert _voreg_code(4.71) == 0b1010001
    assert _ichg_code(2.0) == 0b010011
    assert _ichg_code(0.1) == 0
    assert _ichg_code(0.6) == 0b000101
    assert _ichg_code(1.5) == 0b001110
    print("Encoding self-check OK.")

    charger = RT9466()
    print("DEVICE_ID OK.")
    charger.configure(charge_current_ma=600)
    print(f"status={charger.read_status()} fault={charger.read_fault()}")


if __name__ == "__main__":
    demo()
