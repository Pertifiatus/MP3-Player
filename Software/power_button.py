"""Power button (GPIO9) - short press blanks display/LEDs, ~5s hold shuts down.

GPIO9 is the same button-detect node the TPS63020 soft-latch hardware already
watches (see gpio9-pullup.service in CLAUDE.md) - reading it here too doesn't
interfere, it's just another input listener on an already pulled-up node.
Active-low: HIGH = released, LOW = pressed.
"""
import subprocess
import time

import board
import digitalio

SHUTDOWN_HOLD_S = 5.0


class PowerButton:
    def __init__(self, pin=board.D9):
        self._pin = digitalio.DigitalInOut(pin)
        self._pin.direction = digitalio.Direction.INPUT
        self._pin.pull = digitalio.Pull.UP
        self._pressed_since = None
        self._shutdown_fired = False

    def poll(self):
        """Call regularly (e.g. every main-loop iteration). Returns "short_press"
        on release before the hold threshold, or "shutdown" once when the hold
        threshold is crossed (fires exactly once per press, even if held longer)."""
        pressed = not self._pin.value
        now = time.monotonic()

        if pressed:
            if self._pressed_since is None:
                self._pressed_since = now
                self._shutdown_fired = False
            elif not self._shutdown_fired and now - self._pressed_since >= SHUTDOWN_HOLD_S:
                self._shutdown_fired = True
                return "shutdown"
            return None

        if self._pressed_since is None:
            return None  # already idle - nothing just changed, not a release edge

        fired = self._shutdown_fired
        self._pressed_since = None
        self._shutdown_fired = False
        return None if fired else "short_press"


def trigger_shutdown():
    """Needs a scoped NOPASSWD sudoers rule - plain `sudo systemctl poweroff`
    run from a script has no TTY to answer a password prompt on and would
    just hang forever. One-time setup on the Pi:

        echo 'pkenner ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff' \\
            | sudo tee /etc/sudoers.d/mp3player-poweroff
        sudo chmod 440 /etc/sudoers.d/mp3player-poweroff
        sudo visudo -c
    """
    subprocess.run(["sudo", "-n", "systemctl", "poweroff"], check=False)


def demo():
    """Self-check: poll for 30s, printing short_press/shutdown events. Tap the
    button for a short_press event, hold ~5s for a shutdown event (does NOT
    actually shut down here - trigger_shutdown() is only called from main.py)."""
    pb = PowerButton()
    print("Polling power button for 30s - tap or hold it now.")
    end = time.monotonic() + 30
    while time.monotonic() < end:
        event = pb.poll()
        if event:
            print(event)
        time.sleep(0.02)


if __name__ == "__main__":
    demo()
