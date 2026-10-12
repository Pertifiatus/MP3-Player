"""Smoke test for ui_render.py - no hardware needed. Renders every screen at
every ui_scale step and checks nothing raises and every frame comes back as a
full 240x240 image. Off-device (no DejaVu fonts installed), ui_render._font
falls back to PIL's bundled default font, so pixel geometry isn't exact here,
but this still catches crashes and layout math errors (negative sizes, bad
truncation, etc.) from a normal dev machine.

python3 test_ui_render.py
"""
import os
import tempfile

from settings import Settings
import ui_render
import ui_state
import themes
import ui_common
from themes import klassik
from ui_views import (CodeView, Item, ListView, MessageView, PasswordView, PlayingView, ProgressView,
                      QuickConnectView, RenderCtx, SettingRow, SettingsView, StatusView)


def make_state():
    path = os.path.join(tempfile.gettempdir(), "test_settings_render.json")
    if os.path.exists(path):
        os.remove(path)
    return ui_state.UIState(Settings(path=path))


def _assert_frame(img):
    assert img.size == (ui_render.W, ui_render.W)


def _walk_all_screens(s):
    """Renders every screen/state once - shared by the per-design/per-scale loops below."""
    _assert_frame(ui_render.render(s))  # home

    s.screen = ui_state.SCREEN_LIBRARY
    _assert_frame(ui_render.render(s))

    s.library_sel = 1  # "Techno Mix" - longest track list, exercises row cutoff
    s.library_open()
    _assert_frame(ui_render.render(s))

    s.playlist_sel = 0
    s.playlist_open()
    _assert_frame(ui_render.render(s))  # now playing

    s.screen = ui_state.SCREEN_SETTINGS_ROOT
    _assert_frame(ui_render.render(s))

    for cat, items in ui_state.SETTINGS_ITEMS.items():
        s.settings_category = cat
        s.screen = ui_state.SCREEN_SETTINGS_DETAIL
        for i in range(len(items)):
            s.settings_detail_sel = i
            _assert_frame(ui_render.render(s))

    s.screen = ui_state.SCREEN_SYNC_LOGIN
    _assert_frame(ui_render.render(s))  # "Verbinde..." (no info yet)
    s.sync_login_info = {"verification_url": "https://youtube.com/activate", "user_code": "ABCD-1234"}
    _assert_frame(ui_render.render(s))
    s.sync_login_info = None
    s.sync_login_error = "Ein sehr langer Fehlertext der auf mehrere Zeilen umgebrochen werden sollte"
    _assert_frame(ui_render.render(s))

    s.sync_login_error = None
    s.screen = ui_state.SCREEN_SYNC_PROGRESS
    s.sync_progress = (3, 10, "Some Track Name")
    _assert_frame(ui_render.render(s))
    s.sync_progress = (10, 10, "")
    _assert_frame(ui_render.render(s))

    s.start_bt_menu()
    _assert_frame(ui_render.render(s))  # toggle + "Neue Geraete koppeln" only, no known devices yet
    s.bt_known_devices = [
        {"mac": "AA:BB:CC:DD:EE:FF", "name": "Sony WH-1000XM4", "connected": True},
        {"mac": "11:22:33:44:55:66", "name": "", "connected": False},
    ]
    for i in range(len(s.bt_menu_items())):
        s.bt_menu_sel = i
        _assert_frame(ui_render.render(s))

    s.bt_menu_sel = 1  # the connected device
    s.bt_menu_open()
    assert s.screen == ui_state.SCREEN_BT_DEVICE
    for i in range(len(s.bt_device_items())):
        s.bt_device_sel = i
        _assert_frame(ui_render.render(s))
    s.bt_device_sel = 0
    action = s.bt_device_select()
    assert action == ("disconnect", "AA:BB:CC:DD:EE:FF")
    _assert_frame(ui_render.render(s))  # "Bitte warten..."
    s.bt_device_action_done(True)
    assert s.screen == ui_state.SCREEN_BT_MENU  # success returns to the menu
    s.screen = ui_state.SCREEN_BT_DEVICE  # re-enter to exercise the error branch too
    s.bt_action_status = "working"
    s.bt_device_action_done(False, "Trennen fehlgeschlagen")
    _assert_frame(ui_render.render(s))  # error, still on SCREEN_BT_DEVICE

    s.start_bt_pairing()
    _assert_frame(ui_render.render(s))  # "Suche Geraete..."
    s.bt_scan_done([])
    _assert_frame(ui_render.render(s))  # "Keine Geraete gefunden"
    s.bt_scan_done([
        {"mac": "AA:BB:CC:DD:EE:FF", "name": "Sony WH-1000XM4", "paired": False},
        {"mac": "11:22:33:44:55:66", "name": "", "paired": True},
    ])
    for i in range(2):
        s.bt_scan_sel = i
        _assert_frame(ui_render.render(s))
    s.bt_scan_sel = 0
    mac = s.bt_scan_select()
    assert mac == "AA:BB:CC:DD:EE:FF"
    _assert_frame(ui_render.render(s))  # "Verbinde..."
    s.bt_pair_done(True)
    _assert_frame(ui_render.render(s))  # "Verbunden!"
    s.bt_pair_done(False, "Verbindung fehlgeschlagen")
    _assert_frame(ui_render.render(s))  # error

    s.start_wifi_menu()
    _assert_frame(ui_render.render(s))  # toggle + "Neues WLAN verbinden" only, no known networks yet
    s.wifi_known_networks = [
        # profile name deliberately differs from the SSID here, like this
        # project's own cloud-init/netplan-created profile does on the real
        # Pi - exercises that wifi_device_select() uses "name", not "ssid".
        {"name": "netplan-wlan0-Heimnetz", "ssid": "Heimnetz", "connected": True},
        {"name": "Cafe WLAN", "ssid": "Cafe WLAN", "connected": False},
    ]
    for i in range(len(s.wifi_menu_items())):
        s.wifi_menu_sel = i
        _assert_frame(ui_render.render(s))

    # index by kind rather than a hardcoded position - wifi_menu_items() has
    # grown a "wake" entry between the toggle and the network list since this
    # was first written, which silently shifted every fixed index after it.
    s.wifi_menu_sel = next(i for i, it in enumerate(s.wifi_menu_items())
                            if it["kind"] == "network" and it["connected"])
    s.wifi_menu_open()
    assert s.screen == ui_state.SCREEN_WIFI_DEVICE
    for i in range(len(s.wifi_device_items())):
        s.wifi_device_sel = i
        _assert_frame(ui_render.render(s))
    s.wifi_device_sel = 0
    action = s.wifi_device_select()
    assert action == ("disconnect", "netplan-wlan0-Heimnetz")
    _assert_frame(ui_render.render(s))  # "Bitte warten..."
    s.wifi_device_action_done(True)
    assert s.screen == ui_state.SCREEN_WIFI_MENU  # success returns to the menu
    s.screen = ui_state.SCREEN_WIFI_DEVICE  # re-enter to exercise the error branch too
    s.wifi_action_status = "working"
    s.wifi_device_action_done(False, "Trennen fehlgeschlagen")
    _assert_frame(ui_render.render(s))  # error, still on SCREEN_WIFI_DEVICE

    s.start_wifi_scan()
    # refresh_wifi_menu() above re-fetched wifi_known_networks from the real
    # (hardware-only) nmcli call, wiping the fixture set earlier - restore it
    # so the "already known" scan-select branch below is actually exercised.
    s.wifi_known_networks = [{"name": "netplan-wlan0-Heimnetz", "ssid": "Heimnetz", "connected": True}]
    _assert_frame(ui_render.render(s))  # "Suche Netzwerke..."
    s.wifi_scan_done([])
    _assert_frame(ui_render.render(s))  # "Keine Netzwerke gefunden"
    s.wifi_scan_done([
        {"ssid": "Heimnetz", "signal": 80, "secured": True},   # secured but already known -> direct connect
        {"ssid": "Cafe Open", "signal": 50, "secured": False},  # unsecured -> direct connect
        {"ssid": "New Secured", "signal": 30, "secured": True},  # secured + unknown -> password entry
    ])
    for i in range(3):
        s.wifi_scan_sel = i
        _assert_frame(ui_render.render(s))

    s.wifi_scan_sel = 0
    result = s.wifi_scan_select()
    assert result == ("Heimnetz", None)
    _assert_frame(ui_render.render(s))  # "Verbinde..."
    s.wifi_connect_done(False, "Verbindung fehlgeschlagen")
    _assert_frame(ui_render.render(s))  # error

    s.wifi_scan_sel = 2
    s.wifi_connect_status = None
    result = s.wifi_scan_select()
    assert result is None and s.screen == ui_state.SCREEN_WIFI_PASSWORD

    for i in range(0, len(ui_state.WIFI_CHARSET), 7):  # sample the wheel, not every char
        s.wifi_password_char_idx = i
        _assert_frame(ui_render.render(s))
    s.wifi_password_chars = list("hunter2")
    _assert_frame(ui_render.render(s))
    s.wifi_password_backspace()
    _assert_frame(ui_render.render(s))

    # regression: submitting from here used to leave the wheel screen showing
    # with zero feedback on both success and failure - confirmed live, see
    # ui_state.wifi_password_submit / render_wifi_password.
    s.wifi_password_submit()
    _assert_frame(ui_render.render(s))  # "Verbinde..."
    s.wifi_connect_done(False, "Verbindung fehlgeschlagen")
    _assert_frame(ui_render.render(s))  # error, with a "Play: erneut versuchen" hint

    s.start_playlist_manage()
    for i in range(len(ui_state.LIBRARY)):
        s.playlist_manage_sel = i
        _assert_frame(ui_render.render(s))
    s.playlist_manage_sel = 0
    s.playlist_manage_open()
    assert s.screen == ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL
    for i in range(len(s.playlist_manage_detail_items())):
        s.playlist_manage_detail_sel = i
        _assert_frame(ui_render.render(s))
    s.playlist_manage_detail_sel = 1  # "delete" row
    s.playlist_manage_confirm_delete = True  # the warning-colored state
    _assert_frame(ui_render.render(s))

    _assert_frame(ui_render.render_shutdown(s))


def test_all_screens_render_at_every_scale_in_every_design():
    for theme in themes.THEMES:
        for scale_step in ui_render.UI_SCALE_STEPS:
            s = make_state()
            s.settings.set("display", "theme", theme)
            s.settings.set("display", "ui_scale", scale_step)
            _walk_all_screens(s)


def test_quick_connect_overlay_renders_every_phase():
    for theme in themes.THEMES:
        s = make_state()
        s.settings.set("display", "theme", theme)
        s.qc_active = True
        for phase, progress, error in [("hold", 0.0, None), ("hold", 0.5, None), ("hold", 1.0, None),
                                        ("connecting", 1.0, None), ("error", 1.0, "Kein Gerät")]:
            s.qc_phase, s.qc_progress, s.qc_error = phase, progress, error
            _assert_frame(ui_render.render(s))


def test_quick_connect_overlay_survives_qc_phase_reset_mid_render():
    """Regression test: quick_connect_done() (background thread) sets qc_active=False
    then qc_phase=None as two separate writes - render() already checked qc_active
    before calling _draw_quick_connect, so qc_phase can still be None once it gets
    there. Crashed live (KeyError: None) when connecting to an already-connected
    device, which completes fast enough to reliably land in that gap."""
    for theme in themes.THEMES:
        s = make_state()
        s.settings.set("display", "theme", theme)
        s.qc_active = True
        s.qc_phase = None
        _assert_frame(ui_render.render(s))


def test_windowed_range_bounds_and_clamping():
    # normal case: selection well inside a long list - full window both sides
    assert klassik._windowed_range(60, 30) == (27, 34)
    # near the start - clamps at 0 instead of going negative
    assert klassik._windowed_range(60, 0) == (0, 4)
    assert klassik._windowed_range(60, 2) == (0, 6)
    # near the end - clamps at n instead of overrunning
    assert klassik._windowed_range(60, 59) == (56, 60)
    # list shorter than the window on both sides - covers everything
    assert klassik._windowed_range(5, 2) == (0, 5)


def test_playlist_render_windows_a_long_list_at_every_scroll_position():
    """Regression test: render_playlist() used to build (and generate cover art
    for) an entry for every track regardless of list length - confirmed live as
    the lag source on a 60-track playlist, since only ~3-5 rows are ever
    actually drawn (see _render_nav_list's own half_w cutoff). Swaps in a
    synthetic 60-track playlist to prove the windowing stays correct (right
    track highlighted, no crash) at the start, middle and end of a list much
    longer than NAV_LIST_WINDOW, not just the small demo playlists."""
    orig_library = ui_state.LIBRARY
    orig_covers = ui_state.LIBRARY_COVERS
    try:
        big_tracks = [(f"Track {i}", "Artist", 180) for i in range(60)]
        ui_state.LIBRARY = [("Big Playlist", big_tracks)]
        ui_state.LIBRARY_COVERS = [{"cover": None, "tracks": [None] * 60}]
        for theme in themes.THEMES:
            s = make_state()
            s.settings.set("display", "theme", theme)
            s.current_playlist_idx = 0
            s.screen = ui_state.SCREEN_PLAYLIST
            for sel in (0, 30, 59):
                s.playlist_sel = sel
                _assert_frame(ui_render.render(s))
    finally:
        ui_state.LIBRARY = orig_library
        ui_state.LIBRARY_COVERS = orig_covers


def test_every_design_choice_has_a_theme():
    assert {v for v, _ in ui_state.THEME_CHOICES} == set(themes.THEMES)


def test_unknown_design_falls_back_to_klassik():
    # Review Focus 1: a stale/renamed design in settings.json
    s = make_state()
    s.settings.set("display", "theme", "gibt-es-nicht")
    stale = ui_render.render(s)
    s.settings.set("display", "theme", "klassik")
    assert stale.tobytes() == ui_render.render(s).tobytes()
    s.settings.set("display", "theme", "gibt-es-nicht")
    s.settings_category = "display"
    s.screen = ui_state.SCREEN_SETTINGS_DETAIL
    _assert_frame(ui_render.render(s))  # "Design" row shows the raw value, no StopIteration


LONG = ("Ein extrem langer Titel, der garantiert in keine Zeile passt - Umlaute ÄÖÜ äöü ß, "
        "Pfeil → und Punkt · und noch mehr Text dahinter")


def _edge_views():
    """Review Focus 2 + 3: long strings, tiny/huge lists, impossible numbers."""
    cover = (None, "edge", "#FF6157")
    yield ListView(ui_state.SCREEN_LIBRARY, LONG, [Item(LONG, LONG, "♪", "playlist", "accent", cover)], 0)
    yield ListView(ui_state.SCREEN_PLAYLIST, "T", [Item(f"Track {i}", "A · 3:00", kind="track",
                                                        cover=(None, f"t{i}", "#2F8CFF")) for i in range(60)], 59)
    yield ListView(ui_state.SCREEN_HOME, "Mini-Musikplayer", [Item("Bibliothek", "", "♪", "library")], 0)
    yield ListView(ui_state.SCREEN_SETTINGS_ROOT, "Einstellungen",
                   [Item(c["label"], "", c["icon"], c["key"]) for c in ui_state.SETTINGS_CATEGORIES], 5)
    yield ListView(ui_state.SCREEN_BT_MENU, "Bluetooth", [Item("Bluetooth", "An", "B", "toggle", "accent"),
                                                          Item(LONG, LONG, "B", "device", "muted"),
                                                          Item("Neue Geraete koppeln", "", "+", "pair_new", "danger")], 2)
    for mood in ("busy", "error", "success", "info"):
        yield MessageView(ui_state.SCREEN_WIFI_PASSWORD, LONG, mood, LONG, detail=LONG, hint=LONG, subtitle=LONG)
        yield MessageView(ui_state.SCREEN_BT_PAIRING, "Bluetooth", mood, "Kurz")
    yield SettingsView(ui_state.SCREEN_SETTINGS_DETAIL, LONG, "display",
                       [SettingRow(LONG, "choice", LONG, on=True), SettingRow("Stufe", "stepper", 9, max=5, on=True),
                        SettingRow("An", "toggle", True), SettingRow(LONG, "info", LONG),
                        SettingRow("Konto", "action", "Verbinden →")], 4)
    yield SettingsView(ui_state.SCREEN_SETTINGS_DETAIL, "Über", "about", [SettingRow("Version", "info", "Rev 1")], 0)
    yield PlayingView(ui_state.SCREEN_PLAYING, LONG, LONG, LONG, 0, "#FF6157", cover, 0.0, 0.0, False, True)
    yield PlayingView(ui_state.SCREEN_PLAYING, "A", "B", "C", 7, "#8B7CF6", cover, 500.0, 200.0, True, False)
    yield CodeView(ui_state.SCREEN_SYNC_LOGIN, LONG, "https://www.google.com/device?" + "x" * 80, "ABCD-EFGH-IJKL")
    yield ProgressView(ui_state.SCREEN_SYNC_PROGRESS, LONG, 0, 0, LONG, False)
    yield ProgressView(ui_state.SCREEN_SYNC_PROGRESS, "Sync", 12, 10, "", True)
    yield PasswordView(ui_state.SCREEN_WIFI_PASSWORD, LONG, LONG, "x" * 80, ui_state.WIFI_CHARSET, 0, LONG)
    yield PasswordView(ui_state.SCREEN_WIFI_PASSWORD, "WLAN-Passwort", "", "", ui_state.WIFI_CHARSET,
                       len(ui_state.WIFI_CHARSET) - 1, "")


def test_every_design_survives_edge_case_views():
    status = StatusView(5, True, 12.0, None, True, True, False, False, True)
    qc = QuickConnectView("error", 1.0, LONG, True)
    for name, theme in themes.THEMES.items():
        for scale in (ui_render.UI_SCALE_STEPS[1], ui_render.UI_SCALE_STEPS[5]):
            ctx = RenderCtx(scale, status)
            for v in _edge_views():
                img = getattr(theme, "draw_" + v.KIND)(v, ctx)
                assert img.size == (ui_render.W, ui_render.W), (name, v.KIND)
                theme.draw_status(img, status, ctx)
                theme.draw_quick_connect(img, qc, ctx)


def test_font_loader_never_raises_for_missing_files():
    # Review Focus 4: fonts/ not copied to the Pi
    f = ui_common.font("GibtEsNicht.ttf", 14, weight=700)
    assert f.getlength("abc") > 0


def test_variable_font_weight_is_applied():
    regular = ui_common.font("Nunito[wght].ttf", 20)
    bold = ui_common.font("Nunito[wght].ttf", 20, weight=800)
    assert bold.getlength("Bibliothek") > regular.getlength("Bibliothek")


def test_glyph_safe_falls_back_to_ascii_for_missing_symbols():
    # Review Focus 5: PixelifySans has no arrow, keeps umlauts
    pixel = ui_common.font("PixelifySans[wght].ttf", 10)
    assert ui_common.glyph_safe("Verbinden → Über", pixel) == "Verbinden -> Über"
    assert ui_common.fit(LONG, pixel, 60).endswith(("…", "..."))
    assert ui_common.font("PixelifySans[wght].ttf", 10).getlength(ui_common.fit(LONG, pixel, 60)) <= 60


def test_window_rows_fill_from_the_top_and_keep_the_selection_visible():
    # settings forms: rows start right under the header instead of centering the
    # selection (which left the top half empty while the first row was selected)
    rows = list(ui_common.window_rows(6, 0, top=60, bottom=200, pitch=30))
    assert [i for i, _, _, _ in rows] == [0, 1, 2, 3] and rows[0][1] == 75
    assert [i for i, _, _, _ in ui_common.window_rows(6, 5, top=60, bottom=200, pitch=30)] == [2, 3, 4, 5]
    assert [i for i, _, _, _ in ui_common.window_rows(2, 1, top=60, bottom=200, pitch=30)] == [0, 1]
    assert all(off == i - 3 for i, _, _, off in ui_common.window_rows(6, 3, top=60, bottom=200, pitch=30))


def test_list_rows_stay_inside_the_round_safe_area():
    rows = list(ui_common.list_rows(60, 30, 40))
    assert [off for _, _, _, off in rows] == [-2, -1, 0, 1, 2]
    assert all(half >= 40 for _, _, half, _ in rows)
    assert [i for i, _, _, _ in ui_common.list_rows(3, 0, 40)] == [0, 1, 2]


def test_pixelhaus_camera_snaps_first_then_flies_and_settles():
    from themes import pixelhaus
    clock = [100.0]
    old_clock, old_cam = pixelhaus._clock, pixelhaus._CAM
    pixelhaus._clock, pixelhaus._CAM = (lambda: clock[0]), pixelhaus.Camera()
    try:
        s = make_state()
        s.settings.set("display", "theme", "pixelhaus")
        ui_render.render(s)
        assert not ui_render.animating(s)        # first frame: no flight from nowhere
        s.screen = ui_state.SCREEN_SETTINGS_ROOT
        ui_render.render(s)
        assert ui_render.animating(s)            # floats from the living room to the workshop
        clock[0] += 0.2
        ui_render.render(s)
        assert ui_render.animating(s)
        clock[0] += 5.0                          # e.g. screen was off meanwhile
        ui_render.render(s)
        assert not ui_render.animating(s)        # arrived; resting frame drawn
    finally:
        pixelhaus._clock, pixelhaus._CAM = old_clock, old_cam


def test_pixelhaus_arrow_points_toward_the_target_room():
    from themes import pixelhaus
    assert pixelhaus._rotated("arrow", 0)[0] == "..X.."                                # tip up
    assert [r[-1] for r in pixelhaus._rotated("arrow", 90)] == [".", ".", "X", ".", "."]  # tip right
    assert pixelhaus._rotated("arrow", 180)[-1] == "..X.."                             # tip down
    assert pixelhaus._arrow_rot(706, -175) == 90   # living room -> library: mostly right
    assert pixelhaus._arrow_rot(-50, -400) == 0    # mostly up
    assert pixelhaus._arrow_rot(0, 300) == 180
    assert pixelhaus._arrow_rot(-300, 10) == 270


def test_pixelhaus_renders_without_its_asset():
    # Review Focus 4: assets/pixelhaus.png not deployed
    from themes import pixelhaus
    old = pixelhaus.ASSET_PATH
    pixelhaus.ASSET_PATH = "gibt/es/nicht.png"
    pixelhaus._house.cache_clear()
    try:
        s = make_state()
        s.settings.set("display", "theme", "pixelhaus")
        _walk_all_screens(s)
    finally:
        pixelhaus.ASSET_PATH = old
        pixelhaus._house.cache_clear()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests passed")
