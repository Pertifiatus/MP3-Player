"""Pure-logic test for sync_youtube.sync_library()'s bookkeeping - no network,
no real yt-dlp downloads. Covers the two things that went wrong live on
23.09.2026: failed downloads vanishing silently, and library.json only being
written at the very end of a sync.

python3 test_sync_youtube.py
"""
import json
import os
import tempfile

import yt_dlp

import sync_youtube as s


class _FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: "ok*" ids succeed, "bad*" raise
    DownloadError, "boom" raises something unexpected (aborts the sync)."""

    def __init__(self, opts):
        self.out_dir = os.path.dirname(opts["outtmpl"])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download):
        vid = url.rsplit("=", 1)[1]
        if vid.startswith("bad"):
            raise yt_dlp.DownloadError("rate-limited")
        if vid == "boom":
            raise OSError("network down")
        path = os.path.join(self.out_dir, vid + ".opus")
        open(path, "w").close()
        return {"title": vid, "uploader": "A", "duration": 1, "requested_downloads": [{"filepath": path}]}


def _setup(tmp, playlists):
    s.MUSIC_DIR = os.path.join(tmp, "music")
    s.LIBRARY_MANIFEST_PATH = os.path.join(tmp, "library.json")
    s.is_account_linked = lambda: True
    s.wifi_ok_for_sync = lambda: True
    s.list_public_playlists = lambda: [(name, name, None) for name in playlists]
    s._playlist_video_ids = lambda pid: playlists[pid]
    s._download_image = lambda url, path: None
    s.yt_dlp.YoutubeDL = _FakeYDL


def _manifest():
    with open(s.LIBRARY_MANIFEST_PATH) as f:
        return {pl["name"]: [t["video_id"] for t in pl["tracks"]] for pl in json.load(f)}


def test_failed_downloads_are_counted_not_silent():
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp, {"P": ["ok1", "bad1", "ok2", "bad2"]})
        failed, total = s.sync_library(lambda *a: None)
        assert total == 4
        assert [vid for vid, _ in failed] == ["bad1", "bad2"]
        assert "rate-limited" in failed[0][1]
        assert _manifest() == {"P": ["ok1", "ok2"]}


def test_aborted_sync_keeps_progress_and_old_playlists():
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp, {"A": ["ok1"], "B": ["ok2"]})
        s.sync_library(lambda *a: None)
        # second sync: A gets a new track, then dies before reaching B
        _setup(tmp, {"A": ["ok1", "ok3", "boom"], "B": ["ok2"]})
        try:
            s.sync_library(lambda *a: None)
            assert False, "expected the OSError to propagate"
        except OSError:
            pass
        # ok3 was saved before the crash, B's old track wasn't dropped
        assert _manifest() == {"A": ["ok1", "ok3"], "B": ["ok2"]}


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"\n{len(tests)} tests passed")
