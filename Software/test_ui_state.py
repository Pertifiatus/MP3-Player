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


def test_quick_connect_release_before_threshold_cancels():
    s = make_state()
    s.quick_connect_press()
    assert s.qc_active and s.qc_phase == "hold"
    s.quick_connect_release()
    assert not s.qc_active
    assert s.qc_phase is None


def test_quick_connect_threshold_without_known_device_fails_fast():
    s = make_state()
    s.settings.set("connectivity", "last_bt_device", None)
    s.last_played = (0, 0)  # a song exists, but no device - should still fail
    s.quick_connect_press()
    s._qc_started_at -= ui_state.QUICK_CONNECT_HOLD_S  # simulate the full hold elapsing
    assert s.quick_connect_tick() is True
    mac = s.quick_connect_start()
    assert mac is None
    assert s.qc_phase == "error"
    assert s.qc_error == "Kein Gerät"


def test_quick_connect_threshold_without_last_played_fails_fast():
    s = make_state()
    s.settings.set("connectivity", "last_bt_device", "AA:BB:CC:DD:EE:FF")
    s.last_played = None
    s.quick_connect_press()
    s._qc_started_at -= ui_state.QUICK_CONNECT_HOLD_S
    s.quick_connect_tick()
    mac = s.quick_connect_start()
    assert mac is None
    assert s.qc_error == "Kein Song"


def test_quick_connect_success_resumes_last_played_track():
    s = make_state()
    s.settings.set("connectivity", "last_bt_device", "AA:BB:CC:DD:EE:FF")
    s.last_played = (0, 1)
    s.quick_connect_press()
    s._qc_started_at -= ui_state.QUICK_CONNECT_HOLD_S
    s.quick_connect_tick()
    mac = s.quick_connect_start()
    assert mac == "AA:BB:CC:DD:EE:FF"
    assert s.qc_phase == "connecting"

    s.quick_connect_done(True)
    assert s.screen == ui_state.SCREEN_PLAYING
    assert (s.now_playing.playlist_idx, s.now_playing.index) == (0, 1)
    assert not s.qc_active


def test_quick_connect_failure_shows_error_then_auto_dismisses():
    s = make_state()
    s.settings.set("connectivity", "last_bt_device", "AA:BB:CC:DD:EE:FF")
    s.last_played = (0, 0)
    s.quick_connect_press()
    s._qc_started_at -= ui_state.QUICK_CONNECT_HOLD_S
    s.quick_connect_tick()
    s.quick_connect_start()

    s.quick_connect_done(False, "Verbindung fehlgeschlagen")
    assert s.qc_active and s.qc_phase == "error"
    assert s.qc_error == "Verbindung fehlgeschlagen"
    assert s.quick_connect_error_tick() is False, "must not dismiss before QUICK_CONNECT_ERROR_S elapses"

    s._qc_error_at -= ui_state.QUICK_CONNECT_ERROR_S
    assert s.quick_connect_error_tick() is True
    assert not s.qc_active
    assert s.qc_phase is None


def test_last_played_survives_a_simulated_reboot():
    path = os.path.join(tempfile.gettempdir(), "test_settings_reboot.json")
    if os.path.exists(path):
        os.remove(path)

    s1 = ui_state.UIState(Settings(path=path))
    s1.current_playlist_idx = 0
    s1.playlist_sel = 1
    s1.playlist_open()
    assert s1.last_played == (0, 1)

    # New UIState + Settings instance against the same file, as a fresh
    # process after a reboot would create - last_played must still be there.
    s2 = ui_state.UIState(Settings(path=path))
    assert s2.last_played == (0, 1)


def test_last_played_out_of_range_after_resync_is_ignored():
    path = os.path.join(tempfile.gettempdir(), "test_settings_stale.json")
    if os.path.exists(path):
        os.remove(path)

    settings = Settings(path=path)
    # simulate a value left over from before a re-sync shrank the library -
    # an index this far out of bounds can't come from a real playlist_open()
    settings.set("playback", "last_played", [0, 999999])
    s = ui_state.UIState(settings)
    assert s.last_played is None, "an out-of-range stored index must not crash home_items()/home_open()"


def test_note_now_playing_tracks_manual_skip():
    # Real bug: last_played was only ever set once, in playlist_open() - so
    # Home's "Fortsetzen" tile (and Quick Connect's resume) kept pointing at
    # whichever track was first tapped, forever, even after the user skipped
    # forward. PlaybackSync.sync() (main.py) calls note_now_playing() every
    # tick to fix this - this test drives that same method directly.
    s = make_state()
    s.current_playlist_idx = 0
    s.playlist_sel = 0
    s.playlist_open()
    assert s.last_played == (0, 0)

    s.now_playing.skip(1)
    assert s.last_played == (0, 0), "not updated yet - note_now_playing() hasn't run this tick"
    s.note_now_playing()
    assert s.last_played == (0, 1), "should now follow the skipped-to track, not the first one played"


def test_note_now_playing_tracks_auto_advance_at_track_end():
    s = make_state()
    s.current_playlist_idx = 0
    s.playlist_sel = 0
    s.playlist_open()
    np = s.now_playing
    dur = np.current()[2]
    np.position = dur - 0.001
    np._last_tick -= 1.0  # simulate 1s having passed
    np.tick()  # rolls over to track 1 on its own, same as PlaybackSync.sync() would on mpv idle
    assert np.index == 1

    s.note_now_playing()
    assert s.last_played == (0, 1), "auto-advance must update last_played too, not just manual selection"


def test_note_now_playing_is_a_noop_with_nothing_playing():
    s = make_state()
    assert s.now_playing is None
    s.note_now_playing()  # must not raise just because nothing is playing
    assert s.last_played is None


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests passed")
