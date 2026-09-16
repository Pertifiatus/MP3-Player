# Status-Ring (Akku + WLAN/Bluetooth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show battery %, WLAN status and Bluetooth status as a ring hugging the round front-display's outer bezel margin, controllable via a new Settings toggle (Home-only vs. every screen).

**Architecture:** A pure-rendering function (`ui_render._draw_status_ring`) draws the ring onto whatever image `ui_render.render()` already produced, using three new plain fields on `UIState` (`battery_pct`, `wifi_connected`, `bt_connected`) that `main.py` refreshes on a slow poll cycle (30s battery, 10s WLAN/BT), mirroring the existing throttled-poll pattern already used for motion/BT/WiFi redraws in `main.py`.

**Tech Stack:** Python 3, PIL/Pillow (`ImageDraw.arc`/`ellipse`), existing `max17048.MAX17048` + `connectivity.py` drivers.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-16-status-ring-design.md` - all pixel constants below (radius, angles, colors) are copied verbatim from there.
- The ring does **not** scale with `ui_scale` (fixed hardware-margin element, same reasoning as `ui_render.SAFE_R`).
- No new pip dependencies - only stdlib `math` (already imported in `ui_render.py`) and the existing `max17048`/`connectivity` modules.
- Every new pure-logic/rendering piece gets a test runnable with `python3 test_*.py` on a normal dev machine (no hardware) - matches this project's existing convention (see `test_ui_state.py`, `test_ui_render.py`). `main.py`'s hardware-loop wiring itself has no existing tests anywhere in this codebase (confirmed: no `test_main.py`) - that task ends in a manual on-device verification instead, consistent with how every other `main.py` change in this project's history (see `Software/NOTES_FOR_PER.md`) was verified.

---

### Task 1: "Statusanzeige" setting + visibility rule

**Files:**
- Modify: `Software/settings.py:7-12` (add default)
- Modify: `Software/ui_state.py` (add `SETTINGS_ITEMS["display"]` entry + `UIState.status_ring_visible()`)
- Test: `Software/test_ui_state.py`

**Interfaces:**
- Consumes: `Settings.get`/`Settings.set` (existing, unchanged), `UIState.screen`, `ui_state.SCREEN_HOME` (existing).
- Produces: `UIState.status_ring_visible(self) -> bool` - used by Task 2's `ui_render.render()` and Task 3's `main.py` dirty-flag logic.

- [ ] **Step 1: Write the failing test**

Add to `Software/test_ui_state.py` (near `test_choice_cycles`, same style):

```python
def test_status_ring_visible_depends_on_setting_and_screen():
    s = make_state()
    s.settings.set("display", "status_ring", "home")
    s.screen = ui_state.SCREEN_HOME
    assert s.status_ring_visible()
    s.screen = ui_state.SCREEN_LIBRARY
    assert not s.status_ring_visible()

    s.settings.set("display", "status_ring", "always")
    assert s.status_ring_visible()
    s.screen = ui_state.SCREEN_HOME
    assert s.status_ring_visible()


def test_status_ring_setting_cycles_via_settings_detail():
    s = make_state()
    s.settings.set("display", "status_ring", "home")
    s.settings_category = "display"
    idx = next(i for i, it in enumerate(ui_state.SETTINGS_ITEMS["display"]) if it["key"] == "status_ring")
    s.settings_detail_sel = idx
    s.settings_detail_activate()
    assert s.settings.get("display", "status_ring") == "always"
    s.settings_detail_activate()
    assert s.settings.get("display", "status_ring") == "home"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Software && python3 test_ui_state.py`
Expected: `AttributeError: 'UIState' object has no attribute 'status_ring_visible'` (or `KeyError: 'status_ring'` if it gets that far first)

- [ ] **Step 3: Add the setting default**

In `Software/settings.py`, inside `DEFAULTS["display"]` (currently lines 8-12):

```python
    "display": {
        "brightness": 3,     # 1-5, drives GC9A01 backlight PWM (GPIO13)
        "auto_sleep_s": 30,  # 0 = never sleep
        "ui_scale": 3,       # 1-5, index into ui_render.UI_SCALE_STEPS
        "status_ring": "home",  # "home" or "always" - see ui_render._draw_status_ring
    },
```

- [ ] **Step 4: Add the declarative settings-menu entry and the visibility method**

In `Software/ui_state.py`, inside `SETTINGS_ITEMS["display"]` (the list that currently ends with the `auto_sleep_s` choice entry), append:

```python
        {"key": "status_ring", "label": "Statusanzeige", "type": "choice",
         "choices": [("home", "Nur Home"), ("always", "Ueberall")]},
```

Add a method on `UIState` (near the other small helpers, e.g. right after `toggle_encoder_mode`'s class or anywhere inside `class UIState:` - place it right after `__init__`):

```python
    def status_ring_visible(self):
        return self.settings.get("display", "status_ring") == "always" or self.screen == SCREEN_HOME
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd Software && python3 test_ui_state.py`
Expected: `... 23 tests passed` (one more than the previous count - all `OK`, no failures)

- [ ] **Step 6: Commit**

```bash
git add Software/settings.py Software/ui_state.py Software/test_ui_state.py
git commit -m "Add Statusanzeige (status-ring visibility) setting"
```

---

### Task 2: `_draw_status_ring` rendering + dispatcher integration

**Files:**
- Modify: `Software/ui_state.py` (three new `UIState.__init__` fields)
- Modify: `Software/ui_render.py` (new constants, `_ring_point`, `_draw_status_dot`, `_draw_status_ring`, `render()` change)
- Test: `Software/test_ui_render.py`

**Interfaces:**
- Consumes: `UIState.status_ring_visible()` (Task 1), `UIState.settings.get("connectivity", "wifi"/"bluetooth")` (existing), `ui_render.ACCENT`/`TEXT`/`DIM`/`CATEGORY_COLORS` (existing), `ui_render._text_centered`/`_font` (existing).
- Produces: `UIState.battery_pct` (float 0-100 or `None`), `UIState.wifi_connected` / `UIState.bt_connected` (bool) - Task 3 sets these from real hardware polls. `ui_render._draw_status_ring(draw, state)` - not called directly by Task 3, only indirectly via `ui_render.render()`.

- [ ] **Step 1: Write the failing test**

Add to `Software/test_ui_render.py` (new top-level test function, same file, same style as `test_all_screens_render_at_every_scale`):

```python
def test_status_ring_renders_without_crashing():
    for battery_pct in (None, 0, 1, 50, 100, 104):  # 104: gauge over-reads slightly past 100, see max17048.py
        for wifi_on, wifi_connected in ((False, False), (True, False), (True, True)):
            for bt_on, bt_connected in ((False, False), (True, False), (True, True)):
                s = make_state()
                s.battery_pct = battery_pct
                s.wifi_connected = wifi_connected
                s.bt_connected = bt_connected
                s.settings.set("connectivity", "wifi", wifi_on)
                s.settings.set("connectivity", "bluetooth", bt_on)

                s.settings.set("display", "status_ring", "home")
                _assert_frame(ui_render.render(s))  # SCREEN_HOME - ring drawn

                s.screen = ui_state.SCREEN_LIBRARY
                _assert_frame(ui_render.render(s))  # "home" mode, not home - ring skipped

                s.settings.set("display", "status_ring", "always")
                _assert_frame(ui_render.render(s))  # "always" mode - ring drawn on library too
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Software && python3 test_ui_render.py`
Expected: `AttributeError: 'UIState' object has no attribute 'battery_pct'` (test file sets it before first render, so this fires immediately)

- [ ] **Step 3: Add the three state fields**

In `Software/ui_state.py`, inside `UIState.__init__`, right after the existing `self.imu = None` line:

```python
        self.battery_pct = None  # 0-100 or None (gauge unavailable/not yet read); set by main.py from MAX17048
        self.wifi_connected = False  # set by main.py from connectivity.wifi_known_connections()
        self.bt_connected = False  # set by main.py from connectivity.bluetooth_known_devices()
```

- [ ] **Step 4: Run test to verify it now fails later (rendering not implemented yet)**

Run: `cd Software && python3 test_ui_render.py`
Expected: passes through field access now, but `render()` itself doesn't yet call any ring code, so this actually **passes already at this point** (nothing crashes - `render()` doesn't touch the new fields yet). That's expected: this step only proves the state fields exist. The ring behavior (mode="home" hides on Library) isn't asserted by pixel content in this test, only crash-freedom, so it can't fail here - proceed to Step 5 regardless.

- [ ] **Step 5: Implement `_draw_status_ring` and wire it into `render()`**

In `Software/ui_render.py`, add these module-level constants right after the existing `SAFE_R = 104` block (after `CARD_MAX_Y`'s definition, before `_header`):

```python
# --- status ring (battery + WLAN/BT) -----------------------------------------
# Fixed hardware-margin element, like SAFE_R - does NOT scale with ui_scale.
# Sits between SAFE_R (104) and the physical bezel (r=120): outer edge at
# RING_R + RING_WIDTH/2 = 116, ~4px from the true edge; inner edge at
# RING_R - RING_WIDTH/2 = 104, flush with SAFE_R. See
# docs/superpowers/specs/2026-09-16-status-ring-design.md for the layout this
# was tuned against.
RING_R = 110
RING_WIDTH = 12
RING_START_DEG = -55
RING_END_DEG = 30
WIFI_DOT_DEG = 38
BT_DOT_DEG = 46
DOT_R = 6
RING_TRACK = (58, 58, 60)
RING_OFF = (72, 72, 76)  # matches _draw_toggle_pill's "off" fill


def _ring_point(deg, r=RING_R):
    rad = math.radians(deg)
    return (W / 2 + r * math.cos(rad), W / 2 + r * math.sin(rad))


def _draw_status_dot(draw, deg, color, on, connected):
    x, y = _ring_point(deg)
    box = [x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R]
    if connected:
        draw.ellipse(box, fill=color)
    elif on:
        draw.ellipse(box, outline=color, width=2)
    else:
        draw.ellipse(box, fill=RING_OFF)


def _draw_status_ring(draw, state):
    bbox = [W / 2 - RING_R, W / 2 - RING_R, W / 2 + RING_R, W / 2 + RING_R]

    # track (empty slot), rounded ends - PIL's arc() has flat ends, so the caps
    # are faked with small filled circles at both endpoints (a stroke-linecap
    # of "round" is exactly a semicircle of radius=width/2 at the endpoint;
    # a full circle there looks identical since the arc itself covers the rest)
    draw.arc(bbox, RING_START_DEG, RING_END_DEG, fill=RING_TRACK, width=RING_WIDTH)
    for deg in (RING_START_DEG, RING_END_DEG):
        x, y = _ring_point(deg)
        draw.ellipse([x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R], fill=RING_TRACK)

    if state.battery_pct is not None:
        pct = max(0, min(100, round(state.battery_pct)))
        if pct > 0:
            fill_end = RING_START_DEG + (RING_END_DEG - RING_START_DEG) * pct / 100
            draw.arc(bbox, RING_START_DEG, fill_end, fill=ACCENT, width=RING_WIDTH)
            for deg in (RING_START_DEG, fill_end):
                x, y = _ring_point(deg)
                draw.ellipse([x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R], fill=ACCENT)
        # anchored inward (r=85, well inside SAFE_R) so it can never land outside
        # the physical bezel regardless of font metrics - exact position vs. the
        # Home header may still need live tuning, see the spec's known-follow-up note
        text_x, text_y = _ring_point(RING_START_DEG, r=85)
        _text_centered(draw, text_x, text_y, f"{pct}%", _font("ring_pct", 1.0), DIM)

    _draw_status_dot(draw, WIFI_DOT_DEG, TEXT, state.settings.get("connectivity", "wifi"), state.wifi_connected)
    _draw_status_dot(draw, BT_DOT_DEG, CATEGORY_COLORS["connectivity"],
                      state.settings.get("connectivity", "bluetooth"), state.bt_connected)
```

Add the new font to `FONT_FILES` (the dict defined around line 52-66), inserting after `"header"`:

```python
    "ring_pct": (FONT_DIR + "DejaVuSans-Bold.ttf", 11),
```

Finally, change `render()` at the bottom of the file from:

```python
def render(state: ui_state.UIState) -> Image.Image:
    return _RENDERERS[state.screen](state)
```

to:

```python
def render(state: ui_state.UIState) -> Image.Image:
    img = _RENDERERS[state.screen](state)
    if state.status_ring_visible():
        _draw_status_ring(ImageDraw.Draw(img), state)
    return img
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd Software && python3 test_ui_render.py`
Expected: `... N tests passed` (all `OK`, no failures/exceptions)

- [ ] **Step 7: Commit**

```bash
git add Software/ui_state.py Software/ui_render.py Software/test_ui_render.py
git commit -m "Render battery/WLAN/Bluetooth status ring on the front display"
```

---

### Task 3: `main.py` wiring - real battery/connectivity polling

**Files:**
- Modify: `Software/main.py`

**Interfaces:**
- Consumes: `max17048.MAX17048().read_soc_pct()` (existing, unchanged), `connectivity.wifi_known_connections()` / `connectivity.bluetooth_known_devices()` (existing, unchanged), `UIState.status_ring_visible()` (Task 1), `UIState.battery_pct`/`wifi_connected`/`bt_connected` (Task 2).
- Produces: nothing consumed by a later task - this is the final integration point.

No unit test exists for `main.py`'s hardware loop anywhere in this codebase (it drives real GPIO/I2C/SPI) - verification is manual, on the actual Pi, same as every other `main.py` change documented in `Software/NOTES_FOR_PER.md`.

- [ ] **Step 1: Add the import and poll-interval constants**

In `Software/main.py`, add to the imports (near the other `from X import Y` lines, after `from qmi8658 import ...`):

```python
from max17048 import MAX17048
```

Add two constants next to the existing `*_INTERVAL` constants near the top of the file (after `SYNC_REDRAW_INTERVAL`):

```python
BATTERY_POLL_INTERVAL = 30  # SOC changes slowly - no reason to hit I2C more often
STATUS_POLL_INTERVAL = 10  # WLAN/BT "connected" check - cheap nmcli/bluetoothctl queries, no scan involved
```

- [ ] **Step 2: Construct the gauge alongside the IMU**

In `main()`, right after the existing IMU try/except block:

```python
    try:
        state.imu = QMI8658()
    except Exception as e:
        print(f"QMI8658A nicht verfuegbar, Bewegungs-Features deaktiviert: {e}")
        state.imu = None
```

add:

```python
    try:
        battery_gauge = MAX17048()
    except Exception as e:
        print(f"MAX17048 nicht verfuegbar, Akkustand-Anzeige deaktiviert: {e}")
        battery_gauge = None
```

- [ ] **Step 3: Initialize the poll clocks**

Next to the existing `last_*` initializations (`last_playing_redraw`, `last_motion_poll`, etc.), add:

```python
    last_battery_poll = time.monotonic()
    last_status_poll = time.monotonic()
```

- [ ] **Step 4: Poll and mark dirty on change**

In the main `while True:` loop, right after the existing motion-poll block:

```python
        if state.imu is not None and now - last_motion_poll >= MOTION_POLL_INTERVAL:
            last_motion_poll = now
            if apply_motion_features(state):
                dirty = True
```

add:

```python
        if battery_gauge is not None and now - last_battery_poll >= BATTERY_POLL_INTERVAL:
            last_battery_poll = now
            try:
                new_pct = round(battery_gauge.read_soc_pct())
            except OSError:
                new_pct = state.battery_pct  # transient I2C hiccup - keep the last known value
            if new_pct != state.battery_pct:
                state.battery_pct = new_pct
                if state.status_ring_visible():
                    dirty = True

        if now - last_status_poll >= STATUS_POLL_INTERVAL:
            last_status_poll = now
            new_wifi_connected = any(n["connected"] for n in connectivity.wifi_known_connections())
            new_bt_connected = any(d["connected"] for d in connectivity.bluetooth_known_devices())
            if new_wifi_connected != state.wifi_connected or new_bt_connected != state.bt_connected:
                state.wifi_connected = new_wifi_connected
                state.bt_connected = new_bt_connected
                if state.status_ring_visible():
                    dirty = True
```

- [ ] **Step 5: Syntax-check locally (no hardware needed for this much)**

Run: `cd Software && python3 -c "import py_compile; py_compile.compile('main.py', doraise=True); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add Software/main.py
git commit -m "Poll MAX17048 + WLAN/BT connection state for the status ring"
```

- [ ] **Step 7: Deploy to the Pi and verify live**

```bash
KEY=~/.ssh/id_ed25519_mp3player
HOST=pkenner@192.168.188.108
scp -i "$KEY" Software/settings.py Software/ui_state.py Software/ui_render.py Software/main.py "$HOST:/tmp/"
ssh -i "$KEY" "$HOST" "cp /tmp/{settings,ui_state,ui_render,main}.py ~/mp3player/ && rm /tmp/{settings,ui_state,ui_render,main}.py"
ssh -i "$KEY" "$HOST" "sudo systemctl restart mp3player.service"
```

Then, looking at the actual front display:
- Home screen shows the ring: gray-to-teal battery slot on the right edge with a `NN%` label near the top, a white WLAN dot, a blue-ish Bluetooth dot.
- Toggle "Statusanzeige" in Settings → Anzeige between "Nur Home" and "Ueberall"; confirm the ring disappears/appears on Library/Now-Playing accordingly.
- Toggle WLAN/Bluetooth off in Settings → Verbindung; confirm the corresponding dot goes from filled to dimmed within ~10s.
- Check whether the `NN%` label collides with the "MINI-MUSIKPLAYER" home header (the known open point from the spec) - if it does, nudge `text_x, text_y = _ring_point(RING_START_DEG, r=85)` in `ui_render._draw_status_ring` (e.g. a smaller `r` moves it further from the edge) and re-deploy.

If the label/header collide or spacing looks off on the real DejaVu fonts, fix the constants directly in `Software/ui_render.py`, redeploy, and commit the fix as its own follow-up commit (`git commit -m "Tune status-ring percentage label position after live check"`) - matches how every other pixel-tuning pass in this project's history was done (see `Software/NOTES_FOR_PER.md`).

---

## Self-Review Notes

- **Spec coverage:** Settings toggle (Task 1), ring visuals/3-state dots/percentage text (Task 2), MAX17048 + connectivity polling with the documented intervals (Task 3), known header-collision follow-up carried into Task 3's manual-verify step. All spec sections covered.
- **Placeholders:** none - every step has complete, runnable code.
- **Type/name consistency checked:** `status_ring_visible()` (Task 1) is the exact name used by both `ui_render.render()` (Task 2) and `main.py` (Task 3). `battery_pct`/`wifi_connected`/`bt_connected` (Task 2 field names) are the exact names Task 3 assigns to. `RING_START_DEG`/`RING_END_DEG`/`RING_R`/`DOT_R` are defined once in Task 2 and not redefined elsewhere.
