"""Pure-logic tests for the ButtonBox driver - no hardware needed.
smbus2 only exists on Linux (imports fcntl), so it's stubbed out here to let
this run on the Windows dev machine too. Run directly: python3 test_buttonbox.py
"""
import sys
import types


class _FakeSMBus:
    """Stands in for smbus2.SMBus - poll() reads whatever .data is set to."""

    def __init__(self, bus_number):
        self.data = 0xFF  # everything released/resting

    def write_byte_data(self, addr, reg, value):
        pass

    def read_byte_data(self, addr, reg):
        return self.data


if "smbus2" not in sys.modules:
    stub = types.ModuleType("smbus2")
    stub.SMBus = _FakeSMBus
    sys.modules["smbus2"] = stub

import buttonbox
from buttonbox import ButtonBox, decode_encoder_step, PIN_ENC_A, PIN_ENC_B, PIN_ENC_SW, PIN_PLAY_PAUSE


class _FakeClock:
    """Lets debounce-window tests advance time deterministically instead of
    relying on real wall-clock sleeps."""

    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def make_box_with_clock():
    clock = _FakeClock()
    original = buttonbox.time.monotonic
    buttonbox.time.monotonic = clock
    box = ButtonBox()
    return box, clock, original


def make_data(enc=0b00, sw=1, play=1):
    """Build a raw SX1509 data byte. sw/play: 1=released, 0=pressed (active-low).
    shuffle/stop are hardcoded released (1) - not under test here."""
    enc_a = (enc >> 1) & 1
    enc_b = enc & 1
    shuffle_stop_released = 0b11 << 4
    return (enc_a << PIN_ENC_A) | (enc_b << PIN_ENC_B) | (sw << PIN_ENC_SW) \
        | (play << PIN_PLAY_PAUSE) | shuffle_stop_released

CW_STEP = 0b01    # one quarter-step clockwise from resting 00
CCW_STEP = 0b10   # one quarter-step counter-clockwise from resting 00


def run_sequence(pin_readings, start_reading=0b00):
    state = (0, start_reading, 0)
    directions = []
    for reading in pin_readings:
        if reading == state[1]:
            continue  # poll() only feeds decode_encoder_step on an actual pin change
        state, direction = decode_encoder_step(state, reading)
        if direction:
            directions.append(direction)
    return directions, state


def test_single_step_does_not_fire():
    # DETENT_STEPS=4: a lone quarter-step is not enough yet.
    directions, state = run_sequence([CW_STEP])
    assert directions == [], directions


def test_two_steps_still_does_not_fire():
    # halfway through a cycle still isn't a full click.
    directions, state = run_sequence([0b01, 0b11])
    assert directions == [], directions


def test_full_cw_click_fires_once():
    # a full 4-step Gray cycle is exactly one DETENT_STEPS=4 click.
    directions, state = run_sequence([0b01, 0b11, 0b10, 0b00])
    assert directions == [1], directions


def test_full_ccw_click_fires_once():
    directions, state = run_sequence([0b10, 0b11, 0b01, 0b00])
    assert directions == [-1], directions


def test_repeated_clicks_both_directions():
    directions, state = run_sequence([0b01, 0b11, 0b10, 0b00] * 2 + [0b10, 0b11, 0b01, 0b00])
    assert directions == [1, 1, -1], directions


def test_small_nudge_and_back_does_not_fire():
    # a nudge CW then immediately back to rest nets zero - no click either way.
    directions, state = run_sequence([0b01, 0b00])
    assert directions == [], directions


def test_skipped_reading_from_slow_polling_does_not_crash():
    # simulate a slow poll loop that misses an intermediate state (jumps
    # straight from 00 to 11, the diagonal) - should not raise, and should
    # not emit a bogus direction from an invalid/ambiguous jump.
    directions, state = run_sequence([0b11, 0b00])
    assert directions == [], directions


def test_real_hardware_noise_pattern_is_fully_suppressed():
    # captured verbatim from a real main.log run (see NOTES_FOR_PER.md): the
    # encoder kept flipping cleanly between 11 and one neighbor, repeatedly,
    # with nobody able to complete a real turn - this is what made it "jump
    # back" ~95% of the time under the old per-step-firing logic. A never-reset
    # running tally must absorb ALL of this since it never nets more than 1
    # tick away from center.
    noisy_11_01 = [0b11, 0b01] * 6
    directions, state = run_sequence(noisy_11_01, start_reading=0b11)
    assert directions == [], directions

    noisy_11_10 = [0b11, 0b10] * 4
    directions, state = run_sequence(noisy_11_10, start_reading=0b11)
    assert directions == [], directions


def test_sustained_rotation_past_noise_still_fires():
    # a real turn isn't perfectly clean either - mixed forward/backward
    # wobble that nets a full click's worth of progress must still register.
    directions, state = run_sequence(
        [0b01, 0b11, 0b10, 0b11, 0b10, 0b00, 0b10, 0b00, 0b01, 0b00, 0b01, 0b11, 0b10, 0b00]
    )
    assert directions == [1, -1, 1, 1], directions


def test_button_press_fires_once_after_debounce_window():
    box, clock, original = make_box_with_clock()
    try:
        box._bus.data = make_data(play=0)  # pressed
        assert box.poll() == []  # edge just happened, not settled yet
        clock.advance(buttonbox.BTN_DEBOUNCE_S + 0.001)
        events = box.poll()
        assert events == [{"type": "button_down", "name": "play_pause"}], events
        # holding steady afterward must not refire
        clock.advance(1.0)
        assert box.poll() == []
    finally:
        buttonbox.time.monotonic = original


def test_button_bounce_resets_the_settle_window():
    # ported from CubeLED's handleButton(): ANY raw edge resets the settle
    # timer, so a bounce right before the window would have elapsed pushes
    # acceptance back out - unlike counting N stable samples, which can get
    # lucky and accept a short quiet gap mid-bounce-train.
    box, clock, original = make_box_with_clock()
    try:
        box._bus.data = make_data(play=0)  # pressed
        assert box.poll() == []  # edge registered now, not settled yet
        clock.advance(buttonbox.BTN_DEBOUNCE_S - 0.005)  # almost settled
        assert box.poll() == []
        box._bus.data = make_data(play=1)  # bounce back right before settling
        assert box.poll() == []  # edge resets the settle timer (registered now)
        clock.advance(buttonbox.BTN_DEBOUNCE_S - 0.005)  # would've settled under the OLD timer
        assert box.poll() == []  # ...but not under the reset one
        box._bus.data = make_data(play=0)  # genuine press
        assert box.poll() == []  # edge registered again
        clock.advance(buttonbox.BTN_DEBOUNCE_S + 0.001)
        events = box.poll()
        assert events == [{"type": "button_down", "name": "play_pause"}], events
    finally:
        buttonbox.time.monotonic = original


def test_button_requires_release_before_pressing_again():
    box, clock, original = make_box_with_clock()
    try:
        box._bus.data = make_data(play=0)
        assert box.poll() == []  # edge registered
        clock.advance(buttonbox.BTN_DEBOUNCE_S + 0.001)
        assert box.poll() == [{"type": "button_down", "name": "play_pause"}]

        box._bus.data = make_data(play=1)
        assert box.poll() == []  # edge registered
        clock.advance(buttonbox.BTN_DEBOUNCE_S + 0.001)
        assert box.poll() == [{"type": "button_up", "name": "play_pause"}]

        # a bounce back to pressed for under the debounce window must not re-fire
        box._bus.data = make_data(play=0)
        assert box.poll() == []
        box._bus.data = make_data(play=1)
        events = box.poll()
        assert events == [], events  # bounce absorbed, timer reset, no stray press
    finally:
        buttonbox.time.monotonic = original


def test_encoder_glitch_within_debounce_window_is_ignored():
    box, clock, original = make_box_with_clock()
    try:
        box._enc_state = (0, 0b00, 0)  # known baseline, independent of FakeSMBus's default
        box._enc_raw = 0b00
        box._bus.data = make_data(enc=0b01)  # glitch
        assert box.poll() == []
        box._bus.data = make_data(enc=0b00)  # bounces straight back before settling
        events = box.poll()
        assert events == []  # never reached decode_encoder_step - no direction at all
        assert box._enc_state[0] == 0  # tally untouched by the glitch
    finally:
        buttonbox.time.monotonic = original


def test_encoder_settled_step_is_counted_but_needs_a_full_click_to_fire():
    box, clock, original = make_box_with_clock()
    try:
        box._enc_state = (0, 0b00, 0)
        box._enc_raw = 0b00
        for reading in (0b01, 0b11, 0b10):  # 3 of 4 quarter-steps - not a full click yet
            box._bus.data = make_data(enc=reading)
            assert box.poll() == []  # edge registered
            clock.advance(buttonbox.ENC_DEBOUNCE_S + 0.001)
            assert box.poll() == []
        assert box._enc_state[0] == 3  # tally did advance

        box._bus.data = make_data(enc=0b00)  # 4th quarter-step completes the cycle
        assert box.poll() == []  # edge registered
        clock.advance(buttonbox.ENC_DEBOUNCE_S + 0.001)
        events = box.poll()
        assert events == [{"type": "rotate", "direction": 1}], events
    finally:
        buttonbox.time.monotonic = original


def test_click_overshoot_spring_back_right_at_the_boundary_is_suppressed():
    # a full click fires (dir=1), then a minor mechanical overshoot springs
    # back one quarter-step right at the boundary it just crossed - that
    # would otherwise immediately un-cross it and report the opposite
    # direction, which the suppression window must catch.
    box, clock, original = make_box_with_clock()
    try:
        box._enc_state = (0, 0b00, 0)
        box._enc_raw = 0b00
        events = []
        for reading in (0b01, 0b11, 0b10, 0b00):
            box._bus.data = make_data(enc=reading)
            box.poll()  # register the edge
            clock.advance(buttonbox.ENC_DEBOUNCE_S + 0.001)
            events.extend(box.poll())  # accept it
        assert events == [{"type": "rotate", "direction": 1}], events

        box._bus.data = make_data(enc=0b10)  # overshoot spring-back, one quarter-step
        box.poll()  # register the edge
        clock.advance(buttonbox.ENC_DEBOUNCE_S + 0.001)  # well within the 30ms window
        assert box.poll() == []
    finally:
        buttonbox.time.monotonic = original


def test_genuine_reversal_after_the_suppression_window_still_fires():
    # a real, deliberate direction change well after the window must not be
    # mistaken for an overshoot - real clicks are always >300ms apart.
    box, clock, original = make_box_with_clock()
    try:
        box._enc_state = (0, 0b00, 0)
        box._enc_raw = 0b00
        for reading in (0b01, 0b11, 0b10, 0b00):
            box._bus.data = make_data(enc=reading)
            box.poll()
            clock.advance(buttonbox.ENC_DEBOUNCE_S + 0.001)
            box.poll()

        clock.advance(0.5)  # well past ROTATE_OPPOSITE_SUPPRESS_S
        events = []
        for reading in (0b10, 0b11, 0b01, 0b00):  # a full CCW click
            box._bus.data = make_data(enc=reading)
            box.poll()
            clock.advance(buttonbox.ENC_DEBOUNCE_S + 0.001)
            events.extend(box.poll())
        assert events == [{"type": "rotate", "direction": -1}], events
    finally:
        buttonbox.time.monotonic = original


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"{len(tests)} tests passed.")
