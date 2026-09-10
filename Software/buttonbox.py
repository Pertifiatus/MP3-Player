"""ButtonBox input driver (SX1509 I2C GPIO expander).

Hardware wiring, see KiCad/Projekt 1/ButtonBox/ButtonBox.net:
  I/O0 = rotary encoder A
  I/O1 = rotary encoder B
  I/O2 = rotary encoder switch (click)
  I/O3 = Play/Pause button
  I/O4 = Shuffle button
  I/O5 = Stop button
All active-low (pulled to GND when pressed/rotated), SX1509 internal pull-ups used.
NINT is not wired to the Pi -> must be polled, no interrupt-driven reads.
"""
import time
from smbus2 import SMBus

SX1509_ADDR = 0x3E  # ADDR0/ADDR1 both tied to GND; confirm with i2cdetect after soldering
BUS = 1

REG_DIR_A = 0x0F
REG_PULLUP_A = 0x07
REG_DATA_A = 0x11

PIN_ENC_A = 0
PIN_ENC_B = 1
PIN_ENC_SW = 2
PIN_PLAY_PAUSE = 3
PIN_SHUFFLE = 4
PIN_STOP = 5

BUTTON_NAMES = {
    PIN_PLAY_PAUSE: "play_pause",
    PIN_SHUFFLE: "shuffle",
    PIN_STOP: "stop",
    PIN_ENC_SW: "knob",
}

# quadrature transition table: (prev_AB, curr_AB) -> +1 (CW) / -1 (CCW)
_QUAD_TABLE = {
    (0b00, 0b01): 1, (0b01, 0b11): 1, (0b11, 0b10): 1, (0b10, 0b00): 1,
    (0b00, 0b10): -1, (0b10, 0b11): -1, (0b11, 0b01): -1, (0b01, 0b00): -1,
}

DEBOUNCE_S = 0.03


class ButtonBox:
    def __init__(self, bus=BUS, address=SX1509_ADDR):
        self._bus = SMBus(bus)
        self._addr = address
        self._bus.write_byte_data(self._addr, REG_DIR_A, 0xFF)      # bank A all inputs (POR default anyway)
        self._bus.write_byte_data(self._addr, REG_PULLUP_A, 0x3F)   # pull-ups on I/O0-5

        data = self._read_data_a()
        self._button_state = {n: bool(data & (1 << n)) for n in BUTTON_NAMES}
        self._button_changed_at = {n: 0.0 for n in BUTTON_NAMES}
        self._enc_prev = ((data >> PIN_ENC_A) & 1) << 1 | ((data >> PIN_ENC_B) & 1)

    def _read_data_a(self):
        return self._bus.read_byte_data(self._addr, REG_DATA_A)

    def poll(self):
        """Read current pin states, return a list of event dicts. Call regularly (e.g. every 5-10ms)."""
        events = []
        now = time.monotonic()
        data = self._read_data_a()

        for num, name in BUTTON_NAMES.items():
            level = bool(data & (1 << num))  # True = released (pulled up), False = pressed
            if level != self._button_state[num] and (now - self._button_changed_at[num]) > DEBOUNCE_S:
                self._button_state[num] = level
                self._button_changed_at[num] = now
                events.append({"type": "button_up" if level else "button_down", "name": name})

        curr = ((data >> PIN_ENC_A) & 1) << 1 | ((data >> PIN_ENC_B) & 1)
        if curr != self._enc_prev:
            direction = _QUAD_TABLE.get((self._enc_prev, curr))
            if direction:
                events.append({"type": "rotate", "direction": direction})
            self._enc_prev = curr

        return events


def demo():
    """Self-check: init the expander and poll for 15s, printing events. Requires real hardware on the I2C bus."""
    box = ButtonBox()
    print("Polling ButtonBox for 15s - press buttons / turn the knob now.")
    end = time.monotonic() + 15
    while time.monotonic() < end:
        for event in box.poll():
            print(event)
        time.sleep(0.005)
    # ponytail: fixed 5ms poll interval, no interrupt (NINT not wired to the Pi) -
    # tighten this or move to a periodic thread if fast knob spins feel laggy in the real UI


if __name__ == "__main__":
    demo()
