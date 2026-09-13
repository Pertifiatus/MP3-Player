"""UI state machine for the front display."""
import json
import os
import time

import connectivity
import sync_youtube

# --- screens -----------------------------------------------------------------
SCREEN_HOME = "home"
SCREEN_LIBRARY = "library"
SCREEN_PLAYLIST = "playlist"
SCREEN_PLAYING = "playing"
SCREEN_SETTINGS_ROOT = "settings_root"
SCREEN_SETTINGS_DETAIL = "settings_detail"
SCREEN_SYNC_LOGIN = "sync_login"
SCREEN_SYNC_PROGRESS = "sync_progress"
SCREEN_BT_PAIRING = "bt_pairing"
SCREEN_BT_MENU = "bt_menu"
SCREEN_BT_DEVICE = "bt_device"
SCREEN_WIFI_MENU = "wifi_menu"
SCREEN_WIFI_DEVICE = "wifi_device"
SCREEN_WIFI_SCAN = "wifi_scan"
SCREEN_WIFI_PASSWORD = "wifi_password"
SCREEN_PLAYLIST_MANAGE = "playlist_manage"
SCREEN_PLAYLIST_MANAGE_DETAIL = "playlist_manage_detail"

# Encoder-wheel charset for WiFi password entry (rotate = cycle char, knob = accept
# it and advance) - same interaction as an old click-wheel iPod's text entry, the
# only text input this device has (no keyboard, just encoder + 3 buttons).
WIFI_CHARSET = (" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                 "-_.!@#$%^&*")

VERSION_STRING = "Rev 1 (Board 2)"

# --- fake library (same shape as beispiel.html, used until a real sync has run) -
_DEMO_LIBRARY = [
    ("Liked Songs", [("Blinding Lights", "The Weeknd", 200), ("Levitating", "Dua Lipa", 203),
                      ("As It Was", "Harry Styles", 167), ("Get Lucky", "Daft Punk ft. Pharrell", 248),
                      ("Redbone", "Childish Gambino", 327)]),
    ("Techno Mix", [("One More Time", "Daft Punk", 320), ("D.A.N.C.E.", "Justice", 203),
                     ("Formula", "Charlotte de Witte", 300), ("In My Mind", "Amelie Lens", 360),
                     ("Your Mind", "Adam Beyer", 390), ("Galvanize", "The Chemical Brothers", 250)]),
    ("Roadtrip", [("Go Your Own Way", "Fleetwood Mac", 218), ("Free Fallin'", "Tom Petty", 255),
                   ("Hotel California", "Eagles", 390), ("Born to Run", "Bruce Springsteen", 270)]),
    ("Lo-Fi Focus", [("Aruarian Dance", "Nujabes", 236), ("Feather", "Nujabes", 252),
                       ("Time: The Donut of the Heart", "J Dilla", 120), ("Lonely", "Tomppabeats", 150),
                       ("Petals", "Idealism", 180)]),
]


def _load_library():
    """Real library.json (written by sync_youtube.sync_library()) if a sync has ever
    completed, else the hardcoded demo data above. Playlists with zero tracks are
    dropped - library_move()/playlist_move() index modulo len(tracks), which would
    divide by zero for an empty one (e.g. a library playlist synced with nothing in it).

    Returns (library, covers, files): `library` is the (name, [(title, artist,
    duration), ...]) shape everything else here already expects; `covers` and
    `files` are same-length, same-order parallel structures - kept separate
    rather than widening the tuples, since those get unpacked as exactly 3
    values in several places (ui_render.py, NowPlaying.current()/tick()).
    `covers` is {"cover": path_or_None, "tracks": [path_or_None, ...]}. `files`
    is [path_or_None, ...], one per track, pointing at the actual downloaded
    audio file for NowPlaying/player.py to play - None for the demo library
    (nothing downloaded, nothing to play) or any track a sync skipped."""
    if os.path.exists(sync_youtube.LIBRARY_MANIFEST_PATH):
        with open(sync_youtube.LIBRARY_MANIFEST_PATH) as f:
            manifest = json.load(f)
        library = [(pl["name"], [(t["title"], t["artist"], t["duration"]) for t in pl["tracks"]])
                   for pl in manifest]
        covers = [{"cover": pl.get("cover"), "tracks": [t.get("cover") for t in pl["tracks"]]}
                  for pl in manifest]
        files = [[t.get("file") for t in pl["tracks"]] for pl in manifest]
        keep = [i for i, pl in enumerate(library) if pl[1]]
        library = [library[i] for i in keep]
        covers = [covers[i] for i in keep]
        files = [files[i] for i in keep]
        if library:
            return library, covers, files
    return (_DEMO_LIBRARY,
            [{"cover": None, "tracks": [None] * len(tracks)} for _, tracks in _DEMO_LIBRARY],
            [[None] * len(tracks) for _, tracks in _DEMO_LIBRARY])


LIBRARY, LIBRARY_COVERS, LIBRARY_FILES = _load_library()
PLAYLIST_COLORS = ["#FF6157", "#2F8CFF", "#FFB020", "#34D399", "#FB5A9D", "#22D3C7", "#A7D129", "#8B7CF6"]


def reload_library():
    """Re-reads library.json into the module-level LIBRARY/LIBRARY_COVERS/
    LIBRARY_FILES globals - needed after delete_playlist() (see UIState's
    playlist management below) since those are otherwise only ever loaded
    once, at import time."""
    global LIBRARY, LIBRARY_COVERS, LIBRARY_FILES
    LIBRARY, LIBRARY_COVERS, LIBRARY_FILES = _load_library()

# --- settings schema (declarative, drives both render + activation) ----------
# type: toggle | stepper (min/max int) | choice (list of (value,label)) | action | info
SETTINGS_CATEGORIES = [
    {"key": "display", "label": "Anzeige", "icon": "A"},
    {"key": "led", "label": "LED", "icon": "L"},
    {"key": "connectivity", "label": "Verbindung", "icon": "V"},
    {"key": "sync", "label": "Sync", "icon": "S"},
    {"key": "motion", "label": "Bewegung", "icon": "B"},
    {"key": "about", "label": "Über", "icon": "i"},
]

SETTINGS_ITEMS = {
    "display": [
        {"key": "brightness", "label": "Helligkeit", "type": "stepper", "min": 1, "max": 5},
        {"key": "ui_scale", "label": "UI-Groesse", "type": "stepper", "min": 1, "max": 5},
        {"key": "auto_sleep_s", "label": "Auto-Aus", "type": "choice",
         "choices": [(0, "Nie"), (15, "15s"), (30, "30s"), (60, "60s"), (120, "2min")]},
    ],
    "led": [
        {"key": "enabled", "label": "LED an", "type": "toggle"},
        {"key": "mode", "label": "Modus", "type": "choice",
         "choices": [("static", "Statisch"), ("battery", "Akkustand")]},
        {"key": "color_index", "label": "Farbe", "type": "choice",
         "choices": [(0, "Weiss"), (1, "Tuerkis"), (2, "Rot"), (3, "Blau"), (4, "Orange"), (5, "Violett")]},
        {"key": "brightness", "label": "Helligkeit", "type": "stepper", "min": 1, "max": 5},
    ],
    "connectivity": [
        {"key": "wifi_menu", "label": "WLAN", "type": "action"},
        {"key": "bluetooth_menu", "label": "Bluetooth", "type": "action"},
        {"key": "audio_output", "label": "Audioausgang", "type": "choice",
         "choices": [("bluetooth", "Bluetooth"), ("jack", "Klinke")]},
    ],
    "sync": [
        {"key": "account", "label": "Konto", "type": "action"},
        {"key": "sync_now", "label": "Jetzt synchronisieren", "type": "action"},
        {"key": "auto_sync_on_charge", "label": "Auto-Sync bei Ladegeraet", "type": "toggle"},
        {"key": "playlists", "label": "Playlists verwalten", "type": "action"},
        # "detail" is a placeholder - the actual value is computed live by
        # ui_render._value_repr() (free space changes constantly, unlike every
        # other "info" row here, which is a fixed string like VERSION_STRING).
        {"key": "storage", "label": "Speicher", "type": "info", "detail": ""},
    ],
    "motion": [
        {"key": "auto_display_switch", "label": "Auto-Display-Wechsel", "type": "toggle"},
        {"key": "shake_to_shuffle", "label": "Schuetteln = Shuffle", "type": "toggle"},
        {"key": "flip_to_pause", "label": "Umdrehen = Pause", "type": "toggle"},
    ],
    "about": [
        {"key": "version", "label": "Version", "type": "info", "detail": VERSION_STRING},
    ],
}


# Encoder rotation on the Playing screen does one of two things, toggled by a
# knob click (see main.py's handle_event): skip to the next/previous track, or
# adjust volume. A held-and-rotated knob instead scrubs the current track
# regardless of mode - see NowPlaying.scrub().
ENCODER_MODE_SKIP = "skip"
ENCODER_MODE_VOLUME = "volume"

SCRUB_STEP_S = 5.0


class NowPlaying:
    def __init__(self, tracks, index, playlist_idx):
        self.tracks = tracks
        self.index = index
        self.playlist_idx = playlist_idx
        self.playing = True
        self.position = 0.0
        self._last_tick = time.monotonic()
        self.encoder_mode = ENCODER_MODE_SKIP

    def current(self):
        return self.tracks[self.index]

    def current_file(self):
        """Path to the actual downloaded audio file for the current track, or
        None (demo library, or a track a sync skipped) - see player.py, which
        is the only thing that reads this; everything UI-facing still goes
        through current()'s plain (title, artist, duration)."""
        return LIBRARY_FILES[self.playlist_idx][self.index]

    def toggle(self):
        self.playing = not self.playing
        self._last_tick = time.monotonic()

    def skip(self, direction):
        self.index = (self.index + direction) % len(self.tracks)
        self.position = 0.0

    def scrub(self, direction, step=SCRUB_STEP_S):
        """Seek within the current track only - never wraps to the next/previous
        one, unlike skip()."""
        dur = self.current()[2]
        self.position = max(0.0, min(dur, self.position + direction * step))

    def toggle_encoder_mode(self):
        self.encoder_mode = (ENCODER_MODE_VOLUME if self.encoder_mode == ENCODER_MODE_SKIP
                              else ENCODER_MODE_SKIP)
        return self.encoder_mode

    def tick(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        if self.playing:
            dur = self.current()[2]
            self.position = min(self.position + dt, dur)
            if self.position >= dur:
                self.skip(1)


class UIState:
    def __init__(self, settings):
        self.settings = settings
        self.screen = SCREEN_HOME
        self.home_sel = 0
        self.library_sel = 0
        self.playlist_sel = 0
        self.current_playlist_idx = 0
        self.now_playing = None
        self.last_played = None  # (playlist_idx, track_idx)
        self.shuffle = False
        self.imu = None  # set by main.py after QMI8658() succeeds, else stays None

        self.settings_root_sel = 0
        self.settings_category = None
        self.settings_detail_sel = 0

        self.sync_login_info = None  # dict from sync_youtube.start_device_flow()
        self.sync_login_error = None
        self.sync_progress = None  # (current, total, track_name)
        self.sync_error = None

        self.bt_known_devices = []  # [{"mac", "name", "connected"}, ...] from connectivity.bluetooth_known_devices()
        self.bt_menu_sel = 0
        self.bt_device_mac = None
        self.bt_device_name = None
        self.bt_device_connected = False
        self.bt_device_sel = 0
        self.bt_action_status = None  # None | "working" | "error" - connect/disconnect/remove on SCREEN_BT_DEVICE
        self.bt_action_error = None

        self.bt_scan_devices = []  # [{"mac", "name", "paired"}, ...] from connectivity.bluetooth_scan()
        self.bt_scan_sel = 0
        self.bt_scanning = False
        self.bt_pair_status = None  # None | "pairing" | "done" | "error"
        self.bt_pair_error = None
        self.bt_pair_device_name = None

        self.wifi_known_networks = []  # [{"name", "ssid", "connected"}, ...] from connectivity.wifi_known_connections()
        self.wifi_menu_sel = 0
        self.wifi_device_name = None  # nmcli connection profile id - NOT necessarily the ssid, see connectivity.py
        self.wifi_device_ssid = None  # display-only
        self.wifi_device_connected = False
        self.wifi_device_sel = 0
        self.wifi_action_status = None  # None | "working" | "error" - connect/disconnect/forget on SCREEN_WIFI_DEVICE
        self.wifi_action_error = None

        self.wifi_scan_networks = []  # [{"ssid", "signal", "secured"}, ...] from connectivity.wifi_scan()
        self.wifi_scan_sel = 0
        self.wifi_scanning = False
        self.wifi_pending_ssid = None
        self.wifi_password_chars = []
        self.wifi_password_char_idx = 0
        self.wifi_connect_status = None  # None | "connecting" | "error"
        self.wifi_connect_error = None

        self.playlist_manage_sel = 0
        self.playlist_manage_idx = None
        self.playlist_manage_detail_sel = 0
        self.playlist_manage_confirm_delete = False

        # The WLAN/Bluetooth toggles must reflect what the radios are actually
        # doing, not just whatever was last written to settings.json - e.g. if
        # bluetooth-unblock.service left BT powered on independently of this
        # app, or a previous run's sudo call silently failed. Best-effort: a
        # dev machine without nmcli/bluetoothctl just keeps the stored default.
        actual_wifi = connectivity.wifi_is_enabled()
        if actual_wifi is not None:
            self.settings.set("connectivity", "wifi", actual_wifi)
        actual_bt = connectivity.bluetooth_is_enabled()
        if actual_bt is not None:
            self.settings.set("connectivity", "bluetooth", actual_bt)

    # --- home --------------------------------------------------------------
    def home_items(self):
        items = [{"key": "library", "label": "Bibliothek", "sub": "Alle Playlists durchsuchen", "icon": "♪"}]
        if self.last_played:
            pl_idx, tr_idx = self.last_played
            track = LIBRARY[pl_idx][1][tr_idx]
            items.append({"key": "resume", "label": track[0],
                          "sub": f"Fortsetzen · {LIBRARY[pl_idx][0]}",
                          "icon": ">", "color": PLAYLIST_COLORS[pl_idx % len(PLAYLIST_COLORS)],
                          "seed": f"tr-{LIBRARY[pl_idx][0]}-{track[0]}"})
        items.append({"key": "settings", "label": "Einstellungen", "sub": "WLAN, Bluetooth, mehr", "icon": "⚙"})
        return items

    def home_move(self, direction):
        n = len(self.home_items())
        self.home_sel = (self.home_sel + direction) % n

    def home_open(self):
        item = self.home_items()[self.home_sel]
        if item["key"] == "library":
            self.screen = SCREEN_LIBRARY
            self.library_sel = 0
        elif item["key"] == "settings":
            self.screen = SCREEN_SETTINGS_ROOT
            self.settings_root_sel = 0
        elif item["key"] == "resume":
            pl_idx, tr_idx = self.last_played
            self.current_playlist_idx = pl_idx
            self.now_playing = NowPlaying(LIBRARY[pl_idx][1], tr_idx, pl_idx)
            self.screen = SCREEN_PLAYING

    # --- now playing: volume (encoder in ENCODER_MODE_VOLUME) ----------------
    VOLUME_STEP = 5

    def adjust_volume(self, direction):
        vol = self.settings.get("connectivity", "volume")
        vol = max(0, min(100, vol + direction * self.VOLUME_STEP))
        self.settings.set("connectivity", "volume", vol)
        connectivity.set_system_volume(vol)
        return vol

    # --- library / playlist --------------------------------------------------
    def library_move(self, direction):
        self.library_sel = (self.library_sel + direction) % len(LIBRARY)

    def library_open(self):
        self.current_playlist_idx = self.library_sel
        self.playlist_sel = 0
        self.screen = SCREEN_PLAYLIST

    def playlist_move(self, direction):
        n = len(LIBRARY[self.current_playlist_idx][1])
        self.playlist_sel = (self.playlist_sel + direction) % n

    def playlist_open(self):
        tracks = LIBRARY[self.current_playlist_idx][1]
        self.now_playing = NowPlaying(tracks, self.playlist_sel, self.current_playlist_idx)
        self.last_played = (self.current_playlist_idx, self.playlist_sel)
        self.screen = SCREEN_PLAYING

    # --- settings --------------------------------------------------------------
    def settings_root_move(self, direction):
        self.settings_root_sel = (self.settings_root_sel + direction) % len(SETTINGS_CATEGORIES)

    def settings_root_open(self):
        self.settings_category = SETTINGS_CATEGORIES[self.settings_root_sel]["key"]
        self.settings_detail_sel = 0
        self.screen = SCREEN_SETTINGS_DETAIL

    def settings_detail_move(self, direction):
        items = SETTINGS_ITEMS[self.settings_category]
        self.settings_detail_sel = (self.settings_detail_sel + direction) % len(items)

    def settings_detail_activate(self):
        cat = self.settings_category
        item = SETTINGS_ITEMS[cat][self.settings_detail_sel]
        key, kind = item["key"], item["type"]

        if kind == "toggle":
            new_val = not self.settings.get(cat, key)
            self.settings.set(cat, key, new_val)
        elif kind == "stepper":
            val = self.settings.get(cat, key) + 1
            if val > item["max"]:
                val = item["min"]
            self.settings.set(cat, key, val)
        elif kind == "choice":
            values = [c[0] for c in item["choices"]]
            cur = self.settings.get(cat, key)
            nxt = values[(values.index(cur) + 1) % len(values)] if cur in values else values[0]
            self.settings.set(cat, key, nxt)
        elif kind == "action":
            self._settings_action(key)

    def _settings_action(self, key):
        if key == "account":
            if sync_youtube.is_account_linked():
                sync_youtube.unlink_account()
                self.settings.set("sync", "account_linked", False)
            else:
                self.start_sync_login()
        elif key == "sync_now":
            self.start_sync_now()
        elif key == "bluetooth_menu":
            self.start_bt_menu()
        elif key == "wifi_menu":
            self.start_wifi_menu()
        elif key == "playlists":
            self.start_playlist_manage()

    # --- wifi: menu (toggle + known networks + "connect new") -----------------
    def start_wifi_menu(self):
        self.screen = SCREEN_WIFI_MENU
        self.wifi_menu_sel = 0
        self.refresh_wifi_menu()

    def refresh_wifi_menu(self):
        self.wifi_known_networks = connectivity.wifi_known_connections()

    def wifi_menu_items(self):
        wifi_on = self.settings.get("connectivity", "wifi")
        items = [{"kind": "toggle", "label": "WLAN", "sub": "An" if wifi_on else "Aus", "on": wifi_on}]
        for n in self.wifi_known_networks:
            items.append({"kind": "network", "label": n["ssid"], "ssid": n["ssid"], "name": n["name"],
                          "connected": n.get("connected", False),
                          "sub": "Verbunden" if n.get("connected") else "Gespeichert"})
        items.append({"kind": "connect_new", "label": "Neues WLAN verbinden", "sub": ""})
        return items

    def wifi_menu_move(self, direction):
        self.wifi_menu_sel = (self.wifi_menu_sel + direction) % len(self.wifi_menu_items())

    def wifi_menu_open(self):
        item = self.wifi_menu_items()[self.wifi_menu_sel]
        if item["kind"] == "toggle":
            new_val = not self.settings.get("connectivity", "wifi")
            if connectivity.wifi_set_enabled(new_val):
                self.settings.set("connectivity", "wifi", new_val)
                # Flipping the radio changes every network's "connected" state
                # (all go False on "off") - refresh so the list doesn't keep
                # showing a network as connected once the radio is actually down.
                self.refresh_wifi_menu()
        elif item["kind"] == "network":
            self.wifi_device_name = item["name"]
            self.wifi_device_ssid = item["ssid"]
            self.wifi_device_connected = item["connected"]
            self.wifi_device_sel = 0
            self.wifi_action_status = None
            self.wifi_action_error = None
            self.screen = SCREEN_WIFI_DEVICE
        elif item["kind"] == "connect_new":
            self.start_wifi_scan()

    # --- wifi: per-network connect/disconnect/forget --------------------------
    def wifi_device_items(self):
        return [
            {"key": "connect_toggle", "label": "Trennen" if self.wifi_device_connected else "Verbinden"},
            {"key": "forget", "label": "Entfernen"},
        ]

    def wifi_device_move(self, direction):
        self.wifi_device_sel = (self.wifi_device_sel + direction) % len(self.wifi_device_items())

    def wifi_device_select(self):
        """Returns (action, connection_name) for main.py's WifiWorker to run, or
        None if an action is already in flight. Uses the nmcli connection NAME
        (self.wifi_device_name), not the SSID - connection up/down/delete are
        addressed by profile name, which isn't always the same string (see
        connectivity.wifi_known_connections)."""
        if self.wifi_action_status == "working":
            return None
        item = self.wifi_device_items()[self.wifi_device_sel]
        self.wifi_action_status = "working"
        if item["key"] == "connect_toggle":
            return ("disconnect" if self.wifi_device_connected else "connect"), self.wifi_device_name
        return "forget", self.wifi_device_name

    def wifi_device_action_done(self, success, error=None):
        if success:
            self.wifi_action_status = None
            self.refresh_wifi_menu()
            self.screen = SCREEN_WIFI_MENU
            n = len(self.wifi_menu_items())
            if self.wifi_menu_sel >= n:
                self.wifi_menu_sel = max(0, n - 1)
        else:
            self.wifi_action_status = "error"
            self.wifi_action_error = error

    # --- wifi: scan + connect to a NEW network ---------------------------------
    # Scanning/connecting are slow (seconds) and run on a background thread owned
    # by main.py's WifiWorker, same reasoning as BTWorker/SyncWorker - these
    # methods only touch state, the caller is responsible for starting the thread.
    def start_wifi_scan(self):
        self.screen = SCREEN_WIFI_SCAN
        self.wifi_scan_networks = []
        self.wifi_scan_sel = 0
        self.wifi_scanning = True
        self.wifi_connect_status = None
        self.wifi_connect_error = None

    def wifi_scan_done(self, networks):
        """Also called by main.py's periodic background re-scan while sitting on
        SCREEN_WIFI_SCAN (see WIFI_RESCAN_INTERVAL there), not just the initial
        scan - keeps the list "live" so a network that wasn't broadcasting yet
        (e.g. a phone hotspot only just turned on) shows up without the user
        having to back out and re-enter the screen. Since the list can reorder
        or gain/lose entries between rescans, keep the highlighted selection on
        the same SSID by identity rather than by index, falling back to the top
        if it's no longer there."""
        prev_ssid = (self.wifi_scan_networks[self.wifi_scan_sel]["ssid"]
                     if self.wifi_scan_networks else None)
        self.wifi_scan_networks = networks
        self.wifi_scanning = False
        self.wifi_scan_sel = next((i for i, n in enumerate(networks) if n["ssid"] == prev_ssid), 0)

    def wifi_scan_move(self, direction):
        if self.wifi_scan_networks:
            self.wifi_scan_sel = (self.wifi_scan_sel + direction) % len(self.wifi_scan_networks)

    def wifi_scan_select(self):
        """Returns (ssid, password) for main.py's WifiWorker to connect with
        immediately (open network, or one already known to nmcli), or None if
        it switched to the password-entry screen instead (new secured network) -
        or if nothing is selectable (still scanning, empty list, already busy)."""
        if not self.wifi_scan_networks or self.wifi_connect_status == "connecting":
            return None
        net = self.wifi_scan_networks[self.wifi_scan_sel]
        known_ssids = {n["ssid"] for n in self.wifi_known_networks}
        if not net["secured"] or net["ssid"] in known_ssids:
            self.wifi_connect_status = "connecting"
            self.wifi_pending_ssid = net["ssid"]
            return net["ssid"], None
        self.start_wifi_password_entry(net["ssid"])
        return None

    def wifi_connect_done(self, success, error=None):
        if success:
            self.wifi_connect_status = None
            self.wifi_pending_ssid = None
            self.refresh_wifi_menu()
            self.screen = SCREEN_WIFI_MENU
            n = len(self.wifi_menu_items())
            if self.wifi_menu_sel >= n:
                self.wifi_menu_sel = max(0, n - 1)
        else:
            self.wifi_connect_status = "error"
            self.wifi_connect_error = error

    # --- wifi: password entry (encoder letter-wheel, click-wheel iPod style) ---
    def start_wifi_password_entry(self, ssid):
        self.screen = SCREEN_WIFI_PASSWORD
        self.wifi_pending_ssid = ssid
        self.wifi_password_chars = []
        self.wifi_password_char_idx = 0
        self.wifi_connect_status = None
        self.wifi_connect_error = None

    def wifi_password_rotate(self, direction):
        if self.wifi_connect_status is not None:
            return  # wheel isn't shown while "Verbinde..."/error feedback is - don't edit invisibly
        self.wifi_password_char_idx = (self.wifi_password_char_idx + direction) % len(WIFI_CHARSET)

    def wifi_password_current_char(self):
        return WIFI_CHARSET[self.wifi_password_char_idx]

    def wifi_password_confirm_char(self):
        if self.wifi_connect_status is not None:
            return
        self.wifi_password_chars.append(self.wifi_password_current_char())
        self.wifi_password_char_idx = 0

    def wifi_password_backspace(self):
        if self.wifi_connect_status is not None:
            return
        if self.wifi_password_chars:
            self.wifi_password_chars.pop()

    def wifi_password_text(self):
        return "".join(self.wifi_password_chars)

    def wifi_password_submit(self):
        """Returns (ssid, password) for main.py's WifiWorker to connect with, or
        None if a connect attempt from here is already in flight (guards against
        the button repeat-firing while nmcli is still working - WifiWorker's own
        thread-alive check already no-ops a stacked call, but the caller needs a
        signal too so it doesn't keep re-reading a stale (ssid, password))."""
        if self.wifi_connect_status == "connecting":
            return None
        self.wifi_connect_status = "connecting"
        return self.wifi_pending_ssid, self.wifi_password_text()

    # --- bluetooth: menu (toggle + known devices + "pair new") ----------------
    def start_bt_menu(self):
        self.screen = SCREEN_BT_MENU
        self.bt_menu_sel = 0
        self.refresh_bt_menu()

    def refresh_bt_menu(self):
        self.bt_known_devices = connectivity.bluetooth_known_devices()

    def bt_menu_items(self):
        bt_on = self.settings.get("connectivity", "bluetooth")
        items = [{"kind": "toggle", "label": "Bluetooth", "sub": "An" if bt_on else "Aus", "on": bt_on}]
        for d in self.bt_known_devices:
            items.append({"kind": "device", "label": d["name"] or d["mac"], "mac": d["mac"],
                          "connected": d.get("connected", False),
                          "sub": "Verbunden" if d.get("connected") else "Gekoppelt"})
        items.append({"kind": "pair_new", "label": "Neue Geraete koppeln", "sub": ""})
        return items

    def bt_menu_move(self, direction):
        self.bt_menu_sel = (self.bt_menu_sel + direction) % len(self.bt_menu_items())

    def bt_menu_open(self):
        item = self.bt_menu_items()[self.bt_menu_sel]
        if item["kind"] == "toggle":
            new_val = not self.settings.get("connectivity", "bluetooth")
            if connectivity.bluetooth_set_enabled(new_val):
                self.settings.set("connectivity", "bluetooth", new_val)
        elif item["kind"] == "device":
            self.bt_device_mac = item["mac"]
            self.bt_device_name = item["label"]
            self.bt_device_connected = item["connected"]
            self.bt_device_sel = 0
            self.bt_action_status = None
            self.bt_action_error = None
            self.screen = SCREEN_BT_DEVICE
        elif item["kind"] == "pair_new":
            self.start_bt_pairing()

    # --- bluetooth: per-device connect/disconnect/remove ----------------------
    def bt_device_items(self):
        return [
            {"key": "connect_toggle", "label": "Trennen" if self.bt_device_connected else "Verbinden"},
            {"key": "remove", "label": "Entfernen"},
        ]

    def bt_device_move(self, direction):
        self.bt_device_sel = (self.bt_device_sel + direction) % len(self.bt_device_items())

    def bt_device_select(self):
        """Returns (action, mac) for main.py's BTWorker to run, or None if an
        action is already in flight."""
        if self.bt_action_status == "working":
            return None
        item = self.bt_device_items()[self.bt_device_sel]
        self.bt_action_status = "working"
        if item["key"] == "connect_toggle":
            return ("disconnect" if self.bt_device_connected else "connect"), self.bt_device_mac
        return "remove", self.bt_device_mac

    def bt_device_action_done(self, success, error=None):
        if success:
            self.bt_action_status = None
            self.refresh_bt_menu()
            self.screen = SCREEN_BT_MENU
            n = len(self.bt_menu_items())
            if self.bt_menu_sel >= n:
                self.bt_menu_sel = max(0, n - 1)
        else:
            self.bt_action_status = "error"
            self.bt_action_error = error

    # --- bluetooth: scan + pair a NEW device -----------------------------------
    # Scanning and pairing themselves are slow (seconds) and run on a background
    # thread owned by main.py's BTWorker, same reasoning as SyncWorker for the
    # YouTube login poll/sync - these methods only touch state, the caller
    # (main.py) is responsible for actually starting that thread.
    def start_bt_pairing(self):
        self.screen = SCREEN_BT_PAIRING
        self.bt_scan_devices = []
        self.bt_scan_sel = 0
        self.bt_scanning = True
        self.bt_pair_status = None
        self.bt_pair_error = None
        self.bt_pair_device_name = None

    def bt_scan_done(self, devices):
        self.bt_scan_devices = devices
        self.bt_scanning = False

    def bt_scan_move(self, direction):
        if self.bt_scan_devices:
            self.bt_scan_sel = (self.bt_scan_sel + direction) % len(self.bt_scan_devices)

    def bt_scan_select(self):
        """Returns the MAC to pair with, or None if there's nothing to select
        (still scanning, empty list, or a pairing attempt already in flight)."""
        if not self.bt_scan_devices or self.bt_pair_status == "pairing":
            return None
        device = self.bt_scan_devices[self.bt_scan_sel]
        self.bt_pair_status = "pairing"
        self.bt_pair_device_name = device["name"] or device["mac"]
        return device["mac"]

    def bt_pair_done(self, success, error=None):
        self.bt_pair_status = "done" if success else "error"
        self.bt_pair_error = error

    # --- sync: device-flow login ---------------------------------------------
    def start_sync_login(self):
        self.sync_login_error = None
        try:
            self.sync_login_info = sync_youtube.start_device_flow()
            self.screen = SCREEN_SYNC_LOGIN
        except sync_youtube.NoCredentialsError as e:
            self.sync_login_error = str(e)
            self.screen = SCREEN_SYNC_LOGIN

    def poll_sync_login(self):
        """Call periodically while on SCREEN_SYNC_LOGIN. Returns True once done (success
        or error) so main.py knows whether the screen needs a fresh render."""
        if not self.sync_login_info:
            return False
        try:
            done = sync_youtube.poll_device_flow(self.sync_login_info["device_code"])
        except RuntimeError as e:
            self.sync_login_error = str(e)
            self.sync_login_info = None
            return True
        if done:
            self.settings.set("sync", "account_linked", True)
            self.sync_login_info = None
            self.screen = SCREEN_SETTINGS_DETAIL
            return True
        return False

    # --- sync: now -------------------------------------------------------------
    def start_sync_now(self):
        self.sync_progress = (0, 1, "")
        self.sync_error = None
        self.screen = SCREEN_SYNC_PROGRESS

    def sync_progress_callback(self, current, total, track_name):
        self.sync_progress = (current, total, track_name)

    def sync_done(self):
        return self.sync_progress and self.sync_progress[0] >= self.sync_progress[1]

    # --- playlist management: exclude from sync / delete to free space --------
    def start_playlist_manage(self):
        self.screen = SCREEN_PLAYLIST_MANAGE
        self.playlist_manage_sel = 0

    def playlist_manage_move(self, direction):
        if LIBRARY:
            self.playlist_manage_sel = (self.playlist_manage_sel + direction) % len(LIBRARY)

    def playlist_manage_open(self):
        if not LIBRARY:
            return
        self.playlist_manage_idx = self.playlist_manage_sel
        self.playlist_manage_detail_sel = 0
        self.playlist_manage_confirm_delete = False
        self.screen = SCREEN_PLAYLIST_MANAGE_DETAIL

    def playlist_manage_detail_name(self):
        return LIBRARY[self.playlist_manage_idx][0]

    def playlist_manage_is_excluded(self):
        return self.playlist_manage_detail_name() in self.settings.get("sync", "excluded_playlists")

    def playlist_manage_detail_items(self):
        exclude_label = ("Sync wieder einschliessen" if self.playlist_manage_is_excluded()
                          else "Von Sync ausschliessen")
        delete_label = "Wirklich loeschen?" if self.playlist_manage_confirm_delete else "Playlist loeschen"
        return [
            {"key": "exclude", "label": exclude_label},
            {"key": "delete", "label": delete_label},
        ]

    def playlist_manage_detail_move(self, direction):
        n = len(self.playlist_manage_detail_items())
        self.playlist_manage_detail_sel = (self.playlist_manage_detail_sel + direction) % n

    def playlist_manage_detail_select(self):
        item = self.playlist_manage_detail_items()[self.playlist_manage_detail_sel]
        if item["key"] == "exclude":
            name = self.playlist_manage_detail_name()
            excluded = set(self.settings.get("sync", "excluded_playlists"))
            excluded.symmetric_difference_update({name})
            self.settings.set("sync", "excluded_playlists", sorted(excluded))
            return
        # "delete" - a destructive action gets a confirm-then-commit gesture
        # instead of firing on the first click, same reasoning as anywhere else
        # an irreversible action sits behind a single button on this device.
        if not self.playlist_manage_confirm_delete:
            self.playlist_manage_confirm_delete = True
            return
        self._delete_playlist(self.playlist_manage_idx)

    def _delete_playlist(self, idx):
        name = LIBRARY[idx][0]
        sync_youtube.delete_playlist(name)
        reload_library()
        # Deleting a playlist shifts every LIBRARY index after it, which would
        # silently point now_playing/last_played/current_playlist_idx at the
        # wrong playlist if left alone - simplest safe rule is to drop that
        # state entirely rather than trying to shift every index that might
        # reference it (a playlist delete is rare and deliberate; losing
        # "resume last track" is a fine trade for never showing a mismatched
        # track/cover).
        self.now_playing = None
        self.last_played = None
        self.library_sel = 0
        self.current_playlist_idx = 0
        self.playlist_manage_confirm_delete = False
        self.playlist_manage_sel = min(self.playlist_manage_sel, max(0, len(LIBRARY) - 1))
        self.screen = SCREEN_PLAYLIST_MANAGE

    # --- back navigation ---------------------------------------------------
    def back(self):
        if self.screen == SCREEN_PLAYING:
            self.now_playing = None
            self.screen = SCREEN_HOME
        elif self.screen == SCREEN_PLAYLIST:
            self.screen = SCREEN_LIBRARY
        elif self.screen == SCREEN_LIBRARY:
            self.screen = SCREEN_HOME
        elif self.screen == SCREEN_SETTINGS_DETAIL:
            self.screen = SCREEN_SETTINGS_ROOT
        elif self.screen == SCREEN_SETTINGS_ROOT:
            self.screen = SCREEN_HOME
        elif self.screen in (SCREEN_SYNC_LOGIN, SCREEN_SYNC_PROGRESS):
            self.sync_login_info = None
            self.screen = SCREEN_SETTINGS_DETAIL
        elif self.screen == SCREEN_BT_DEVICE:
            self.screen = SCREEN_BT_MENU
        elif self.screen == SCREEN_BT_MENU:
            self.screen = SCREEN_SETTINGS_DETAIL
        elif self.screen == SCREEN_BT_PAIRING:
            self.refresh_bt_menu()
            self.screen = SCREEN_BT_MENU
        elif self.screen == SCREEN_WIFI_DEVICE:
            self.screen = SCREEN_WIFI_MENU
        elif self.screen == SCREEN_WIFI_MENU:
            self.screen = SCREEN_SETTINGS_DETAIL
        elif self.screen == SCREEN_WIFI_PASSWORD:
            self.screen = SCREEN_WIFI_SCAN
        elif self.screen == SCREEN_WIFI_SCAN:
            self.refresh_wifi_menu()
            self.screen = SCREEN_WIFI_MENU
        elif self.screen == SCREEN_PLAYLIST_MANAGE_DETAIL:
            self.playlist_manage_confirm_delete = False
            self.screen = SCREEN_PLAYLIST_MANAGE
        elif self.screen == SCREEN_PLAYLIST_MANAGE:
            self.screen = SCREEN_SETTINGS_DETAIL
