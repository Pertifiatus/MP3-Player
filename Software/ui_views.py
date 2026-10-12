"""What each front-display screen shows, as plain data - never how it looks.

ui_render.render() builds exactly one view per frame from the UIState and hands
it to the active design (themes/*), which draws it with its own layout. All the
"which state means which text" logic that used to be spread over the old
render_* functions lives here, once, for every design.

Entries carry meaning, not colors: Item.kind says what a row *is* (a playlist,
the BT toggle, the "display" settings category, ...) and Item.tone whether it
is active ("accent"), inactive ("muted") or destructive ("danger") - each design
maps that to its own colors/objects (Klassik: badge color, Pixelhaus: a room).
"""
from dataclasses import dataclass
from typing import ClassVar, Optional

import sync_youtube
import ui_state


@dataclass
class Item:
    label: str
    sub: str = ""
    icon: str = ""
    kind: str = ""
    tone: str = "accent"           # accent | muted | danger
    cover: Optional[tuple] = None  # (path_or_None, seed, color_hex) -> ui_common.cover_image(cover, size)


@dataclass
class ListView:
    KIND: ClassVar[str] = "list"
    screen: str
    title: str
    items: list
    sel: int


@dataclass
class MessageView:
    KIND: ClassVar[str] = "message"
    screen: str
    title: str
    mood: str            # busy | error | success | info
    text: str
    detail: str = ""     # the specific thing: a device/SSID name, the error message
    hint: str = ""       # what the user can do about it
    subtitle: str = ""   # shown under the title (WLAN-Passwort: the SSID)


@dataclass
class SettingRow:
    label: str
    kind: str            # toggle | stepper | choice | info | action
    value: object        # toggle: bool, stepper: int, everything else: display text
    max: int = 0         # stepper only
    on: bool = False     # value is "active"/highlighted (Klassik: accent color)


@dataclass
class SettingsView:
    KIND: ClassVar[str] = "settings"
    screen: str
    title: str
    category: str
    rows: list
    sel: int


@dataclass
class PlayingView:
    KIND: ClassVar[str] = "playing"
    screen: str
    title: str
    artist: str
    playlist: str
    playlist_idx: int
    color: str           # playlist color "#RRGGBB"
    cover: tuple
    position: float
    duration: float
    playing: bool
    shuffle: bool


@dataclass
class CodeView:
    KIND: ClassVar[str] = "code"
    screen: str
    title: str
    url: str
    code: str


@dataclass
class ProgressView:
    KIND: ClassVar[str] = "progress"
    screen: str
    title: str
    current: int
    total: int
    track: str
    done: bool


@dataclass
class PasswordView:
    KIND: ClassVar[str] = "password"
    screen: str
    title: str
    ssid: str
    typed: str
    charset: str
    char_idx: int
    hint: str


@dataclass
class StatusView:
    battery_pct: Optional[int]
    charging: bool
    watts: Optional[float]
    eta_min: Optional[float]
    wifi_on: bool
    wifi_connected: bool
    bt_on: bool
    bt_connected: bool
    show_labels: bool    # room for the %/ETA text: Home at rest and Now Playing only


@dataclass
class QuickConnectView:
    phase: str           # hold | connecting | error
    progress: float      # 0.0-1.0
    label: str
    error: bool


@dataclass
class RenderCtx:
    scale: float         # UI-Groesse factor, see ui_render.UI_SCALE_STEPS
    status: StatusView


def playlist_color(idx):
    return ui_state.PLAYLIST_COLORS[idx % len(ui_state.PLAYLIST_COLORS)]


def fmt_time(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


# --- screen builders --------------------------------------------------------------

def _home(state):
    items = []
    for it in state.home_items():
        cover = None
        if it["key"] == "resume":
            pl_idx, tr_idx = state.last_played
            cover = (ui_state.LIBRARY_COVERS[pl_idx]["tracks"][tr_idx], it["seed"], it["color"])
        items.append(Item(it["label"], it["sub"], it["icon"], kind=it["key"], cover=cover))
    return ListView(ui_state.SCREEN_HOME, "Mini-Musikplayer", items, state.home_sel)


def _library(state):
    items = [Item(name, f"{len(tracks)} Songs", kind="playlist",
                  cover=(ui_state.LIBRARY_COVERS[i]["cover"], f"pl-{name}", playlist_color(i)))
             for i, (name, tracks) in enumerate(ui_state.LIBRARY)]
    return ListView(ui_state.SCREEN_LIBRARY, "Bibliothek", items, state.library_sel)


def _playlist(state):
    idx = state.current_playlist_idx
    name, tracks = ui_state.LIBRARY[idx]
    color = playlist_color(idx)
    covers = ui_state.LIBRARY_COVERS[idx]["tracks"]
    items = [Item(title, f"{artist} · {fmt_time(dur)}", kind="track", cover=(covers[t], f"tr-{name}-{title}", color))
             for t, (title, artist, dur) in enumerate(tracks)]
    return ListView(ui_state.SCREEN_PLAYLIST, name, items, state.playlist_sel)


def _playing(state):
    np_ = state.now_playing
    title, artist, dur = np_.current()
    name = ui_state.LIBRARY[np_.playlist_idx][0]
    color = playlist_color(np_.playlist_idx)
    cover = (ui_state.LIBRARY_COVERS[np_.playlist_idx]["tracks"][np_.index], f"tr-{name}-{title}", color)
    return PlayingView(ui_state.SCREEN_PLAYING, title, artist, name, np_.playlist_idx, color, cover,
                       np_.position, dur, np_.playing, state.shuffle)


def _settings_root(state):
    items = [Item(c["label"], "", c["icon"], kind=c["key"]) for c in ui_state.SETTINGS_CATEGORIES]
    return ListView(ui_state.SCREEN_SETTINGS_ROOT, "Einstellungen", items, state.settings_root_sel)


def _setting_row(cat, item, state):
    kind, key, label = item["type"], item["key"], item["label"]
    if kind == "toggle":
        return SettingRow(label, kind, bool(state.settings.get(cat, key)))
    if kind == "stepper":
        return SettingRow(label, kind, state.settings.get(cat, key), max=item["max"], on=True)
    if kind == "choice":
        val = state.settings.get(cat, key)
        # A stale value (e.g. a design renamed by an update) shows as-is instead
        # of crashing the whole settings screen.
        text = next((c[1] for c in item["choices"] if c[0] == val), str(val))
        return SettingRow(label, kind, text, on=True)
    if kind == "info":
        if key == "storage":
            # unlike every other "info" row, this changes constantly - can't
            # be baked into SETTINGS_ITEMS as a fixed string like VERSION_STRING
            try:
                return SettingRow(label, kind, f"{sync_youtube.free_space_gb():.1f} GB frei")
            except OSError:
                return SettingRow(label, kind, "unbekannt")
        return SettingRow(label, kind, item["detail"])
    if key == "account":
        linked = bool(state.settings.get("sync", "account_linked"))
        return SettingRow(label, kind, "Verknuepft" if linked else "Verbinden →", on=linked)
    if key in ("bluetooth_menu", "wifi_menu"):
        on = bool(state.settings.get("connectivity", "bluetooth" if key == "bluetooth_menu" else "wifi"))
        return SettingRow(label, kind, "An" if on else "Aus", on=on)
    return SettingRow(label, kind, "→")


def _settings_detail(state):
    cat = state.settings_category
    title = next(c["label"] for c in ui_state.SETTINGS_CATEGORIES if c["key"] == cat)
    rows = [_setting_row(cat, it, state) for it in ui_state.SETTINGS_ITEMS[cat]]
    return SettingsView(ui_state.SCREEN_SETTINGS_DETAIL, title, cat, rows, state.settings_detail_sel)


def _sync_login(state):
    t = "YouTube koppeln"
    if state.sync_login_error:
        return MessageView(ui_state.SCREEN_SYNC_LOGIN, t, "error", "Fehler:", detail=state.sync_login_error)
    if not state.sync_login_info:
        return MessageView(ui_state.SCREEN_SYNC_LOGIN, t, "busy", "Verbinde...")
    info = state.sync_login_info
    return CodeView(ui_state.SCREEN_SYNC_LOGIN, t, info["verification_url"], info["user_code"])


def _sync_progress(state):
    t = "Synchronisiere"
    if state.sync_error:
        return MessageView(ui_state.SCREEN_SYNC_PROGRESS, t, "error", "Fehler:", detail=state.sync_error)
    current, total, track = state.sync_progress
    return ProgressView(ui_state.SCREEN_SYNC_PROGRESS, t, current, total, track, bool(state.sync_done()))


def _on_tone(on):
    return "accent" if on else "muted"


def _bt_menu(state):
    items = [Item(it["label"], it["sub"], "+" if it["kind"] == "pair_new" else "B", kind=it["kind"],
                  tone=_on_tone(it.get("on") or it.get("connected")))
             for it in state.bt_menu_items()]
    return ListView(ui_state.SCREEN_BT_MENU, "Bluetooth", items, state.bt_menu_sel)


def _bt_device(state):
    t = state.bt_device_name or ""
    if state.bt_action_status == "working":
        return MessageView(ui_state.SCREEN_BT_DEVICE, t, "busy", "Bitte warten...")
    if state.bt_action_status == "error":
        return MessageView(ui_state.SCREEN_BT_DEVICE, t, "error", "Fehler:",
                           detail=state.bt_action_error or "Unbekannter Fehler")
    items = [Item(it["label"], "", "B", kind=it["key"], tone="muted") for it in state.bt_device_items()]
    return ListView(ui_state.SCREEN_BT_DEVICE, t, items, state.bt_device_sel)


def _bt_pairing(state):
    t, scr = "Bluetooth", ui_state.SCREEN_BT_PAIRING
    if state.bt_pair_status == "pairing":
        return MessageView(scr, t, "busy", "Verbinde...", detail=state.bt_pair_device_name or "")
    if state.bt_pair_status == "done":
        return MessageView(scr, t, "success", "Verbunden!", detail=state.bt_pair_device_name or "")
    if state.bt_pair_status == "error":
        return MessageView(scr, t, "error", "Fehler:", detail=state.bt_pair_error or "Unbekannter Fehler")
    if state.bt_scanning:
        return MessageView(scr, t, "busy", "Suche Geräte...", hint="Kopfhörer in Pairing-Modus")
    if not state.bt_scan_devices:
        return MessageView(scr, t, "info", "Keine Geräte gefunden", hint="Kopfhörer in Pairing-Modus?")
    items = [Item(d["name"] or d["mac"], "Gekoppelt" if d.get("paired") else d["mac"], "B",
                  kind="scan_device", tone=_on_tone(d.get("paired")))
             for d in state.bt_scan_devices]
    return ListView(scr, t, items, state.bt_scan_sel)


def _wifi_menu(state):
    t, scr = "WLAN", ui_state.SCREEN_WIFI_MENU
    if state.wifi_wake_status == "working":
        return MessageView(scr, t, "busy", "Aufwecken...")
    if state.wifi_wake_status == "error":
        return MessageView(scr, t, "error", "Fehler:", detail=state.wifi_wake_error or "Unbekannter Fehler")
    items = [Item(it["label"], it["sub"], "+" if it["kind"] == "connect_new" else "W", kind=it["kind"],
                  tone=_on_tone(it.get("on") or it.get("connected")))
             for it in state.wifi_menu_items()]
    return ListView(scr, t, items, state.wifi_menu_sel)


def _wifi_device(state):
    t, scr = state.wifi_device_ssid or "", ui_state.SCREEN_WIFI_DEVICE
    if state.wifi_action_status == "working":
        return MessageView(scr, t, "busy", "Bitte warten...")
    if state.wifi_action_status == "error":
        return MessageView(scr, t, "error", "Fehler:", detail=state.wifi_action_error or "Unbekannter Fehler")
    items = [Item(it["label"], "", "W", kind=it["key"], tone="muted") for it in state.wifi_device_items()]
    return ListView(scr, t, items, state.wifi_device_sel)


def _wifi_scan(state):
    t, scr = "WLAN", ui_state.SCREEN_WIFI_SCAN
    if state.wifi_connect_status == "connecting":
        return MessageView(scr, t, "busy", "Verbinde...", detail=state.wifi_pending_ssid or "")
    if state.wifi_connect_status == "error":
        return MessageView(scr, t, "error", "Fehler:", detail=state.wifi_connect_error or "Unbekannter Fehler")
    if state.wifi_scanning:
        return MessageView(scr, t, "busy", "Suche Netzwerke...")
    if not state.wifi_scan_networks:
        return MessageView(scr, t, "info", "Keine Netzwerke gefunden")
    known = {n["ssid"] for n in state.wifi_known_networks}
    items = [Item(n["ssid"], "Gespeichert" if n["ssid"] in known else ("Gesichert" if n["secured"] else "Offen"),
                  "W", kind="scan_network", tone=_on_tone(n["ssid"] in known))
             for n in state.wifi_scan_networks]
    return ListView(scr, t, items, state.wifi_scan_sel)


def _wifi_password(state):
    t, scr, ssid = "WLAN-Passwort", ui_state.SCREEN_WIFI_PASSWORD, state.wifi_pending_ssid or ""
    if state.wifi_connect_status == "connecting":
        return MessageView(scr, t, "busy", "Verbinde...", detail=ssid, subtitle=ssid)
    if state.wifi_connect_status == "error":
        return MessageView(scr, t, "error", "Fehler:", detail=state.wifi_connect_error or "Unbekannter Fehler",
                           hint="Play: erneut versuchen", subtitle=ssid)
    return PasswordView(scr, t, ssid, state.wifi_password_text(), ui_state.WIFI_CHARSET,
                        state.wifi_password_char_idx,
                        "Dreh: Zeichen  ·  Klick: uebernehmen  ·  Shuffle: Loeschen  ·  Play: Fertig")


def _playlist_manage(state):
    t, scr = "Playlists", ui_state.SCREEN_PLAYLIST_MANAGE
    if not ui_state.LIBRARY:
        return MessageView(scr, t, "info", "Keine Playlists")
    excluded = set(state.settings.get("sync", "excluded_playlists"))
    items = [Item(name, "Ausgeschlossen" if name in excluded else f"{len(tracks)} Songs", "♪",
                  kind="manage_playlist", tone=_on_tone(name not in excluded))
             for name, tracks in ui_state.LIBRARY]
    return ListView(scr, t, items, state.playlist_manage_sel)


def _playlist_manage_detail(state):
    items = [Item(it["label"], "", "!" if it["key"] == "delete" else "S", kind=it["key"],
                  tone="danger" if (it["key"] == "delete" and state.playlist_manage_confirm_delete) else "muted")
             for it in state.playlist_manage_detail_items()]
    return ListView(ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL, state.playlist_manage_detail_name(), items,
                    state.playlist_manage_detail_sel)


_BUILDERS = {
    ui_state.SCREEN_HOME: _home,
    ui_state.SCREEN_LIBRARY: _library,
    ui_state.SCREEN_PLAYLIST: _playlist,
    ui_state.SCREEN_PLAYING: _playing,
    ui_state.SCREEN_SETTINGS_ROOT: _settings_root,
    ui_state.SCREEN_SETTINGS_DETAIL: _settings_detail,
    ui_state.SCREEN_SYNC_LOGIN: _sync_login,
    ui_state.SCREEN_SYNC_PROGRESS: _sync_progress,
    ui_state.SCREEN_BT_PAIRING: _bt_pairing,
    ui_state.SCREEN_BT_MENU: _bt_menu,
    ui_state.SCREEN_BT_DEVICE: _bt_device,
    ui_state.SCREEN_WIFI_MENU: _wifi_menu,
    ui_state.SCREEN_WIFI_DEVICE: _wifi_device,
    ui_state.SCREEN_WIFI_SCAN: _wifi_scan,
    ui_state.SCREEN_WIFI_PASSWORD: _wifi_password,
    ui_state.SCREEN_PLAYLIST_MANAGE: _playlist_manage,
    ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL: _playlist_manage_detail,
}


def build(state):
    return _BUILDERS[state.screen](state)


def status(state):
    s = state.settings
    return StatusView(state.battery_pct, state.charging, state.battery_watts, state.battery_eta_min,
                      bool(s.get("connectivity", "wifi")), state.wifi_connected,
                      bool(s.get("connectivity", "bluetooth")), state.bt_connected,
                      show_labels=((state.screen == ui_state.SCREEN_HOME and state.home_sel == 0)
                                   or state.screen == ui_state.SCREEN_PLAYING))


def quick_connect(state):
    """None once the background thread has already cleared the gesture - read
    qc_phase exactly once: quick_connect_done() resets qc_active and qc_phase as
    two separate writes (see ui_state), so a second read could see None."""
    phase = state.qc_phase
    if phase is None:
        return None
    label = {"hold": "Quick Connect", "connecting": "Verbinde...", "error": state.qc_error or "Fehler"}[phase]
    return QuickConnectView(phase, state.qc_progress, label, phase == "error")
