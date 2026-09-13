"""Persistent settings model, JSON file on disk next to this script."""
import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULTS = {
    "display": {
        "brightness": 3,     # 1-5, drives GC9A01 backlight PWM (GPIO13)
        "auto_sleep_s": 30,  # 0 = never sleep
        "ui_scale": 3,       # 1-5, index into ui_render.UI_SCALE_STEPS
    },
    "led": {
        "enabled": True,
        "mode": "static",     # off / static / battery, see led_control.py
        "color_index": 1,     # index into led_control.COLOR_PRESETS
        "brightness": 3,      # 1-5
    },
    "connectivity": {
        "wifi": True,
        "bluetooth": True,
        "audio_output": "bluetooth",  # bluetooth / jack
        "volume": 70,  # 0-100, encoder volume-mode on the Playing screen
    },
    "sync": {
        "auto_sync_on_charge": False,
        "account_linked": False,
        "excluded_playlists": [],  # playlist names sync_library() skips entirely
    },
    "motion": {
        "auto_display_switch": True,
        "shake_to_shuffle": True,
        "flip_to_pause": True,
    },
}


class Settings:
    def __init__(self, path=SETTINGS_PATH):
        self._path = path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    loaded = json.load(f)
                return {k: {**v, **loaded.get(k, {})} for k, v in DEFAULTS.items()}
            except (json.JSONDecodeError, OSError):
                pass
        return {k: dict(v) for k, v in DEFAULTS.items()}

    def save(self):
        with open(self._path, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, category, key):
        return self.data[category][key]

    def set(self, category, key, value):
        self.data[category][key] = value
        self.save()
