"""SK6812 addressable LED control (GPIO12 / PWM0_0).

Chain length assumption: 6 LEDs on the main board (LED1-6) + 3 on the ButtonBox
(LED1-3) = 9, daisy-chained on one GPIO12 data line. NOT yet verified against the
PCB - see NOTES_FOR_PER.md. Adjust NUM_LEDS once confirmed.

Needs root (sudo) to run - the underlying rpi_ws281x library uses PWM+DMA which
requires direct hardware access. Run this module (or anything importing it) with
sudo, or set up a small systemd service running as root for the real player.
"""
import time

import board
import neopixel

NUM_LEDS = 9
PIN = board.D12

MODE_OFF = "off"
MODE_STATIC = "static"
MODE_BATTERY = "battery"

# ponytail: a handful of curated presets instead of a full HSV colour-wheel UI -
# picking an exact hue via 3 buttons + a knob is fiddly on a tiny screen, a preset
# cycle (stepper in Settings) is much faster to use. Add more here if needed.
COLOR_PRESETS = [
    (255, 255, 255),  # weiss
    (51, 225, 176),  # accent-tuerkis (passend zur UI)
    (255, 97, 87),  # rot
    (47, 140, 255),  # blau
    (255, 176, 32),  # orange
    (139, 124, 246),  # violett
]


class LEDController:
    def __init__(self, num_leds=NUM_LEDS, pin=PIN):
        self._pixels = neopixel.NeoPixel(pin, num_leds, brightness=1.0, auto_write=False)
        self.mode = MODE_OFF
        self.color = COLOR_PRESETS[0]
        self.brightness = 3  # 1-5 stepper, matches display brightness UX

    def _apply_brightness(self, rgb):
        scale = self.brightness / 5.0
        return tuple(int(c * scale) for c in rgb)

    def refresh(self, battery_pct=None):
        """Push the current mode/color/brightness to the strip. Call after any change,
        and periodically (e.g. once/sec) while mode == MODE_BATTERY so the indicator
        tracks the live charge level."""
        if self.mode == MODE_OFF:
            self._pixels.fill((0, 0, 0))
        elif self.mode == MODE_STATIC:
            self._pixels.fill(self._apply_brightness(self.color))
        elif self.mode == MODE_BATTERY:
            pct = battery_pct if battery_pct is not None else 0
            lit = round(NUM_LEDS * pct / 100)
            color = (0, 200, 90) if pct > 20 else (220, 60, 40)
            color = self._apply_brightness(color)
            for i in range(NUM_LEDS):
                self._pixels[i] = color if i < lit else (0, 0, 0)
        self._pixels.show()

    def off(self):
        self.mode = MODE_OFF
        self.refresh()

    def flash_indicator(self, index, rgb, duration, fps=30):
        """Fade a single LED in and out (triangle envelope) over `duration`
        seconds, leaving every other LED untouched - used for the brief
        skip/volume mode-change cue on the encoder knob (see main.py). Blocks
        the caller for `duration`; led_service.py's poll loop is fine pausing
        here since it isn't doing anything else time-critical meanwhile.
        Restores `index` to whatever the current mode/color/brightness would
        show there afterward, via the normal refresh() path."""
        steps = max(6, round(duration * fps))
        for i in range(steps):
            t = i / (steps - 1)
            level = t * 2 if t < 0.5 else (1 - t) * 2  # up then down
            self._pixels[index] = tuple(round(c * level) for c in self._apply_brightness(rgb))
            self._pixels.show()
            time.sleep(duration / steps)
        self.refresh()


def demo():
    """Self-check: cycle through the presets for a few seconds each. Requires real
    hardware and root (sudo python3 led_control.py)."""
    leds = LEDController()
    leds.mode = MODE_STATIC
    for color in COLOR_PRESETS:
        leds.color = color
        leds.refresh()
        print(f"color={color}")
        time.sleep(2)
    leds.off()


if __name__ == "__main__":
    demo()
