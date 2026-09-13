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


def make_state():
    path = os.path.join(tempfile.gettempdir(), "test_settings_render.json")
    if os.path.exists(path):
        os.remove(path)
    return ui_state.UIState(Settings(path=path))


def _assert_frame(img):
    assert img.size == (ui_render.W, ui_render.W)


def test_all_screens_render_at_every_scale():
    for scale_step in ui_render.UI_SCALE_STEPS:
        s = make_state()
        s.settings.set("display", "ui_scale", scale_step)

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

        s.wifi_menu_sel = 1  # the connected network
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

        _assert_frame(ui_render.render_shutdown())


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests passed")
