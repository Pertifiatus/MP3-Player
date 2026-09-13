"""Main UI loop for the front display (GC9A01), driven by ButtonBox + QMI8658A."""
import os
import random
import threading
import time

import numpy as np
import board
import digitalio
import fourwire
import displayio
import adafruit_gc9a01a

import player
import ui_state
import ui_render
import connectivity
import sync_youtube
from buttonbox import ButtonBox, ThreadedPoller
from power_button import PowerButton, trigger_shutdown
from settings import Settings
from qmi8658 import QMI8658, orientation, magnitude, SHAKE_THRESHOLD_G

# Real per-frame cost measured on-device: ~83ms (37ms render + 46ms SPI push,
# see journalctl -u mp3player.service). The previous 250ms value was an
# untested guess and throttled the disc animation to a choppy 4fps despite
# the hardware comfortably sustaining ~10fps - set close to the real floor,
# not the old guess.
PLAYING_REDRAW_INTERVAL = 0.1
MOTION_POLL_INTERVAL = 0.1
BT_REDRAW_INTERVAL = 0.5  # catches scan/pair completion without needing a button press
WIFI_REDRAW_INTERVAL = 0.5  # same reasoning, for WifiWorker's scan/connect
WIFI_RESCAN_INTERVAL = 6  # re-scan periodically while sitting on the WLAN list, so a
                          # network that wasn't broadcasting yet (e.g. a phone hotspot
                          # just switched on) shows up without leaving and re-entering
SYNC_REDRAW_INTERVAL = 0.5  # same reasoning - device-flow poll / download progress land via SyncWorker


def init_display():
    displayio.release_displays()
    backlight = digitalio.DigitalInOut(board.D13)
    backlight.direction = digitalio.Direction.OUTPUT
    backlight.value = True
    spi = board.SPI()
    display_bus = fourwire.FourWire(
        spi, command=board.D24, chip_select=board.CE0, reset=board.D25, baudrate=24000000
    )
    # adafruit_gc9a01a.GC9A01A(...) runs the chip's power-on/gamma/sleep-out/
    # COLMOD/MADCTL init sequence over display_bus - that's the only thing it's
    # still used for below (see FrameSink). Keep the returned object alive so
    # it isn't garbage-collected/released, even though nothing reads its
    # root_group after this.
    display = adafruit_gc9a01a.GC9A01A(display_bus, width=240, height=240)
    return display_bus, display, backlight


CMD_CASET = 0x2A  # column address set
CMD_RASET = 0x2B  # row address set
CMD_RAMWR = 0x2C  # memory write


class FrameSink:
    """Pushes rendered PIL frames straight to the display over SPI, bypassing
    displayio's Bitmap/TileGrid/ColorConverter machinery entirely.

    History (see NOTES_FOR_PER.md): the old OnDiskBitmap path re-read every pixel
    from disk each frame (~700-900ms/frame). Moving to an in-RAM Bitmap written
    pixel-by-pixel via bitmap[i]=value was STILL ~700-900ms/frame, because
    Bitmap.__setitem__ allocates a fresh Area() and recomputes the dirty rect on
    every single call. A bulk buffer write into the Bitmap fixed THAT (down to a
    few ms) - but displayio still has to walk the whole dirty bitmap pixel-by-pixel
    in pure Python (TileGrid._fill_area(), confirmed in Adafruit_Blinka_Displayio's
    source) to compose it back out over SPI on every refresh. That's a second,
    separate slow Python loop inside displayio itself, unavoidable as long as
    anything goes through Bitmap/TileGrid/Group.

    Real fix: skip displayio's composition layer completely. FourWire.send(command,
    data) is a public method (confirmed in the installed fourwire package) that
    does a raw SPI command+data transfer with correct CS/DC handling - exactly
    what a bare-metal/Arduino GC9A01 driver does. Standard MIPI DBI command set
    (same numbering as ILI9341/ST7789/GC9A01): 0x2A/0x2B set the column/row
    address window, 0x2C streams raw pixel bytes into it. The chip is already
    configured for RGB565 by adafruit_gc9a01a's init sequence, so this only
    needs to send bytes - no separate reinit.
    """

    def __init__(self, display_bus, width=240, height=240):
        self.bus = display_bus
        self.width = width
        self.height = height
        self._caset = bytes([0, 0, (width - 1) >> 8, (width - 1) & 0xFF])
        self._raset = bytes([0, 0, (height - 1) >> 8, (height - 1) & 0xFF])

    def push(self, img):
        arr = np.asarray(img.convert("RGB"), dtype=np.uint16)
        rgb565 = (((arr[..., 0] & 0xF8) << 8) | ((arr[..., 1] & 0xFC) << 3) | (arr[..., 2] >> 3))
        # Big-endian (MSB first) on the wire - standard for this display family.
        # If colors come out wrong (swapped/garbled, as opposed to just a plain
        # wrong hue), switch this to "<u2" instead.
        pixel_bytes = rgb565.astype(">u2").tobytes()
        self.bus.send(CMD_CASET, self._caset)
        self.bus.send(CMD_RASET, self._raset)
        self.bus.send(CMD_RAMWR, pixel_bytes)


class SyncWorker:
    """Runs the slow network parts of sync_youtube in a background thread so button
    polling keeps working while we wait on a device-flow approval or a download.
    Communicates back via plain attribute writes on `state` - no lock, acceptable
    for this simple read-mostly-render / write-mostly-worker pattern in CPython."""

    def __init__(self, state):
        self.state = state
        self._thread = None

    def start_login_poll(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._login_poll_loop, daemon=True)
        self._thread.start()

    def _login_poll_loop(self):
        info = self.state.sync_login_info
        if not info:
            return
        interval = info.get("interval", 5)
        while self.state.sync_login_info is info:
            time.sleep(interval)
            if self.state.sync_login_info is not info:
                return
            self.state.poll_sync_login()
            if self.state.sync_login_info is None:
                return

    def start_sync(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()

    def _sync_loop(self):
        try:
            excluded = self.state.settings.get("sync", "excluded_playlists")
            sync_youtube.sync_library(self.state.sync_progress_callback, excluded=excluded)
        except RuntimeError as e:
            self.state.sync_error = str(e)


class BTWorker:
    """Runs bluetooth scan/pair in a background thread - same reasoning as
    SyncWorker above: both block for seconds and must not freeze button polling."""

    def __init__(self, state):
        self.state = state
        self._thread = None

    def start_scan(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._scan, daemon=True)
        self._thread.start()

    def _scan(self):
        devices = connectivity.bluetooth_scan()
        self.state.bt_scan_done(devices)

    def start_pair(self, mac):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._pair, args=(mac,), daemon=True)
        self._thread.start()

    def _pair(self, mac):
        success, error = connectivity.bluetooth_pair(mac)
        self.state.bt_pair_done(success, error)

    def start_device_action(self, action, mac):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._device_action, args=(action, mac), daemon=True)
        self._thread.start()

    def _device_action(self, action, mac):
        fn = {"connect": connectivity.bluetooth_connect,
              "disconnect": connectivity.bluetooth_disconnect,
              "remove": connectivity.bluetooth_remove}[action]
        success, error = fn(mac)
        self.state.bt_device_action_done(success, error)


class WifiWorker:
    """Runs WiFi scan/connect in a background thread - same reasoning as BTWorker."""

    def __init__(self, state):
        self.state = state
        self._thread = None

    def start_scan(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._scan, daemon=True)
        self._thread.start()

    def _scan(self):
        networks = connectivity.wifi_scan()
        self.state.wifi_scan_done(networks)

    def start_connect(self, ssid, password):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._connect, args=(ssid, password), daemon=True)
        self._thread.start()

    def _connect(self, ssid, password):
        success, error = connectivity.wifi_connect(ssid, password)
        self.state.wifi_connect_done(success, error)

    def start_device_action(self, action, ssid):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._device_action, args=(action, ssid), daemon=True)
        self._thread.start()

    def _device_action(self, action, ssid):
        fn = {"connect": connectivity.wifi_connect_known,
              "disconnect": connectivity.wifi_disconnect,
              "remove": connectivity.wifi_forget}[action]
        success, error = fn(ssid)
        self.state.wifi_device_action_done(success, error)


class PlaybackSync:
    """Keeps the real mpv player (see player.py) in sync with ui_state.NowPlaying
    - which track is loaded, play/pause, and position - falling back to
    NowPlaying's own simulated tick() when the current track has no real
    downloaded file (demo library, or one a sync skipped/hasn't reached yet).

    Loading a NEW track runs on a background thread, unlike the plain
    position()/pause()/resume() polling below: the very first play() this
    process ever does has to spawn mpv itself and wait for its IPC socket to
    appear (player.py's AudioPlayer._ensure_started()), which can take ~1-2s
    on this hardware - confirmed live to freeze the whole render loop and
    button polling for that long when run inline, which looked exactly like
    the app hanging. AudioPlayer._command() is lock-protected, so this thread
    and the main-thread polling below can't corrupt each other's IPC traffic
    by talking to mpv at the same time."""

    def __init__(self, audio_player):
        self.player = audio_player
        self._track_key = None
        self._pending_key = None  # track_key currently loading on the background thread
        self._playing = None
        self._thread = None

    def _reset(self):
        if self._track_key is not None or self._pending_key is not None:
            self.player.stop()
        self._track_key = None
        self._pending_key = None
        self._playing = None

    def _load(self, file_path, track_key, playing):
        print(f"[playback] _load starting: track_key={track_key} file={file_path!r} playing={playing}", flush=True)
        try:
            self.player.play(file_path)
            print(f"[playback] play() returned OK for {track_key}", flush=True)
            if not playing:
                self.player.pause()
            self._track_key = track_key
        except Exception as e:
            print(f"[playback] _load EXCEPTION for {track_key}: {type(e).__name__}: {e}", flush=True)
            raise
        finally:
            # Clear the pending marker even if play() raised (e.g. mpv's
            # connection genuinely dropped) - otherwise sync() would treat this
            # track_key as "still loading" forever and never retry it.
            self._pending_key = None

    def sync(self, state):
        np = state.now_playing
        if np is None:
            self._reset()
            return

        file_path = np.current_file()
        if not file_path or not os.path.exists(file_path):
            self._reset()
            np.tick()  # demo/no-file track - keep the old simulated behavior
            return

        track_key = (np.playlist_idx, np.index)
        if track_key not in (self._track_key, self._pending_key):
            print(f"[playback] sync(): new track_key={track_key}, spawning load thread "
                  f"(prev track_key={self._track_key}, pending={self._pending_key})", flush=True)
            self._pending_key = track_key
            self._playing = np.playing
            self._thread = threading.Thread(target=self._load, args=(file_path, track_key, np.playing), daemon=True)
            self._thread.start()
            return
        if track_key == self._pending_key:
            return  # still loading in the background - nothing to poll yet

        if self._playing != np.playing:
            (self.player.resume() if np.playing else self.player.pause())
            self._playing = np.playing

        # A track we believe is loaded (track_key == self._track_key) but that
        # mpv now reports idle for has ended - naturally, or it failed to open,
        # either way there's nothing left to poll a position from - see
        # player.is_idle()'s docstring for why this replaced eof-reached.
        if self.player.is_idle():
            np.skip(1)
            self._track_key = None  # force a fresh loadfile on the next sync() call
            return

        pos = self.player.position()
        if pos is not None:
            np.position = pos


# Colors for the knob's skip<->volume mode-change LED cue (main board LED index
# 4, see led_service.py) - yellow/2s entering volume mode, a quick blue blip
# back to skip. Matches ui_state.ENCODER_MODE_* semantics, not a UI palette
# constant, so it lives here next to the code that fires it.
_MODE_CUE_VOLUME = ([255, 204, 0], 2.0)
_MODE_CUE_SKIP = ([10, 132, 255], 0.6)


def handle_event(state, event, worker, bt_worker, wifi_worker, audio_player, knob_held, knob_rotated_while_held):
    screen = state.screen

    if event["type"] == "rotate":
        d = event["direction"]
        if screen == ui_state.SCREEN_HOME:
            state.home_move(d)
        elif screen == ui_state.SCREEN_LIBRARY:
            state.library_move(d)
        elif screen == ui_state.SCREEN_PLAYLIST:
            state.playlist_move(d)
        elif screen == ui_state.SCREEN_PLAYING and state.now_playing:
            np = state.now_playing
            if knob_held:
                # Holding the knob down and turning scrubs the current track,
                # regardless of skip/volume mode - clamped inside the track by
                # NowPlaying.scrub() itself (never wraps to another track).
                np.scrub(d)
                file_path = np.current_file()
                if file_path and os.path.exists(file_path):
                    audio_player.seek(np.position)
            elif np.encoder_mode == ui_state.ENCODER_MODE_VOLUME:
                state.adjust_volume(d)
            else:
                np.skip(d)
        elif screen == ui_state.SCREEN_SETTINGS_ROOT:
            state.settings_root_move(d)
        elif screen == ui_state.SCREEN_SETTINGS_DETAIL:
            state.settings_detail_move(d)
        elif screen == ui_state.SCREEN_BT_MENU:
            state.bt_menu_move(d)
        elif screen == ui_state.SCREEN_BT_DEVICE:
            state.bt_device_move(d)
        elif screen == ui_state.SCREEN_BT_PAIRING:
            state.bt_scan_move(d)
        elif screen == ui_state.SCREEN_WIFI_MENU:
            state.wifi_menu_move(d)
        elif screen == ui_state.SCREEN_WIFI_DEVICE:
            state.wifi_device_move(d)
        elif screen == ui_state.SCREEN_WIFI_SCAN:
            state.wifi_scan_move(d)
        elif screen == ui_state.SCREEN_WIFI_PASSWORD:
            state.wifi_password_rotate(d)
        elif screen == ui_state.SCREEN_PLAYLIST_MANAGE:
            state.playlist_manage_move(d)
        elif screen == ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL:
            state.playlist_manage_detail_move(d)
        else:
            return False
        return True

    # The knob's click action on the Playing screen fires on release, not
    # press (every other screen's knob click still fires on button_down
    # below) - it needs to know whether a rotate happened while held (a scrub
    # gesture, handled above) before deciding whether this was actually a
    # plain click (toggle skip/volume mode) or not.
    if event["type"] == "button_up" and event["name"] == "knob":
        if screen == ui_state.SCREEN_PLAYING and state.now_playing and not knob_rotated_while_held:
            new_mode = state.now_playing.toggle_encoder_mode()
            color, duration = (_MODE_CUE_VOLUME if new_mode == ui_state.ENCODER_MODE_VOLUME else _MODE_CUE_SKIP)
            state.settings.set("led", "indicator", {"color": color, "duration": duration, "ts": time.time()})
            return True
        return False

    if event["type"] != "button_down":
        return False
    name = event["name"]

    if name == "knob":
        if screen == ui_state.SCREEN_PLAYING and state.now_playing:
            return False  # deferred to button_up above
        elif screen == ui_state.SCREEN_HOME:
            state.home_open()
        elif screen == ui_state.SCREEN_LIBRARY:
            state.library_open()
        elif screen == ui_state.SCREEN_PLAYLIST:
            state.playlist_open()
        elif screen == ui_state.SCREEN_SETTINGS_ROOT:
            state.settings_root_open()
        elif screen == ui_state.SCREEN_SETTINGS_DETAIL:
            state.settings_detail_activate()
            if state.screen == ui_state.SCREEN_SYNC_LOGIN:
                worker.start_login_poll()
            elif state.screen == ui_state.SCREEN_SYNC_PROGRESS:
                worker.start_sync()
        elif screen == ui_state.SCREEN_BT_MENU:
            state.bt_menu_open()
            if state.screen == ui_state.SCREEN_BT_PAIRING:
                bt_worker.start_scan()
        elif screen == ui_state.SCREEN_BT_DEVICE:
            action = state.bt_device_select()
            if action:
                bt_worker.start_device_action(*action)
        elif screen == ui_state.SCREEN_BT_PAIRING:
            mac = state.bt_scan_select()
            if mac:
                bt_worker.start_pair(mac)
        elif screen == ui_state.SCREEN_WIFI_MENU:
            state.wifi_menu_open()
            if state.screen == ui_state.SCREEN_WIFI_SCAN:
                wifi_worker.start_scan()
        elif screen == ui_state.SCREEN_WIFI_DEVICE:
            action = state.wifi_device_select()
            if action:
                wifi_worker.start_device_action(*action)
        elif screen == ui_state.SCREEN_WIFI_SCAN:
            result = state.wifi_scan_select()
            if result:
                wifi_worker.start_connect(*result)
        elif screen == ui_state.SCREEN_WIFI_PASSWORD:
            state.wifi_password_confirm_char()
        elif screen == ui_state.SCREEN_PLAYLIST_MANAGE:
            state.playlist_manage_open()
        elif screen == ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL:
            state.playlist_manage_detail_select()
        else:
            return False
        return True

    if name == "stop":
        if screen in (ui_state.SCREEN_LIBRARY, ui_state.SCREEN_PLAYLIST, ui_state.SCREEN_PLAYING,
                      ui_state.SCREEN_SETTINGS_ROOT, ui_state.SCREEN_SETTINGS_DETAIL,
                      ui_state.SCREEN_SYNC_LOGIN, ui_state.SCREEN_SYNC_PROGRESS,
                      ui_state.SCREEN_BT_MENU, ui_state.SCREEN_BT_DEVICE, ui_state.SCREEN_BT_PAIRING,
                      ui_state.SCREEN_WIFI_MENU, ui_state.SCREEN_WIFI_DEVICE, ui_state.SCREEN_WIFI_SCAN,
                      ui_state.SCREEN_WIFI_PASSWORD, ui_state.SCREEN_PLAYLIST_MANAGE,
                      ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL):
            state.back()
            return True
        return False

    if name == "play_pause" and screen == ui_state.SCREEN_PLAYING and state.now_playing:
        state.now_playing.toggle()
        return True

    if name == "play_pause" and screen == ui_state.SCREEN_WIFI_PASSWORD:
        result = state.wifi_password_submit()
        if result:
            wifi_worker.start_connect(*result)
        return True

    if name == "shuffle" and screen == ui_state.SCREEN_PLAYING:
        state.shuffle = not state.shuffle
        return True

    if name == "shuffle" and screen == ui_state.SCREEN_WIFI_PASSWORD:
        state.wifi_password_backspace()
        return True

    return False


def apply_motion_features(state):
    """Poll the IMU and apply shake-to-shuffle / flip-to-pause. Returns True if
    something changed that needs a redraw.

    ponytail: simple threshold logic, no cooldown beyond the fixed poll interval -
    a real shake gesture will likely fire this multiple times in a row. Add a
    cooldown/debounce once this is tested on real hardware.

    NOT implemented here: "Auto-Display-Wechsel" (auto_display_switch setting).
    That needs the back display driven from this same loop too (today it's a
    separate script) - the setting exists in Settings/UI already, but doesn't
    do anything yet. See NOTES_FOR_PER.md.
    """
    accel = state.imu.read_accel_g()
    mag = magnitude(accel)
    dirty = False

    if (state.settings.get("motion", "shake_to_shuffle") and mag > SHAKE_THRESHOLD_G
            and state.screen == ui_state.SCREEN_PLAYING and state.now_playing):
        state.now_playing.skip(random.choice([-1, 1]))
        state.shuffle = True
        dirty = True

    if state.settings.get("motion", "flip_to_pause"):
        # ponytail: "z-" assumed to mean "face down" - NOT verified against real
        # hardware (depends on how the QMI8658A sits relative to the two screens).
        # Hold the board face-down/face-up and check orientation() output first.
        if (orientation(accel) == "z-" and state.screen == ui_state.SCREEN_PLAYING
                and state.now_playing and state.now_playing.playing):
            state.now_playing.toggle()
            dirty = True

    return dirty


def main():
    settings = Settings()
    display_bus, display, backlight = init_display()
    sink = FrameSink(display_bus)
    buttons = ThreadedPoller(ButtonBox())
    power_button = PowerButton()
    state = ui_state.UIState(settings)
    worker = SyncWorker(state)
    bt_worker = BTWorker(state)
    wifi_worker = WifiWorker(state)
    playback = PlaybackSync(player.AudioPlayer())
    screen_off = False
    led_enabled_before_off = None

    try:
        state.imu = QMI8658()
    except Exception as e:
        print(f"QMI8658A nicht verfuegbar, Bewegungs-Features deaktiviert: {e}")
        state.imu = None

    sink.push(ui_render.render(state))
    last_playing_redraw = time.monotonic()
    last_motion_poll = time.monotonic()
    last_bt_redraw = time.monotonic()
    last_wifi_redraw = time.monotonic()
    last_wifi_rescan = time.monotonic()
    last_sync_redraw = time.monotonic()
    last_rendered_screen = state.screen
    knob_held = False
    knob_rotated_while_held = False

    while True:
        loop_start = time.monotonic()
        dirty = False
        poll_start = loop_start
        for event in buttons.poll():
            print(f"[{time.monotonic():.3f}] event: {event}", flush=True)
            if handle_event(state, event, worker, bt_worker, wifi_worker,
                             playback.player, knob_held, knob_rotated_while_held):
                dirty = True
            if event["type"] == "button_down" and event.get("name") == "knob":
                knob_held = True
                knob_rotated_while_held = False
            elif event["type"] == "button_up" and event.get("name") == "knob":
                knob_held = False
            elif event["type"] == "rotate" and knob_held:
                knob_rotated_while_held = True

        # Catches a screen change made by a background worker (SyncWorker,
        # BTWorker) between two of this loop's iterations - the periodic
        # BT_REDRAW_INTERVAL/SYNC_REDRAW_INTERVAL checks below only fire
        # while state.screen is STILL the async one; if a worker thread flips
        # it to a new screen in between, that check stops applying on the
        # very next iteration and the transition itself never gets a redraw
        # (silently stuck showing the old screen forever, confirmed live:
        # device-flow login succeeded and account_linked flipped to true in
        # settings.json, but the "Warte auf Bestaetigung" screen never
        # advanced to Settings). This is the general fix - whatever changed
        # state.screen, redraw once to catch up.
        if state.screen != last_rendered_screen:
            dirty = True
            if state.screen == ui_state.SCREEN_WIFI_SCAN:
                # the knob handler that opened this screen already triggered the
                # first scan - start the rescan clock now so it doesn't also
                # fire an immediate, redundant second one
                last_wifi_rescan = time.monotonic()

        pb_event = power_button.poll()
        if pb_event == "shutdown":
            sink.push(ui_render.render_shutdown())
            trigger_shutdown()
            return
        if pb_event == "short_press":
            screen_off = not screen_off
            if screen_off:
                led_enabled_before_off = settings.get("led", "enabled")
                settings.set("led", "enabled", False)
                backlight.value = False
            else:
                settings.set("led", "enabled", True if led_enabled_before_off is None else led_enabled_before_off)
                backlight.value = True
                dirty = True
        poll_ms = (time.monotonic() - poll_start) * 1000

        now = time.monotonic()

        # Not gated on screen==SCREEN_PLAYING: sync() also has to run right after
        # the user backs out (now_playing goes None) so it notices and stops the
        # real mpv player - otherwise audio keeps playing in the background with
        # the UI back on Home, since nothing else would ever call player.stop().
        playback.sync(state)
        if state.screen == ui_state.SCREEN_PLAYING and state.now_playing:
            if now - last_playing_redraw >= PLAYING_REDRAW_INTERVAL:
                last_playing_redraw = now
                dirty = True

        if state.imu is not None and now - last_motion_poll >= MOTION_POLL_INTERVAL:
            last_motion_poll = now
            if apply_motion_features(state):
                dirty = True

        # Not gated on bt_scanning/bt_pair_status: the exact moment scanning ends
        # but pairing hasn't started (list is ready, waiting for the user to pick
        # a device) matched NEITHER condition, so the redraw silently stopped
        # firing right when the list first became visible - confirmed live: the
        # screen stayed on "Suche Geraete..." until a button press forced a
        # redraw, which by then had already jumped straight into pairing.
        # SCREEN_BT_DEVICE has the same class of gap for its failure case: a
        # successful connect/disconnect/remove changes state.screen (caught by
        # the last_rendered_screen check above), but an error leaves it on the
        # same screen with only bt_action_status changing.
        if (state.screen in (ui_state.SCREEN_BT_PAIRING, ui_state.SCREEN_BT_DEVICE)
                and now - last_bt_redraw >= BT_REDRAW_INTERVAL):
            last_bt_redraw = now
            dirty = True

        # Same reasoning as the BT case above - WifiWorker's scan/connect run on a
        # background thread and only change wifi_scan_status/wifi_action_status,
        # not necessarily state.screen, while in flight. SCREEN_WIFI_PASSWORD needs
        # this too: a failed connect from there sets wifi_connect_status="error"
        # but stays on the same screen (confirmed live: the "Verbinde..."/error
        # feedback never appeared without this, looking like Play/Pause did nothing).
        if (state.screen in (ui_state.SCREEN_WIFI_SCAN, ui_state.SCREEN_WIFI_DEVICE, ui_state.SCREEN_WIFI_PASSWORD)
                and now - last_wifi_redraw >= WIFI_REDRAW_INTERVAL):
            last_wifi_redraw = now
            dirty = True

        # Keep the WLAN list "live" while the user is just browsing it (not mid
        # password-entry-triggered connect) - a network that wasn't broadcasting
        # yet when the screen first opened (e.g. a phone hotspot switched on
        # afterwards) would otherwise never appear without backing out and
        # re-entering "Neues WLAN verbinden". wifi_worker.start_scan() itself
        # already no-ops if a scan is still in flight, so this can't stack up.
        if (state.screen == ui_state.SCREEN_WIFI_SCAN and state.wifi_connect_status is None
                and now - last_wifi_rescan >= WIFI_RESCAN_INTERVAL):
            last_wifi_rescan = now
            wifi_worker.start_scan()

        if (state.screen in (ui_state.SCREEN_SYNC_LOGIN, ui_state.SCREEN_SYNC_PROGRESS)
                and now - last_sync_redraw >= SYNC_REDRAW_INTERVAL):
            last_sync_redraw = now
            dirty = True

        if dirty and not screen_off:
            render_start = time.monotonic()
            img = ui_render.render(state)
            render_ms = (time.monotonic() - render_start) * 1000
            push_start = time.monotonic()
            sink.push(img)
            push_ms = (time.monotonic() - push_start) * 1000
            total_ms = (time.monotonic() - loop_start) * 1000
            print(f"[{time.monotonic():.3f}] frame screen={state.screen} "
                  f"poll={poll_ms:.1f}ms render={render_ms:.1f}ms push={push_ms:.1f}ms "
                  f"total={total_ms:.1f}ms", flush=True)
            last_rendered_screen = state.screen

        time.sleep(0.01)


if __name__ == "__main__":
    main()
