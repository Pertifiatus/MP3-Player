"""Pure-logic self-check for ui_state.py - no hardware needed, runs anywhere.

python3 test_ui_state.py
"""
import os
import tempfile

from settings import Settings
import ui_state


def make_state():
    path = os.path.join(tempfile.gettempdir(), "test_settings.json")
    if os.path.exists(path):
        os.remove(path)
    return ui_state.UIState(Settings(path=path))


def test_home_navigation_wraps():
    s = make_state()
    n = len(s.home_items())
    assert s.home_sel == 0
    s.home_move(-1)
    assert s.home_sel == n - 1, "moving up from 0 should wrap to the last item"
    s.home_move(1)
    assert s.home_sel == 0


def test_home_open_library_and_back():
    s = make_state()
    s.home_sel = 0  # "Bibliothek" is always first
    s.home_open()
    assert s.screen == ui_state.SCREEN_LIBRARY
    s.back()
    assert s.screen == ui_state.SCREEN_HOME


def test_play_track_and_back_resets_now_playing():
    s = make_state()
    s.current_playlist_idx = 0
    s.playlist_sel = 0
    s.playlist_open()
    assert s.screen == ui_state.SCREEN_PLAYING
    assert s.now_playing is not None
    assert s.last_played == (0, 0)
    s.back()
    assert s.screen == ui_state.SCREEN_HOME
    assert s.now_playing is None, "Stop/back from Now-Playing should clear playback"


def test_now_playing_tick_advances_and_skips():
    s = make_state()
    s.current_playlist_idx = 0
    s.playlist_sel = 0
    s.playlist_open()
    np = s.now_playing
    dur = np.current()[2]
    np.position = dur - 0.001
    np._last_tick -= 1.0  # simulate 1s having passed
    np.tick()
    assert np.index == 1, "should have rolled over to the next track"
    assert np.position == 0.0


def test_now_playing_current_file_matches_library_files_shape():
    s = make_state()
    s.current_playlist_idx = 0
    s.playlist_sel = 0
    s.playlist_open()
    np = s.now_playing
    expected = ui_state.LIBRARY_FILES[np.playlist_idx][np.index]
    assert np.current_file() == expected
    # LIBRARY_FILES must be indexable exactly like LIBRARY (same playlist/track
    # shape) - a length mismatch here would raise IndexError instead of
    # silently returning the wrong track's file, so len() equality is the
    # actual property worth asserting, not just "some value came back".
    assert len(ui_state.LIBRARY_FILES) == len(ui_state.LIBRARY)
    assert len(ui_state.LIBRARY_FILES[np.playlist_idx]) == len(ui_state.LIBRARY[np.playlist_idx][1])


def test_encoder_mode_toggles_skip_volume():
    s = make_state()
    s.current_playlist_idx = 0
    s.playlist_sel = 0
    s.playlist_open()
    np = s.now_playing
    assert np.encoder_mode == ui_state.ENCODER_MODE_SKIP
    assert np.toggle_encoder_mode() == ui_state.ENCODER_MODE_VOLUME
    assert np.encoder_mode == ui_state.ENCODER_MODE_VOLUME
    assert np.toggle_encoder_mode() == ui_state.ENCODER_MODE_SKIP


def test_scrub_clamps_within_current_track_and_never_skips():
    s = make_state()
    s.current_playlist_idx = 0
    s.playlist_sel = 0
    s.playlist_open()
    np = s.now_playing
    dur = np.current()[2]
    start_index = np.index

    np.position = 1.0
    np.scrub(-1)  # would go negative without clamping
    assert np.position == 0.0
    assert np.index == start_index, "scrub must never roll over to another track"

    np.position = dur - 1.0
    np.scrub(1)  # would exceed the track's own duration without clamping
    assert np.position == dur
    assert np.index == start_index


def test_toggle_setting():
    s = make_state()
    before = s.settings.get("connectivity", "wifi")
    s.settings.set("connectivity", "wifi", not before)
    assert s.settings.get("connectivity", "wifi") == (not before)


def test_settings_navigation_and_activation():
    s = make_state()
    s.screen = ui_state.SCREEN_SETTINGS_ROOT
    s.settings_root_sel = 1  # "led"
    s.settings_root_open()
    assert s.settings_category == "led"
    assert s.screen == ui_state.SCREEN_SETTINGS_DETAIL

    items = ui_state.SETTINGS_ITEMS["led"]
    toggle_idx = next(i for i, it in enumerate(items) if it["key"] == "enabled")
    s.settings_detail_sel = toggle_idx
    before = s.settings.get("led", "enabled")
    s.settings_detail_activate()
    assert s.settings.get("led", "enabled") == (not before)

    s.back()
    assert s.screen == ui_state.SCREEN_SETTINGS_ROOT
    s.back()
    assert s.screen == ui_state.SCREEN_HOME


def test_stepper_wraps():
    s = make_state()
    s.settings.set("display", "brightness", 5)
    s.settings_category = "display"
    idx = next(i for i, it in enumerate(ui_state.SETTINGS_ITEMS["display"]) if it["key"] == "brightness")
    s.settings_detail_sel = idx
    s.settings_detail_activate()
    assert s.settings.get("display", "brightness") == 1, "stepper should wrap from max back to min"


def test_choice_cycles():
    s = make_state()
    s.settings.set("led", "mode", "static")
    s.settings_category = "led"
    idx = next(i for i, it in enumerate(ui_state.SETTINGS_ITEMS["led"]) if it["key"] == "mode")
    s.settings_detail_sel = idx
    s.settings_detail_activate()
    assert s.settings.get("led", "mode") == "battery"
    s.settings_detail_activate()
    assert s.settings.get("led", "mode") == "static"


def test_wifi_scan_done_keeps_selection_on_same_ssid_across_a_rescan():
    # main.py periodically re-triggers wifi_scan() while the user just sits on
    # the list (WIFI_RESCAN_INTERVAL) - the list can reorder or gain/lose
    # entries between rescans, so the highlighted network must track the SSID
    # the user was actually on, not the raw index.
    s = make_state()
    s.start_wifi_scan()
    s.wifi_scan_done([
        {"ssid": "Alpha", "signal": 50, "secured": False},
        {"ssid": "Bravo", "signal": 90, "secured": True},
    ])
    s.wifi_scan_sel = 1  # "Bravo"

    # a rescan reorders (Bravo's signal dropped) and adds a new, stronger network
    s.wifi_scan_done([
        {"ssid": "Charlie", "signal": 95, "secured": True},
        {"ssid": "Bravo", "signal": 40, "secured": True},
        {"ssid": "Alpha", "signal": 50, "secured": False},
    ])
    assert s.wifi_scan_networks[s.wifi_scan_sel]["ssid"] == "Bravo"

    # Bravo disappears entirely -> falls back to the top of the list, not a crash
    s.wifi_scan_done([{"ssid": "Alpha", "signal": 50, "secured": False}])
    assert s.wifi_scan_sel == 0


def test_wifi_password_wheel_compose_and_backspace():
    s = make_state()
    s.start_wifi_password_entry("Cafe WLAN")
    assert s.screen == ui_state.SCREEN_WIFI_PASSWORD

    s.wifi_password_rotate(-1)  # wrap backwards from index 0 to the last char
    assert s.wifi_password_char_idx == len(ui_state.WIFI_CHARSET) - 1
    s.wifi_password_rotate(1)
    assert s.wifi_password_char_idx == 0

    for _ in range(ui_state.WIFI_CHARSET.index("h")):
        s.wifi_password_rotate(1)
    s.wifi_password_confirm_char()
    assert s.wifi_password_text() == "h"
    assert s.wifi_password_char_idx == 0, "wheel resets to the start for the next character"

    s.wifi_password_backspace()
    assert s.wifi_password_text() == ""
    s.wifi_password_backspace()  # backspacing an empty password must not raise
    assert s.wifi_password_text() == ""


def test_wifi_password_submit_returns_ssid_and_password():
    s = make_state()
    s.start_wifi_password_entry("Cafe WLAN")
    s.wifi_password_chars = list("hunter2")
    ssid, password = s.wifi_password_submit()
    assert (ssid, password) == ("Cafe WLAN", "hunter2")
    assert s.wifi_connect_status == "connecting"


def test_wifi_password_submit_blocks_while_already_connecting_but_allows_retry_after_error():
    # Regression: pressing Play/Pause repeatedly while a connect attempt was
    # still in flight (or after it failed silently, before render_wifi_password
    # showed any feedback for that) looked like the button did nothing -
    # confirmed live. A second submit while "connecting" must no-op...
    s = make_state()
    s.start_wifi_password_entry("Cafe WLAN")
    s.wifi_password_chars = list("hunter2")
    assert s.wifi_password_submit() == ("Cafe WLAN", "hunter2")
    assert s.wifi_password_submit() is None, "must not resubmit while a connect is already in flight"

    # ...but once that attempt reports an error, a retry must work again.
    s.wifi_connect_done(False, "Verbindung fehlgeschlagen")
    assert s.wifi_connect_status == "error"
    assert s.wifi_password_submit() == ("Cafe WLAN", "hunter2")


def test_wifi_password_wheel_ignores_input_while_connecting_or_error():
    # Rotating/confirming/backspacing while the "Verbinde..."/error feedback is
    # on screen (not the letter wheel) would silently mutate a password the
    # user can't see being edited - guard against that class of surprise.
    s = make_state()
    s.start_wifi_password_entry("Cafe WLAN")
    s.wifi_password_chars = list("ab")
    s.wifi_password_submit()  # -> "connecting"

    s.wifi_password_rotate(1)
    s.wifi_password_confirm_char()
    s.wifi_password_backspace()
    assert s.wifi_password_text() == "ab", "wheel input must be ignored while connecting"

    s.wifi_connect_done(False, "Verbindung fehlgeschlagen")
    s.wifi_password_confirm_char()
    assert s.wifi_password_text() == "ab", "wheel input must be ignored on the error screen too"


def test_playlist_manage_exclude_toggles():
    s = make_state()
    s.start_playlist_manage()
    name = ui_state.LIBRARY[s.playlist_manage_sel][0]
    s.playlist_manage_open()
    assert not s.playlist_manage_is_excluded()
    s.playlist_manage_detail_select()  # row 0 ("exclude") - toggles on
    assert s.playlist_manage_is_excluded()
    assert name in s.settings.get("sync", "excluded_playlists")
    s.playlist_manage_detail_select()  # toggles back off
    assert not s.playlist_manage_is_excluded()
    assert name not in s.settings.get("sync", "excluded_playlists")


def test_playlist_manage_delete_requires_confirmation():
    # Only exercises the confirm-arming step, not an actual delete -
    # sync_youtube.delete_playlist() touches real paths on disk (MUSIC_DIR/
    # library.json next to sync_youtube.py, not a tmp path), which isn't safe
    # to run from a unit test.
    s = make_state()
    s.start_playlist_manage()
    s.playlist_manage_open()
    s.playlist_manage_detail_move(1)  # row 1 = "delete"
    assert s.playlist_manage_detail_items()[s.playlist_manage_detail_sel]["key"] == "delete"
    assert not s.playlist_manage_confirm_delete
    s.playlist_manage_detail_select()  # first press only arms confirmation
    assert s.playlist_manage_confirm_delete
    assert s.screen == ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL, "must not navigate away without a second press"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests passed")
