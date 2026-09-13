"""Adaptive charge-current controller - standalone poller, same shape as led_service.py.

Slows charging in the low-SOC and high-SOC bands (gentler on the cell near empty/full),
runs the normal rate in the middle. Only rewrites RT9466's ICHG register when the target
band actually changes, so it doesn't hammer the I2C bus every poll.

Run standalone (would get its own systemd unit like gpio16-hold.service, see CLAUDE.md):
    python3 charge_control.py
"""
import time

from max17048 import MAX17048
from rt9466 import RT9466

POLL_INTERVAL_S = 30

SLOW_MA = 600     # SOC 0-20% and 80-100% - 3000mAh cell, ~0.2C
NORMAL_MA = 1500  # SOC 20-80% - ~0.5C


def band_current_ma(soc_pct):
    if soc_pct < 20 or soc_pct > 80:
        return SLOW_MA
    return NORMAL_MA


def main():
    gauge = MAX17048()
    charger = RT9466()
    last_target = NORMAL_MA
    charger.configure(charge_current_ma=last_target)

    while True:
        soc = gauge.read_soc_pct()
        target = band_current_ma(soc)
        if target != last_target:
            charger.set_charge_current(target)
            last_target = target
            print(f"SOC={soc:.1f}% -> charge current {target}mA")
        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
