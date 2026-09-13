"""QMI8658A IMU driver (raw I2C, see CLAUDE.md Abschnitt 7 fuer die 0x6A-Adress-Diskrepanz).

Register map and init sequence verified live on Board 2 on 08.09.2026 (WHO_AM_I=0x05,
plausible accel/gyro/temp readings). Address is 0x6A, not the datasheet-documented 0x6B.
"""
import time
from smbus2 import SMBus

ADDR = 0x6A
BUS = 1

REG_WHO_AM_I = 0x00
REG_CTRL1 = 0x02
REG_CTRL2 = 0x03
REG_CTRL3 = 0x04
REG_CTRL4 = 0x05
REG_CTRL5 = 0x06
REG_CTRL6 = 0x07
REG_CTRL7 = 0x08
REG_TEMP_OUT = 0x33
REG_ACCEL_OUT = 0x35
REG_GYRO_OUT = 0x3B

ACCEL_SENS = 4096.0  # LSB/g at +-8g (CTRL2=0x26)
GYRO_SENS = 16.0  # LSB/dps at +-2048dps (CTRL3=0x56)

# ponytail: fixed thresholds, tune once real hardware feedback is available
SHAKE_THRESHOLD_G = 2.2  # |accel| spike above this triggers a shake event
FLIP_STILL_G = 0.3  # gyro/accel jitter below this counts as "settled" for orientation reads


def _s16(lo, hi):
    v = (hi << 8) | lo
    return v - 65536 if v >= 32768 else v


class QMI8658:
    def __init__(self, bus=BUS, address=ADDR):
        self._bus = SMBus(bus)
        self._addr = address
        who = self._bus.read_byte_data(self._addr, REG_WHO_AM_I)
        if who != 0x05:
            raise RuntimeError(f"QMI8658A WHO_AM_I mismatch: got 0x{who:02x}, expected 0x05")

        self._bus.write_byte_data(self._addr, REG_CTRL1, 0x60)  # address auto-increment
        self._bus.write_byte_data(self._addr, REG_CTRL2, 0x26)  # accel +-8g, ODR 125Hz
        self._bus.write_byte_data(self._addr, REG_CTRL3, 0x56)  # gyro +-512dps, ODR 125Hz
        self._bus.write_byte_data(self._addr, REG_CTRL4, 0x00)  # magnetometer off
        self._bus.write_byte_data(self._addr, REG_CTRL5, 0x00)  # low-pass filters off
        self._bus.write_byte_data(self._addr, REG_CTRL6, 0x00)  # motion-on-demand off
        self._bus.write_byte_data(self._addr, REG_CTRL7, 0x03)  # enable accel + gyro
        time.sleep(0.05)

    def _read_block(self, reg, length):
        write = __import__("smbus2").i2c_msg.write(self._addr, [reg])
        read = __import__("smbus2").i2c_msg.read(self._addr, length)
        self._bus.i2c_rdwr(write, read)
        return list(read)

    def read_temp_c(self):
        raw = self._read_block(REG_TEMP_OUT, 2)
        whole = raw[1] - 256 if raw[1] >= 128 else raw[1]
        return whole + raw[0] / 256.0

    def read_accel_g(self):
        """Returns (x, y, z) in g."""
        raw = self._read_block(REG_ACCEL_OUT, 6)
        ax = _s16(raw[0], raw[1]) / ACCEL_SENS
        ay = _s16(raw[2], raw[3]) / ACCEL_SENS
        az = _s16(raw[4], raw[5]) / ACCEL_SENS
        return ax, ay, az

    def read_gyro_dps(self):
        """Returns (x, y, z) in degrees/sec."""
        raw = self._read_block(REG_GYRO_OUT, 6)
        gx = _s16(raw[0], raw[1]) / GYRO_SENS
        gy = _s16(raw[2], raw[3]) / GYRO_SENS
        gz = _s16(raw[4], raw[5]) / GYRO_SENS
        return gx, gy, gz


def orientation(accel_g):
    """Classify which axis is closest to +-1g ("up"). Returns e.g. 'z+', 'z-', 'x+', ...

    ponytail: whichever raw axis reads closest to gravity wins - simple and good enough
    for a 2-sided device (front/back), no tilt-compensation/fusion. Axis-to-physical-side
    mapping (which axis is "front screen up") is NOT yet known - depends on how the QMI8658A
    is oriented on the PCB relative to the two displays. Needs a live check: hold the device
    face-up/face-down and print read_accel_g() to see which axis+sign corresponds to which
    physical side, then adjust FRONT_UP_AXIS/FRONT_DOWN_AXIS in main.py accordingly.
    """
    ax, ay, az = accel_g
    axes = {"x": ax, "y": ay, "z": az}
    dominant = max(axes, key=lambda k: abs(axes[k]))
    sign = "+" if axes[dominant] >= 0 else "-"
    return dominant + sign


def magnitude(accel_g):
    ax, ay, az = accel_g
    return (ax * ax + ay * ay + az * az) ** 0.5


def demo():
    """Self-check: print live accel/gyro/temp + orientation for 10s. Requires real hardware."""
    imu = QMI8658()
    print("WHO_AM_I OK. Reading for 10s - move the board around.")
    end = time.monotonic() + 10
    while time.monotonic() < end:
        accel = imu.read_accel_g()
        gyro = imu.read_gyro_dps()
        temp = imu.read_temp_c()
        print(f"accel={tuple(round(v, 2) for v in accel)}g "
              f"gyro={tuple(round(v, 1) for v in gyro)}dps "
              f"temp={temp:.1f}C orientation={orientation(accel)} "
              f"|a|={magnitude(accel):.2f}")
        time.sleep(0.2)


if __name__ == "__main__":
    demo()
