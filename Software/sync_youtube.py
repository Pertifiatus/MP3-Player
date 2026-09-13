"""YouTube sync: device-flow login (YouTube Data API v3) + real playlist sync via
yt-dlp/ffmpeg - no ytmusicapi.

History: an earlier version of this file used ytmusicapi to browse the logged-in
account's actual YouTube Music library (Liked Music + private playlists), which
needs ytmusicapi's own OAuth flow (different endpoint/scope/grant-type than the
public Data API v3 below). That login succeeded, but EVERY authenticated
ytmusicapi call then failed with "400 Bad Request: Request contains an invalid
argument" - a confirmed, currently-open server-side restriction Google applies to
YouTube Music's private/reverse-engineered API when accessed via OAuth instead of
a real browser session (see github.com/sigma67/ytmusicapi issues #676/#682).
Anonymous ytmusicapi calls still worked, so it's specifically an OAuth-vs-browser
distinction, not something fixable in our code.

Given that, this syncs only the logged-in account's PUBLIC playlists instead:
the Data API v3 (`playlists.list?mine=true`) is Google's own supported, documented
API - not the scraped one - so it isn't subject to the same block. Per-track
metadata (title/duration/uploader) and the actual download both go through yt-dlp
directly against the public playlist/video URLs, which needs no auth at all since
public content is, by definition, visible without logging in.

REQUIRED BEFORE THIS CAN LOG IN:
  1. Google Cloud Console -> create a project -> OAuth consent screen (External,
     testing mode is fine for personal use) -> Credentials -> Create OAuth
     client ID -> type "TVs and Limited Input devices".
  2. Enable the "YouTube Data API v3" for that project.
  3. Put the resulting client_id/client_secret into youtube_credentials.json
     next to this file (not committed to git - contains a secret):
         {"client_id": "...", "client_secret": "..."}
"""
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

import yt_dlp

import connectivity

CREDENTIALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_credentials.json")
TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_token.json")
MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
LIBRARY_MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.json")
# Netscape-format cookies.txt, exported from a browser logged into YouTube -
# optional, only referenced if present (see _yt_dlp_cookie_opts()). Works
# around "Sign in to confirm you're not a bot" on videos yt-dlp's normal
# (logged-out) extraction can't reach - confirmed live (12.09.2026): happens
# per-video, not IP-wide (some videos fine, others not), no --extractor-args
# player_client swap fixed it. yt-dlp does NOT write rotated cookies back to
# this file on its own (confirmed via yt-dlp's own FAQ) - it's a manually
# refreshed snapshot, re-export and replace this file if downloads relying on
# it start failing again.
YOUTUBE_COOKIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_cookies.txt")

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
PLAYLISTS_API = "https://www.googleapis.com/youtube/v3/playlists"


class NoCredentialsError(Exception):
    """youtube_credentials.json is missing - see the module docstring."""


def _load_credentials():
    if not os.path.exists(CREDENTIALS_PATH):
        raise NoCredentialsError(f"{CREDENTIALS_PATH} fehlt - siehe sync_youtube.py Docstring")
    with open(CREDENTIALS_PATH) as f:
        return json.load(f)


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def start_device_flow():
    """Kick off the device-flow login. Returns dict with user_code, verification_url,
    device_code (needed for polling) and interval (seconds between poll attempts)."""
    creds = _load_credentials()
    resp = _post(DEVICE_CODE_URL, {"client_id": creds["client_id"], "scope": SCOPE})
    return {
        "user_code": resp["user_code"],
        "verification_url": resp["verification_url"],
        "device_code": resp["device_code"],
        "interval": resp.get("interval", 5),
        "expires_in": resp["expires_in"],
    }


def poll_device_flow(device_code):
    """Call once per `interval` seconds (from start_device_flow) until it returns True
    (authorized, token saved to disk) or raises on denial/expiry. Returns False while
    the user still hasn't approved on their phone/computer yet."""
    creds = _load_credentials()
    try:
        resp = _post(TOKEN_URL, {
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        error = body.get("error")
        if error == "authorization_pending":
            return False
        if error == "slow_down":
            time.sleep(5)
            return False
        raise RuntimeError(f"Device-Flow abgelehnt/abgelaufen: {error}")

    resp["expires_at"] = int(time.time()) + resp["expires_in"]
    with open(TOKEN_PATH, "w") as f:
        json.dump(resp, f, indent=2)
    return True


def is_account_linked():
    return os.path.exists(TOKEN_PATH)


def unlink_account():
    if os.path.exists(TOKEN_PATH):
        os.remove(TOKEN_PATH)


def _access_token():
    """Current access token, refreshing it first if it's expired/close to it."""
    with open(TOKEN_PATH) as f:
        token = json.load(f)
    if token["expires_at"] - int(time.time()) > 60:
        return token["access_token"]

    creds = _load_credentials()
    resp = _post(TOKEN_URL, {
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": token["refresh_token"],
        "grant_type": "refresh_token",
    })
    token["access_token"] = resp["access_token"]
    token["expires_at"] = int(time.time()) + resp["expires_in"]
    with open(TOKEN_PATH, "w") as f:
        json.dump(token, f, indent=2)
    return token["access_token"]


def _get_json(url, params):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                  headers={"Authorization": f"Bearer {_access_token()}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _best_thumbnail_url(thumbnails):
    # covers only ever get shown at up to 210px (the now-playing disc) - "medium"
    # (320x180) covers that with room to spare. maxres (1280x720, 60-100KB) was
    # 5-10x that for no visible benefit and measurably slowed the sync down
    # across ~250 playlist+track thumbnails.
    for size in ("medium", "high", "standard", "default", "maxres"):
        if size in thumbnails:
            return thumbnails[size]["url"]
    return None


def list_public_playlists():
    """The logged-in account's own playlists, via the real (non-reverse-engineered)
    Data API v3 - filtered down to ones with privacyStatus "public". Returns
    [(playlistId, title, cover_url), ...]."""
    playlists = []
    page_token = ""
    while True:
        params = {"part": "snippet,status", "mine": "true", "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        data = _get_json(PLAYLISTS_API, params)
        for item in data.get("items", []):
            if item["status"]["privacyStatus"] == "public":
                cover_url = _best_thumbnail_url(item["snippet"].get("thumbnails", {}))
                playlists.append((item["id"], item["snippet"]["title"], cover_url))
        page_token = data.get("nextPageToken")
        if not page_token:
            return playlists


def wifi_ok_for_sync():
    """Block sync over a metered connection (e.g. a phone hotspot) - otherwise
    any WLAN the device is connected to is fine, since it can now join more
    than one network via Einstellungen > Verbindung > WLAN (connectivity.py)."""
    return connectivity.wifi_is_metered() is not True


def _safe_filename(s):
    return "".join(c for c in s if c not in '/\\:*?"<>|').strip()[:150]


def _yt_dlp_cookie_opts():
    if os.path.exists(YOUTUBE_COOKIES_PATH):
        return {"cookiefile": YOUTUBE_COOKIES_PATH}
    return {}


def _pick_track_thumbnail_url(info):
    """yt-dlp's info["thumbnail"] is its single best (usually maxres, 1280x720)
    pick - same oversized-for-what-we-display issue as _best_thumbnail_url above.
    info["thumbnails"] carries width/height per candidate; take the smallest one
    that's still >= 320px wide, or the largest available if none are that big."""
    thumbnails = [t for t in info.get("thumbnails", []) if t.get("width") and t.get("url")]
    if not thumbnails:
        return info.get("thumbnail")
    thumbnails.sort(key=lambda t: t["width"])
    for t in thumbnails:
        if t["width"] >= 320:
            return t["url"]
    return thumbnails[-1]["url"]


def _download_image(url, dest_path):
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read()
        with open(dest_path, "wb") as f:
            f.write(data)
        return dest_path
    except (urllib.error.URLError, OSError):
        return None  # missing cover art isn't worth failing the whole sync over


def _playlist_video_ids(playlist_id):
    """Cheap flat listing (no per-video metadata fetch) just to get an ordered
    list of video ids and a track count for the progress bar before downloading."""
    opts = {"extract_flat": True, "quiet": True, "no_warnings": True, **_yt_dlp_cookie_opts()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    return [e["id"] for e in info.get("entries", []) if e]


def _previous_manifest_by_name():
    """{playlist_name: playlist_dict} from the existing library.json, if any."""
    if not os.path.exists(LIBRARY_MANIFEST_PATH):
        return {}
    with open(LIBRARY_MANIFEST_PATH) as f:
        manifest = json.load(f)
    return {pl["name"]: pl for pl in manifest}


def _previously_synced_tracks(old_manifest_by_name):
    """{video_id: track_dict} across all previously-synced playlists - lets a
    repeat sync skip re-downloading audio/cover it already has on disk instead
    of redoing all of it every time "Jetzt synchronisieren" is pressed."""
    return {t["video_id"]: t for pl in old_manifest_by_name.values()
            for t in pl["tracks"] if t.get("video_id")}


def sync_library(progress_callback, excluded=()):
    """Download every video in each of the account's public playlists (audio only,
    remuxed to m4a by ffmpeg) that isn't already downloaded from a previous sync,
    and write library.json so ui_state can load real data instead of the
    hardcoded demo LIBRARY. progress_callback(current, total, track_name) is
    called after each track. Title/duration/uploader (used as the display
    "artist") come from yt-dlp's own per-video metadata, fetched as a side
    effect of downloading - not from YouTube Music's private API.

    `excluded`: playlist names (see ui_state's "Playlists verwalten" screen) to
    skip syncing entirely. A previously-synced excluded playlist keeps whatever
    it already has (carried forward as-is below) rather than disappearing from
    the library - excluding only opts out of *future* downloads, it isn't the
    same as deleting (see delete_playlist())."""
    if not is_account_linked():
        raise RuntimeError("Kein YouTube-Konto verknuepft")
    if not wifi_ok_for_sync():
        raise RuntimeError("Mobilfunk-Verbindung erkannt, Sync uebersprungen")

    all_playlists = list_public_playlists()
    old_manifest_by_name = _previous_manifest_by_name()
    already_synced = _previously_synced_tracks(old_manifest_by_name)

    playlists = [p for p in all_playlists if p[1] not in excluded]
    video_ids_by_playlist = [_playlist_video_ids(pid) for pid, _, _ in playlists]
    total = sum(len(ids) for ids in video_ids_by_playlist)

    manifest = [{"name": title, "cover": None, "tracks": []} for _, title, _ in playlists]
    i = 0
    for pl_idx, ((playlist_id, title, cover_url), video_ids) in enumerate(zip(playlists, video_ids_by_playlist)):
        out_dir = os.path.join(MUSIC_DIR, _safe_filename(title))
        os.makedirs(out_dir, exist_ok=True)
        manifest[pl_idx]["cover"] = _download_image(cover_url, os.path.join(out_dir, "cover.jpg"))

        for video_id in video_ids:
            i += 1
            existing = already_synced.get(video_id)
            if existing and os.path.exists(existing["file"]):
                manifest[pl_idx]["tracks"].append(existing)
                progress_callback(i, total, f"{existing['artist']} - {existing['title']} (bereits vorhanden)")
                continue

            # No "preferredcodec" - that forces FFmpegExtractAudio to transcode
            # (e.g. Opus/WebM -> AAC) even though the source is already audio-only,
            # which is a full re-encode: measured ~60-90s/track of Pi CPU time
            # instead of the ~1s a plain container remux takes. Audio playback
            # isn't implemented yet (see CLAUDE.md, ES8388), so there's no reason
            # to force a specific codec here - keep whatever YouTube served.
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
                "postprocessors": [{"key": "FFmpegExtractAudio"}],
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
                # Needed for videos whose formats are signature-protected - without
                # it yt-dlp silently has fewer formats available and can fail
                # entirely (~42% of a real playlist in testing). Deno is yt-dlp's
                # own default runtime but isn't apt-installable on Raspberry Pi OS
                # without a separate curl-based install script; Node.js is and
                # is equally supported.
                "js_runtimes": {"node": {}},
                **_yt_dlp_cookie_opts(),
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                track_title = info.get("title", video_id)
                artist = info.get("uploader") or "Unbekannt"
                duration = int(info.get("duration") or 0)
                file_path = info["requested_downloads"][0]["filepath"]
                cover_path = _download_image(
                    _pick_track_thumbnail_url(info), os.path.splitext(file_path)[0] + ".jpg"
                )
                manifest[pl_idx]["tracks"].append(
                    {"video_id": video_id, "title": track_title, "artist": artist, "duration": duration,
                     "file": file_path, "cover": cover_path}
                )
                progress_callback(i, total, f"{artist} - {track_title}")
            except yt_dlp.DownloadError:
                # region-locked/deleted/private-since-listed - skip, keep syncing
                progress_callback(i, total, video_id)

    for _, title, _ in all_playlists:
        if title in excluded and title in old_manifest_by_name:
            manifest.append(old_manifest_by_name[title])

    with open(LIBRARY_MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def delete_playlist(name):
    """Removes a playlist's downloaded audio/covers and drops it from
    library.json - unlike excluding it from sync (see sync_library's
    `excluded` param), this actually frees the disk space. The caller
    (ui_state.py) is responsible for reloading LIBRARY/LIBRARY_COVERS/
    LIBRARY_FILES afterward - this module doesn't know about that state."""
    manifest_by_name = _previous_manifest_by_name()
    manifest_by_name.pop(name, None)
    with open(LIBRARY_MANIFEST_PATH, "w") as f:
        json.dump(list(manifest_by_name.values()), f, indent=2)

    out_dir = os.path.join(MUSIC_DIR, _safe_filename(name))
    shutil.rmtree(out_dir, ignore_errors=True)


def free_space_gb():
    """Free space on the filesystem holding the downloaded audio (MUSIC_DIR),
    for the "Speicher" info row in Einstellungen > Sync."""
    os.makedirs(MUSIC_DIR, exist_ok=True)
    return shutil.disk_usage(MUSIC_DIR).free / (1024 ** 3)
