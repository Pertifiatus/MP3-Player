# Design-Themes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seven new, fundamentally different front-display designs (Cybercore, Y2K, Glassmorphism, Neumorphism, Bento Grid, Pixelhaus, Cyberpunk) next to the existing iOS look ("Klassik"), switchable under Einstellungen → Anzeige → Design.

**Architecture:** `ui_views.py` turns the `UIState` into exactly one neutral *view* per frame (content only: items, selection, status - no pixels). Each design is a module in `Software/themes/` that draws those views with its own layout onto the full 240×240 frame. `ui_render.py` becomes a thin façade (build view → active design draws → status/quick-connect overlays). Shared drawing helpers move to `ui_common.py`. Today's renderer moves verbatim into `themes/klassik.py` and is verified pixel-identical by a before/after frame comparison.

**Tech Stack:** Python 3 + Pillow + numpy (already on the Pi via apt), bundled OFL fonts in `Software/fonts/`, one PNG asset (`Software/assets/pixelhaus.png`). No new pip dependencies.

**Spec:** `docs/superpowers/specs/2026-10-12-design-themes-design.md`

## Global Constraints

- No new pip dependencies; Pillow ≥ 9.4 API only (Pi ships apt `python3-pil`); `ImageFont.load_default(size)` only behind `try/except TypeError`.
- Display 240×240, physically round: everything important within `SAFE_R = 104` px of (120, 120); status-ring geometry (`RING_*` constants) unchanged for every design, only its look changes.
- Klassik stays pixel-identical, except exactly: "Suche Netzwerke…" y 106→110, "Keine Playlists" y 106→100, WLAN menu shows its header while "Aufwecken…".
- Settings key `display.theme`, default `"klassik"`; settings label `"Design"`, first entry under Anzeige; choice values/labels exactly: `klassik/Klassik, cybercore/Cybercore, y2k/Y2K, glass/Glas, neumorph/Neumorph, bento/Bento, pixelhaus/Pixelhaus, cyberpunk/Cyberpunk` (in that order once all exist). Unknown stored value → Klassik, never a crash.
- No idle animation: menus redraw only on input (as today); Now Playing at `PLAYING_REDRAW_INTERVAL` (0.1 s); Pixelhaus camera flights via `ANIM_REDRAW_INTERVAL = 0.05`; busy indicators may only animate on screens main.py already redraws periodically (BT/WLAN/Sync, 0.5 s).
- Fonts only from `Software/fonts/` (the approved OFL list in the spec) with each family's `OFL.txt` next to it; a missing font or asset never crashes - fallback rendering instead.
- Performance budget: each design's slowest screen (median of 5 renders) ≤ Klassik's Now-Playing median, measured on the same machine (`python preview_themes.py --bench`).
- UI text stays German (as today). Icons are drawn as shapes (`ui_common.icon`), never as exotic Unicode glyphs.
- Klassik, Cybercore, Y2K, Glass, Neumorph, Cyberpunk scale fonts/rows with `ctx.scale` (UI-Größe); Bento and Pixelhaus ignore it.
- Tests: plain-assert scripts run as `python test_<name>.py` from `Software/` (project convention, no pytest).

## Review Focus

1. **Stale/unknown `display.theme` (or any choice value) in `settings.json`** - e.g. a renamed design after an update → Klassik is drawn and the settings row shows the raw stored value; today `_value_repr`'s `next(...)` would raise StopIteration. Pinned in Task 1 (row value) and Task 3 (render fallback).
2. **Long strings** - 80+ char YouTube titles, long SSIDs/device names, multi-line error text, long device-flow URLs → truncated/wrapped, never a crash, in every design and UI scale. Pinned in Task 4's edge-case contract test (runs every registered design).
3. **List and number edges** - 1-item lists, selection on the last of 60 items, stepper value > max, sync `total == 0` / `current > total`, track `duration == 0` → no crash, no division by zero. Pinned in Task 4's contract test.
4. **Missing assets** - fonts not copied to the Pi, `pixelhaus.png` missing → fallback fonts/background, no crash. Pinned in Task 4 (fonts) and Task 11 (asset).
5. **Glyphs missing in a design's font** (`→ · … ● ○ ␣` in UI strings) → ASCII fallback instead of tofu boxes. Pinned in Task 4 (`glyph_safe` test).

---

## File Map

| File | Responsibility |
|---|---|
| `Software/ui_views.py` (new) | View dataclasses + `build(state)`, `status(state)`, `quick_connect(state)` - all "which state → which content" logic |
| `Software/ui_common.py` (new) | Shared drawing helpers: round-bezel math, text fit/wrap, cover art, ring geometry, fonts, glyph fallback, vector icons, ring-status drawing |
| `Software/themes/__init__.py` (new) | Registry `THEMES`, `get(name)` |
| `Software/themes/klassik.py` (new) | Today's renderer, moved verbatim + `draw_*` adapters |
| `Software/themes/{cybercore,y2k,glass,neumorph,bento,cyberpunk,pixelhaus}.py` (new) | One design each |
| `Software/ui_render.py` (rewrite) | Façade: `render`, `render_shutdown`, `animating`, `UI_SCALE_STEPS`, `W` |
| `Software/preview_themes.py` (new) | PNG contact sheet per design + `--bench` timing |
| `Software/fonts/` (new) | OFL fonts + license files |
| `Software/assets/pixelhaus.png` (new) | Per's house image (copied from the main checkout's repo root) |
| `Software/settings.py`, `ui_state.py`, `main.py` | Theme setting, Design menu entry, animation hook |
| `Software/test_ui_views.py` (new), `test_ui_render.py`, `test_ui_state.py` | Tests |

## Working Conventions

- Run everything from `Software/`: `cd "C:/Users/Per Kenner/Documents/GitHub/MP3-Player/.claude/worktrees/pi-design-variations-308146/Software"`.
- `SCRATCH` = `C:/Users/PERKEN~1/AppData/Local/Temp/claude/C--Users-Per-Kenner-Documents-GitHub-MP3-Player--claude-worktrees-pi-design-variations-308146/14795ef4-eb4c-4856-8180-0eb262ac08ae/scratchpad` (never committed).
- Design tasks (5-12) follow: implement module → tests green → `python preview_themes.py <design>` → open `previews/<design>.png` → fix clipping/overlaps → `python preview_themes.py --bench <design> klassik` → commit. The layout tables are the binding spec; coordinates may move up to ±8 px during preview tuning when the preview shows a clash with the bezel or the status-ring labels. On Home-at-rest and Now Playing keep the area x < 60, y 45-80 free - `draw_status` puts the %/ETA labels there.
- Commit messages end with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Klassik baseline frames + `ui_views.py`

**Files:**
- Create: `Software/ui_views.py`, `Software/test_ui_views.py`
- Scratch (not committed): `SCRATCH/klassik_walk.py`, `SCRATCH/capture_frames.py`, `SCRATCH/compare_frames.py`, `SCRATCH/frames_before/`

**Interfaces:**
- Consumes: `ui_state` (screens, `LIBRARY`, `LIBRARY_COVERS`, `PLAYLIST_COLORS`, `SETTINGS_ITEMS`, `SETTINGS_CATEGORIES`, `WIFI_CHARSET`, `UIState` item methods), `sync_youtube.free_space_gb()`.
- Produces (exact names, used by every later task): `Item`, `ListView`, `MessageView`, `SettingRow`, `SettingsView`, `PlayingView`, `CodeView`, `ProgressView`, `PasswordView`, `StatusView`, `QuickConnectView`, `RenderCtx`, `playlist_color(idx) -> str`, `fmt_time(seconds) -> str`, `build(state) -> view`, `status(state) -> StatusView`, `quick_connect(state) -> QuickConnectView | None`. Every drawable view has a class attribute `KIND` in `{"list","message","settings","playing","code","progress","password"}` and a `screen` field.

- [ ] **Step 1: Capture the Klassik baseline before touching any renderer code**

```bash
cp test_ui_render.py "$SCRATCH/klassik_walk.py"
```

Create `SCRATCH/capture_frames.py`:

```python
"""Render every frame of the ORIGINAL test_ui_render walk into PNGs.
usage (from Software/): python SCRATCH/capture_frames.py OUTDIR"""
import importlib.util
import os
import sys

sys.path.insert(0, os.getcwd())
spec = importlib.util.spec_from_file_location(
    "klassik_walk", os.path.join(os.path.dirname(os.path.abspath(__file__)), "klassik_walk.py"))
walk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(walk)

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
count = [0]


def capture(img):
    count[0] += 1
    img.save(os.path.join(out, f"{count[0]:04d}.png"))


walk._assert_frame = capture
for name in ("test_all_screens_render_at_every_scale",
             "test_quick_connect_overlay_renders_every_phase",
             "test_quick_connect_overlay_survives_qc_phase_reset_mid_render",
             "test_playlist_render_windows_a_long_list_at_every_scroll_position"):
    getattr(walk, name)()
print(count[0], "frames")
```

Create `SCRATCH/compare_frames.py`:

```python
"""usage: python compare_frames.py BEFORE_DIR AFTER_DIR - lists frames that differ."""
import os
import sys

from PIL import Image, ImageChops

before, after = sys.argv[1], sys.argv[2]
diffs = []
for name in sorted(os.listdir(before)):
    a = Image.open(os.path.join(before, name)).convert("RGB")
    b = Image.open(os.path.join(after, name)).convert("RGB")
    if ImageChops.difference(a, b).getbbox():
        diffs.append(name)
print(len(diffs), "differing frames:", diffs)
```

Run: `python "$SCRATCH/capture_frames.py" "$SCRATCH/frames_before"`
Expected: `<N> frames` (note N - the after-run must print the same N).

- [ ] **Step 2: Write the failing tests**

Create `Software/test_ui_views.py`:

```python
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
```

- [ ] **Step 3: Run to verify it fails**

Run: `python test_ui_views.py`
Expected: `ModuleNotFoundError: No module named 'ui_views'`

- [ ] **Step 4: Write `Software/ui_views.py`**

```python
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
        # of crashing the whole settings screen - see Review Focus in the plan.
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
```

- [ ] **Step 5: Run the tests**

Run: `python test_ui_views.py && python test_ui_state.py && python test_ui_render.py`
Expected: all `OK`, `10 tests passed` / `28 tests passed` / `5 tests passed`.

- [ ] **Step 6: Commit**

```bash
git add ui_views.py test_ui_views.py
git commit -m "Add ui_views: screen content as plain view data for switchable designs"
```

---

### Task 2: `ui_common.py`, `themes/` with Klassik, `ui_render.py` façade

**Files:**
- Create: `Software/ui_common.py`, `Software/themes/__init__.py`, `Software/themes/klassik.py`
- Modify (rewrite): `Software/ui_render.py`
- Modify: `Software/test_ui_render.py` (one reference)

**Interfaces:**
- Consumes: everything from Task 1.
- Produces:
  - `ui_common`: `HERE`, `W`, `SAFE_R`, `safe_half_width(y, r=SAFE_R, cy=W/2)`, `text_centered(draw, x_center, y, s, font, fill)`, `text_centered_fit(draw, x_center, y, s, fonts, fill, max_width)`, `truncate(draw, text, font, max_width)`, `letter_spaced(s)`, `wrap_text(draw, text, x_center, y, font, fill, max_width, line_height=16)`, `hex_to_rgb(h)`, `shade(rgb, pct)`, `rotated_rect_points(cx, cy, w, h, angle_deg)`, `format_eta(minutes)`, `RING_R, RING_WIDTH, RING_ANCHOR_DEG, RING_FAR_DEG, WIFI_DOT_DEG, BT_DOT_DEG, DOT_R`, `ring_point(deg, r=RING_R)`, `ring_arc(img, start_deg, end_deg, color, r=RING_R, width=RING_WIDTH)`, `lightning_bolt(draw, cx, cy, size, color)`, `shuffle_icon(draw, cx, cy, size, color)`, `cover_image(ref, size)`, `cover_art(seed, color_a_hex, color_b_hex, size=210)`.
  - Every theme module: `draw_list(view, ctx)`, `draw_message(view, ctx)`, `draw_settings(view, ctx)`, `draw_playing(view, ctx)`, `draw_code(view, ctx)`, `draw_progress(view, ctx)`, `draw_password(view, ctx)` → `Image` (RGB 240×240); `draw_status(img, status, ctx)`, `draw_quick_connect(img, qc, ctx)` → draw in place; `draw_shutdown(ctx)` → `Image` (`ctx` may be `None`); optional `animating() -> bool`.
  - `themes.THEMES: dict[str, module]`, `themes.get(name) -> module` (Klassik fallback).
  - `ui_render.W`, `ui_render.UI_SCALE_STEPS`, `ui_render.render(state)`, `ui_render.render_shutdown(state=None)`.

- [ ] **Step 1: Create `Software/ui_common.py`**

Move these blocks out of the current `ui_render.py` **verbatim**, renaming only as listed; keep their comments/docstrings:

| From `ui_render.py` (current lines) | To `ui_common.py` name |
|---|---|
| `W = 240` (26) | `W` |
| SAFE_R comment + `SAFE_R` (112-117), `_safe_half_width` (120-124) | `SAFE_R`, `safe_half_width` |
| `_text_centered` (88-91) | `text_centered` |
| `_text_centered_fit` (94-105) | `text_centered_fit` (internal calls → `truncate`, `text_centered`) |
| `_letter_spaced` (108-109) | `letter_spaced` |
| `_truncate` (284-289) | `truncate` |
| `_wrap_text` (944-959) | `wrap_text` (internal call → `text_centered`) |
| `_hex_to_rgb`, `_shade`, `_rotated_rect_points` (292-310) | `hex_to_rgb`, `shade`, `rotated_rect_points` |
| `_format_eta` (211-215) | `format_eta` |
| ring comment + `RING_R` … `DOT_R` (135-156, **without** `RING_TRACK`/`RING_OFF`/`CHARGE_GREEN`) | same names |
| `_ring_point` (162-164) | `ring_point` |
| `_draw_lightning_bolt` (167-174) | `lightning_bolt` |
| `_draw_ring_arc` (191-208) | `ring_arc`, signature `ring_arc(img, start_deg, end_deg, color, r=RING_R, width=RING_WIDTH)`; body uses `r`/`width` instead of `RING_R`/`RING_WIDTH` |
| `_draw_shuffle_icon` (326-337) | `shuffle_icon` |
| `_cover_cache`, `_cover_image`, `cover_art` (383-443) | see below |

Header of the new file:

```python
"""Drawing helpers shared by every design in themes/: round-bezel geometry,
text fitting, cover art, the status-ring geometry. Pure PIL/numpy - no UI state.
"""
import functools
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
```

Cover loading becomes ref-based and cached (the procedural `cover_art` and its `_cover_cache` move unchanged):

```python
def cover_image(ref, size):
    """`ref` = (path_or_None, seed, color_hex) as carried by ui_views (Item.cover,
    PlayingView.cover). The returned image is shared (cached) - never draw on it
    in place, .copy() it first."""
    return _cover_image(ref[0], ref[1], ref[2], int(size))


@functools.lru_cache(maxsize=64)
def _cover_image(cover_path, seed, color_hex, size):
    """Real synced thumbnail if one exists and still loads, else the procedural
    placeholder - covers the demo library (no real files at all) and any track
    whose thumbnail download failed/was skipped during sync. Cached: Now Playing
    redraws ~10x/s and used to decode the JPEG from disk on every frame."""
    if cover_path:
        try:
            img = Image.open(cover_path).convert("RGB")
            # YouTube thumbnails are 16:9 - a plain resize((size,size)) squishes
            # them into a square instead of just cropping to one. Center-crop
            # to a square first (matches cover_art()'s own square output).
            w, h = img.size
            side = min(w, h)
            left, top = (w - side) // 2, (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
            return img.resize((size, size))
        except OSError:
            pass
    return cover_art(seed, color_hex, color_hex, size=size)
```

- [ ] **Step 2: Create `Software/themes/klassik.py`**

Header (replaces the old module docstring + imports):

```python
"""Klassik: the original iOS/tvOS-inspired look - true-black background, iOS
system-gray palette, "inset grouped" list cards with hairline separators, vivid
single-color squircle icon badges (Settings-app style), frosted-glass control
pill on the Now-Playing screen. Focus/selection uses a lifted-background
highlight (tvOS-style, since this is D-pad/encoder navigated, not touch) rather
than a heavy outline.

UI-Groesse (ctx.scale) is a real layout-density knob, not a post-render zoom:
it scales fonts, row heights and internal margins in the list screens, so a
smaller setting fits *more* items in the same round safe area. SAFE_R itself
never scales - it's the physical round-bezel limit, not a style margin.

Moved here unchanged from ui_render.py when designs became switchable (see
docs/superpowers/specs/2026-10-12-design-themes-design.md) - keep it
pixel-identical unless a change is meant for Klassik itself.
"""
import functools
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import ui_common
from ui_common import (
    BT_DOT_DEG, DOT_R, RING_ANCHOR_DEG, RING_FAR_DEG, RING_R, RING_WIDTH, SAFE_R, W, WIFI_DOT_DEG,
    format_eta as _format_eta, letter_spaced as _letter_spaced, lightning_bolt as _draw_lightning_bolt,
    ring_arc as _draw_ring_arc, ring_point as _ring_point, rotated_rect_points as _rotated_rect_points,
    safe_half_width as _safe_half_width, shuffle_icon as _draw_shuffle_icon, text_centered as _text_centered,
    text_centered_fit as _text_centered_fit, truncate as _truncate, wrap_text as _wrap_text)
from ui_views import fmt_time as _fmt_time
```

Then move **verbatim** from the current `ui_render.py`: palette + `CATEGORY_COLORS` (28-45), `FONT_DIR`/`FONT_FILES`/`_font` (51-79), `_MIN_CARD_HALF_W`/`CARD_MAX_Y` with comment (127-132), `RING_TRACK`/`RING_OFF`/`CHARGE_GREEN` (157-159), `_draw_status_dot` (177-188), `_header` (275-281), `_frosted_pill` (313-323), quick-connect constants (341-344), `_render_nav_list` (448-508), `NAV_LIST_WINDOW` comment + `_windowed_range` (511-527), `_draw_circular_text` + `_compose_disc` (695-744), `_caret` (860-863), `_draw_toggle_pill` (900-904). Add `DANGER = (255, 69, 58)` after `CARD_BG`.

Then the adapters (new code):

```python
# --- views (see ui_views) -------------------------------------------------------

def _base():
    img = Image.new("RGB", (W, W), BG)
    return img, ImageDraw.Draw(img)


def _tone_color(item):
    if item.kind in CATEGORY_COLORS:
        return CATEGORY_COLORS[item.kind]
    return {"accent": ACCENT, "muted": CARD_BG, "danger": DANGER}[item.tone]


def draw_list(view, ctx):
    scale = ctx.scale
    img, draw = _base()
    # _render_nav_list always centers the selected row on screen middle, so
    # scrolling down past the first item pushes earlier rows up into the
    # header's y - only show the header at rest (top item selected).
    if view.sel == 0:
        _header(draw, 36, view.title.upper(), _font("header", scale), DIM)
    lo, hi = _windowed_range(len(view.items), view.sel)
    entries = []
    for item in view.items[lo:hi]:
        entry = {"label": item.label, "sub": item.sub, "icon": item.icon, "color_rgb": _tone_color(item)}
        if item.cover is not None:
            entry["cover_img"] = ui_common.cover_image(item.cover, 140)
        entries.append(entry)
    _render_nav_list(img, draw, entries, view.sel - lo, scale)
    return img


def draw_message(view, ctx):
    scale = ctx.scale
    f_sub_l, f_sub_s = _font("sub_l", scale), _font("sub_s", scale)
    img, draw = _base()
    _header(draw, 36, view.title.upper(), _font("header", scale), DIM)
    if view.subtitle:
        _text_centered_fit(draw, W / 2, 58, view.subtitle, [f_sub_s], DIM, max_width=160)
    second = view.detail or view.hint
    if view.mood == "error":
        _text_centered(draw, W / 2, 90, view.text, f_sub_l, DANGER)
        _wrap_text(draw, view.detail, W / 2, 116, f_sub_s, DIM, max_width=200)
        if view.hint:
            _text_centered(draw, W / 2, 178, view.hint, f_sub_s, DIM)
    elif view.mood == "busy":
        _text_centered(draw, W / 2, 106 if second else 110, view.text, f_sub_l, DIM)
        if second:
            _text_centered(draw, W / 2, 130, second, f_sub_s, ACCENT if view.detail else DIM)
    else:  # success / info
        _text_centered(draw, W / 2, 100, view.text, f_sub_l, ACCENT if view.mood == "success" else DIM)
        if second:
            _text_centered(draw, W / 2, 124, second, f_sub_s, DIM)
    return img
```

`draw_settings(view, ctx)`: the body of the old `render_settings_detail` (764-857) with exactly these edits - `scale = ctx.scale`; `rows = view.rows` replaces `items = …`; the header uses `view.title.upper()`; `sel = view.sel`; the loop reads `for row, item in enumerate(rows[start:start + visible])`; `val_text, val_color = _value_repr(item)`; `is_toggle = item.kind == "toggle"`; `lbl = _truncate(draw, item.label, …)`; the toggle call passes `bool(item.value)`. New `_value_repr` replaces the old one (866-897):

```python
def _value_repr(row):
    if row.kind == "stepper":
        return ("●" * row.value) + ("○" * (row.max - row.value)), ACCENT
    if row.kind == "toggle":
        return "", DIM
    return str(row.value), (ACCENT if row.on else DIM)
```

`draw_playing(view, ctx)`: the body of the old `render_playing` (608-692) with these edits - `scale = ctx.scale`; `title, artist, dur = view.title, view.artist, view.duration`; `progress = min(1.0, view.position / dur) if dur else 0.0`; `art = ui_common.cover_image(view.cover, disc_d)`; every `np.position` → `view.position`, `np.playing` → `view.playing`, `state.shuffle` → `view.shuffle`; the `color_hex`/`playlist_name`/`cover_path` lines are deleted.

```python
def draw_code(view, ctx):
    scale = ctx.scale
    f_header, f_sub_l = _font("header", scale), _font("sub_l", scale)
    f_sub_s, f_mono = _font("sub_s", scale), _font("mono", scale)
    img, draw = _base()
    _header(draw, 36, view.title.upper(), f_header, DIM)
    pad = max(3, round(5 * scale))
    half = min(_safe_half_width(58), _safe_half_width(178))
    card_box = [W / 2 - half + pad, 58, W / 2 + half - pad, 178]
    draw.rounded_rectangle(card_box, radius=round(20 * scale), fill=GROUP_BG)
    _text_centered(draw, W / 2, 72, "Gehe zu", f_sub_s, DIM)
    _text_centered_fit(draw, W / 2, 92, view.url, [f_sub_l, f_sub_s], TEXT,
                       max_width=card_box[2] - card_box[0] - 10)
    _text_centered(draw, W / 2, 124, "und gib diesen Code ein:", f_sub_s, DIM)
    _text_centered(draw, W / 2, 144, view.code, f_mono, ACCENT)
    _text_centered(draw, W / 2, 198, "Warte auf Bestätigung …", f_sub_s, DIM)
    return img


def draw_progress(view, ctx):
    scale = ctx.scale
    f_header, f_sub_l, f_sub_s = _font("header", scale), _font("sub_l", scale), _font("sub_s", scale)
    img, draw = _base()
    _header(draw, 36, view.title.upper(), f_header, DIM)
    pct = min(1.0, view.current / view.total) if view.total else 0
    bar_x0, bar_x1, bar_y = 30, W - 30, 130
    draw.rounded_rectangle([bar_x0, bar_y, bar_x1, bar_y + 10], radius=5, fill=(58, 58, 60))
    fill_x1 = bar_x0 + (bar_x1 - bar_x0) * pct
    if fill_x1 > bar_x0:
        draw.rounded_rectangle([bar_x0, bar_y, fill_x1, bar_y + 10], radius=5, fill=ACCENT)
    _text_centered(draw, W / 2, 150, f"{view.current} / {view.total}", f_sub_l, TEXT)
    if view.track:
        _text_centered(draw, W / 2, 174, view.track, f_sub_s, DIM)
    if view.done:
        _text_centered(draw, W / 2, 204, "Fertig!", f_sub_l, ACCENT)
    return img
```

`draw_password(view, ctx)`: the old `render_wifi_password` (1199-1244) minus its two connect-status branches (now `MessageView`s), with `scale = ctx.scale`, `_header(draw, 36, view.title.upper(), …)`, subtitle `view.ssid`, `typed = view.typed`, `current = view.charset[view.char_idx]`, hint text `view.hint`.

```python
def draw_status(img, sv, ctx):
    draw = ImageDraw.Draw(img)
    # track (empty slot), rounded ends - the caps are faked with small filled
    # circles at both endpoints (a stroke-linecap of "round" is exactly a
    # semicircle of radius=width/2 at the endpoint)
    _draw_ring_arc(img, RING_ANCHOR_DEG, RING_FAR_DEG, RING_TRACK)
    for deg in (RING_ANCHOR_DEG, RING_FAR_DEG):
        x, y = _ring_point(deg)
        cap_r = RING_WIDTH / 2
        draw.ellipse([x - cap_r, y - cap_r, x + cap_r, y + cap_r], fill=RING_TRACK)

    if sv.battery_pct is not None:
        pct = max(0, min(100, round(sv.battery_pct)))
        if pct > 0:
            # anchored at RING_FAR_DEG (bottom), growing toward the top as charge
            # increases - the slot empties from the TOP down as the battery drains
            fill_bound = RING_FAR_DEG + (RING_ANCHOR_DEG - RING_FAR_DEG) * pct / 100
            _draw_ring_arc(img, RING_FAR_DEG, fill_bound, ACCENT)
            for deg in (RING_FAR_DEG, fill_bound):
                x, y = _ring_point(deg)
                cap_r = RING_WIDTH / 2
                draw.ellipse([x - cap_r, y - cap_r, x + cap_r, y + cap_r], fill=ACCENT)
        if sv.charging:
            bolt_x, bolt_y = _ring_point(180)
            _draw_lightning_bolt(draw, bolt_x, bolt_y, 14, CHARGE_GREEN)
        # r=100 sits inside SAFE_R - only on Home-at-rest / Now Playing (sv.show_labels),
        # anywhere else it would paint over that screen's own content
        if sv.show_labels:
            f_pct = _font("ring_pct", 1.0)
            pct_x, pct_y = _ring_point(RING_ANCHOR_DEG, r=100)
            _text_centered(draw, pct_x + 10, pct_y - f_pct.size - 2, f"{pct}%", f_pct, DIM)
            if sv.charging and sv.watts is not None:
                _text_centered(draw, pct_x, pct_y, f"{round(sv.watts)}W", f_pct, ACCENT)
            elif not sv.charging and sv.eta_min is not None:
                _text_centered(draw, pct_x, pct_y, _format_eta(sv.eta_min), f_pct, DIM)

    _draw_status_dot(draw, WIFI_DOT_DEG, TEXT, sv.wifi_on, sv.wifi_connected)
    _draw_status_dot(draw, BT_DOT_DEG, CATEGORY_COLORS["connectivity"], sv.bt_on, sv.bt_connected)


def draw_quick_connect(img, qc, ctx):
    """Ring overlay for Home's hold-Play/Pause gesture - darkens/blurs the whole
    frame (not just a circle behind the ring) for legibility."""
    cx = cy = W / 2
    blurred = img.filter(ImageFilter.GaussianBlur(3))
    img.paste(Image.blend(blurred, Image.new("RGB", img.size, (0, 0, 0)), 0.6), (0, 0))
    draw = ImageDraw.Draw(img)
    ring_box = [cx - QC_RING_R, cy - QC_RING_R, cx + QC_RING_R, cy + QC_RING_R]
    draw.ellipse(ring_box, outline=QC_RING_TRACK, width=QC_RING_STROKE)
    if qc.progress >= 1.0:
        draw.ellipse(ring_box, outline=TEXT, width=QC_RING_STROKE)
    elif qc.progress > 0:
        draw.arc(ring_box, start=-90, end=-90 + 360 * qc.progress, fill=TEXT, width=QC_RING_STROKE)
    _text_centered(draw, cx, cy - QC_RING_R - 28, qc.label, _font("sub_l", ctx.scale),
                   QC_ERROR_COLOR if qc.error else TEXT)


def draw_shutdown(ctx):
    img, draw = _base()
    _text_centered(draw, W / 2, W / 2 - 12, "Shutting down", _font("title_s", 1.0), TEXT)
    _text_centered(draw, W / 2, W / 2 + 14, "...", _font("sub_l", 1.0), DIM)
    return img
```

- [ ] **Step 3: Create `Software/themes/__init__.py`**

```python
"""Front-display designs (Settings → Anzeige → Design), one module each - see
docs/superpowers/specs/2026-10-12-design-themes-design.md. Every module draws
the views from ui_views with its own layout; ui_render picks the active one.

Adding a design: new module here + entry in THEMES + its choice in
ui_state.THEME_CHOICES (test_ui_render checks both lists match)."""
from themes import klassik

THEMES = {
    "klassik": klassik,
}


def get(name):
    return THEMES.get(name, klassik)
```

- [ ] **Step 4: Rewrite `Software/ui_render.py`**

```python
"""Front-display rendering: builds the current screen's view (ui_views) and lets
the active design (themes/, Einstellungen → Anzeige → Design) draw it, then adds
the status-ring and Quick-Connect overlays."""
import themes
import ui_views
from ui_common import W

# UI-Groesse setting (1-5 stepper) -> layout density multiplier. 3 = 100%, matches
# every pixel constant in the designs as tuned. Below 1.0 shrinks fonts/rows/
# margins so more list content fits on screen; above 1.0 grows them for
# readability at the cost of items visible at once.
UI_SCALE_STEPS = {1: 0.75, 2: 0.88, 3: 1.0, 4: 1.15, 5: 1.3}


def _theme(state):
    return themes.get(state.settings.get("display", "theme"))


def _ctx(state):
    return ui_views.RenderCtx(UI_SCALE_STEPS[state.settings.get("display", "ui_scale")], ui_views.status(state))


def render(state):
    theme, ctx = _theme(state), _ctx(state)
    view = ui_views.build(state)
    img = getattr(theme, "draw_" + view.KIND)(view, ctx)
    if state.status_ring_visible():
        theme.draw_status(img, ctx.status, ctx)
    if state.qc_active:
        qc = ui_views.quick_connect(state)
        if qc is not None:
            theme.draw_quick_connect(img, qc, ctx)
    return img


def render_shutdown(state=None):
    """Standalone message screen for the power-button long-press (power_button.py) -
    not part of the screen/state machine (nothing to navigate back from)."""
    if state is None:
        return themes.klassik.draw_shutdown(None)
    return _theme(state).draw_shutdown(_ctx(state))
```

`ui_render._theme()` reads `display.theme`, so the default has to exist from this task on (otherwise `Settings.get` raises `KeyError`). `Settings._load` merges `DEFAULTS` into every loaded file, so older `settings.json` files on the Pi pick it up automatically. In `Software/settings.py` `DEFAULTS["display"]` add after `"status_ring": …`:

```python
        "theme": "klassik",  # see themes/__init__.py - Einstellungen → Anzeige → Design
```

- [ ] **Step 5: Update the test's private reference**

In `Software/test_ui_render.py`: add `from themes import klassik` to the imports and replace every `ui_render._windowed_range(` with `klassik._windowed_range(`.

- [ ] **Step 6: Run all tests**

Run: `python test_ui_views.py && python test_ui_state.py && python test_ui_render.py && python test_power_button.py && python test_player.py`
Expected: all pass.

- [ ] **Step 7: Pixel-compare Klassik against the baseline**

Run: `python "$SCRATCH/capture_frames.py" "$SCRATCH/frames_after" && python "$SCRATCH/compare_frames.py" "$SCRATCH/frames_before" "$SCRATCH/frames_after"`
Expected: same frame count as Step 1 of Task 1; `5 differing frames` - the "Suche Netzwerke…" frame once per UI scale (text moved 4 px down). Open one differing pair to confirm it is that frame. Any other differing frame is a porting bug: diff the two PNGs, fix `klassik.py`, re-run.

- [ ] **Step 8: Commit**

```bash
git add ui_common.py themes/__init__.py themes/klassik.py ui_render.py settings.py test_ui_render.py
git commit -m "Move renderer into themes/klassik behind a view-based ui_render facade"
```

---

### Task 3: "Design" setting, animation hook, previews

**Files:**
- Modify: `Software/ui_state.py`, `Software/ui_render.py`, `Software/main.py`, `Software/test_ui_state.py`, `Software/test_ui_render.py`, `.gitignore`
- Create: `Software/preview_themes.py`

**Interfaces:**
- Consumes: Task 2's façade and registry.
- Produces: `ui_state.THEME_CHOICES: list[tuple[str, str]]`; `ui_render.animating(state) -> bool`; `preview_themes.states(theme) -> iterator of (label, state)`; `preview_themes.render_settled(state) -> Image`; CLI `python preview_themes.py [--bench] [design ...]`.

- [ ] **Step 1: Write the failing tests**

Append to `Software/test_ui_state.py` (before the `__main__` block):

```python
def test_design_choice_cycles_through_all_designs():
    s = make_state()
    s.settings_category = "display"
    s.settings_detail_sel = next(i for i, it in enumerate(ui_state.SETTINGS_ITEMS["display"])
                                 if it["key"] == "theme")
    values = [v for v, _ in ui_state.THEME_CHOICES]
    seen = []
    for _ in values:
        s.settings_detail_activate()
        seen.append(s.settings.get("display", "theme"))
    assert seen == values[1:] + values[:1]  # every design once, then back to Klassik
```

In `Software/test_ui_render.py`: add `import themes`; move the whole body of `test_all_screens_render_at_every_scale` (from `_assert_frame(ui_render.render(s))  # home` through `_assert_frame(ui_render.render_shutdown())`) into a helper `def _walk_all_screens(s):`, changing only its last line to `_assert_frame(ui_render.render_shutdown(s))`; then replace the test and the other two multi-frame tests with design loops, and add two tests:

```python
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
```

(keep the docstring of `test_quick_connect_overlay_survives_qc_phase_reset_mid_render` and `test_playlist_render_windows_a_long_list_at_every_scroll_position`, and wrap each body in `for theme in themes.THEMES:` with `s.settings.set("display", "theme", theme)` right after `s = make_state()`.)

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python test_ui_state.py`
Expected: FAIL - `AttributeError: module 'ui_state' has no attribute 'THEME_CHOICES'`.

- [ ] **Step 3: Implement the setting**

In `Software/ui_state.py`, right above `SETTINGS_ITEMS = {`:

```python
# Einstellungen → Anzeige → Design. Every value needs a module in themes.THEMES
# (test_ui_render.test_every_design_choice_has_a_theme guards that).
THEME_CHOICES = [("klassik", "Klassik")]
```

and make it the first entry of `SETTINGS_ITEMS["display"]`:

```python
        {"key": "theme", "label": "Design", "type": "choice", "choices": THEME_CHOICES},
```

In `Software/ui_render.py` add:

```python
def animating(state):
    """True while the active design is mid-animation and wants frames even
    without input - the Pixelhaus camera flight (see main.py)."""
    return getattr(_theme(state), "animating", lambda: False)()
```

In `Software/main.py`:
1. Below `QUICK_CONNECT_REDRAW_INTERVAL = …` add:
   ```python
   ANIM_REDRAW_INTERVAL = 0.05  # design animations (Pixelhaus camera flight) - effectively "as fast
                                # as the SPI push allows"; ui_render.animating() is False otherwise
   ```
2. Next to `last_qc_redraw = time.monotonic()` add `last_anim_redraw = time.monotonic()`.
3. Right before `if dirty and not screen_off:` add:
   ```python
           if ui_render.animating(state) and now - last_anim_redraw >= ANIM_REDRAW_INTERVAL:
               last_anim_redraw = now
               dirty = True
   ```
4. `sink.push(ui_render.render_shutdown())` → `sink.push(ui_render.render_shutdown(state))`.

- [ ] **Step 4: Create `Software/preview_themes.py`**

```python
"""Contact sheet of every screen in every design - look at designs without the Pi.

    python3 preview_themes.py              # all designs -> previews/<design>.png
    python3 preview_themes.py y2k bento    # just these
    python3 preview_themes.py --bench      # median render ms per design (run it on the Pi too)

Each tile is one rendered 240x240 frame seen through the round bezel, so
anything clipped by the bezel shows up as clipped here too.
"""
import os
import statistics
import sys
import tempfile
import time

from PIL import Image, ImageDraw

import themes
import ui_render
import ui_state
from settings import Settings

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "previews")
W = ui_render.W


def _state(theme):
    path = os.path.join(tempfile.gettempdir(), f"preview_settings_{theme}.json")
    if os.path.exists(path):
        os.remove(path)
    s = ui_state.UIState(Settings(path=path))
    s.settings.set("display", "theme", theme)
    s.settings.set("display", "status_ring", "always")
    s.battery_pct, s.battery_eta_min, s.wifi_connected = 73, 190, True
    s.last_played = (0, 1)
    return s


def states(theme):
    """(label, state) for every screen/state worth looking at. Yields the SAME
    state object mutated step by step - render it before asking for the next."""
    s = _state(theme)
    yield "Home", s
    s.home_sel = 1
    yield "Home: Fortsetzen", s
    s.home_sel = 0
    s.screen, s.library_sel = ui_state.SCREEN_LIBRARY, 1
    yield "Bibliothek", s
    s.library_open()
    s.playlist_sel = 2
    yield "Playlist", s
    s.playlist_open()
    s.now_playing.position = 75.0
    yield "Now Playing", s
    s.now_playing.playing, s.shuffle = False, True
    yield "Pause + Shuffle", s
    s.back()
    s.shuffle = False
    s.screen, s.settings_root_sel = ui_state.SCREEN_SETTINGS_ROOT, 2
    yield "Einstellungen", s
    for cat, sel in (("display", 0), ("led", 3), ("sync", 0)):
        s.screen, s.settings_category, s.settings_detail_sel = ui_state.SCREEN_SETTINGS_DETAIL, cat, sel
        yield f"Settings: {cat}", s
    s.screen = ui_state.SCREEN_SYNC_LOGIN
    s.sync_login_info = {"verification_url": "https://www.google.com/device", "user_code": "WXYZ-4321"}
    yield "YouTube koppeln", s
    s.sync_login_info = None
    s.start_sync_now()
    s.sync_progress_callback(6, 10, "Blinding Lights")
    yield "Sync 6/10", s
    s.sync_progress_callback(10, 10, "")
    yield "Sync fertig", s
    s.start_bt_menu()
    s.bt_known_devices = [{"mac": "AA:BB:CC:DD:EE:FF", "name": "Sony WH-1000XM4", "connected": True},
                          {"mac": "11:22:33:44:55:66", "name": "JBL Flip 5", "connected": False}]
    s.bt_menu_sel = 1
    yield "Bluetooth", s
    s.start_bt_pairing()
    yield "BT: Suche", s
    s.bt_pair_status, s.bt_pair_error = "error", "Gerät hat die Verbindung abgelehnt"
    yield "BT: Fehler", s
    s.start_wifi_menu()
    s.wifi_known_networks = [{"name": "Heim", "ssid": "TILTEDTOWERS", "connected": True}]
    s.wifi_menu_sel = 2
    yield "WLAN", s
    s.start_wifi_scan()
    s.wifi_scan_done([{"ssid": "TILTEDTOWERS", "signal": 80, "secured": True},
                      {"ssid": "Cafe Kleiner Hunger", "signal": 50, "secured": False},
                      {"ssid": "FRITZ!Box 7590 XY", "signal": 30, "secured": True}])
    s.wifi_scan_sel = 1
    yield "WLAN-Liste", s
    s.start_wifi_password_entry("FRITZ!Box 7590 XY")
    s.wifi_password_chars, s.wifi_password_char_idx = list("hunter2"), 12
    yield "WLAN-Passwort", s
    s.start_playlist_manage()
    s.playlist_manage_sel = 1
    yield "Playlists verwalten", s
    s.playlist_manage_open()
    s.playlist_manage_detail_sel, s.playlist_manage_confirm_delete = 1, True
    yield "Loeschen?", s
    s.screen = ui_state.SCREEN_HOME
    s.qc_active, s.qc_phase, s.qc_progress = True, "hold", 0.6
    yield "Quick Connect", s
    s.qc_phase, s.qc_error, s.qc_progress = "error", "Kein Gerät", 1.0
    yield "QC Fehler", s
    s.qc_active, s.qc_phase = False, None


def render_settled(s):
    """Render; if the design is mid-animation (Pixelhaus camera), jump its clock
    past the flight and render the resting frame instead."""
    theme = themes.get(s.settings.get("display", "theme"))
    img = ui_render.render(s)
    if ui_render.animating(s) and hasattr(theme, "_clock"):
        real = theme._clock
        theme._clock = lambda: real() + 10.0
        try:
            img = ui_render.render(s)
        finally:
            theme._clock = real
    return img


def _tile(img, label):
    tile = Image.new("RGB", (W + 10, W + 30), (24, 24, 28))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, W - 1, W - 1], fill=255)
    tile.paste(img, (5, 5), mask)
    ImageDraw.Draw(tile).text((8, W + 10), label, fill=(220, 220, 220))
    return tile


def sheet(theme):
    tiles = [_tile(render_settled(s), label) for label, s in states(theme)]
    s = _state(theme)
    tiles.append(_tile(ui_render.render_shutdown(s), "Ausschalten"))
    cols = 6
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].size
    out = Image.new("RGB", (cols * tw, rows * th), (12, 12, 14))
    for i, t in enumerate(tiles):
        out.paste(t, ((i % cols) * tw, (i // cols) * th))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{theme}.png")
    out.save(path)
    return path


def bench(theme):
    """(slowest screen label, its median ms, Now-Playing median ms) - 5 renders each."""
    worst, playing = ("", 0.0), 0.0
    for label, s in states(theme):
        render_settled(s)  # warm caches/assets first, like a running device
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            ui_render.render(s)
            times.append((time.perf_counter() - t0) * 1000)
        med = statistics.median(times)
        if med > worst[1]:
            worst = (label, med)
        if label == "Now Playing":
            playing = med
    return worst[0], worst[1], playing


if __name__ == "__main__":
    args = sys.argv[1:]
    do_bench = "--bench" in args
    names = [a for a in args if a != "--bench"] or list(themes.THEMES)
    for name in names:
        if do_bench:
            label, ms, playing = bench(name)
            print(f"{name:10s} slowest {ms:6.1f} ms ({label}), Now Playing {playing:6.1f} ms")
        else:
            print(sheet(name))
```

In `.gitignore` under the Python block add:

```
# preview_themes.py output
Software/previews/
```

- [ ] **Step 5: Run tests and the preview**

Run: `python test_ui_state.py && python test_ui_views.py && python test_ui_render.py && python preview_themes.py klassik && python preview_themes.py --bench klassik`
Expected: all tests pass; `previews/klassik.png` written (open it - 25 tiles, Klassik as on the device); bench prints one line (note Klassik's Now-Playing ms = the performance budget).

- [ ] **Step 6: Commit**

```bash
git add ui_state.py ui_render.py main.py preview_themes.py test_ui_state.py test_ui_render.py ../.gitignore
git commit -m "Add Design setting, design animation hook and theme preview sheets"
```

---

### Task 4: Fonts + design toolkit + edge-case contract test

**Files:**
- Create: `Software/fonts/` (10 TTF + 8 OFL files)
- Modify: `Software/ui_common.py` (append toolkit), `Software/test_ui_render.py`

**Interfaces:**
- Produces (in `ui_common`): `FONT_DIR`, `font(file, size, weight=None)`, `glyph_safe(text, font)`, `fit(text, font, max_w)`, `text(draw, xy, s, font, fill, anchor="la", max_w=None) -> width`, `wrap(text, font, max_w, max_lines=None) -> list[str]`, `circle_mask(d)`, `rounded_mask(w, h, r)`, `list_rows(n, sel, pitch, center_y=W/2, min_half=40)`, `busy_phase(period=1.0, steps=4)`, `ICON_FOR_KIND`, `icon_for(item, screen)`, `icon(draw, name, cx, cy, size, color)`, `draw_ring_status(img, sv, style)`.

- [ ] **Step 1: Download the approved fonts (freigegeben in chat, 12.10.2026)**

```bash
mkdir -p fonts && cd fonts
B=https://github.com/google/fonts/raw/main/ofl
get() { curl -sSLf --max-time 60 -o "$1" "$2"; }
get "Orbitron[wght].ttf"        "$B/orbitron/Orbitron%5Bwght%5D.ttf"
get Orbitron-OFL.txt            "$B/orbitron/OFL.txt"
get ShareTechMono-Regular.ttf   "$B/sharetechmono/ShareTechMono-Regular.ttf"
get ShareTechMono-OFL.txt       "$B/sharetechmono/OFL.txt"
get Rajdhani-Medium.ttf         "$B/rajdhani/Rajdhani-Medium.ttf"
get Rajdhani-Bold.ttf           "$B/rajdhani/Rajdhani-Bold.ttf"
get Rajdhani-OFL.txt            "$B/rajdhani/OFL.txt"
get Righteous-Regular.ttf       "$B/righteous/Righteous-Regular.ttf"
get Righteous-OFL.txt           "$B/righteous/OFL.txt"
get "Nunito[wght].ttf"          "$B/nunito/Nunito%5Bwght%5D.ttf"
get Nunito-OFL.txt              "$B/nunito/OFL.txt"
get Poppins-Regular.ttf         "$B/poppins/Poppins-Regular.ttf"
get Poppins-SemiBold.ttf        "$B/poppins/Poppins-SemiBold.ttf"
get Poppins-OFL.txt             "$B/poppins/OFL.txt"
get "SpaceGrotesk[wght].ttf"    "$B/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf"
get SpaceGrotesk-OFL.txt        "$B/spacegrotesk/OFL.txt"
get "PixelifySans[wght].ttf"    "$B/pixelifysans/PixelifySans%5Bwght%5D.ttf"
get PixelifySans-OFL.txt        "$B/pixelifysans/OFL.txt"
cd ..
ls -l fonts
```

Expected sizes (bytes): Orbitron 38576, ShareTechMono 43272, Rajdhani-Medium 384348, Rajdhani-Bold 400680, Righteous 43104, Nunito 276932, Poppins-Regular 160316, Poppins-SemiBold 157312, SpaceGrotesk 136676, PixelifySans 79160; each `*-OFL.txt` ≈ 4.4 KB. Then verify every TTF loads:

```bash
python -c "import glob; from PIL import ImageFont; [ImageFont.truetype(f, 14) for f in glob.glob('fonts/*.ttf')]; print('fonts ok')"
```

- [ ] **Step 2: Write the failing tests**

Append to `Software/test_ui_render.py`:

```python
import ui_common
import ui_views
from ui_views import (CodeView, Item, ListView, MessageView, PasswordView, PlayingView, ProgressView,
                      QuickConnectView, RenderCtx, SettingRow, SettingsView, StatusView)

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


def test_list_rows_stay_inside_the_round_safe_area():
    rows = list(ui_common.list_rows(60, 30, 40))
    assert [off for _, _, _, off in rows] == [-2, -1, 0, 1, 2]
    assert all(half >= 40 for _, _, half, _ in rows)
    assert [i for i, _, _, _ in ui_common.list_rows(3, 0, 40)] == [0, 1, 2]
```

- [ ] **Step 3: Run to verify they fail**

Run: `python test_ui_render.py`
Expected: FAIL - `AttributeError: module 'ui_common' has no attribute 'font'`.

- [ ] **Step 4: Append the toolkit to `Software/ui_common.py`**

```python
# =============================================================================
# Toolkit for the designs in themes/ (Klassik keeps its own DejaVu helpers above
# so it stays pixel-identical).
# =============================================================================
import time

FONT_DIR = os.path.join(HERE, "fonts")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/"


@functools.lru_cache(maxsize=None)
def font(file, size, weight=None):
    """Bundled font from fonts/ (OFL, see fonts/*-OFL.txt). `weight` (e.g. 700)
    only matters for variable fonts ("[wght]" in the file name). Never raises:
    a missing/unreadable file falls back to DejaVu (always on the Pi) or PIL's
    own default font - a forgotten font copy must not take the UI down."""
    size = max(6, round(size))
    try:
        f = ImageFont.truetype(os.path.join(FONT_DIR, file), size)
        if weight is not None:
            try:
                f.set_variation_by_axes([weight])
            except (OSError, ValueError, AttributeError):
                pass  # static font, or a FreeType build without variation support
        return f
    except OSError:
        pass
    try:
        return ImageFont.truetype(_DEJAVU + ("DejaVuSans-Bold.ttf" if (weight or 0) >= 600 else "DejaVuSans.ttf"), size)
    except OSError:
        try:
            return ImageFont.load_default(size)
        except TypeError:  # Pillow < 10.1
            return ImageFont.load_default()


# Symbols our UI strings use that several bundled fonts lack (tofu boxes otherwise).
_GLYPH_FALLBACK = {"→": "->", "←": "<-", "·": "-", "…": "...", "●": "*", "○": "o", "■": "#", "□": "-",
                   "▶": ">", "♪": "~", "⚙": "*", "␣": "_", "✦": "*", "❚": "|", "–": "-", "—": "-"}


@functools.lru_cache(maxsize=4096)
def _has_glyph(f, ch):
    notdef = f.getmask("\uFFFF")
    m = f.getmask(ch)
    return (m.size, bytes(m)) != (notdef.size, bytes(notdef))


def glyph_safe(text, f):
    """`text` with symbols missing from font `f` replaced by ASCII stand-ins."""
    return "".join(c if c.isascii() or c not in _GLYPH_FALLBACK or _has_glyph(f, c) else _GLYPH_FALLBACK[c]
                   for c in str(text))


def fit(text, f, max_w):
    """glyph_safe `text`, cut with an ellipsis so it is at most max_w px wide."""
    s = glyph_safe(text, f)
    if f.getlength(s) <= max_w:
        return s
    ell = glyph_safe("…", f)
    while s and f.getlength(s + ell) > max_w:
        s = s[:-1]
    return (s.rstrip() + ell) if s else ell


def text(draw, xy, s, f, fill, anchor="la", max_w=None):
    """draw.text with glyph fallback (+ ellipsis fit if max_w). Returns the drawn width."""
    s = fit(s, f, max_w) if max_w is not None else glyph_safe(s, f)
    draw.text(xy, s, font=f, fill=fill, anchor=anchor)
    return f.getlength(s)


def wrap(text_, f, max_w, max_lines=None):
    """Word-wrapped lines (glyph-safe), each ≤ max_w; the last kept line gets an
    ellipsis when max_lines cuts the rest off."""
    words, lines, line = glyph_safe(text_, f).split(), [], ""
    for word in words:
        test = (line + " " + word).strip()
        if f.getlength(test) > max_w and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    lines = [fit(l, f, max_w) for l in lines]
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(lines[-1] + glyph_safe("…", f), f, max_w)
    return lines


@functools.lru_cache(maxsize=32)
def circle_mask(d):
    m = Image.new("L", (int(d), int(d)), 0)
    ImageDraw.Draw(m).ellipse([0, 0, int(d) - 1, int(d) - 1], fill=255)
    return m


@functools.lru_cache(maxsize=64)
def rounded_mask(w, h, r):
    m = Image.new("L", (int(w), int(h)), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, int(w) - 1, int(h) - 1], radius=int(r), fill=255)
    return m


def list_rows(n, sel, pitch, center_y=W / 2, min_half=40):
    """Rows of a selection-centered vertical list that land inside the round safe
    area: yields (index, y_center, half_width, offset), offset = index - sel."""
    for i in range(max(0, sel - 4), min(n, sel + 5)):
        y = center_y + (i - sel) * pitch
        half = safe_half_width(y)
        if half >= min_half:
            yield i, y, half, i - sel


def busy_phase(period=1.0, steps=4):
    """Animation step for busy indicators. Only advances where main.py already
    redraws periodically (BT/WLAN/Sync screens, ~2x/s) - no idle animation."""
    return int(time.monotonic() / period * steps) % steps


# --- vector icons ---------------------------------------------------------------
# Shapes, never Unicode glyphs: several symbols are missing from the bundled
# fonts and DejaVu (see NOTES_FOR_PER.md). `size` = icon height in px.
ICON_FOR_KIND = {
    "library": "note", "playlist": "note", "manage_playlist": "note", "track": "note",
    "resume": "play", "settings": "gear", "pair_new": "plus", "connect_new": "plus",
    "wake": "wifi", "network": "wifi", "scan_network": "wifi", "device": "bt", "scan_device": "bt",
    "exclude": "sync", "delete": "warn", "remove": "warn", "forget": "warn",
    "display": "sun", "led": "bulb", "connectivity": "wifi", "sync": "sync", "motion": "wave", "about": "info",
}


def icon_for(item, screen):
    """Icon name for a list Item. The BT/WLAN on-off toggle and the per-device
    connect action share kinds across both menus, so those go by screen."""
    if item.kind in ("toggle", "connect_toggle"):
        return "bt" if screen.startswith("bt_") else "wifi"
    return ICON_FOR_KIND.get(item.kind, "dot")


def icon(draw, name, cx, cy, size, color):
    s = size / 16.0
    lw = max(1, round(1.6 * s))

    def p(x, y):
        return (cx + x * s, cy + y * s)

    if name == "note":
        draw.ellipse([*p(-6, 2), *p(-0.5, 7)], fill=color)
        draw.line([p(-1.2, 4.5), p(-1.2, -7)], fill=color, width=lw)
        draw.polygon([p(-1.2, -7), p(5, -4), p(5, -1), p(-1.2, -4)], fill=color)
    elif name == "play":
        draw.polygon([p(-5, -7), p(7, 0), p(-5, 7)], fill=color)
    elif name == "pause":
        draw.rectangle([*p(-6, -7), *p(-2, 7)], fill=color)
        draw.rectangle([*p(2, -7), *p(6, 7)], fill=color)
    elif name == "gear":
        pts = [p((8 if k % 2 == 0 else 5.8) * math.cos(math.pi * k / 8), (8 if k % 2 == 0 else 5.8) * math.sin(math.pi * k / 8))
               for k in range(16)]
        draw.polygon(pts, outline=color, width=lw)
        draw.ellipse([*p(-2.5, -2.5), *p(2.5, 2.5)], outline=color, width=lw)
    elif name == "plus":
        draw.line([p(-7, 0), p(7, 0)], fill=color, width=lw + 1)
        draw.line([p(0, -7), p(0, 7)], fill=color, width=lw + 1)
    elif name == "wifi":
        for r in (4, 8, 12):
            draw.arc([*p(-r, 6 - r), *p(r, 6 + r)], 225, 315, fill=color, width=lw)
        draw.ellipse([*p(-1.6, 4.4), *p(1.6, 7.6)], fill=color)
    elif name == "bt":
        draw.line([p(-4, -4), p(4, 4), p(0, 8), p(0, -8), p(4, -4), p(-4, 4)], fill=color, width=lw, joint="curve")
    elif name == "sync":
        draw.arc([*p(-7, -7), *p(7, 7)], 200, 340, fill=color, width=lw)
        draw.arc([*p(-7, -7), *p(7, 7)], 20, 160, fill=color, width=lw)
        draw.polygon([p(7.5, -4.5), p(3.5, -3), p(7, 0)], fill=color)
        draw.polygon([p(-7.5, 4.5), p(-3.5, 3), p(-7, 0)], fill=color)
    elif name == "warn":
        draw.polygon([p(0, -8), p(8, 7), p(-8, 7)], outline=color, width=lw)
        draw.line([p(0, -3), p(0, 2.5)], fill=color, width=lw)
        draw.ellipse([*p(-1, 4), *p(1, 6)], fill=color)
    elif name == "sun":
        draw.ellipse([*p(-3.5, -3.5), *p(3.5, 3.5)], fill=color)
        for k in range(8):
            a = math.pi * k / 4
            draw.line([p(5.5 * math.cos(a), 5.5 * math.sin(a)), p(8 * math.cos(a), 8 * math.sin(a))], fill=color, width=lw)
    elif name == "bulb":
        draw.ellipse([*p(-5.5, -8), *p(5.5, 3)], outline=color, width=lw)
        draw.rectangle([*p(-3, 3), *p(3, 7)], fill=color)
    elif name == "wave":
        draw.line([p(x / 2, 5 * math.sin(x / 2 * 0.55)) for x in range(-16, 17)], fill=color, width=lw)
    elif name == "info":
        draw.ellipse([*p(-8, -8), *p(8, 8)], outline=color, width=lw)
        draw.ellipse([*p(-1.2, -5.5), *p(1.2, -3.1)], fill=color)
        draw.line([p(0, -1.5), p(0, 5)], fill=color, width=lw + 1)
    else:  # "dot"
        draw.ellipse([*p(-3, -3), *p(3, 3)], fill=color)


# --- status ring in a design's own style --------------------------------------------

def draw_ring_status(img, sv, st):
    """Battery arc + WLAN/BT dots + %/ETA labels at the shared, hardware-tuned
    RING_* geometry, styled by dict `st`:
      fill, off, wifi, bt, text, accent, font   required
      track (None = no track), low (≤20 %), bolt, segments (0 = continuous
      with round caps), dot ("circle" | "square" | "diamond")."""
    draw = ImageDraw.Draw(img)
    seg = st.get("segments", 0)
    if st.get("track") is not None:
        _ring_band(img, draw, RING_FAR_DEG, RING_ANCHOR_DEG, st["track"], seg)
    if sv.battery_pct is not None:
        pct = max(0, min(100, round(sv.battery_pct)))
        if pct > 0:
            bound = RING_FAR_DEG + (RING_ANCHOR_DEG - RING_FAR_DEG) * pct / 100
            _ring_band(img, draw, RING_FAR_DEG, bound, st.get("low", st["fill"]) if pct <= 20 else st["fill"], seg)
        if sv.charging:
            lightning_bolt(draw, *ring_point(180), 14, st.get("bolt", st["accent"]))
        if sv.show_labels:
            f = st["font"]
            px, py = ring_point(RING_ANCHOR_DEG, r=100)
            _ring_label(draw, px + 10, py - f.size - 2, f"{pct}%", f, st["text"])
            if sv.charging and sv.watts is not None:
                _ring_label(draw, px, py, f"{round(sv.watts)}W", f, st["accent"])
            elif not sv.charging and sv.eta_min is not None:
                _ring_label(draw, px, py, format_eta(sv.eta_min), f, st["text"])
    shape = st.get("dot", "circle")
    _ring_dot(draw, WIFI_DOT_DEG, st["wifi"], st["off"], sv.wifi_on, sv.wifi_connected, shape)
    _ring_dot(draw, BT_DOT_DEG, st["bt"], st["off"], sv.bt_on, sv.bt_connected, shape)


def _ring_label(draw, x_center, y, s, f, fill):
    s = glyph_safe(s, f)
    draw.text((x_center - f.getlength(s) / 2, y), s, font=f, fill=fill)


def _ring_band(img, draw, a, b, color, segments):
    lo, hi = sorted((a, b))
    if not segments:
        ring_arc(img, lo, hi, color)
        cap = RING_WIDTH / 2
        for deg in (lo, hi):
            x, y = ring_point(deg)
            draw.ellipse([x - cap, y - cap, x + cap, y + cap], fill=color)
        return
    span = (RING_ANCHOR_DEG - RING_FAR_DEG) / segments
    for k in range(segments):
        s0 = max(lo, RING_FAR_DEG + k * span + 1.2)
        s1 = min(hi, RING_FAR_DEG + (k + 1) * span - 1.2)
        if s1 > s0:
            ring_arc(img, s0, s1, color)


def _ring_dot(draw, deg, color, off_color, on, connected, shape):
    """Off wins over a stale "connected" (StatusWorker polls only every ~10 s)."""
    x, y = ring_point(deg)
    r = DOT_R
    fill, outline = (off_color, None) if not on else ((color, None) if connected else (None, color))
    if shape == "diamond":
        draw.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=fill, outline=outline)
    elif shape == "square":
        draw.rectangle([x - r + 1, y - r + 1, x + r - 1, y + r - 1], fill=fill, outline=outline, width=2)
    else:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=outline, width=2)
```

- [ ] **Step 5: Run the tests**

Run: `python test_ui_render.py && python test_ui_views.py && python test_ui_state.py`
Expected: all pass (the contract test runs Klassik only so far).

- [ ] **Step 6: Commit**

```bash
git add fonts ui_common.py test_ui_render.py
git commit -m "Bundle OFL fonts and add the shared design toolkit + edge-case contract test"
```

---

## Design Tasks 5-10 - common steps

Each design task has the same five steps; only the module content differs (given per task below).

- [ ] **Step 1: Make the registry test fail** - add the design's `(value, label)` to `ui_state.THEME_CHOICES` (position given per task). Run `python test_ui_render.py` → FAIL in `test_every_design_choice_has_a_theme`.
- [ ] **Step 2: Implement** `Software/themes/<design>.py` per the task's constants, primitives and layout table; every module starts with a docstring naming the design language, imports `ui_common` (+ PIL/numpy as needed) and defines all ten `draw_*` functions from the interface. Then add `from themes import <design>` and `"<value>": <design>,` to `themes/__init__.py` (same order as `THEME_CHOICES`).
- [ ] **Step 3: Tests** - `python test_ui_render.py && python test_ui_views.py && python test_ui_state.py` → all pass (the full walk + edge-case contract now include the new design).
- [ ] **Step 4: Preview + bench** - `python preview_themes.py <value>`, open `previews/<value>.png`, fix anything clipped by the bezel, overlapping, unreadable or colliding with the status-ring labels (Working Conventions); then `python preview_themes.py --bench <value> klassik` → the design's "slowest" ≤ Klassik's "Now Playing". Over budget → cache the expensive layer (backgrounds, blurs, sprites, cover derivatives) with `functools.lru_cache` keyed by size/colors/cover ref.
- [ ] **Step 5: Commit** - `git add themes/<value>.py themes/__init__.py ui_state.py && git commit -m "Add <Design> design"`.

Shared rules for all designs: draw text only through `ui_common.text/fit/wrap` (glyph fallback); icons via `ui_common.icon(draw, ui_common.icon_for(item, view.screen), …)`; covers via `ui_common.cover_image(ref, size)` (never mutate the result); multiply every font size and row pitch by `ctx.scale` (except Bento/Pixelhaus); clamp stepper values `min(value, max)`, progress fractions to `[0, 1]` and list indices to `0 … len(items)-1`; keep text inside `ui_common.safe_half_width(y)` at its y; `draw_shutdown` must accept `ctx=None` (use scale 1.0).

Table shorthand: `field wrap(F, w, n)` means `ui_common.wrap(view.field, F, w, n)` drawn line by line (line step = `F.size + 4`); `half(y)` = `ui_common.safe_half_width(y)`; `s` = `ctx.scale`; `"mm"`/`"la"`/`"ra"` are PIL text anchors; "fit"/"max_w" = `ui_common.fit`; "tail-fit" = keep the end of the string (`"…" + typed[-k:]` with the largest k that fits).

### Task 5: Cybercore (`themes/cybercore.py`)

Choice: append `("cybercore", "Cybercore")`.

**Constants**

```python
BG = (2, 6, 14); GRID = (0, 64, 84); GRID_DIM = (0, 34, 46)
CYAN = (0, 234, 255); CYAN_DIM = (0, 128, 150); WHITE = (226, 248, 255); DIM = (86, 136, 156)
GREEN = (124, 255, 79); RED = (255, 72, 72)


def _t(size, scale=1.0):  # titles
    return ui_common.font("Orbitron[wght].ttf", size * scale, weight=700)


def _m(size, scale=1.0):  # everything else
    return ui_common.font("ShareTechMono-Regular.ttf", size * scale)
```

**Primitives**

```python
@functools.lru_cache(maxsize=1)
def _bg():
    """Radar rings + crosshair, Tron floor grid below the horizon, binary columns, scanlines."""
    img = Image.new("RGB", (W, W), BG)
    d = ImageDraw.Draw(img)
    for r in (36, 68, 100):
        for a in range(0, 360, 12):  # dashed rings
            d.arc([120 - r, 120 - r, 120 + r, 120 + r], a, a + 7, fill=GRID_DIM)
    d.line([(120, 24), (120, 216)], fill=GRID_DIM)
    d.line([(24, 120), (216, 120)], fill=GRID_DIM)
    horizon, vp = 152, (120, 128)
    for k in range(1, 9):
        y = horizon + 88 * (k / 8) ** 2
        d.line([(0, y), (W, y)], fill=GRID)
    for k in range(-9, 10):
        x_far = vp[0] + k * 40 * (horizon - vp[1]) / (W - vp[1])
        d.line([(x_far, horizon), (vp[0] + k * 40, W)], fill=GRID)
    rng = random.Random(1999)
    f = _m(9)
    for x in (26, 34, 198, 206):
        for y in range(70, 172, 10):
            d.text((x, y), rng.choice("01"), font=f, fill=GRID)
    arr = np.asarray(img).copy()
    arr[1::2] = (arr[1::2] * 0.82).astype(np.uint8)
    return Image.fromarray(arr)


def _brackets(draw, box, color, length=8, width=2):
    """HUD target corners."""
    x0, y0, x1, y1 = box
    for x, y, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        draw.line([(x, y), (x + dx * length, y)], fill=color, width=width)
        draw.line([(x, y), (x, y + dy * length)], fill=color, width=width)


def _glow_text(img, xy, s, f, color, max_w=None):
    """Text with a soft same-color halo - blur only the text's own small box."""
    s = ui_common.fit(s, f, max_w) if max_w else ui_common.glyph_safe(s, f)
    x, y = int(xy[0]), int(xy[1])
    w, h = int(f.getlength(s)) + 12, int(f.size * 1.4) + 12
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((6, 6), s, font=f, fill=color + (255,))
    halo = layer.filter(ImageFilter.GaussianBlur(3))
    img.paste(halo, (x - 6, y - 6), halo)
    img.paste(layer, (x - 6, y - 6), layer)


@functools.lru_cache(maxsize=48)
def _duotone(ref, size):
    """Cover as a 2-tone Bayer-dithered image (screen-printed-on-a-CRT look)."""
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16
    g = np.asarray(ui_common.cover_image(ref, size).convert("L"), np.float32) / 255
    thr = np.tile(bayer, (size // 4 + 1, size // 4 + 1))[:size, :size]
    on = (g * 1.15 > thr)[..., None]
    return Image.fromarray(np.where(on, np.array(CYAN, np.uint8), np.array(BG, np.uint8)).astype(np.uint8))
```

**Layout** (`s` = `ctx.scale`, `half(y)` = `ui_common.safe_half_width(y)`)

| View | Composition |
|---|---|
| list | `_bg()` copy. Header `"[ " + title.upper() + " ]"` `_t(12,s)` CYAN, anchor `"mm"` at (120, 30), max_w `2*half(30)-16`; under it `f"0x{sel+1:02X}/{len(items):02X} :: {screen.upper()}"` `_m(9,s)` DIM at (120, 45) `"mm"`. Rows `list_rows(n, sel, 38*s, center_y=124)`: **off 0** → brackets box `(120-half+12, y-20, 120+half-12, y+20)` CYAN; thumb 28×28 at x=`120-half+18`: `_duotone(cover, 28)` or `icon(…, 18, CYAN)` in a 1px CYAN square; label `_glow_text` `_m(16,s)` WHITE at (thumb+36, y-16), max_w to box right-8; sub `"> " + sub` `_m(11,s)` CYAN_DIM at (thumb+36, y+3). **off ±1** → `f"{i+1:02d} // {label.upper()}"` `_m(12,s)` DIM centered at y, max_w `2*half-24`; **off ±2** → same in GRID. Scrollbar x 213-215, y 74-166 GRID, thumb CYAN (height `max(8, 92/n)`). Item tone: muted → label WHITE→DIM; danger → brackets RED. |
| settings | Header like list. Rows `list_rows(n, sel, 26*s, center_y=128, min_half=60)`: row box x `120-half+10 … 120+half-10`; **selected** → filled CYAN rect (h 22*s) with label/value in BG; else label `_m(12,s)` WHITE / value colored. Dotted leader `"·"` (glyph-safe) DIM between label end and value start. Values: toggle `"[ON ]"` GREEN / `"[OFF]"` DIM; stepper `min(v,max)` filled 6×9 CYAN rects + empty GRID outlines, 2 px gaps; else `str(value)` CYAN if `on` else DIM. |
| message | `_bg()`. Header `"[ " + title.upper() + " ]"`; subtitle `_m(11,s)` DIM (120, 54). Line `"> " + text.upper()` (error: `"!! " + text.upper()`) `_m(15,s)` at (120, 96) `"mm"`, color busy CYAN / success GREEN / info WHITE / error RED; busy appends `" " + "|/-\\"[busy_phase(0.5, 4)]`. detail via `wrap(_m(12,s), 180, 3)` from y 114 step 16 (busy: CYAN, else WHITE); hint `wrap(_m(10,s), 170, 2)` DIM below. |
| playing | `_bg()`. Tick ring: 60 ticks, tick k at angle `-90+6k`, from r 60 to 68 around (120, 92), width 2, CYAN if `k/60 < progress` else GRID. Cover `_duotone(cover, 100)` pasted at (70, 42) through `circle_mask(100)`. Radar sweep: RGBA layer, 6 pieslices of 6° trailing behind angle `a = position*45 % 360` with alpha 140,110,80,55,35,20 (CYAN) inside r 50 around (120, 92), composited. Hub circle r 11 BG at (120, 92) with `icon("pause" if playing else "play", 120, 92, 12, CYAN)`. Time `f"{fmt_time(pos)} / {fmt_time(dur)}"` `_m(12,s)` CYAN (120, 166) `"mm"`; `"SHF"` `_m(10,s)` GREEN at (172, 166) if shuffle; title `_m(15,s)` WHITE (120, 184) `"mm"` max_w `2*half(192)-16`; artist `_m(11,s)` DIM (120, 202) `"mm"` max_w `2*half(208)-16`. |
| code | `_bg()`; header; `"> GOTO"` `_m(11,s)` DIM (120, 66); url `_m(12,s)` CYAN (120, 84) max_w 186; `"> ENTER CODE"` DIM (120, 106); code `_t(20,s)` WHITE (120, 132) `"mm"` inside `_brackets((40, 114, 200, 150))`; `"> AWAITING AUTH " + spinner` `_m(11,s)` DIM (120, 172). |
| progress | `_bg()`; header; 12 cells (11×14, gap 2) centered at y 104; filled CYAN for `k < round(12*frac)`, else GRID outline; `f"{current:02d}/{total:02d}"` `_t(20,s)` WHITE (120, 136) `"mm"`; track `_m(11,s)` DIM (120, 162) max_w 170; done → `"> COMPLETE"` `_m(13,s)` GREEN (120, 184). |
| password | `_bg()`; header; ssid `_m(11,s)` DIM (120, 50); typed + `"_"` `_m(15,s)` WHITE (120, 72) - if too wide keep the tail (`"…" + typed[-n:]`); wheel column at x 120: chars `charset[(idx+k) % len]` for k = -2…2 at y 104, 120, 140, 160, 176: k 0 → `_t(22,s)` WHITE in `_brackets((102, 124, 138, 156))`, ±1 `_m(14,s)` CYAN_DIM, ±2 `_m(11,s)` GRID; space shows `"_"`. Hint `wrap(_m(9,s), 150, 2)` DIM from y 192. |
| status | `ui_common.draw_ring_status(img, sv, {"track": GRID_DIM, "fill": CYAN, "low": RED, "off": (30, 50, 60), "wifi": WHITE, "bt": CYAN, "text": DIM, "accent": GREEN, "font": _m(10), "segments": 18, "dot": "square"})` |
| quick_connect | blend frame 0.7 toward BG; `_brackets((40, 40, 200, 200), CYAN, 14, 2)`; arc r 70 width 4 from -90° to `-90+360*progress` CYAN (full circle at 1.0, track GRID); label `_m(14,s)` (RED if error else WHITE) at (120, 120) `"mm"` max_w 120. |
| shutdown | `_bg()`; `"> SHUTDOWN_"` `_m(16)` CYAN (120, 110) `"mm"`; `"SESSION TERMINATED"` `_m(10)` DIM (120, 132) `"mm"`. |

### Task 6: Y2K (`themes/y2k.py`)

Choice: append `("y2k", "Y2K")`.

**Constants**

```python
HOLO = ((255, 196, 232), (182, 226, 255), (196, 255, 232), (220, 200, 255))  # TL, TR, BL, BR
HOT = (255, 46, 151); PINK = (255, 120, 196); AQUA = (0, 176, 255); LILAC = (176, 150, 255)
INK = (52, 28, 110); WHITE = (255, 255, 255); SILVER = (206, 212, 228); RED = (235, 40, 70)
CHROME_STOPS = ((0.0, (255, 255, 255)), (0.45, (205, 215, 235)), (0.55, (104, 112, 150)), (1.0, (236, 240, 250)))


def _title_font(size, scale=1.0):
    return ui_common.font("Righteous-Regular.ttf", size * scale)


def _body(size, scale=1.0, weight=800):
    return ui_common.font("Nunito[wght].ttf", size * scale, weight=weight)
```

**Primitives**

```python
@functools.lru_cache(maxsize=1)
def _bg():
    """Iridescent 4-corner pastel gradient + soft glows + sparkles + soap bubbles."""
    u = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    v = np.linspace(0, 1, W, dtype=np.float32)[:, None, None]
    tl, tr, bl, br = (np.array(c, np.float32) for c in HOLO)
    rgb = (tl * (1 - u) + tr * u) * (1 - v) + (bl * (1 - u) + br * u) * v
    img = Image.fromarray(rgb.astype(np.uint8), "RGB").convert("RGBA")
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for cx, cy, r in ((70, 60, 50), (180, 170, 60)):
        g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 110))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(24)))
    d = ImageDraw.Draw(img)
    rng = random.Random(2001)
    for _ in range(16):
        x, y, r = rng.uniform(20, 220), rng.uniform(20, 220), rng.uniform(2, 6)
        if math.hypot(x - 120, y - 120) < 112:
            _sparkle(d, x, y, r, (255, 255, 255, 230))
    for cx, cy, r in ((58, 170, 12), (186, 62, 9), (166, 198, 7)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 170), width=1)
        d.ellipse([cx - r * 0.55, cy - r * 0.6, cx - r * 0.1, cy - r * 0.2], fill=(255, 255, 255, 210))
    return img.convert("RGB")


def _sparkle(draw, cx, cy, r, color):
    """4-point Y2K star."""
    k = r * 0.22
    draw.polygon([(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
                  (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], fill=color)


def _vgrad(h, stops):
    t = np.linspace(0, 1, max(1, h), dtype=np.float32)
    xs = [p for p, _ in stops]
    return np.stack([np.interp(t, xs, [c[i] for _, c in stops]) for i in range(3)], -1)  # (h, 3)


@functools.lru_cache(maxsize=96)
def _gloss_pill(w, h, base, alpha=255):
    """Aqua candy button: light-top/dark-bottom body + white specular band on the top half."""
    w, h = max(4, int(w)), max(4, int(h))
    light, dark = tuple(min(255, c + 80) for c in base), tuple(max(0, c - 45) for c in base)
    rgb = _vgrad(h, ((0, light), (0.5, base), (1, dark)))
    body = Image.fromarray(np.repeat(rgb[:, None, :], w, 1).astype(np.uint8), "RGB").convert("RGBA")
    body.putalpha(ui_common.rounded_mask(w, h, h // 2).point(lambda a: a * alpha // 255))
    spec = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = max(2, int(h * 0.42))
    band = Image.new("L", (w - 12, sh), 0)
    ImageDraw.Draw(band).rounded_rectangle([0, 0, w - 13, sh - 1], radius=sh // 2, fill=255)
    fade = Image.fromarray((np.linspace(200, 30, sh)[:, None] * np.ones((1, w - 12))).astype(np.uint8), "L")
    spec.paste((255, 255, 255, 255), (6, 2), ImageChops.multiply(band, fade))
    return Image.alpha_composite(body, spec)


@functools.lru_cache(maxsize=96)
def _chrome(s, size):
    """Title text: vertical chrome gradient + indigo outline (Y2K logo look)."""
    f = _title_font(size)
    s = ui_common.glyph_safe(s, f)
    w, h = int(f.getlength(s)) + 8, int(size * 1.4) + 8
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((4, 4), s, font=f, fill=255)
    outline = Image.new("L", (w, h), 0)
    ImageDraw.Draw(outline).text((4, 4), s, font=f, fill=255, stroke_width=2, stroke_fill=255)
    out = Image.new("RGBA", (w, h), INK + (0,))
    out.putalpha(outline)
    grad = Image.fromarray(np.repeat(_vgrad(h, CHROME_STOPS)[:, None, :], w, 1).astype(np.uint8), "RGB").convert("RGBA")
    grad.putalpha(mask)
    return Image.alpha_composite(out, grad)


@functools.lru_cache(maxsize=8)
def _cd(ref, d):
    """Cover printed on a CD: annulus mask, clear hub ring, silver rim."""
    disc = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    mask = ui_common.circle_mask(d).copy()
    hole = d * 0.08
    ImageDraw.Draw(mask).ellipse([d / 2 - hole, d / 2 - hole, d / 2 + hole, d / 2 + hole], fill=0)
    disc.paste(ui_common.cover_image(ref, d).convert("RGBA"), (0, 0), mask)
    dd = ImageDraw.Draw(disc)
    hub = d * 0.18
    dd.ellipse([d / 2 - hub, d / 2 - hub, d / 2 + hub, d / 2 + hub], outline=(235, 240, 250, 200), width=3)
    dd.ellipse([1, 1, d - 2, d - 2], outline=(225, 230, 245, 255), width=2)
    return disc


@functools.lru_cache(maxsize=4)
def _sheen(d):
    """Static rainbow reflection - stays put while the disc spins under it."""
    yy, xx = np.mgrid[0:d, 0:d].astype(np.float32) - d / 2
    ang = np.arctan2(yy, xx)
    hue = ((ang / (2 * np.pi)) % 1.0 * 255).astype(np.uint8)
    full = np.full((d, d), 255, np.uint8)
    rgb = Image.merge("HSV", [Image.fromarray(hue), Image.fromarray((full * 0.55).astype(np.uint8)),
                              Image.fromarray(full)]).convert("RGB")
    alpha = (np.cos(2 * (ang - 0.6)) ** 8 * 110).astype(np.uint8)
    r = np.hypot(xx, yy)
    alpha[(r > d / 2 - 2) | (r < d * 0.18)] = 0
    out = rgb.convert("RGBA")
    out.putalpha(Image.fromarray(alpha))
    return out


def _window(img, box, title, scale):
    """XP-style pop-up: offset shadow, white body, glossy blue title bar, red close box."""
    x0, y0, x1, y1 = (int(v) for v in box)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0 + 3, y0 + 4, x1 + 3, y1 + 4], 10, fill=(170, 140, 220))
    d.rounded_rectangle([x0, y0, x1, y1], 10, fill=(246, 248, 255), outline=(60, 90, 210), width=2)
    bar = _gloss_pill(x1 - x0 - 4, 22, (36, 104, 232))
    img.paste(bar, (x0 + 2, y0 + 2), bar)
    ui_common.text(d, (x0 + 12, y0 + 13), title, _body(11, scale), WHITE, anchor="lm", max_w=x1 - x0 - 44)
    d.rounded_rectangle([x1 - 22, y0 + 6, x1 - 8, y0 + 20], 3, fill=(232, 76, 58), outline=WHITE)
    d.line([(x1 - 18, y0 + 10), (x1 - 12, y0 + 16)], fill=WHITE, width=2)
    d.line([(x1 - 12, y0 + 10), (x1 - 18, y0 + 16)], fill=WHITE, width=2)


def _barber(img, box, frac, phase):
    """Aqua progress bar: glossy track, blue fill with diagonal stripes shifted by `phase` (0-1)."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    track = _gloss_pill(w, h, SILVER)
    img.paste(track, (x0, y0), track)
    fw = int(w * max(0.0, min(1.0, frac)))
    if fw < h:
        return
    fill = _gloss_pill(fw, h, AQUA).copy()
    stripes = Image.new("L", (fw, h), 0)
    sd = ImageDraw.Draw(stripes)
    off = int(phase * 2 * h)
    for x in range(-2 * h + off, fw + h, 2 * h):
        sd.polygon([(x, h), (x + h, h), (x + 2 * h, 0), (x + h, 0)], fill=70)
    fill.paste((255, 255, 255, 255), (0, 0), ImageChops.multiply(stripes, fill.getchannel("A")))
    img.paste(fill, (x0, y0), fill)
```

**Layout**

| View | Composition |
|---|---|
| list | `_bg()` copy. Header `_chrome(title, 18*s)` centered at y 18 (shrink size until width ≤ `2*half(30)-20`), sparkles r 4 left/right of it. Rows `list_rows(n, sel, 56*s, center_y=126, min_half=56)`: **off 0** → `_gloss_pill(2*half-20, 50*s, HOT)` centered at y; inside: glass orb (circle d=`36*s` at left+8: cover through `circle_mask` or `_gloss_pill(d,d,AQUA)` + `icon(…, 18*s, WHITE)`) + white specular dot; label `_body(15,s)` WHITE + sub `_body(11,s,700)` (255,230,245), max_w to pill end; `_sparkle` r 6 WHITE at the pill's top-right. **off ≠ 0** → `_gloss_pill(2*half-28, 36*s, (255,255,255), alpha=150)`, label `_body(12,s)` INK, max_w. Tone: muted orbs SILVER, danger orbs RED, settings categories LILAC. |
| settings | `_bg()`; header chrome; rows `list_rows(n, sel, 34*s, center_y=128, min_half=56)`: each row `_gloss_pill(2*half-24, 30*s, …)` - selected AQUA (text WHITE), else (255,255,255) alpha 150 (text INK). Label left `_body(12,s)`; value right: toggle = `_gloss_pill(34*s, 18*s, HOT if on else SILVER)` + white knob circle; stepper = `max` beads r 5: filled `_gloss_pill(10,10,HOT)`, empty WHITE outline INK; else text `_body(11,s)` HOT if on else INK. |
| message | `_bg()`; `_window(img, (32, 66, 208, 182), title, s)`; icon at (56, 112): busy → ring of 8 dots, dot `busy_phase(0.5,8)` HOT others SILVER; error → RED circle r 13 + white "!"; success → green (52,199,89) circle + white check polyline; info → AQUA circle + white "i". `text` `_body(14,s)` INK at (76, 104) max_w 124; detail `wrap(_body(11,s,600), 128, 3)` INK from y 122; hint `_body(10,s,600)` (120,110,150) at y 166 max_w 160. subtitle (if any) `_body(11,s)` INK centered at y 50. |
| playing | `_bg()`. CD: `_cd(cover, 124).rotate(-position*60 % 360, BICUBIC)` pasted at (58, 28); `_sheen(124)` over it at the same spot (not rotated). Twinkle: 5 sparkles around the CD at fixed seeded spots, radius `3 + 2*abs(sin(position*2 + k))`. Title `_chrome(title, 17*s)` centered at y 156 (shrink/truncate to `2*half(166)-20`); artist `_body(11,s,700)` INK (120, 186) `"mm"` max_w 150; bottom pill `_gloss_pill(96, 20, AQUA)` centered at y 204: `icon("pause"/"play", …, 10, WHITE)` + `fmt_time(position)` `_body(10,s)` WHITE; shuffle → `_sparkle` r 5 HOT right of the pill. |
| code | `_bg()`; `_window((26, 50, 214, 196))`; "Gehe zu" `_body(11,s,700)` INK (120, 88); url `_body(12,s)` AQUA (120, 106) max_w 176; "Code:" INK (120, 128); white field rect (54,138)-(186,170) with INK 1px inset border; code `_chrome(code, 20*s)` centered in the field; "Warte auf Bestätigung …" `_body(10,s,600)` INK (120, 184). |
| progress | `_bg()`; `_window((26, 62, 214, 186))`; `_barber(img, (44, 112, 196, 128), current/total, busy_phase(0.5, 8)/8)`; `f"{current} / {total}"` `_body(15,s)` INK (120, 144); track `_body(11,s,600)` INK (120, 164) max_w 160; done → `_chrome("Fertig!", 18)` + 2 sparkles at y 92. |
| password | `_bg()`; header chrome "WLAN-Passwort"; ssid `_body(11,s,700)` INK (120, 48); white text field (40,62)-(200,86) with typed `_body(14,s)` INK (tail if too long); carousel at y 128: current char `_gloss_pill(52, 52, HOT)` + `_title_font(28,s)` WHITE centered; ±1 `_gloss_pill(34,34,(255,255,255),150)` at x 120±50 with `_body(16,s)` INK; ±2 `_gloss_pill(24,24,(255,255,255),110)` at x 120±88 `_body(11,s)`; space shown as `"_"`. Hint `wrap(_body(9,s,700), 150, 2)` INK from y 168. |
| status | `draw_ring_status(img, sv, {"track": (236, 220, 248), "fill": HOT, "low": RED, "off": (205, 205, 215), "wifi": AQUA, "bt": LILAC, "text": INK, "accent": AQUA, "font": _body(10), "segments": 0, "dot": "circle"})` |
| quick_connect | blend frame 0.5 toward WHITE; 12 sparkles on circle r 70: sparkle k lit HOT (r 7) if `k/12 < progress` else SILVER (r 4); label `_chrome(label, 16)` centered at y 112 (`_body(14)` RED text instead if error). |
| shutdown | `_bg()`; `_chrome("Bye bye!", 24)` centered at y 98; 3 sparkles; `"bis bald ✦"` `_body(12)` INK (120, 140). |

### Task 7: Glassmorphism (`themes/glass.py`)

Choice: append `("glass", "Glas")`.

**Constants**

```python
NAVY = (10, 12, 30)
ORBS = ((123, 47, 247), (241, 7, 163), (0, 210, 255), (255, 138, 0))
TEXT = (255, 255, 255); DIM = (196, 202, 230); ACCENT = (110, 231, 249); RED = (255, 99, 132); GREEN = (74, 222, 128)
ORB_SPOTS = ((60, 58, 82), (192, 70, 72), (64, 190, 76), (186, 186, 86))  # (cx, cy, r)


def _semi(size, scale=1.0):
    return ui_common.font("Poppins-SemiBold.ttf", size * scale)


def _reg(size, scale=1.0):
    return ui_common.font("Poppins-Regular.ttf", size * scale)
```

**Primitives**

```python
@functools.lru_cache(maxsize=16)
def _orb_bg(colors):
    """Navy + four big orbs, blurred into colored light (cached per color set)."""
    img = Image.new("RGB", (W, W), NAVY)
    d = ImageDraw.Draw(img)
    for (cx, cy, r), c in zip(ORB_SPOTS, colors):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    return img.filter(ImageFilter.GaussianBlur(34))


def _bg_for(view):
    """Library/playlist views tint two orbs with the playlist color."""
    color = None
    items = getattr(view, "items", None)
    if items and 0 <= view.sel < len(items) and items[view.sel].cover:
        color = ui_common.hex_to_rgb(items[view.sel].cover[2])
    return _orb_bg(ORBS if color is None else (color, ORBS[1], ORBS[2], color)).copy()


@functools.lru_cache(maxsize=8)
def _cover_backdrop(ref):
    """Now Playing backdrop: the cover blurred full-screen and darkened (Apple-Music style)."""
    img = ui_common.cover_image(ref, W).filter(ImageFilter.GaussianBlur(20))
    return Image.blend(img, Image.new("RGB", (W, W), NAVY), 0.45)


@functools.lru_cache(maxsize=32)
def _shadow(w, h, r, blur=8, alpha=90):
    pad = blur * 2
    m = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(m).rounded_rectangle([pad, pad, pad + w, pad + h], radius=r, fill=alpha)
    out = Image.new("RGBA", m.size, (0, 0, 0, 0))
    out.putalpha(m.filter(ImageFilter.GaussianBlur(blur)))
    return out, pad


def _glass(img, box, r, strength=1.0, selected=False):
    """Frosted panel: soft shadow, translucent white fill, thin light border, top-edge light catch.
    `strength` (0-1) fades it for depth (neighbors of the selection)."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = x1 - x0, y1 - y0
    sh, pad = _shadow(w, h, r)
    img.paste(sh, (x0 - pad, y0 - pad + 4), sh)
    panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    fill_a = int((64 if selected else 38) * strength)
    edge_a = int((150 if selected else 90) * strength)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=(255, 255, 255, fill_a), outline=(255, 255, 255, edge_a))
    d.line([(r, 1), (w - r, 1)], fill=(255, 255, 255, int(120 * strength)))
    img.paste(panel, (x0, y0), panel)
```

**Layout**

| View | Composition |
|---|---|
| list | `_bg_for(view)`. Header `title` `_semi(14,s)` TEXT, letter-spaced via `ui_common.letter_spaced(title.upper())`, `"mm"` at (120, 30), max_w `2*half(30)-12`. Rows `list_rows(n, sel, 66*s, center_y=124, min_half=60)`: card width `2*half-14` (off 0) / `(2*half-14)*0.86` (off ≠ 0), height `60*s` / `48*s`; `_glass(…, r=18, strength=1 if off==0 else 0.6, selected=off==0)`. Inside: thumb (off 0: 44*s, else 32*s) rounded r 12 - cover through `rounded_mask`, else glass circle tinted by tone (accent ACCENT, muted (255,255,255), danger RED, category: a fixed per-category color list) + `icon(…, 18*s, TEXT)`; label `_semi(15 if off==0 else 12, s)` TEXT (alpha via DIM for off ≠ 0); sub `_reg(11,s)` DIM, off 0 only. |
| settings | `_bg_for(view)`; header; one `_glass` panel `(26, 52, 214, 196)` r 22; rows `list_rows(n, sel, 30*s, center_y=124, min_half=70)` clipped to the panel; selected row → inner `_glass` pill (r 12, selected=True); separators (255,255,255,40); toggle: capsule 36×20 `_glass` + knob circle 14: on → ACCENT with a 6 px blurred ACCENT glow behind it, off → (255,255,255); stepper: `max` dots r 4: filled ACCENT, empty outline (255,255,255,120); values `_reg(11,s)` ACCENT if on else DIM. |
| message | `_orb_bg(ORBS).copy()`; header; `_glass((40, 66, 200, 176), r=22)`; icon at (120, 92) r 14: busy → arc 270° rotated by `busy_phase(0.25, 8)*45` ACCENT width 3; error → RED circle + "!"; success → GREEN circle + check; info → "i" in TEXT ring. `text` `_semi(14,s)` TEXT (120, 120) `"mm"` max_w 150; detail `wrap(_reg(11,s), 146, 3)` DIM from y 134; hint `_reg(10,s)` DIM at y 186 (outside the card) max_w 150; subtitle `_reg(11,s)` DIM (120, 52). |
| playing | `_cover_backdrop(cover).copy()` + `_orb_bg(ORBS)` blended 0.25 over it. Cover 112×112 at (64, 30) through `rounded_mask(112,112,18)` with `_shadow(112,112,18,10,140)` under it. Progress line y 150 x 72-168: track (255,255,255) 2 px, fill ACCENT 3 px; times `_reg(9,s)` DIM at both ends (x 72 left-anchored "la", x 168 "ra", y 156). Title `_semi(15,s)` TEXT (120, 172) `"mm"` max_w `2*half(180)-20`; artist `_reg(11,s)` DIM (120, 190) `"mm"` max_w `2*half(196)-20`; glass pill `_glass((96, 200, 144, 220), r=10)` with play/pause icon 10 TEXT; shuffle → `icon("sync", 156, 210, 10, ACCENT)`. |
| code | `_orb_bg(ORBS)`; header; `_glass((30, 56, 210, 194), r=22)`; "Gehe zu" `_reg(11,s)` DIM (120, 76); url `_semi(12,s)` TEXT (120, 94) max_w 166; "Code" `_reg(11,s)` DIM (120, 118); code `_semi(24,s)` ACCENT (120, 142) `"mm"` with a blurred ACCENT glow copy behind; "Warte auf Bestätigung …" `_reg(10,s)` DIM (120, 176). |
| progress | `_orb_bg(ORBS)`; header; `_glass((34, 72, 206, 180))`; capsule track (54,110)-(186,122) white alpha 50, fill = horizontal gradient ACCENT→(123,47,247) masked to the fraction, glow (blur 4) behind; `f"{current} / {total}"` `_semi(16,s)` TEXT (120, 140); track `_reg(11,s)` DIM (120, 160) max_w 150; done → "Fertig!" `_semi(13,s)` GREEN (120, 196). |
| password | `_orb_bg(ORBS)`; header; ssid `_reg(11,s)` DIM (120, 50); input `_glass((40, 62, 200, 88), r=12)` with typed `_semi(14,s)` TEXT (tail-fit); keycaps at y 126: current `_glass((96, 102, 144, 150), r=14, selected=True)` + char `_semi(28,s)` TEXT; ±1 `_glass` 34×34 at x 120±50, strength 0.7, char `_reg(15,s)`; ±2 24×24 at x 120±86, strength 0.4; space shown `"_"`. Hint `wrap(_reg(9,s), 150, 2)` DIM from y 164. |
| status | `draw_ring_status(img, sv, {"track": (70, 72, 104), "fill": ACCENT, "low": RED, "off": (90, 92, 120), "wifi": TEXT, "bt": (140, 170, 255), "text": DIM, "accent": GREEN, "font": _reg(10), "segments": 0})` |
| quick_connect | frame GaussianBlur(6) + blend 0.4 toward NAVY; `_glass((42, 42, 198, 198), r=78)`; arc r 64 width 5: track (255,255,255,60)-ish (draw on RGB as (90,92,120)), progress ACCENT (RED if error); label `_semi(14,s)` (120, 120) `"mm"` max_w 110. |
| shutdown | `_orb_bg(ORBS)`; `_semi(18)` "Bis bald" (120, 110) `"mm"`; `_reg(11)` DIM "Mini-Musikplayer" (120, 134). |

### Task 8: Neumorphism (`themes/neumorph.py`)

Choice: append `("neumorph", "Neumorph")`.

**Constants**

```python
BASE = (224, 229, 236); LIGHT = (255, 255, 255); DARK = (163, 177, 198)
TEXT = (68, 76, 96); DIM = (140, 150, 170); ACCENT = (91, 124, 250); DANGER = (235, 87, 87)


def _nf(size, scale=1.0, weight=700):
    return ui_common.font("Nunito[wght].ttf", size * scale, weight=weight)
```

**Primitives**

```python
@functools.lru_cache(maxsize=64)
def _raised(w, h, r, d=6):
    """Extruded shape: light shadow up-left, dark shadow down-right. Returns (sprite, pad)."""
    w, h, r = int(w), int(h), int(r)
    pad = d * 3
    size = (w + 2 * pad, h + 2 * pad)
    out = Image.new("RGBA", size, BASE + (0,))
    for color, off in ((LIGHT, -d), (DARK, d)):
        sh = Image.new("L", size, 0)
        ImageDraw.Draw(sh).rounded_rectangle([pad + off, pad + off, pad + off + w, pad + off + h], radius=r, fill=210)
        layer = Image.new("RGBA", size, color + (0,))
        layer.putalpha(sh.filter(ImageFilter.GaussianBlur(d)))
        out = Image.alpha_composite(out, layer)
    face = Image.new("L", size, 0)
    ImageDraw.Draw(face).rounded_rectangle([pad, pad, pad + w, pad + h], radius=r, fill=255)
    out.paste(BASE + (255,), (0, 0), face)
    return out, pad


def _inset_from_shape(shape, d):
    """Pressed-in well for an L mask `shape`: dark inner shadow from the top-left
    edge, light from the bottom-right. ImageChops.offset wraps - fine, the
    padding around the shape is uniformly 'outside'."""
    out = Image.new("RGBA", shape.size, BASE + (255,))
    outside = ImageOps.invert(shape)
    for color, off in ((DARK, d), (LIGHT, -d)):
        sh = ImageChops.multiply(ImageChops.offset(outside, off, off).filter(ImageFilter.GaussianBlur(d)), shape)
        layer = Image.new("RGBA", shape.size, color + (0,))
        layer.putalpha(sh)
        out = Image.alpha_composite(out, layer)
    out.putalpha(shape)
    return out


@functools.lru_cache(maxsize=64)
def _inset(w, h, r, d=4):
    w, h, r = int(w), int(h), int(r)
    pad = d * 3
    shape = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(shape).rounded_rectangle([pad, pad, pad + w, pad + h], radius=r, fill=255)
    return _inset_from_shape(shape, d), pad


@functools.lru_cache(maxsize=8)
def _inset_ring(r_out, r_in, d=3):
    """Annular groove centered on the screen (progress ring, status track)."""
    shape = Image.new("L", (W, W), 0)
    sd = ImageDraw.Draw(shape)
    sd.ellipse([W / 2 - r_out, W / 2 - r_out, W / 2 + r_out, W / 2 + r_out], fill=255)
    sd.ellipse([W / 2 - r_in, W / 2 - r_in, W / 2 + r_in, W / 2 + r_in], fill=0)
    return _inset_from_shape(shape, d)


@functools.lru_cache(maxsize=1)
def _bowl():
    """The whole round screen as one shallow pressed-in dish."""
    img = Image.new("RGB", (W, W), BASE)
    well, pad = _inset(232, 232, 116, d=8)
    img.paste(well, (4 - pad, 4 - pad), well)
    return img


def _paste(img, sprite_pad, x, y):
    sprite, pad = sprite_pad
    img.paste(sprite, (int(x) - pad, int(y) - pad), sprite)


def _emboss(draw, xy, s, f, fill, anchor="mm", max_w=None):
    """Letterpress text: a light copy 1 px down-right under the real one."""
    ui_common.text(draw, (xy[0] + 1, xy[1] + 1), s, f, LIGHT, anchor=anchor, max_w=max_w)
    ui_common.text(draw, xy, s, f, fill, anchor=anchor, max_w=max_w)
```

**Layout**

| View | Composition |
|---|---|
| list | `_bowl()` copy. Header `_emboss` `title.upper()` letter-spaced `_nf(13,s,800)` TEXT at (120, 32), max_w `2*half(32)-16`. Rows `list_rows(n, sel, 60*s, center_y=124, min_half=56)`: **off 0** → `_raised(2*half-28, 54*s, 27*s)` at x `120-half+14`, y-27*s; inside: inset circle well `_inset(40*s,40*s,20*s)` at left+8 holding the cover (circle mask, d 34*s) or `icon(…, 18*s, ACCENT/DIM/DANGER by tone)`; label `_nf(15,s,800)` TEXT; sub `_nf(11,s,600)` ACCENT. **off ≠ 0** → no shape, label `_nf(12,s,700)` DIM centered at y, max_w `2*half-40`. Scroll indicator: `_inset(6, 70, 3)` at x 214, y 86; raised dot 6×6 at the scroll fraction. |
| settings | `_bowl()`; header; rows `list_rows(n, sel, 34*s, center_y=126, min_half=64)`: selected → `_raised(2*half-26, 30*s, 15*s)` behind; label `_nf(12,s,700)` TEXT left; value right: toggle = `_inset(36,20,10)` track + `_raised(14,14,7,d=3)` knob left/right, knob tinted ACCENT (paste the raised sprite, then fill a 10 px ACCENT circle inside) when on; stepper = `_inset(56,8,4)` track + ACCENT fill to `min(v,max)/max` + `_raised(12,12,6,d=3)` knob; else text `_nf(11,s,700)` ACCENT if on else DIM. |
| message | `_bowl()`; header; `_raised(84, 84, 42)` at (78, 64); icon inside at (120, 106): busy → ACCENT arc 90° rotating `busy_phase(0.25,8)*45`, width 4, r 18; error → "!" `_nf(30,1,900)` DANGER; success → check polyline ACCENT width 4; info → "i" DIM. `_emboss` text `_nf(14,s,800)` TEXT (120, 166) max_w 170; detail `wrap(_nf(11,s,600), 160, 2)` DIM from y 182; hint `_nf(10,s,600)` DIM below; subtitle `_nf(11,s,700)` DIM (120, 52). |
| playing | `_bowl()`; groove `_inset_ring(103, 89)` pasted at (0,0); ACCENT arc r 96 width 6 from -90° to `-90+360*progress`; knob `_raised(16,16,8,d=3)` centered at the arc end (`ring` point at r 96, that angle). Disc `_raised(156,156,78)` at (42, 42). Cover well `_inset(92,92,46)` at (74, 50); cover circle d 84 at (78, 54). Title `_nf(13,s,800)` TEXT (120, 156) `"mm"` max_w 118; artist `_nf(10,s,600)` DIM (120, 172) max_w 108. Play button at (120, 190): playing → `_raised(26,26,13,d=3)` + pause icon 10 ACCENT; paused → `_inset(26,26,13,d=3)` + play icon 10 ACCENT. Shuffle → small ACCENT `icon("sync", 148, 190, 9, ACCENT)`. |
| code | `_bowl()`; header; "Gehe zu" `_nf(11,s,700)` DIM (120, 70); url `_nf(12,s,800)` TEXT (120, 88) max_w 170; `_inset(150, 44, 14)` at (45, 108); code `_emboss` `_nf(22,s,900)` ACCENT (120, 130); "Warte auf Bestätigung …" `_nf(10,s,600)` DIM (120, 172). |
| progress | `_bowl()`; header; `_inset(150, 14, 7)` at (45, 112) + ACCENT fill rounded to the fraction + `_raised(18,18,9,d=3)` knob at its end; `_emboss` `f"{current}/{total}"` `_nf(22,s,900)` TEXT (120, 146); track `_nf(11,s,600)` DIM (120, 170) max_w 150; done → "Fertig!" `_nf(13,s,800)` ACCENT (120, 190). |
| password | `_bowl()`; header; ssid `_nf(11,s,700)` DIM (120, 50); `_inset(160, 26, 13)` at (40, 62) with typed `_nf(14,s,800)` TEXT (tail-fit); current char `_raised(52,52,14)` at (94, 100) + `_nf(26,s,900)` ACCENT; ±1 chars `_nf(16,s,700)` DIM at x 120±48, ±2 `_nf(11,s,700)` (190,196,210) at x 120±84, y 126; space `"_"`. Hint `wrap(_nf(9,s,700), 150, 2)` DIM from y 168. |
| status | Track: paste `_inset_ring(126, 114)` through a pieslice mask covering 146°-214°; then `draw_ring_status(img, sv, {"track": None, "fill": ACCENT, "low": DANGER, "off": (200, 206, 216), "wifi": TEXT, "bt": ACCENT, "text": DIM, "accent": ACCENT, "font": _nf(10, 1, 800), "segments": 0})`. |
| quick_connect | blend frame 0.6 toward BASE; `_raised(150,150,75)` at (45,45); `_inset_ring(66, 56)` pasted; ACCENT (DANGER if error) arc r 61 width 6 to progress; label `_emboss` `_nf(13,s,800)` TEXT (120, 120) max_w 96. |
| shutdown | `_bowl()`; `_raised(110,110,55)` at (65,65); `_emboss` "Gute Nacht" `_nf(15,1,800)` TEXT (120, 120). |

### Task 9: Bento Grid (`themes/bento.py`)

Choice: append `("bento", "Bento")`. Ignores `ctx.scale`.

**Constants**

```python
BG = (8, 8, 9); TILE = (28, 28, 30); TILE2 = (44, 44, 46)
TEXT = (245, 245, 247); DIM = (142, 142, 147)
LIME = (198, 244, 50); ORANGE = (255, 159, 10); BLUE = (10, 132, 255); PINK = (255, 55, 95); PURPLE = (191, 90, 242)
CAT_COLORS = {"display": ORANGE, "led": LIME, "connectivity": BLUE, "sync": PURPLE, "motion": PINK, "about": TILE2}
CLIP_R = 112                      # round bento: everything outside goes back to BG (status ring sits at r >= 114)
ROW_A, ROW_B, ROW_C = (14, 82), (88, 152), (158, 226)
COLS2 = ((14, 117), (123, 226))
RAD = 16


def _g(size, weight=700):
    return ui_common.font("SpaceGrotesk[wght].ttf", size, weight=weight)
```

**Primitives**

```python
def _tile(draw, box, fill=TILE, sel=False):
    draw.rounded_rectangle(box, RAD, fill=fill)
    if sel:
        draw.rounded_rectangle(box, RAD, outline=TEXT, width=2)


@functools.lru_cache(maxsize=1)
def _outside():
    m = Image.new("L", (W, W), 255)
    ImageDraw.Draw(m).ellipse([W / 2 - CLIP_R, W / 2 - CLIP_R, W / 2 + CLIP_R, W / 2 + CLIP_R], fill=0)
    return m


def _finish(img):
    """Cut the square grid to the round glass - outer tiles get curved outer edges."""
    img.paste(BG, (0, 0, W, W), _outside())
    return img


def _tile_text(draw, box, lines):
    """lines: [(text, font, fill)] stacked from the tile's top-left inner corner,
    each fitted to the part of the tile that is inside the round safe area at its y."""
    x0, y0, x1, y1 = box
    y = y0 + 10
    for s, f, fill in lines:
        half = ui_common.safe_half_width(y + f.size / 2)
        left, right = max(x0 + 10, W / 2 - half + 4), min(x1 - 10, W / 2 + half - 4)
        if right - left > 12:
            ui_common.text(draw, (left, y), s, f, fill, max_w=right - left)
        y += f.size + 4
```

**Layout** (tile boxes `(x0, y0, x1, y1)`; every view ends with `_finish(img)`)

| View | Composition |
|---|---|
| list: Home | Library tile `(14,14,226,82)` (item label `_g(16)` + item sub `_g(11,500)` DIM, `icon("note")` 22 LIME at right); Resume tile `(14,88,152,152)`: cover 48×48 rounded (r 10) at (24, 96) + title `_g(12)` + "Fortsetzen" `_g(10,500)` DIM (if no resume item: "Mini-Musikplayer" tile, not selectable); Battery tile `(158,88,226,152)`: `f"{pct}%"` `_g(20)` LIME (DIM "--" if None), "Akku" `_g(10,500)` DIM, bolt if charging; Settings tile `(14,158,117,226)` gear icon + "Einstellungen" `_g(11)`; Radio tile `(123,158,226,226)`: WLAN/BT rows with dots (filled BLUE when connected, outline when on, TILE2 when off) `_g(10,500)`. Selection = `view.items[sel].kind` → that tile gets `sel=True` and fill TILE2. |
| list: Settings root | 2×3 grid: rows A/B/C × COLS2; category k → tile fill `CAT_COLORS[kind]` when selected (text BG) else TILE with icon in that color; icon 22 + label `_g(12)`. |
| list: other | Row A `(14,14,226,82)`: previous item (label `_g(12,500)` DIM) or the title `_g(14)` when sel == 0; Row B hero `(14,88,226,152)` fill TILE2 sel=True: cover/icon 48 at (24, 96), label `_g(15)`, sub `_g(11,500)` DIM; Row C `(14,158,152,226)`: next item label `_g(12,500)` DIM; counter tile `(158,158,226,226)` fill LIME: `f"{sel+1}"` `_g(22)` BG + `f"/{n}"` `_g(11,500)` BG. Tone danger → hero fill PINK; muted → hero icon DIM. |
| settings | Row A: previous row (label + value small) or the title; Row B hero `(14,88,226,152)` TILE2 sel=True: label `_g(12,500)` DIM top-left, value big: toggle → "AN"/"AUS" `_g(26)` (LIME/DIM) + pill 40×22 (LIME/TILE); stepper → `str(min(v,max))` `_g(30)` LIME + `max` bars 6×(6..20 rising) at the right; else `str(value)` `_g(18)` TEXT/LIME if on (fit); Row C: next row tile `(14,158,152,226)` + counter tile `(158,158,226,226)` ORANGE. |
| message | Row A title tile; Row B hero fill by mood (busy BLUE, error PINK, success LIME (text BG), info TILE2): `text` `_g(18)` + spinner dots `busy_phase` for busy; Row C `(14,158,226,226)` detail/hint `wrap(_g(11,500), …, 3)` via `_tile_text`; subtitle (if any) inside the Row A tile under the title. |
| playing | Cover tile `(14,14,140,152)`: cover 126×138 center-cropped from `cover_image(ref, 140)`, rounded mask r 16; Play tile `(146,14,226,82)` fill LIME when playing (pause icon 24 BG) else TILE (play icon 24 LIME), shuffle badge (small ORANGE dot + "SHF" `_g(9)`) in its corner when on; Time tile `(146,88,226,152)`: `fmt_time(position)` `_g(20)` + `"/"+fmt_time(duration)` `_g(10,500)` DIM; Title tile `(14,158,226,226)`: title `_g(14)`, artist `_g(11,500)` DIM, progress bar 4 px LIME at the tile's inner bottom (x from `W/2-half(212)+8` to `W/2+half(212)-8`). |
| code | Row A title tile; Row B hero LIME: code `_g(26)` BG centered; Row C left `(14,158,152,226)`: url `wrap(_g(10,500), …, 3)`; right `(158,158,226,226)`: "Warte" + spinner. |
| progress | Row A title tile; Row B left `(14,88,152,152)`: `f"{current}/{total}"` `_g(26)`; right `(158,88,226,152)` LIME: `f"{round(100*frac)}%"` `_g(16)` BG; Row C `(14,158,226,226)`: track `_g(11,500)` + 6 px bar; done → Row C fill LIME "Fertig!". |
| password | Row A `(14,14,226,82)`: ssid `_g(11,500)` DIM + typed `_g(14)` (tail-fit); Row B left `(14,88,152,152)`: chars idx-2…idx+2 in a row `_g(16,500)` DIM, current underlined; right `(158,88,226,152)` LIME: current char `_g(34)` BG (space `"_"`); Row C: 4 hint tiles `(14,158,67,226)`, `(73,158,120,226)`, `(126,158,173,226)`, `(179,158,226,226)` with icons wave/dot/sync/play + `_g(8,500)` labels "Dreh", "Klick", "Lösch", "OK". |
| status | `draw_ring_status(img, sv, {"track": (40, 40, 42), "fill": LIME, "low": PINK, "off": TILE2, "wifi": TEXT, "bt": BLUE, "text": DIM, "accent": LIME, "font": _g(10, 500), "segments": 0})` |
| quick_connect | blend frame 0.75 toward BG; hero tile `(30,88,210,152)` TILE2: label `_g(15)` (PINK if error) + bar `(44,136)-(196,142)` LIME to progress. |
| shutdown | tiles: `(14,88,226,152)` "Bis bald" `_g(20)`; `(14,158,117,226)` LIME moon (circle minus offset circle); `(123,158,226,226)` "Mini-Musikplayer" `_g(10,500)` DIM; `_finish`. |

### Task 10: Cyberpunk (`themes/cyberpunk.py`)

Choice: append `("cyberpunk", "Cyberpunk")`.

**Constants**

```python
BG = (5, 5, 8); YELLOW = (252, 238, 10); RED = (255, 0, 60); CYAN = (0, 240, 255)
DIM = (130, 124, 40); WHITE = (240, 240, 230); PANEL = (20, 20, 12)


def _rb(size, scale=1.0):  # Rajdhani Bold
    return ui_common.font("Rajdhani-Bold.ttf", size * scale)


def _rm(size, scale=1.0):  # Rajdhani Medium
    return ui_common.font("Rajdhani-Medium.ttf", size * scale)


def _micro(size=9):
    return ui_common.font("ShareTechMono-Regular.ttf", size)
```

**Primitives**

```python
def _chamfer(x0, y0, x1, y1, c):
    """Panel outline with the top-left and bottom-right corners cut off."""
    return [(x0 + c, y0), (x1, y0), (x1, y1 - c), (x1 - c, y1), (x0, y1), (x0, y0 + c)]


def _glitch(draw, xy, s, f, fill, shift=2, anchor="la", max_w=None):
    """RGB-split text: red copy left, cyan copy right, real text on top."""
    s = ui_common.fit(s, f, max_w) if max_w else ui_common.glyph_safe(s, f)
    x, y = xy
    draw.text((x - shift, y), s, font=f, fill=RED, anchor=anchor)
    draw.text((x + shift, y), s, font=f, fill=CYAN, anchor=anchor)
    draw.text((x, y), s, font=f, fill=fill, anchor=anchor)


def _hazard(img, box, color, step=7):
    """Diagonal warning stripes clipped to `box`."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    tile = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(tile)
    for x in range(-h, w + h, step * 2):
        d.polygon([(x, h), (x + step, h), (x + step + h, 0), (x + h, 0)], fill=color)
    img.paste(tile, (x0, y0))


@functools.lru_cache(maxsize=1)
def _bg():
    """Black, corner brackets on the bezel, microtext, barcode, scanlines."""
    img = Image.new("RGB", (W, W), BG)
    d = ImageDraw.Draw(img)
    for a in (45, 135, 225, 315):  # bezel brackets
        d.arc([10, 10, 230, 230], a - 9, a + 9, fill=YELLOW, width=3)
    ui_common.text(d, (150, 26), "SYS//MP3-2077", _micro(8), DIM)
    ui_common.text(d, (60, 206), "NET:ON  ICE:OK", _micro(8), DIM)
    rng = random.Random(2077)
    x = 96
    while x < 146:
        bw = rng.choice((1, 1, 2, 3))
        d.rectangle([x, 214, x + bw - 1, 221], fill=DIM)
        x += bw + rng.choice((1, 2))
    arr = np.asarray(img).copy()
    arr[::3] = (arr[::3] * 0.7).astype(np.uint8)
    return Image.fromarray(arr)
```

**Layout**

| View | Composition |
|---|---|
| list | `_bg()` copy. Header: red tab rect 6×18 at (`120-half(30)+14`, 22) + `title.upper()` `_rb(18,s)` YELLOW left-aligned after it, max_w to `120+half(30)-10`; microtext `f"// {sel+1:02d} OF {n:02d}"` `_micro(9)` DIM below (y 44). Rows `list_rows(n, sel, 42*s, center_y=128, min_half=56)`: **off 0** → polygon `_chamfer(120-half+10, y-21*s, 120+half-10, y+21*s, 8)` fill YELLOW; index `f"{i+1:02d}"` `_micro(9)` BG at the panel's left; thumb 32×32 (cover through a chamfer mask, with 1 px CYAN frame offset +2,+2 and RED frame offset -2,-2 behind; or `icon(…, 18, BG)`) ; label `_glitch(…, _rb(17,s), BG)` (shift 1) + sub `_rm(12,s)` BG. **off ±1** → `f"{i+1:02d} ▸ "` (glyph-safe) + `label.upper()` `_rb(14,s)` YELLOW with a 1 px YELLOW chamfer outline; **off ±2** → same in DIM, no outline. Scroll: 6 slanted segments at x 210-216 (parallelograms), lit YELLOW at the current fraction. Tone danger → panel RED, text WHITE; muted → label DIM. |
| settings | `_bg()`; header; rows `list_rows(n, sel, 28*s, center_y=128, min_half=62)`: selected → chamfer bar YELLOW (h 24*s) with BG text, else label `_rm(13,s)` YELLOW; value right: toggle → two cells "ON"/"OFF" 22×14 each (active cell filled YELLOW, or RED for off, text BG; other cell outline DIM); stepper → `max` parallelograms 7×12 slanted 3 px, filled YELLOW up to `min(v,max)`, outline DIM; else `str(value)` `_rm(12,s)` CYAN if on else DIM. |
| message | `_bg()`; header; chamfer panel `(30, 72, 210, 182)` outline YELLOW (RED for error) 2 px, fill PANEL; `_hazard(img, (32, 74, 208, 88), RED if error else YELLOW)`; label tag `"// " + {"busy":"CONNECTING","error":"ERROR","success":"COMPLETE","info":"STATUS"}[mood]` `_micro(9)` on a BG rect at (40, 76); `text` `_glitch` `_rb(17,s)` YELLOW (RED if error) at (120, 108) anchor `"mm"` max_w 160; detail `wrap(_rm(12,s), 160, 3)` WHITE from y 124; busy → 8 slanted segments at y 168 (x 52-188), segment `busy_phase(0.5,8)` lit YELLOW; hint `_micro(9)` DIM at y 192 max_w 140; subtitle `_rm(12,s)` CYAN (120, 56). |
| playing | `_bg()`. Cover: `cover_image(ref,116)` through a chamfer polygon mask at (62, 26)-(178, 142); glitch slices: `rng = random.Random(int(position * 3))`; if `rng.random() < 0.12`: 3 strips (h 6-12) of the cover shifted ±(3-8) px horizontally. Frame: chamfer outline YELLOW 2 px; CYAN outline offset (+3,+3) and RED (-3,-3) 1 px behind. State tag on the frame's bottom-left (62, 132)-(122, 146): fill RED, `"▶ PLAYING"`/`"❚❚ PAUSED"` (glyph-safe → use icon play/pause 8 WHITE + text) `_micro(9)` WHITE; shuffle → tag "SHF" CYAN at (150,132)-(178,146). Title `title.upper()` `_rb(19,s)` YELLOW (120, 160) `"mm"` max_w `2*half(168)-16`; artist `_rm(13,s)` CYAN (120, 180) max_w `2*half(186)-20`; progress: 16 parallelograms (w 7, gap 1, slant 3) across x 64-176 at y 194-201, lit YELLOW up to progress else (50,48,20); time `f"{fmt_time(pos)} // {fmt_time(dur)}"` `_micro(9)` DIM (120, 211) `"mm"`. |
| code | `_bg()`; header "NETLINK REQUEST"; `"> " + url` `_rm(12,s)` CYAN (120, 82) max_w 180; chamfer panel (36, 100)-(204, 152) outline YELLOW; code `_glitch` `_rb(28,s)` YELLOW (120, 126) `"mm"`; RED underline 2 px under it; "AWAITING HANDSHAKE" `_micro(9)` DIM (120, 172) + busy segments. |
| progress | `_bg()`; header "DATA TRANSFER"; 20 parallelograms at y 110 (x 40-200), lit YELLOW to the fraction; `f"{current:02d}/{total:02d}"` `_rb(28,s)` YELLOW (120, 142); track `_micro(9)` DIM (120, 166) max_w 150; done → `_glitch("TRANSFER COMPLETE", _rb(14), CYAN)` (120, 186). |
| password | `_bg()`; header "BREACH PROTOCOL"; "BUFFER" `_micro(8)` DIM (44, 48); typed `_rb(15,s)` YELLOW (120, 64) tail-fit 170; code column x 120: 5 chamfer cells 30×24 at y 86, 112, 138(current), 164, 188: current filled YELLOW with BG char `_rb(18,s)`, others outline DIM with YELLOW/DIM chars `_rb(15,s)`; space `"_"`; hint `_micro(8)` DIM at y 212 max_w 90 (`"DREH·KLICK·SHF·PLAY"`). |
| status | `draw_ring_status(img, sv, {"track": (40, 38, 16), "fill": YELLOW, "low": RED, "off": (60, 58, 30), "wifi": CYAN, "bt": YELLOW, "text": DIM, "accent": CYAN, "font": _micro(9), "segments": 12, "dot": "diamond"})` |
| quick_connect | blend 0.7 toward BG; 4 chamfered arc segments r 70 width 6 (each 80°, gap 10°), lit YELLOW (RED if error) up to progress, rest (50,48,20); label `_glitch` `_rb(16,s)` YELLOW at (120, 120) `"mm"` max_w 110. |
| shutdown | `_bg()`; `_hazard(img, (40, 92, 200, 100), YELLOW)`; `_glitch("SYSTEM OFFLINE", _rb(20), YELLOW)` (120, 120) `"mm"`; `_hazard(img, (40, 140, 200, 148), YELLOW)`. |

---

### Task 11: Pixelhaus I - asset, rooms, camera (`themes/pixelhaus.py`)

**Files:**
- Create: `Software/assets/pixelhaus.png` (copy), `Software/themes/pixelhaus.py`
- Modify: `Software/themes/__init__.py`, `Software/ui_state.py`, `Software/test_ui_render.py`

**Interfaces:**
- Consumes: views, `ui_common` toolkit.
- Produces: `pixelhaus.ASSET_PATH`, `pixelhaus.ROOMS`, `pixelhaus.Camera`, module-level `_CAM`, `_clock` (swappable), `_house()` (lru_cache), `animating()`, all ten `draw_*`; `_scene(view) -> (img, arrived)`, `_box(draw, box)`, `_ptext(draw, xy, s, fill, max_w=None, anchor="la")`, `_big(img, xy, s, fill, max_w=None)` for Task 12.

- [ ] **Step 1: Copy the asset**

```bash
mkdir -p assets && cp "../../../../a5404a09-afb5-407a-ad3f-f6cedbedbd2f.png" assets/pixelhaus.png
python -c "from PIL import Image; print(Image.open('assets/pixelhaus.png').size)"
```

Expected: `(1536, 1024)`.

- [ ] **Step 2: Write the failing tests** - append to `Software/test_ui_render.py`:

```python
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
```

Add `("pixelhaus", "Pixelhaus")` to `THEME_CHOICES` **before** `("cyberpunk", "Cyberpunk")`.

- [ ] **Step 3: Run to verify failure** - `python test_ui_render.py` → FAIL (`test_every_design_choice_has_a_theme`, then `ImportError` for `themes.pixelhaus`).

- [ ] **Step 4: Implement the module core**

```python
"""Pixelhaus: every menu is a room in a pixel-art house (2D cross-section, Per's
assets/pixelhaus.png, used 1:1 - one room fills the round screen), and the camera
floats from room to room in a straight line - through walls and ceilings, slight
zoom-out mid-flight - whenever the screen changes. After the flight the frame
stands still (no idle animation); the menu itself is an RPG dialog box.
"""
import functools
import math
import os
import time

from PIL import Image, ImageDraw

import ui_common
import ui_state
from ui_common import W
from ui_views import fmt_time

ASSET_PATH = os.path.join(ui_common.HERE, "assets", "pixelhaus.png")

# Room centers in the asset (measured: floor beams at y≈233/380/544/730, walls per floor).
ROOMS = {
    "schlafzimmer": (352, 303), "saal": (644, 303), "kinderzimmer": (1160, 303),
    "arbeitszimmer": (372, 462), "treppenhalle": (645, 462), "bibliothek": (934, 462),
    "bibliothek_regal": (896, 462), "musikzimmer": (1200, 462),
    "wohnzimmer": (228, 637), "eingangshalle": (644, 637), "kueche": (915, 637), "werkstatt": (1216, 637),
    "kellerlager": (232, 850),
}
SCREEN_ROOM = {
    ui_state.SCREEN_HOME: "wohnzimmer", ui_state.SCREEN_LIBRARY: "bibliothek",
    ui_state.SCREEN_PLAYLIST: "bibliothek_regal", ui_state.SCREEN_PLAYING: "musikzimmer",
    ui_state.SCREEN_SETTINGS_ROOT: "werkstatt",
    ui_state.SCREEN_SYNC_LOGIN: "kinderzimmer", ui_state.SCREEN_SYNC_PROGRESS: "kinderzimmer",
    ui_state.SCREEN_BT_MENU: "arbeitszimmer", ui_state.SCREEN_BT_DEVICE: "arbeitszimmer",
    ui_state.SCREEN_BT_PAIRING: "arbeitszimmer", ui_state.SCREEN_WIFI_MENU: "arbeitszimmer",
    ui_state.SCREEN_WIFI_DEVICE: "arbeitszimmer", ui_state.SCREEN_WIFI_SCAN: "arbeitszimmer",
    ui_state.SCREEN_WIFI_PASSWORD: "arbeitszimmer",
    ui_state.SCREEN_PLAYLIST_MANAGE: "kellerlager", ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL: "kellerlager",
}
CATEGORY_ROOM = {"display": "saal", "led": "treppenhalle", "connectivity": "arbeitszimmer",
                 "sync": "kinderzimmer", "motion": "kueche", "about": "eingangshalle"}
HOME_TARGET = {"library": "bibliothek", "resume": "musikzimmer", "settings": "werkstatt"}
DRIFT_PX = 30

NIGHT = (22, 18, 34)
BOX = (24, 20, 48); BOX_EDGE = (240, 226, 196); BOX_SHADE = (60, 50, 96)
CREAM = (248, 236, 210); DIMC = (150, 140, 172); GOLD = (255, 210, 90); RED = (255, 96, 96); GREEN = (130, 230, 120)

_clock = time.monotonic  # tests and preview_themes swap in a fake clock


class Camera:
    """Floats between rooms in a straight line, smoothstep easing, slight zoom-out
    mid-flight. Pure function of the `now` passed in."""
    MIN_S, MAX_S, BASE_S, SPEED = 0.4, 1.0, 0.35, 1500.0
    ZOOM_DIP, ZOOM_MIN_DIST = 0.2, 120

    def __init__(self):
        self.start = self.target = None
        self.t0 = self.dur = self.dist = 0.0
        self.settled = True

    def aim(self, target, now):
        if self.target is None:  # very first frame: no flight from nowhere
            self.start = self.target = target
            self.dur = self.dist = 0.0
            self.settled = False
            return
        if target == self.target:
            return
        x, y, _, _ = self.frame(now)
        self.start, self.target, self.t0 = (x, y), target, now
        self.dist = math.hypot(target[0] - x, target[1] - y)
        self.dur = min(self.MAX_S, max(self.MIN_S, self.BASE_S + self.dist / self.SPEED))
        self.settled = False

    def frame(self, now):
        """(x, y, zoom, arrived). Arriving collapses the flight, so any later (or,
        with a swapped test clock, earlier) time keeps returning the target."""
        t = 1.0 if self.dur <= 0 else max(0.0, min(1.0, (now - self.t0) / self.dur))
        if t >= 1.0:
            self.start, self.dur, self.dist = self.target, 0.0, 0.0
            return self.target[0], self.target[1], 1.0, True
        e = t * t * (3 - 2 * t)
        x = self.start[0] + (self.target[0] - self.start[0]) * e
        y = self.start[1] + (self.target[1] - self.start[1]) * e
        z = 1.0 - self.ZOOM_DIP * math.sin(math.pi * t) if self.dist >= self.ZOOM_MIN_DIST else 1.0
        return x, y, z, False


_CAM = Camera()


def animating():
    return not _CAM.settled


@functools.lru_cache(maxsize=1)
def _house():
    try:
        return Image.open(ASSET_PATH).convert("RGB")
    except OSError:
        return None  # not deployed - plain background instead, see _scene()


def _room_of(view):
    if getattr(view, "KIND", "") == "settings":
        return CATEGORY_ROOM.get(view.category, "werkstatt")
    return SCREEN_ROOM.get(view.screen, "wohnzimmer")


def _focus_room(view):
    """On Home/Werkstatt the camera leans toward the room the selection leads to."""
    if getattr(view, "KIND", "") != "list" or not 0 <= view.sel < len(view.items):
        return None
    kind = view.items[view.sel].kind
    if view.screen == ui_state.SCREEN_HOME:
        return HOME_TARGET.get(kind)
    if view.screen == ui_state.SCREEN_SETTINGS_ROOT:
        return CATEGORY_ROOM.get(kind)
    return None


def _target(view):
    room = _room_of(view)
    cx, cy = ROOMS[room]
    focus = _focus_room(view)
    if focus and focus != room:
        fx, fy = ROOMS[focus]
        d = math.hypot(fx - cx, fy - cy) or 1.0
        cx, cy = cx + (fx - cx) / d * DRIFT_PX, cy + (fy - cy) / d * DRIFT_PX
    return (round(cx), round(cy))


def _crop(x, y, z=1.0):
    house = _house()
    if house is None:
        return Image.new("RGB", (W, W), NIGHT)
    size = W / z
    img = house.crop((round(x - size / 2), round(y - size / 2), round(x + size / 2), round(y + size / 2)))
    return img if img.size == (W, W) else img.resize((W, W), Image.BILINEAR)


def _scene(view):
    now = _clock()
    _CAM.aim(_target(view), now)
    x, y, z, arrived = _CAM.frame(now)
    if arrived:
        _CAM.settled = True
    return _crop(x, y, z), arrived


# --- pixel UI ---------------------------------------------------------------------------

def _pf():
    return ui_common.font("PixelifySans[wght].ttf", 10)  # 1 font px = 1 screen px: crisp with fontmode "1"


def _ptext(draw, xy, s, fill, max_w=None, anchor="la"):
    draw.fontmode = "1"
    return ui_common.text(draw, xy, s, _pf(), fill, anchor=anchor, max_w=max_w)


@functools.lru_cache(maxsize=256)
def _big_mask(s):
    f = _pf()
    w = max(1, math.ceil(f.getlength(s)))
    m = Image.new("L", (w, 14), 0)
    d = ImageDraw.Draw(m)
    d.fontmode = "1"
    d.text((0, 0), s, font=f, fill=255)
    return m.resize((w * 2, 28), Image.NEAREST)


def _big(img, xy, s, fill, max_w=None):
    """2x pixel text: rendered at 1 px per font pixel, NEAREST-doubled - uniform 2 px pixels."""
    s = ui_common.fit(s, _pf(), max_w / 2) if max_w else ui_common.glyph_safe(s, _pf())
    m = _big_mask(s)
    img.paste(fill, (int(xy[0]), int(xy[1]), int(xy[0]) + m.width, int(xy[1]) + m.height), m)
    return m.width


DIALOG = (34, 134, 206, 204)


def _box(draw, box):
    """RPG window: cream 2 px border, darker inner line, navy fill, stepped corners."""
    x0, y0, x1, y1 = box
    for inset, color in ((0, BOX_EDGE), (2, BOX_SHADE), (4, BOX)):
        c = 4
        a0, b0, a1, b1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
        draw.polygon([(a0 + c, b0), (a1 - c, b0), (a1, b0 + c), (a1, b1 - c), (a1 - c, b1), (a0 + c, b1),
                      (a0, b1 - c), (a0, b0 + c)], fill=color)


def _row_w(y, right=DIALOG[2] - 8, left=DIALOG[0] + 8):
    """Usable text width of a dialog row at y (the round bezel cuts the box corners)."""
    half = ui_common.safe_half_width(y + 6)
    return max(20, min(right, W / 2 + half - 4) - max(left, W / 2 - half + 4))
```

Then the ten views, Task-11 level (text-only dialog box; Task 12 adds the decoration):

| View | Composition (all after `img, arrived = _scene(view)`; if not `arrived` return `img` unchanged) |
|---|---|
| list | `_box(DIALOG)`; prev item label (sel-1) `_ptext` DIMC at (44, 140) max_w `_row_w(140)`; counter `f"{sel+1}/{n}"` `_ptext` DIMC anchor `"ra"` at (198, 140); `▶` (a 5×5 pixel triangle, 2 px cells, GOLD) at (40, 158) + selected label `_big` CREAM at (52, 154) max_w `_row_w(160)-12`; sub `_ptext` GOLD at (52, 176) max_w `_row_w(176)-12`; next label `_ptext` DIMC at (44, 188) max_w `_row_w(188)`. Tone muted → label DIMC; danger → label RED. |
| message | `_box(DIALOG)`; text `_big` (busy CREAM + `"." * (busy_phase(0.5, 3) + 1)` instead of the trailing dots, error RED, success GREEN, info CREAM) at (44, 142); detail `wrap(_pf(), _row_w(168), 2)` CREAM from y 166 step 12; hint `_ptext` DIMC at (44, 190). Subtitle (if any) `_ptext` CREAM centered at (120, 118) on a 2 px BOX strip. |
| settings | `_box(DIALOG)`; rows sel-1, sel, sel+1 at y 140/158/184: selected → ▶ + label `_big` CREAM + value on the same line right-aligned `_ptext` GOLD (toggle "AN"/"AUS", stepper `f"{min(v,max)}/{max}"`, else value) - if label+value don't fit, value moves to y 174; others `_ptext` DIMC `label … value`. Title `_ptext` CREAM centered at (120, 118) on a BOX strip. |
| playing | `_box(DIALOG)`; title `_big` CREAM at (44, 140) max_w `_row_w(146)`; artist `_ptext` GOLD at (44, 162); 2 px-cell progress bar (40 cells of 3 px) at (48, 178)-(168, 184) GOLD/BOX_SHADE; time `f"{fmt_time(pos)}/{fmt_time(dur)}"` `_ptext` DIMC at (48, 188); state glyph (pixel ▶ or ❚❚) at (180, 176). |
| code | `_box((34, 112, 206, 204))`; "Gehe zu" `_ptext` DIMC (44, 118); url `_ptext` CREAM (44, 132) max_w `_row_w(132)`; "Code:" DIMC (44, 150); code `_big` GOLD (44, 162); "Warte…" DIMC (44, 188). |
| progress | `_box(DIALOG)`; `f"{current}/{total}"` `_big` CREAM (44, 140); bar like playing at y 166 (fraction clamped); track `_ptext` DIMC (44, 178) max_w; done → "Fertig!" `_big` GREEN (120, 186) anchor center (compute x from width). |
| password | `_box((34, 112, 206, 204))`; ssid `_ptext` DIMC (44, 118); typed `_ptext` CREAM (44, 132) tail-fit; chars idx-2…idx+2 at y 152: current `_big` GOLD in a 2 px CREAM frame at x 108, neighbors `_ptext` DIMC at x 80/94/134/148; space shown `"_"`; hint `_ptext` DIMC (44, 188) max_w `_row_w(188)`. |
| status | `draw_ring_status(img, sv, {"track": (60, 50, 70), "fill": GOLD, "low": RED, "off": (90, 80, 100), "wifi": CREAM, "bt": (120, 170, 255), "text": CREAM, "accent": GREEN, "font": _pf(), "segments": 10, "dot": "square"})` (Task 12 replaces this with a pixelated ring). |
| quick_connect | `_box((40, 92, 200, 150))`; label `_big` (RED if error else CREAM) at (52, 100) max_w 136; bar 2 px cells at (52, 132)-(188, 140) GOLD to progress. |
| shutdown | `_crop(*ROOMS["schlafzimmer"])` (no flight) + `_box(DIALOG)` + "Gute Nacht…" `_big` CREAM at (52, 150). |

`themes/__init__.py`: add `from themes import pixelhaus` and the `"pixelhaus": pixelhaus,` entry **before** `"cyberpunk"`.

- [ ] **Step 5: Tests** - `python test_ui_render.py && python test_ui_views.py && python test_ui_state.py` → all pass.

- [ ] **Step 6: Preview + tune the room targets** - `python preview_themes.py pixelhaus`; for every tile check the room is the one from the table and its key object (fireplace, shelves, piano, tool wall, …) sits above the dialog box; adjust that room's `ROOMS` y by up to ±30 px where it doesn't. `python preview_themes.py --bench pixelhaus klassik` within budget.

- [ ] **Step 7: Commit** - `git add assets/pixelhaus.png themes/pixelhaus.py themes/__init__.py ui_state.py test_ui_render.py && git commit -m "Add Pixelhaus design: rooms in a pixel-art house with a floating camera"`

### Task 12: Pixelhaus II - room decoration

**Files:** Modify `Software/themes/pixelhaus.py`.

**Interfaces:** Consumes Task 11's `_scene`, `_box`, `_ptext`, `_big`, `DIALOG`, `ROOMS`, `_focus_room`, `_room_of`.

- [ ] **Step 1: Pixel sprites** - add a sprite table drawn in 2 px cells:

```python
SPRITES = {
    "play":    ["X....", "XXX..", "XXXXX", "XXX..", "X...."],
    "pause":   ["XX.XX", "XX.XX", "XX.XX", "XX.XX", "XX.XX"],
    "note":    ["...XX", "...X.", "...X.", "...X.", ".XXX.", "XXXX.", ".XX.."],
    "shuffle": ["X...X", ".X.X.", "..X..", ".X.X.", "X...X"],
    "arrow":   ["..X..", ".XXX.", "XXXXX", "..X..", "..X.."],  # points up; rotate via _sprite(..., rot)
}


def _sprite(img, name, x, y, color, cell=2, rot=0):
    rows = SPRITES[name]
    for _ in range(rot // 90):  # rotate the bitmap clockwise
        rows = ["".join(r[i] for r in reversed(rows)) for i in range(len(rows[0]))]
    d = ImageDraw.Draw(img)
    for j, row in enumerate(rows):
        for i, c in enumerate(row):
            if c == "X":
                d.rectangle([x + i * cell, y + j * cell, x + i * cell + cell - 1, y + j * cell + cell - 1], fill=color)
```

Use `"play"` for every ▶ cursor/state, `"pause"` for ❚❚, `"shuffle"` next to the time on Now Playing when shuffle is on.

- [ ] **Step 2: Room sign** - `_sign(img, text)`: wooden plaque centered at y 30-46: width `_ptext` width + 16 (max 100), fill (122, 74, 40), 2 px border (70, 40, 22), two 2×2 GOLD "nails", two 1 px strings from the plaque corners up to y 22; text `_ptext` CREAM centered. Shown on every arrived frame with the view's title (`view.title`, settings: category title; playing: "Musikzimmer").

- [ ] **Step 3: Framed pixel covers** - `@lru_cache(maxsize=32) _pixel_cover(ref, cells=16, px=3)`: `cover_image(ref, cells).resize((cells*px,)*2, NEAREST)`; `_frame(img, cover, cx, cy)`: 2 px dark-wood border (70, 40, 22) + 2 px GOLD inner border around it. Draw it centered at (120, 84) for list items with a cover (selected item) and Home's resume tile; at (120, 74) with `px=4` on Now Playing.

- [ ] **Step 4: Music room notes** - on Now Playing, 3 `"note"` sprites rising from the piano at screen (70, 140): note k at `phase = (position * 0.4 + k / 3) % 1`, position `(70 + 18 * k + 6 * sin(phase * 6.28), 140 - 70 * phase)`, color GOLD, skipped when the paused flag is set (`not view.playing`).

- [ ] **Step 5: Direction arrow** - on Home and Werkstatt, when `_focus_room(view)` differs from the current room: `"arrow"` sprite (cell 3) at radius 92 from (120,120) in the direction of `ROOMS[focus] - ROOMS[current]`, rotated to the nearest of 0/90/180/270, color GOLD.

- [ ] **Step 6a: Pixel settings widgets** - in `draw_settings`, values become pixel widgets drawn in 2 px cells: toggle = 7×3-cell switch (CREAM frame, GOLD knob block right when on, DIMC knob left when off); stepper = `max` blocks of 2×3 cells, GOLD up to `min(value, max)`, BOX_SHADE otherwise; choice/info/action stay text.

- [ ] **Step 6: Pixel status ring** - replace `draw_status`: track and fill as 4×4 px squares every 4° along r 117 between `RING_FAR_DEG` and `RING_ANCHOR_DEG` (positions snapped to a 2 px grid), track (60,50,70), fill GOLD (RED ≤ 20 %); WLAN/BT as 8×8 squares with 2 px CREAM border (filled when connected, empty when on, (90,80,100) when off); labels `_ptext` CREAM at the shared label spot when `sv.show_labels`.

- [ ] **Step 7: Tests + preview** - `python test_ui_render.py && python preview_themes.py pixelhaus`; check sign/covers/notes/arrow don't collide with the dialog box or bezel; bench within budget.

- [ ] **Step 8: Commit** - `git add themes/pixelhaus.py && git commit -m "Pixelhaus: room signs, pixel covers, music notes, direction arrow, pixel status ring"`

---

### Task 13: Final verification + docs

**Files:** Modify `README.md`, `CLAUDE.md` (section 7 UI bullet).

- [ ] **Step 1: Full test run** - `python test_ui_views.py && python test_ui_state.py && python test_ui_render.py && python test_buttonbox.py && python test_connectivity.py && python test_player.py && python test_power_button.py && python test_rt9466.py && python test_sync_youtube.py && python test_charge_control.py` → all pass.
- [ ] **Step 2: Bench all designs** - `python preview_themes.py --bench` → record the table; every design's slowest ≤ Klassik's Now Playing.
- [ ] **Step 3: Regenerate all previews** - `python preview_themes.py` → 8 PNGs in `previews/`; show them to Per.
- [ ] **Step 4: Docs** - README `Software/` table: add rows `ui_views.py` (screen content as data), `ui_common.py` (shared drawing helpers), `themes/` (8 switchable designs, Einstellungen → Anzeige → Design), `preview_themes.py` (preview sheets / `--bench`), `fonts/`, `assets/`. CLAUDE.md section 7: one bullet "Design-Themes (12.10.2026): 8 Designs umschaltbar … Spec/Plan-Pfade … lokal getestet, auf dem Pi noch nicht verifiziert - Live-Test: alle Designs durchschalten, `python3 preview_themes.py --bench` auf dem Pi laufen lassen".
- [ ] **Step 5: Commit** - `git add README.md CLAUDE.md && git commit -m "Document switchable designs"`
- [ ] **Step 6: Ask Per** whether to deploy to the Pi (copy `Software/` incl. `fonts/`, `assets/`, `themes/` and restart `mp3player.service`) - only with his go-ahead.
