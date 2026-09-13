"""Local audio playback via mpv's JSON IPC socket.

mpv, not ffplay: ffplay's pause/seek only work through keyboard input on an
SDL window, which doesn't exist on this headless device - mpv's
`--input-ipc-server` is a plain JSON-over-unix-socket control protocol built
for exactly this (embedding in another player), no display needed.

Needs `sudo apt install -y mpv` once on the Pi - not installed by default.

Output device: mpv auto-picks via its own audio-output autodetection, which
finds PipeWire's ALSA/pulse compatibility layers (pipewire-alsa/pipewire-pulse,
see connectivity.py's Bluetooth audio setup notes) - same "whatever the current
default sink is" behavior as any other Linux audio app, so switching
jack<->Bluetooth is still the plain ALSA/PipeWire default-sink change described
in CLAUDE.md, nothing player-specific to configure here.

Thread-safety: this class is called from both main.py's render loop (position()/
pause()/resume() to stay in sync each frame) and a background thread for the
initial play() of a new track (see main.py's PlaybackSync - loading a NEW track
can block for ~1-2s the first time, since mpv has to actually start as a
process and create its IPC socket, not just answer an already-connected one;
running that on the main thread froze the whole render loop/button polling for
that long, confirmed live). Both can end up calling _command() around the same
time, and the underlying socket is a single shared connection with no built-in
concurrency support of its own, so _command() is lock-protected here rather
than trusting every caller to serialize access itself.
"""
import json
import os
import socket
import subprocess
import threading
import time

_CONNECT_TIMEOUT_S = 2.0


class AudioPlayer:
    def __init__(self):
        # Per-process, not a shared fixed path: confirmed live that a second,
        # unrelated AudioPlayer (e.g. a one-off diagnostic script run over SSH
        # against the same machine, unaware the real mp3player.service was
        # already running) unlinks-and-rebinds a shared path out from under
        # whichever process bound it first, silently redirecting the FIRST
        # one's future reconnects to the SECOND one's mpv instance instead of
        # its own - the running service then talks to the wrong mpv, staying
        # stuck idle forever while the interloper actually plays audio.
        self._ipc_socket = f"/tmp/mp3player-mpv-{os.getpid()}.sock"
        self._proc = None
        self._sock = None
        self._file = None
        self._next_request_id = 1
        self._lock = threading.Lock()

    # --- process/connection lifecycle -----------------------------------------

    def _ensure_started(self):
        if self._proc and self._proc.poll() is None:
            return
        if os.path.exists(self._ipc_socket):
            os.remove(self._ipc_socket)
        # --ao=pipewire, not mpv's auto-detection: confirmed live that mpv
        # otherwise picks its "alsa" output on this device even though
        # "pipewire" is available (`mpv --ao=help` lists it) - and ALSA has no
        # real route to a Bluetooth sink here (no hardware card at all, no
        # bluealsa installed), so it fails with "[ao/alsa] Playback open
        # error: Host is down" the moment a track actually starts. PipeWire is
        # the one confirmed working backend for Bluetooth audio (see
        # connectivity.py's setup notes) - use it explicitly instead of
        # hoping auto-detection lands on it.
        #
        # stdout/stderr inherited (not DEVNULL): mpv's own error messages were
        # getting silently swallowed here, which is exactly what hid the real
        # cause above - inheriting lets them land in the same journal as
        # everything else main.py prints.
        self._proc = subprocess.Popen(
            ["mpv", "--idle=yes", "--no-video", "--quiet", "--ao=pipewire", f"--input-ipc-server={self._ipc_socket}"],
        )
        self._sock = None
        self._file = None

    def _connect(self):
        if self._sock is not None:
            return
        self._ensure_started()
        deadline = time.monotonic() + _CONNECT_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(_CONNECT_TIMEOUT_S)
                sock.connect(self._ipc_socket)
                self._sock = sock
                self._file = sock.makefile("rwb", buffering=0)
                return
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.05)
        raise RuntimeError("mpv IPC-Socket nicht erreichbar")

    def _reset_connection(self):
        for closer in (self._file, self._sock):
            try:
                if closer:
                    closer.close()
            except OSError:
                pass
        self._sock = None
        self._file = None

    # --- IPC command framing --------------------------------------------------

    def _command(self, *args):
        """Send one mpv IPC command, return its "data" field. Reads and discards
        any spontaneous event lines mpv sends until the reply matching this
        request's id shows up - see mpv's JSON IPC protocol docs."""
        with self._lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            payload = json.dumps({"command": list(args), "request_id": request_id}) + "\n"

            for attempt in (1, 2):  # one retry after a dropped connection
                try:
                    self._connect()
                    self._file.write(payload.encode())
                    while True:
                        line = self._file.readline()
                        if not line:
                            raise ConnectionError("mpv IPC connection closed")
                        msg = json.loads(line)
                        if msg.get("request_id") == request_id:
                            if msg.get("error") != "success":
                                raise RuntimeError(f"mpv: {args} -> {msg.get('error')}")
                            return msg.get("data")
                except (OSError, ConnectionError, json.JSONDecodeError):
                    self._reset_connection()
                    if attempt == 2:
                        raise

    # --- playback control ------------------------------------------------------

    def play(self, path):
        self._command("loadfile", path, "replace")

    def pause(self):
        self._ignore_transient("set_property", "pause", True)

    def resume(self):
        self._ignore_transient("set_property", "pause", False)

    def seek(self, seconds):
        """Silently no-ops if mpv isn't ready for it yet (e.g. the user scrubs
        right as a track starts loading, before its properties are seekable -
        confirmed live as an uncaught RuntimeError that crashed the whole app).
        The next sync() tick reconciles the real position/pause state anyway,
        so a dropped seek here isn't silently wrong, just a no-op for one tick."""
        self._ignore_transient("set_property", "time-pos", seconds)

    def stop(self):
        self._ignore_transient("stop")

    def _ignore_transient(self, *args):
        """Like _command(), but swallows mpv's own "command failed" replies
        (RuntimeError) - normal/expected right after a loadfile, before mpv has
        actually caught up to having a seekable/pausable file loaded. A real
        connection failure (OSError) still propagates from _command()."""
        try:
            self._command(*args)
        except RuntimeError:
            pass

    def position(self):
        """Current playback position in seconds, or None if nothing's loaded
        yet (mpv briefly has no time-pos right after loadfile)."""
        try:
            return self._command("get_property", "time-pos")
        except RuntimeError:
            return None

    def is_idle(self):
        """True once mpv has nothing loaded - a track that just finished
        naturally, one that failed to open, or simply nothing having been
        played yet all look identical from here (mpv unloads and goes idle in
        every case with --idle=yes). Prefer this over eof-reached to detect
        "this track ended": confirmed live that eof-reached is only true for
        a narrow instant before mpv auto-unloads back to idle, so a caller
        polling once per render tick can - and did - miss it entirely, silently
        never advancing to the next track. idle-active stays true afterwards,
        so it can't be missed the same way."""
        try:
            return bool(self._command("get_property", "idle-active"))
        except RuntimeError:
            return False
