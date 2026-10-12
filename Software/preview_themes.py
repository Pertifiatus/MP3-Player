"""Contact sheet of every screen in every design - look at designs without the Pi.

    python3 preview_themes.py              # all designs -> previews/<design>.png
    python3 preview_themes.py y2k bento    # just these
    python3 preview_themes.py --bench      # median render ms per design (run it on the Pi too)

Each tile is one rendered 240x240 frame seen through the round bezel, so
anything clipped by the bezel shows up as clipped here too.
"""
import os
import statistics
import sys
import tempfile
import time

from PIL import Image, ImageDraw

import themes
import ui_render
import ui_state
from settings import Settings

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "previews")
W = ui_render.W


def _state(theme):
    path = os.path.join(tempfile.gettempdir(), f"preview_settings_{theme}.json")
    if os.path.exists(path):
        os.remove(path)
    s = ui_state.UIState(Settings(path=path))
    s.settings.set("display", "theme", theme)
    s.settings.set("display", "status_ring", "always")
    s.battery_pct, s.battery_eta_min, s.wifi_connected = 73, 190, True
    s.last_played = (0, 1)
    return s


def states(theme):
    """(label, state) for every screen/state worth looking at. Yields the SAME
    state object mutated step by step - render it before asking for the next."""
    s = _state(theme)
    yield "Home", s
    s.home_sel = 1
    yield "Home: Fortsetzen", s
    s.home_sel = 0
    s.screen, s.library_sel = ui_state.SCREEN_LIBRARY, 1
    yield "Bibliothek", s
    s.library_open()
    s.playlist_sel = 2
    yield "Playlist", s
    s.playlist_open()
    s.now_playing.position = 75.0
    yield "Now Playing", s
    s.now_playing.playing, s.shuffle = False, True
    yield "Pause + Shuffle", s
    s.back()
    s.shuffle = False
    s.screen, s.settings_root_sel = ui_state.SCREEN_SETTINGS_ROOT, 2
    yield "Einstellungen", s
    for cat, sel in (("display", 0), ("led", 3), ("sync", 0)):
        s.screen, s.settings_category, s.settings_detail_sel = ui_state.SCREEN_SETTINGS_DETAIL, cat, sel
        yield f"Settings: {cat}", s
    s.screen = ui_state.SCREEN_SYNC_LOGIN
    s.sync_login_info = {"verification_url": "https://www.google.com/device", "user_code": "WXYZ-4321"}
    yield "YouTube koppeln", s
    s.sync_login_info = None
    s.start_sync_now()
    s.sync_progress_callback(6, 10, "Blinding Lights")
    yield "Sync 6/10", s
    s.sync_progress_callback(10, 10, "")
    yield "Sync fertig", s
    s.start_bt_menu()
    s.bt_known_devices = [{"mac": "AA:BB:CC:DD:EE:FF", "name": "Sony WH-1000XM4", "connected": True},
                          {"mac": "11:22:33:44:55:66", "name": "JBL Flip 5", "connected": False}]
    s.bt_menu_sel = 1
    yield "Bluetooth", s
    s.start_bt_pairing()
    yield "BT: Suche", s
    s.bt_pair_status, s.bt_pair_error = "error", "Gerät hat die Verbindung abgelehnt"
    yield "BT: Fehler", s
    s.start_wifi_menu()
    s.wifi_known_networks = [{"name": "Heim", "ssid": "TILTEDTOWERS", "connected": True}]
    s.wifi_menu_sel = 2
    yield "WLAN", s
    s.start_wifi_scan()
    s.wifi_scan_done([{"ssid": "TILTEDTOWERS", "signal": 80, "secured": True},
                      {"ssid": "Cafe Kleiner Hunger", "signal": 50, "secured": False},
                      {"ssid": "FRITZ!Box 7590 XY", "signal": 30, "secured": True}])
    s.wifi_scan_sel = 1
    yield "WLAN-Liste", s
    s.start_wifi_password_entry("FRITZ!Box 7590 XY")
    s.wifi_password_chars, s.wifi_password_char_idx = list("hunter2"), 12
    yield "WLAN-Passwort", s
    s.start_playlist_manage()
    s.playlist_manage_sel = 1
    yield "Playlists verwalten", s
    s.playlist_manage_open()
    s.playlist_manage_detail_sel, s.playlist_manage_confirm_delete = 1, True
    yield "Loeschen?", s
    s.screen = ui_state.SCREEN_HOME
    s.qc_active, s.qc_phase, s.qc_progress = True, "hold", 0.6
    yield "Quick Connect", s
    s.qc_phase, s.qc_error, s.qc_progress = "error", "Kein Gerät", 1.0
    yield "QC Fehler", s
    s.qc_active, s.qc_phase = False, None


def render_settled(s):
    """Render; if the design is mid-animation (Pixelhaus camera), jump its clock
    past the flight and render the resting frame instead."""
    theme = themes.get(s.settings.get("display", "theme"))
    img = ui_render.render(s)
    if ui_render.animating(s) and hasattr(theme, "_clock"):
        real = theme._clock
        theme._clock = lambda: real() + 10.0
        try:
            img = ui_render.render(s)
        finally:
            theme._clock = real
    return img


def _tile(img, label):
    tile = Image.new("RGB", (W + 10, W + 30), (24, 24, 28))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, W - 1, W - 1], fill=255)
    tile.paste(img, (5, 5), mask)
    ImageDraw.Draw(tile).text((8, W + 10), label, fill=(220, 220, 220))
    return tile


def sheet(theme):
    tiles = [_tile(render_settled(s), label) for label, s in states(theme)]
    s = _state(theme)
    tiles.append(_tile(ui_render.render_shutdown(s), "Ausschalten"))
    cols = 6
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].size
    out = Image.new("RGB", (cols * tw, rows * th), (12, 12, 14))
    for i, t in enumerate(tiles):
        out.paste(t, ((i % cols) * tw, (i // cols) * th))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{theme}.png")
    out.save(path)
    return path


def bench(theme):
    """(slowest screen label, its median ms, Now-Playing median ms) - 5 renders each."""
    worst, playing = ("", 0.0), 0.0
    for label, s in states(theme):
        render_settled(s)  # warm caches/assets first, like a running device
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            ui_render.render(s)
            times.append((time.perf_counter() - t0) * 1000)
        med = statistics.median(times)
        if med > worst[1]:
            worst = (label, med)
        if label == "Now Playing":
            playing = med
    return worst[0], worst[1], playing


if __name__ == "__main__":
    args = sys.argv[1:]
    do_bench = "--bench" in args
    names = [a for a in args if a != "--bench"] or list(themes.THEMES)
    for name in names:
        if do_bench:
            label, ms, playing = bench(name)
            print(f"{name:10s} slowest {ms:6.1f} ms ({label}), Now Playing {playing:6.1f} ms")
        else:
            print(sheet(name))
