"""ButtonBox input driver (SX1509 I2C GPIO expander).

Hardware wiring, see KiCad/Projekt 1/ButtonBox/ButtonBox.net:
  I/O0 = rotary encoder A
  I/O1 = rotary encoder B
PIN_ENC_A/PIN_ENC_B below are swapped relative to that netlist labeling - rotation
direction came out reversed on real hardware (turning CW registered as CCW), and
swapping which pin feeds which bit of the Gray-code reading is the correct fix
for that (rather than negating `direction` after the fact, which would be
correct for rotate events but silently leave any future A/B-relative decode
logic - e.g. distinguishing a stuck line - reasoning about the wrong pin).
  I/O2 = rotary encoder switch (click)
  I/O3 = Play/Pause button
  I/O4 = Shuffle button
  I/O5 = Stop button
All active-low (pulled to GND when pressed/rotated), SX1509 internal pull-ups used.
NINT is not wired to the Pi -> must be polled, no interrupt-driven reads.
"""
import queue
import threading
import time
from smbus2 import SMBus

SX1509_ADDR = 0x3E  # ADDR0/ADDR1 both tied to GND; confirm with i2cdetect after soldering
BUS = 1

REG_DIR_A = 0x0F
REG_PULLUP_A = 0x07
REG_DATA_A = 0x11

PIN_ENC_A = 1
PIN_ENC_B = 0
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

# Quadrature decode, ported from the proven approach in a sister project
# (../CubeLED/Arduino/V8/V8.ino handleEncoder()/handleEncoderISR()): keep a
# LIFETIME running tally of net quarter-steps that never resets, and only
# report a click when floor-toward-zero(tally / DETENT_STEPS) actually
# changes from the last report.
#
# Two earlier attempts both failed on real hardware (see NOTES_FOR_PER.md):
# DETENT_STEPS=4 with an accumulator that RESET to 0 every time a reversal
# came in lost real rotation to what turned out to be the encoder settling
# back and forth around its own rest position (not bounce - a real hardware
# log showed it flipping cleanly between two adjacent Gray states, e.g.
# 11<->01, repeatedly, seemingly on its own). DETENT_STEPS=1 then fired on
# every one of those flips, i.e. on the noise itself - matching "jumps
# back immediately" almost every time. A never-reset running tally fixes
# both: a 11<->01<->11<->01 wobble keeps the tally oscillating between two
# adjacent small integers forever without ever crossing a DETENT_STEPS
# boundary, so it's silently absorbed - while genuine sustained rotation in
# one direction keeps pushing the tally further and eventually crosses one.
#
# DETENT_STEPS=4 (a full clean Gray cycle per click, matching CubeLED) had
# been lowered to 2 because the encoder never seemed to complete a clean
# 4-step cycle - but that turned out to be the ENC_DEBOUNCE_S/poll-rate bug
# described above (2-3ms-lived intermediate states were getting silently
# dropped), not the encoder. A raw, undebounced 2ms-poll capture on real
# hardware (12.09.2026, see NOTES_FOR_PER.md) proved the mechanism itself
# completes the full 4-step cycle cleanly on every single click with zero
# bounce. With that fixed, DETENT_STEPS=2 instead causes new symptoms of its
# own: a full click now reliably crosses the boundary TWICE (double steps),
# and a click that overshoots the detent by one quarter-step and springs
# back can straddle the 2-boundary and immediately un-cross it (fires
# forward then immediately back). Back to 4: one full clean cycle now maps
# to exactly one report, and a minor overshoot can't come close to
# reversing a full 4 ticks, so it's absorbed by the tally with no extra
# time-based filtering needed.
_GRAY_CYCLE = (0b00, 0b01, 0b11, 0b10)  # index i -> i+1 (mod 4) is one CW quarter-step
_GRAY_INDEX = {reading: i for i, reading in enumerate(_GRAY_CYCLE)}
DETENT_STEPS = 4


def decode_encoder_step(state, curr_reading):
    """One decode step. `state` is (raw_ticks, prev_reading, last_reported) -
    start with (0, <any valid reading>, 0). raw_ticks never resets. Returns
    (new_state, direction) where direction is +1 / -1 / None."""
    raw_ticks, prev_reading, last_reported = state
    if curr_reading not in _GRAY_INDEX or prev_reading not in _GRAY_INDEX:
        return (raw_ticks, curr_reading, last_reported), None

    delta = (_GRAY_INDEX[curr_reading] - _GRAY_INDEX[prev_reading]) % 4
    if delta == 1:
        raw_ticks += 1
    elif delta == 3:
        raw_ticks -= 1
    else:
        return (raw_ticks, curr_reading, last_reported), None  # delta 0/2 - ignore

    reported = int(raw_ticks / DETENT_STEPS)  # truncate toward zero, matches C's `/` on longs
    direction = None
    if reported != last_reported:
        direction = 1 if reported > last_reported else -1
        last_reported = reported
    return (raw_ticks, curr_reading, last_reported), direction


# Time-based debounce: ANY raw edge resets a settle timer, and a reading only
# becomes the new accepted/stable value once the raw signal has been quiet
# (no further edges at all) for the full debounce window. Ported directly from
# a proven-working pattern in a sister project driving the same kind of
# encoder+round-display setup (CubeLED, ESP32) - see
# ../CubeLED/Arduino/V8/V8.ino handleButton(), BTN_DEBOUNCE_MS=30. This is
# stricter than counting N consecutive stable poll() samples: sample-counting
# can still get lucky and accept a short quiet gap *during* an ongoing bounce
# train, while a settle timer that resets on every single edge cannot commit
# until the bouncing has genuinely stopped for the whole window.
#
# Button debounce also structurally guarantees "must release before firing
# again": button_down only fires when the stable value transitions to
# pressed, which requires first passing back through a fully debounced
# "released" stable state - a bounce back to pressed for less than the debounce
# window never reaches "stable", so it can't re-fire early.
BTN_DEBOUNCE_S = 0.03
# A raw, undebounced 2ms-poll capture on real hardware (12.09.2026, see
# NOTES_FOR_PER.md) showed a perfectly clean signal - every click completed
# the full 4-state Gray cycle with zero bounce/reversal - but individual
# intermediate states lasted as little as ~2-3ms. The previous 5ms value
# required 5ms of *quiet* before accepting a reading, which a 2-3ms-lived
# state can never satisfy - it get silently dropped, which is what produced
# the "only half the Gray cycle observed" symptom, not a hardware fault.
# Since there's no real bounce to filter, this only needs to guard against
# an occasional I2C glitch, not genuine switch chatter.
ENC_DEBOUNCE_S = 0.001

# DETENT_STEPS only fixes double-firing on a full click - the boundary
# itself is still exactly 1-tick-sensitive no matter how big DETENT_STEPS
# is, so a real physical overshoot-and-settle-back right at the detent can
# immediately un-cross the boundary it just crossed, reporting the opposite
# direction a few ms later (a genuine live-usage report, not something the
# earlier 2ms raw capture would show - that was a deliberate slow single
# click, not release behavior at natural turning speed). Real distinct
# clicks are always >300ms apart in every capture in NOTES_FOR_PER.md, so a
# generous window here can't eat one; same-direction re-fires don't need
# this at all since DETENT_STEPS=4 already means one click = one report.
ROTATE_OPPOSITE_SUPPRESS_S = 0.03


class ButtonBox:
    def __init__(self, bus=BUS, address=SX1509_ADDR):
        self._bus = SMBus(bus)
        self._addr = address
        self._bus.write_byte_data(self._addr, REG_DIR_A, 0xFF)      # bank A all inputs (POR default anyway)
        self._bus.write_byte_data(self._addr, REG_PULLUP_A, 0x3F)   # pull-ups on I/O0-5

        now = time.monotonic()
        data = self._read_data_a()
        self._button_state = {n: bool(data & (1 << n)) for n in BUTTON_NAMES}  # debounced/stable
        self._button_raw = dict(self._button_state)
        self._button_raw_changed_at = {n: now for n in BUTTON_NAMES}

        enc_reading = ((data >> PIN_ENC_A) & 1) << 1 | ((data >> PIN_ENC_B) & 1)
        self._enc_state = (0, enc_reading, 0)  # (raw_ticks, stable reading, last_reported)
        self._enc_raw = enc_reading
        self._enc_raw_changed_at = now
        self._last_rotate_dir = None
        self._last_rotate_time = None

    def _read_data_a(self):
        return self._bus.read_byte_data(self._addr, REG_DATA_A)

    def poll(self):
        """Read current pin states, return a list of event dicts. Call regularly (e.g. every 5-10ms).
        Encoder states can be as short as ~2-3ms (see ENC_DEBOUNCE_S comment above), so a caller
        needing reliable rotation detection should poll this from a fast background thread instead
        of its own slower loop - see ThreadedPoller below, used by Software/main.py."""
        events = []
        now = time.monotonic()
        data = self._read_data_a()

        for num, name in BUTTON_NAMES.items():
            raw = bool(data & (1 << num))  # True = released (pulled up), False = pressed
            if raw != self._button_raw[num]:
                self._button_raw[num] = raw
                self._button_raw_changed_at[num] = now
            if now - self._button_raw_changed_at[num] < BTN_DEBOUNCE_S:
                continue  # still settling
            if raw == self._button_state[num]:
                continue  # stable value hasn't actually changed
            self._button_state[num] = raw
            events.append({"type": "button_up" if raw else "button_down", "name": name})

        raw_enc = ((data >> PIN_ENC_A) & 1) << 1 | ((data >> PIN_ENC_B) & 1)
        if raw_enc != self._enc_raw:
            self._enc_raw = raw_enc
            self._enc_raw_changed_at = now
        if now - self._enc_raw_changed_at >= ENC_DEBOUNCE_S and raw_enc != self._enc_state[1]:
            prev_reading = self._enc_state[1]
            self._enc_state, direction = decode_encoder_step(self._enc_state, raw_enc)
            print(f"[{now:.3f}] enc raw={data:#04x} pins {prev_reading:02b}->{raw_enc:02b} "
                  f"ticks={self._enc_state[0]} dir={direction}", flush=True)
            if direction:
                just_reversed = (self._last_rotate_time is not None
                                  and direction != self._last_rotate_dir
                                  and now - self._last_rotate_time < ROTATE_OPPOSITE_SUPPRESS_S)
                if not just_reversed:
                    events.append({"type": "rotate", "direction": direction})
                    self._last_rotate_dir = direction
                    self._last_rotate_time = now

        return events


# Encoder states can be as short as ~2-3ms (see ENC_DEBOUNCE_S comment above),
# so whatever calls poll() needs to do so well under that - too fast for
# Software/main.py's 10ms render-loop cadence, which also briefly blocks on
# actual rendering. This wraps any poll()-able object (ButtonBox, but also
# useful for PowerButton) with a background thread that polls it as fast as
# the I2C bus allows; the wrapped poll() just drains the queue the thread
# fills, decoupled from whatever the caller's own loop is busy with.
class ThreadedPoller:
    def __init__(self, target, interval=0.001):
        self._target = target
        self._events = queue.Queue()
        self._thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        self._thread.start()

    def _run(self, interval):
        while True:
            for event in self._target.poll():
                self._events.put(event)
            time.sleep(interval)

    def poll(self):
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events


def demo():
    """Self-check: init the expander and poll for 15s, printing events. Requires real hardware on the I2C bus."""
    box = ThreadedPoller(ButtonBox())
    print("Polling ButtonBox for 15s - press buttons / turn the knob now.")
    end = time.monotonic() + 15
    while time.monotonic() < end:
        for event in box.poll():
            print(event)
        time.sleep(0.02)  # just draining the queue here; the background thread does the real polling


if __name__ == "__main__":
    demo()
