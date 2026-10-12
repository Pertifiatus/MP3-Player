"""Which view each screen/state produces - the content contract every design
draws (see themes/). No hardware needed.

python3 test_ui_views.py
"""
import os
import tempfile

from settings import Settings
import ui_state
import ui_views


def make_state():
    path = os.path.join(tempfile.gettempdir(), "test_settings_views.json")
    if os.path.exists(path):
        os.remove(path)
    return ui_state.UIState(Settings(path=path))


def test_home_items_carry_kind_and_resume_cover():
    s = make_state()
    s.last_played = (0, 1)
    v = ui_views.build(s)
    assert v.KIND == "list" and v.title == "Mini-Musikplayer" and v.sel == 0
    assert [it.kind for it in v.items] == ["library", "resume", "settings"]
    name, tracks = ui_state.LIBRARY[0]
    assert v.items[1].cover == (ui_state.LIBRARY_COVERS[0]["tracks"][1], f"tr-{name}-{tracks[1][0]}",
                                ui_state.PLAYLIST_COLORS[0])
    assert v.items[0].cover is None


def test_playlist_view_lists_every_track_with_its_cover_seed():
    s = make_state()
    s.library_sel = 1
    s.library_open()
    v = ui_views.build(s)
    name, tracks = ui_state.LIBRARY[1]
    assert v.KIND == "list" and v.title == name and len(v.items) == len(tracks)
    assert v.items[0].sub == f"{tracks[0][1]} · {ui_views.fmt_time(tracks[0][2])}"
    assert v.items[0].cover[1] == f"tr-{name}-{tracks[0][0]}"


def test_playing_view():
    s = make_state()
    s.library_open()
    s.playlist_sel = 2
    s.playlist_open()
    s.now_playing.position = 61.0
    v = ui_views.build(s)
    title, artist, dur = ui_state.LIBRARY[0][1][2]
    assert v.KIND == "playing" and (v.title, v.artist, v.duration) == (title, artist, dur)
    assert v.position == 61.0 and v.playing and not v.shuffle and v.color == ui_state.PLAYLIST_COLORS[0]


def test_settings_rows_carry_kind_value_and_emphasis():
    s = make_state()
    s.settings_category = "display"
    s.screen = ui_state.SCREEN_SETTINGS_DETAIL
    v = ui_views.build(s)
    rows = {r.label: r for r in v.rows}
    assert v.KIND == "settings" and v.title == "Anzeige" and v.category == "display"
    assert (rows["Helligkeit"].kind, rows["Helligkeit"].value, rows["Helligkeit"].max) == ("stepper", 3, 5)
    assert (rows["Auto-Aus"].value, rows["Auto-Aus"].on) == ("30s", True)

    s.settings_category = "sync"
    rows = {r.label: r for r in ui_views.build(s).rows}
    assert rows["Konto"].value == "Verbinden →" and not rows["Konto"].on
    assert rows["Auto-Sync bei Ladegeraet"].kind == "toggle" and rows["Auto-Sync bei Ladegeraet"].value is False
    assert rows["Speicher"].kind == "info"


def test_choice_row_with_unknown_stored_value_shows_the_raw_value():
    # Review Focus 1: a stale value in settings.json must not crash the settings screen
    s = make_state()
    s.settings.set("display", "auto_sleep_s", 999)
    s.settings_category = "display"
    s.screen = ui_state.SCREEN_SETTINGS_DETAIL
    rows = {r.label: r for r in ui_views.build(s).rows}
    assert rows["Auto-Aus"].value == "999"


def test_bt_pairing_states_map_to_message_and_list_views():
    s = make_state()
    s.start_bt_pairing()
    v = ui_views.build(s)
    assert (v.KIND, v.mood, v.text, v.hint) == ("message", "busy", "Suche Geräte...", "Kopfhörer in Pairing-Modus")
    s.bt_scan_done([])
    assert ui_views.build(s).mood == "info"
    s.bt_scan_done([{"mac": "AA:BB", "name": "", "paired": True}])
    v = ui_views.build(s)
    assert v.KIND == "list" and v.items[0].label == "AA:BB" and v.items[0].tone == "accent"
    s.bt_scan_select()
    v = ui_views.build(s)
    assert (v.mood, v.detail) == ("busy", "AA:BB")
    s.bt_pair_done(False, "nope")
    v = ui_views.build(s)
    assert (v.mood, v.text, v.detail) == ("error", "Fehler:", "nope")


def test_wifi_scan_and_password_views():
    s = make_state()
    s.start_wifi_scan()
    assert ui_views.build(s).text == "Suche Netzwerke..."
    s.wifi_known_networks = [{"name": "p", "ssid": "Heim", "connected": True}]
    s.wifi_scan_done([{"ssid": "Heim", "signal": 80, "secured": True},
                      {"ssid": "Cafe", "signal": 40, "secured": False}])
    v = ui_views.build(s)
    assert [(it.sub, it.tone) for it in v.items] == [("Gespeichert", "accent"), ("Offen", "muted")]
    s.start_wifi_password_entry("Neu")
    s.wifi_password_chars = list("abc")
    v = ui_views.build(s)
    assert (v.KIND, v.ssid, v.typed, v.charset) == ("password", "Neu", "abc", ui_state.WIFI_CHARSET)
    s.wifi_password_submit()
    s.wifi_connect_done(False, "falsch")
    v = ui_views.build(s)
    assert (v.mood, v.subtitle, v.hint) == ("error", "Neu", "Play: erneut versuchen")


def test_sync_views():
    s = make_state()
    s.screen = ui_state.SCREEN_SYNC_LOGIN
    assert ui_views.build(s).mood == "busy"
    s.sync_login_info = {"verification_url": "https://x.y/activate", "user_code": "AB-12"}
    v = ui_views.build(s)
    assert (v.KIND, v.url, v.code) == ("code", "https://x.y/activate", "AB-12")
    s.start_sync_now()
    s.sync_progress_callback(3, 10, "Song")
    v = ui_views.build(s)
    assert (v.KIND, v.current, v.total, v.track, v.done) == ("progress", 3, 10, "Song", False)


def test_playlist_manage_detail_marks_confirmed_delete_as_danger():
    s = make_state()
    s.start_playlist_manage()
    s.playlist_manage_open()
    s.playlist_manage_confirm_delete = True
    v = ui_views.build(s)
    assert [it.tone for it in v.items] == ["muted", "danger"]


def test_status_and_quick_connect_views():
    s = make_state()
    s.battery_pct, s.charging = 55, True
    sv = ui_views.status(s)
    assert sv.battery_pct == 55 and sv.charging and sv.show_labels  # Home at rest
    s.home_sel = 1
    assert not ui_views.status(s).show_labels
    s.qc_active, s.qc_phase = True, None  # background thread cleared it mid-frame
    assert ui_views.quick_connect(s) is None
    s.qc_phase, s.qc_progress, s.qc_error = "error", 1.0, "Kein Gerät"
    qc = ui_views.quick_connect(s)
    assert (qc.label, qc.error) == ("Kein Gerät", True)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests passed")
