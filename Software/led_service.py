"""Standalone LED service - watches settings.json and drives the SK6812 strip.

Runs SEPARATELY from main.py (which stays a normal user process for the display/
buttons/IMU) because neopixel/rpi_ws281x needs PWM+DMA hardware access, which
needs root. Run this with sudo (or set up a systemd unit that runs as root):

    sudo python3 led_service.py

main.py never touches the LEDs directly - it only writes to settings.json (via
Settings.set()), and this service picks up the change within POLL_INTERVAL_S.

Also handles one-shot "indicator" flashes (see main.py's encoder-knob skip/
volume mode toggle on the Playing screen): main.py writes
settings["led"]["indicator"] = {"color": [r,g,b], "duration": s, "ts": <time.time()>}
and this service runs LEDController.flash_indicator() once per distinct `ts`
it sees. POLL_INTERVAL_S is short specifically so that cue feels immediate
rather than laggy - the file read itself is cheap either way.
"""
import time

from led_control import LEDController, COLOR_PRESETS, MODE_OFF, MODE_STATIC, MODE_BATTERY
from max17048 import MAX17048
from settings import Settings

POLL_INTERVAL_S = 0.1

_gauge = MAX17048()


def read_battery_pct():
    """Reads SOC from the MAX17048 fuel gauge. Returns None on I2C failure, battery mode
    then falls back to a dim static accent color so it's at least visibly "on" instead of
    silently doing nothing."""
    try:
        return _gauge.read_soc_pct()
    except OSError:
        return None


# "5th LED" of the 6 on the main board (see led_control.py's chain-layout
# comment) - the one main.py flashes for the skip/volume mode cue.
INDICATOR_LED_INDEX = 4


def main():
    leds = LEDController()
    last_state = None
    last_indicator_ts = None

    while True:
        settings = Settings()  # cheap: just re-reads the small JSON file
        led = settings.data["led"]
        state = (led["enabled"], led["mode"], led["color_index"], led["brightness"])

        if state != last_state:
            last_state = state
            leds.brightness = led["brightness"]
            if not led["enabled"]:
                leds.mode = MODE_OFF
            elif led["mode"] == "battery":
                leds.mode = MODE_BATTERY
            else:
                leds.mode = MODE_STATIC
                leds.color = COLOR_PRESETS[led["color_index"]]

        battery_pct = read_battery_pct() if leds.mode == MODE_BATTERY else None
        if leds.mode == MODE_BATTERY and battery_pct is None:
            leds.mode = MODE_STATIC
            leds.color = (40, 40, 40)  # dim grey: "on but no battery data yet"

        leds.refresh(battery_pct=battery_pct)

        indicator = led.get("indicator")
        if indicator and indicator["ts"] != last_indicator_ts:
            last_indicator_ts = indicator["ts"]
            leds.flash_indicator(INDICATOR_LED_INDEX, tuple(indicator["color"]), indicator["duration"])

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
