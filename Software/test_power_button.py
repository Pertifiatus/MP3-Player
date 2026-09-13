"""Pure-logic tests for the power button press/hold state machine - no hardware
needed. board/digitalio are stubbed (Blinka only exists on the Pi). Run
directly: python3 test_power_button.py
"""
import sys
import types


class _FakePin:
    def __init__(self):
        self.direction = None
        self.pull = None
        self.value = True  # released (pulled up)


if "board" not in sys.modules:
    board_stub = types.ModuleType("board")
    board_stub.D9 = "D9"
    sys.modules["board"] = board_stub

if "digitalio" not in sys.modules:
    digitalio_stub = types.ModuleType("digitalio")
    digitalio_stub.Direction = types.SimpleNamespace(OUTPUT=1, INPUT=2)
    digitalio_stub.Pull = types.SimpleNamespace(UP=1, DOWN=2)
    digitalio_stub.DigitalInOut = lambda pin: _FakePin()
    sys.modules["digitalio"] = digitalio_stub

import power_button
from power_button import PowerButton, SHUTDOWN_HOLD_S


class _FakeClock:
    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def make_button_with_clock():
    clock = _FakeClock()
    original = power_button.time.monotonic
    power_button.time.monotonic = clock
    pb = PowerButton()
    return pb, clock, original


def test_quick_tap_fires_short_press_on_release():
    pb, clock, original = make_button_with_clock()
    try:
        pb._pin.value = False  # pressed
        assert pb.poll() is None
        clock.advance(0.2)
        assert pb.poll() is None  # still held, well under the shutdown threshold
        pb._pin.value = True  # released
        assert pb.poll() == "short_press"
    finally:
        power_button.time.monotonic = original


def test_holding_past_threshold_fires_shutdown_once():
    pb, clock, original = make_button_with_clock()
    try:
        pb._pin.value = False
        assert pb.poll() is None
        clock.advance(SHUTDOWN_HOLD_S + 0.01)
        assert pb.poll() == "shutdown"
        clock.advance(1.0)
        assert pb.poll() is None  # still held - does not refire
    finally:
        power_button.time.monotonic = original


def test_release_after_shutdown_does_not_also_fire_short_press():
    pb, clock, original = make_button_with_clock()
    try:
        pb._pin.value = False
        assert pb.poll() is None  # registers press start
        clock.advance(SHUTDOWN_HOLD_S + 0.01)
        assert pb.poll() == "shutdown"
        pb._pin.value = True  # finally let go
        assert pb.poll() is None
    finally:
        power_button.time.monotonic = original


def test_idle_polling_without_any_press_never_fires():
    # real bug found on hardware: the "not pressed" branch didn't check whether
    # a press had actually happened, so it returned "short_press" on every
    # single idle poll - which in main.py's ~10-60ms loop meant the backlight
    # got toggled continuously even with nobody touching the button.
    pb, clock, original = make_button_with_clock()
    try:
        for _ in range(50):
            assert pb.poll() is None
            clock.advance(0.01)
    finally:
        power_button.time.monotonic = original


def test_next_press_after_release_works_normally():
    pb, clock, original = make_button_with_clock()
    try:
        pb._pin.value = False
        assert pb.poll() is None  # registers press start
        clock.advance(0.1)
        pb._pin.value = True
        assert pb.poll() == "short_press"
        assert pb.poll() is None  # idle afterward - must not refire

        pb._pin.value = False
        assert pb.poll() is None
        clock.advance(0.1)
        pb._pin.value = True
        assert pb.poll() == "short_press"
        assert pb.poll() is None
    finally:
        power_button.time.monotonic = original


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"{len(tests)} tests passed.")
