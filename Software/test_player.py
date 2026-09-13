"""Pure-logic test for player.py's mpv IPC command framing - no real mpv needed.
Bypasses AudioPlayer._connect() (which starts a real mpv subprocess and unix
socket) with a fake file-like object, to isolate the JSON request/response
parsing itself - the part most likely to have a real bug (matching request_id,
skipping spontaneous event lines mpv can send).

python3 test_player.py
"""
import json

import player


class _FakeMpvFile:
    """Stands in for the socket.makefile() object - records what AudioPlayer
    writes, and hands back scripted lines (JSON, one per line) on readline()."""

    def __init__(self, response_lines):
        self.sent = []
        self._lines = iter(response_lines)

    def write(self, data):
        self.sent.append(json.loads(data.decode()))

    def readline(self):
        try:
            return (json.dumps(next(self._lines)) + "\n").encode()
        except StopIteration:
            return b""


def _player_with_fake_file(response_lines):
    p = player.AudioPlayer()
    p._file = _FakeMpvFile(response_lines)
    p._sock = object()  # anything not None, so _connect() thinks we're already connected
    return p


def test_command_returns_data_on_matching_reply():
    p = _player_with_fake_file([{"request_id": 1, "error": "success", "data": 42.5}])
    assert p.position() == 42.5
    assert p._file.sent == [{"command": ["get_property", "time-pos"], "request_id": 1}]


def test_command_skips_spontaneous_event_lines():
    # mpv can push unsolicited {"event": ...} lines on the same connection -
    # the reply matching our request_id might not be the very next line.
    p = _player_with_fake_file([
        {"event": "pause"},
        {"event": "seek"},
        {"request_id": 1, "error": "success", "data": True},
    ])
    assert p.is_idle() is True


def test_command_raises_on_mpv_error_and_position_returns_none():
    p = _player_with_fake_file([{"request_id": 1, "error": "property unavailable"}])
    assert p.position() is None  # position() swallows the error, returns None


def test_play_pause_resume_send_expected_commands():
    p = _player_with_fake_file([
        {"request_id": 1, "error": "success"},
        {"request_id": 2, "error": "success"},
        {"request_id": 3, "error": "success"},
    ])
    p.play("/music/track.opus")
    p.pause()
    p.resume()
    assert p._file.sent == [
        {"command": ["loadfile", "/music/track.opus", "replace"], "request_id": 1},
        {"command": ["set_property", "pause", True], "request_id": 2},
        {"command": ["set_property", "pause", False], "request_id": 3},
    ]


def test_seek_pause_resume_stop_swallow_transient_mpv_errors():
    # Regression guard: seek() right after loadfile (before mpv has caught up
    # to having a seekable file) used to raise this exact RuntimeError
    # uncaught, crashing the whole app - confirmed live. pause/resume/stop can
    # hit the same "not ready yet" window, so all four must degrade quietly;
    # the real state gets reconciled on the next sync() tick regardless.
    for method, args in [("seek", (5.0,)), ("pause", ()), ("resume", ()), ("stop", ())]:
        p = _player_with_fake_file([{"request_id": 1, "error": "property unavailable"}])
        getattr(p, method)(*args)  # must not raise


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests passed")
