"""Bento Grid: an Apple-keynote style mosaic - dark rounded tiles of different
sizes, a few loud hero tiles (lime / orange / blue / pink), big numbers. The
square grid is cut by the round glass, so the outer tiles get curved outer
edges (a "round bento"). Every screen is a fixed tile composition - the
selected entry is the big hero tile with its neighbors as small tiles around
it; Home and Now Playing are info mosaics. Fixed layout: ignores UI-Groesse.
Space Grotesk.
"""
import dataclasses
import functools
import math

from PIL import Image, ImageDraw

import ui_common
import ui_state
from ui_common import W
from ui_views import fmt_time

BG = (8, 8, 9)
TILE = (28, 28, 30)
TILE2 = (44, 44, 46)
TEXT = (245, 245, 247)
DIM = (142, 142, 147)
LIME = (198, 244, 50)
ORANGE = (255, 159, 10)
BLUE = (10, 132, 255)
PINK = (255, 55, 95)
PURPLE = (191, 90, 242)
CAT_COLORS = {"display": ORANGE, "led": LIME, "connectivity": BLUE, "sync": PURPLE, "motion": PINK, "about": TILE2}
CLIP_R = 112  # round bento: everything outside goes back to BG (status ring sits at r >= 114)
RAD = 16

ROW_A, ROW_B, ROW_C = (14, 82), (88, 152), (158, 226)
TOP = (14, 14, 226, 82)
HERO = (14, 88, 226, 152)


def _g(size, weight=700):
    return ui_common.font("SpaceGrotesk[wght].ttf", size, weight=weight)


def _half(y):
    return ui_common.safe_half_width(y)


# --- primitives -------------------------------------------------------------------

def _tile(draw, box, fill=TILE, sel=False):
    draw.rounded_rectangle(box, RAD, fill=TILE2 if (sel and fill == TILE) else fill)
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


def _base():
    img = Image.new("RGB", (W, W), BG)
    return img, ImageDraw.Draw(img)


def _put(draw, box, xy, s, f, fill, anchor="mm"):
    """Text clamped to its tile AND to the round safe area at its own y (the
    circle cuts the outer tiles). anchor: "mm" centered on x, "lm" starting at x."""
    x, y = xy
    half = _half(y)
    lo, hi = max(box[0] + 8, W / 2 - half + 4), min(box[2] - 8, W / 2 + half - 4)
    if anchor[0] == "m":
        x = min(max(x, lo), hi)
        max_w = 2 * min(x - lo, hi - x)
    else:
        x = max(x, lo)
        max_w = hi - x
    if max_w > 8:
        ui_common.text(draw, (x, y), s, f, fill, anchor=anchor, max_w=max_w)


def _spinner(draw, cx, cy, color):
    active = ui_common.busy_phase(0.5, 3)
    for k in range(3):
        x = cx + (k - 1) * 10
        draw.ellipse([x - 3, cy - 3, x + 3, cy + 3], fill=color if k == active else TILE2)


def _cover(img, ref, box, size):
    x0, y0 = int(box[0]), int(box[1])
    img.paste(ui_common.cover_image(ref, size), (x0, y0), ui_common.rounded_mask(size, size, 10))


def _row_value(row):
    if row.kind == "toggle":
        return "AN" if row.value else "AUS"
    if row.kind == "stepper":
        return f"{max(0, min(row.value, row.max))}/{row.max}"
    return str(row.value)


# --- views ------------------------------------------------------------------------

def _home(img, draw, view, status):
    sel_kind = view.items[max(0, min(view.sel, len(view.items) - 1))].kind
    items = {it.kind: it for it in view.items}
    lib = items.get("library")
    _tile(draw, TOP, sel=sel_kind == "library")
    ui_common.icon(draw, "note", 70, 60, 22, LIME)
    if lib:
        _put(draw, TOP, (90, 52), lib.label, _g(16), TEXT, "lm")
        _put(draw, TOP, (90, 70), lib.sub, _g(10, 500), DIM, "lm")

    resume = items.get("resume")
    box = (14, 88, 152, 152)
    _tile(draw, box, sel=sel_kind == "resume")
    if resume:
        _cover(img, resume.cover, (26, 96), 48)
        _put(draw, box, (82, 110), resume.label, _g(12), TEXT, "lm")
        _put(draw, box, (82, 128), "Fortsetzen", _g(10, 500), LIME, "lm")
    else:
        _put(draw, box, (83, 112), "Mini-", _g(13), DIM)
        _put(draw, box, (83, 130), "Musikplayer", _g(13), DIM)

    box = (158, 88, 226, 152)
    _tile(draw, box)
    pct = status.battery_pct
    _put(draw, box, (190, 112), "--" if pct is None else f"{round(pct)}%", _g(20), DIM if pct is None else LIME)
    _put(draw, box, (190, 136), "Lädt" if status.charging else "Akku", _g(10, 500), DIM)

    settings = items.get("settings")
    box = (14, 158, 140, 226)
    _tile(draw, box, sel=sel_kind == "settings")
    if settings:
        _put(draw, box, (84, 176), settings.label, _g(12), TEXT)
        _put(draw, box, (84, 194), "WLAN · BT · mehr", _g(9, 500), DIM)

    box = (146, 158, 226, 226)
    _tile(draw, box)
    for y, label, on, connected, color in ((176, "WLAN", status.wifi_on, status.wifi_connected, TEXT),
                                           (194, "BT", status.bt_on, status.bt_connected, BLUE)):
        _put(draw, box, (156, y), label, _g(10, 500), DIM, "lm")
        cx = min(198, W / 2 + _half(y) - 10)
        dot = [cx - 4, y - 4, cx + 4, y + 4]
        if not on:
            draw.ellipse(dot, fill=TILE2)
        elif connected:
            draw.ellipse(dot, fill=color)
        else:
            draw.ellipse(dot, outline=color, width=2)


def _settings_root(img, draw, view):
    cells = [(c, r) for r in (ROW_A, ROW_B, ROW_C) for c in ((14, 117), (123, 226))]
    sel = max(0, min(view.sel, len(view.items) - 1))
    for k, item in enumerate(view.items[:6]):
        (x0, x1), (y0, y1) = cells[k]
        box = (x0, y0, x1, y1)
        color = CAT_COLORS.get(item.kind, TILE2)
        selected = k == sel
        _tile(draw, box, fill=color if selected else TILE, sel=selected)
        ink = BG if selected and color not in (TILE2,) else TEXT
        icon_y, label_y = (48, 68) if y0 == ROW_A[0] else ((108, 132) if y0 == ROW_B[0] else (172, 190))
        cx = (x0 + x1) / 2 + (12 if x0 < 120 else -12) * (y0 != ROW_B[0])
        ui_common.icon(draw, ui_common.icon_for(item, view.screen), cx, icon_y, 20, ink if selected else color)
        _put(draw, box, (cx, label_y), item.label, _g(11), ink, "mm")


def _hero_list(img, draw, view):
    n = len(view.items)
    sel = max(0, min(view.sel, n - 1))
    item = view.items[sel]
    _tile(draw, TOP)
    if sel == 0:
        _put(draw, TOP, (120, 58), view.title, _g(14), TEXT)
    else:
        _put(draw, TOP, (120, 58), view.items[sel - 1].label, _g(12, 500), DIM)
    hero_fill = PINK if item.tone == "danger" else TILE
    _tile(draw, HERO, fill=hero_fill, sel=True)
    ink = BG if item.tone == "danger" else TEXT
    if item.cover is not None:
        _cover(img, item.cover, (26, 96), 48)
    else:
        draw.rounded_rectangle([26, 96, 74, 144], 10, fill=TILE2 if item.tone != "danger" else (200, 30, 70))
        ui_common.icon(draw, ui_common.icon_for(item, view.screen), 50, 120, 22,
                       DIM if item.tone == "muted" else (TEXT if item.tone == "danger" else LIME))
    if item.sub:
        _put(draw, HERO, (84, 110), item.label, _g(15), ink, "lm")
        _put(draw, HERO, (84, 130), item.sub, _g(11, 500), ink if item.tone == "danger" else DIM, "lm")
    else:
        _put(draw, HERO, (84, 120), item.label, _g(15), ink, "lm")
    box = (14, 158, 152, 226)
    _tile(draw, box)
    if sel + 1 < n:
        _put(draw, box, (90, 180), view.items[sel + 1].label, _g(12, 500), DIM)
    box = (158, 158, 226, 226)
    _tile(draw, box, fill=LIME)
    _put(draw, box, (180, 178), str(sel + 1), _g(22), BG)
    _put(draw, box, (176, 198), f"/{n}", _g(11, 500), BG)


def draw_list(view, ctx):
    img, draw = _base()
    if view.screen == ui_state.SCREEN_HOME:
        _home(img, draw, view, ctx.status)
    elif view.screen == ui_state.SCREEN_SETTINGS_ROOT:
        _settings_root(img, draw, view)
    else:
        _hero_list(img, draw, view)
    return _finish(img)


def draw_settings(view, ctx):
    img, draw = _base()
    n = len(view.rows)
    sel = max(0, min(view.sel, n - 1))
    row = view.rows[sel]
    _tile(draw, TOP)
    if sel == 0:
        _put(draw, TOP, (120, 58), view.title, _g(14), TEXT)
    else:
        prev = view.rows[sel - 1]
        _put(draw, TOP, (120, 52), prev.label, _g(11, 500), DIM)
        _put(draw, TOP, (120, 70), _row_value(prev), _g(10, 500), DIM)
    _tile(draw, HERO, sel=True)
    _put(draw, HERO, (26, 102), row.label, _g(12, 500), DIM, "lm")
    if row.kind == "toggle":
        _put(draw, HERO, (26, 130), "AN" if row.value else "AUS", _g(26), LIME if row.value else DIM, "lm")
        pill = [168, 119, 208, 141]
        draw.rounded_rectangle(pill, 11, fill=LIME if row.value else TILE2)
        kx = 188 if row.value else 170
        draw.ellipse([kx, 121, kx + 18, 139], fill=BG if row.value else DIM)
    elif row.kind == "stepper":
        v = max(0, min(row.value, row.max))
        _put(draw, HERO, (26, 128), str(v), _g(30), LIME, "lm")
        for k in range(row.max):
            h = 6 + 14 * (k + 1) / row.max
            x = 140 + k * 12
            draw.rounded_rectangle([x, 140 - h, x + 7, 140], 2, fill=LIME if k < v else TILE2)
    else:
        _put(draw, HERO, (26, 130), str(row.value), _g(18), LIME if row.on else TEXT, "lm")
    box = (14, 158, 152, 226)
    _tile(draw, box)
    if sel + 1 < n:
        nxt = view.rows[sel + 1]
        _put(draw, box, (90, 176), nxt.label, _g(11, 500), DIM)
        _put(draw, box, (90, 194), _row_value(nxt), _g(10, 500), DIM)
    box = (158, 158, 226, 226)
    _tile(draw, box, fill=ORANGE)
    _put(draw, box, (180, 178), str(sel + 1), _g(22), BG)
    _put(draw, box, (176, 198), f"/{n}", _g(11, 500), BG)
    return _finish(img)


def draw_message(view, ctx):
    img, draw = _base()
    _tile(draw, TOP)
    if view.subtitle:
        _put(draw, TOP, (120, 50), view.title, _g(13), TEXT)
        _put(draw, TOP, (120, 68), view.subtitle, _g(10, 500), DIM)
    else:
        _put(draw, TOP, (120, 58), view.title, _g(14), TEXT)
    fill = {"busy": BLUE, "error": PINK, "success": LIME, "info": TILE2}[view.mood]
    ink = BG if view.mood == "success" else TEXT
    _tile(draw, HERO, fill=fill)
    _put(draw, HERO, (120, 116 if view.mood == "busy" else 120), view.text, _g(18), ink)
    if view.mood == "busy":
        _spinner(draw, 120, 138, TEXT)
    box = (14, 158, 226, 226)
    _tile(draw, box)
    f = _g(11, 500)
    lines = ui_common.wrap(" ".join(t for t in (view.detail, view.hint) if t), f, 170, 3)
    for k, ln in enumerate(lines):
        _put(draw, box, (120, 174 + k * 15), ln, f, TEXT if k == 0 and view.detail else DIM)
    return _finish(img)


def draw_playing(view, ctx):
    img, draw = _base()
    cover = ui_common.cover_image(view.cover, 140).crop((7, 1, 133, 139))
    img.paste(cover, (14, 14), ui_common.rounded_mask(126, 138, RAD))
    box = (146, 14, 226, 82)
    _tile(draw, box, fill=LIME if view.playing else TILE)
    ui_common.icon(draw, "pause" if view.playing else "play", 172, 56, 22, BG if view.playing else LIME)
    if view.shuffle:
        draw.ellipse([186, 70, 194, 78], fill=ORANGE)
        ui_common.text(draw, (198, 74), "SHF", _g(9), BG if view.playing else ORANGE, anchor="lm")
    box = (146, 88, 226, 152)
    _tile(draw, box)
    _put(draw, box, (186, 112), fmt_time(view.position), _g(20), TEXT)
    _put(draw, box, (186, 134), "/" + fmt_time(view.duration), _g(10, 500), DIM)
    box = (14, 158, 226, 226)
    _tile(draw, box)
    _put(draw, box, (120, 174), view.title, _g(14), TEXT)
    _put(draw, box, (120, 192), view.artist, _g(11, 500), DIM)
    half = _half(212)
    x0, x1 = W / 2 - half + 8, W / 2 + half - 8
    progress = max(0.0, min(1.0, view.position / view.duration)) if view.duration else 0.0
    draw.rounded_rectangle([x0, 204, x1, 208], 2, fill=TILE2)
    if progress > 0:
        draw.rounded_rectangle([x0, 204, x0 + (x1 - x0) * progress, 208], 2, fill=LIME)
    return _finish(img)


def draw_code(view, ctx):
    img, draw = _base()
    _tile(draw, TOP)
    _put(draw, TOP, (120, 58), view.title, _g(14), TEXT)
    _tile(draw, HERO, fill=LIME)
    _put(draw, HERO, (120, 120), view.code, _g(26), BG)
    box = (14, 158, 152, 226)
    _tile(draw, box)
    f = _g(10, 500)
    for k, ln in enumerate(ui_common.wrap(view.url.replace("/", "/ "), f, 110, 3)):
        _put(draw, box, (88, 174 + k * 14), ln.replace("/ ", "/"), f, TEXT if k == 0 else DIM)
    box = (158, 158, 226, 226)
    _tile(draw, box)
    _put(draw, box, (180, 176), "Warte", _g(11, 500), DIM)
    _spinner(draw, 178, 194, LIME)
    return _finish(img)


def draw_progress(view, ctx):
    img, draw = _base()
    _tile(draw, TOP)
    _put(draw, TOP, (120, 58), view.title, _g(14), TEXT)
    box = (14, 88, 152, 152)
    _tile(draw, box)
    _put(draw, box, (83, 120), f"{view.current}/{view.total}", _g(26), TEXT)
    frac = max(0.0, min(1.0, view.current / view.total)) if view.total else 0.0
    box = (158, 88, 226, 152)
    _tile(draw, box, fill=LIME)
    _put(draw, box, (190, 120), f"{round(100 * frac)}%", _g(16), BG)
    box = (14, 158, 226, 226)
    if view.done:
        _tile(draw, box, fill=LIME)
        _put(draw, box, (120, 182), "Fertig!", _g(18), BG)
    else:
        _tile(draw, box)
        _put(draw, box, (120, 176), view.track, _g(11, 500), TEXT)
        draw.rounded_rectangle([54, 192, 186, 198], 3, fill=TILE2)
        if frac > 0:
            draw.rounded_rectangle([54, 192, 54 + 132 * frac, 198], 3, fill=LIME)
    return _finish(img)


def draw_password(view, ctx):
    img, draw = _base()
    _tile(draw, TOP)
    _put(draw, TOP, (120, 48), view.ssid, _g(11, 500), DIM)
    f = _g(14)
    typed = view.typed
    if ui_common.text_len(typed, f) > 130:
        k = len(typed)
        while k > 1 and ui_common.text_len("…" + typed[-k:], f) > 130:
            k -= 1
        typed = "…" + typed[-k:]
    _put(draw, TOP, (120, 68), typed or " ", f, TEXT)
    box = (14, 88, 152, 152)
    _tile(draw, box)
    n = len(view.charset)
    for k, x in zip(range(-2, 3), (34, 58, 83, 108, 132)):
        ch = view.charset[(view.char_idx + k) % n]
        ch = "_" if ch == " " else ch
        ui_common.text(draw, (x, 120), ch, _g(16, 500) if k else _g(18), TEXT if k == 0 else DIM, anchor="mm")
        if k == 0:
            draw.line([(x - 7, 133), (x + 7, 133)], fill=LIME, width=2)
    box = (158, 88, 226, 152)
    _tile(draw, box, fill=LIME)
    ch = view.charset[view.char_idx]
    _put(draw, box, (190, 120), "_" if ch == " " else ch, _g(34), BG)
    for (x0, x1), icon, label in zip(((14, 67), (73, 120), (126, 173), (179, 226)),
                                     ("wave", "dot", "sync", "play"), ("Dreh", "Klick", "Lösch", "OK")):
        box = (x0, 158, x1, 226)
        _tile(draw, box)
        cx = min(max((x0 + x1) / 2, W / 2 - _half(176) + 14), W / 2 + _half(176) - 14)
        ui_common.icon(draw, icon, cx, 176, 12, LIME)
        _put(draw, box, (cx, 196), label, _g(8, 500), DIM)
    return _finish(img)


def draw_status(img, sv, ctx):
    # No %/ETA text on the ring: its spot is inside the top-left tile on every
    # bento screen, and Home already has its own battery tile.
    sv = dataclasses.replace(sv, show_labels=False)
    ui_common.draw_ring_status(img, sv, {"track": (40, 40, 42), "fill": LIME, "low": PINK, "off": TILE2,
                                         "wifi": TEXT, "bt": BLUE, "text": DIM, "accent": LIME,
                                         "font": _g(10, 500), "segments": 0})


def draw_quick_connect(img, qc, ctx):
    img.paste(Image.blend(img, Image.new("RGB", img.size, BG), 0.8), (0, 0))
    draw = ImageDraw.Draw(img)
    box = (30, 88, 210, 152)
    _tile(draw, box, fill=TILE2)
    _put(draw, box, (120, 110), qc.label, _g(15), PINK if qc.error else TEXT)
    draw.rounded_rectangle([44, 134, 196, 140], 3, fill=TILE)
    if qc.progress > 0:
        draw.rounded_rectangle([44, 134, 44 + 152 * min(1.0, qc.progress), 140], 3, fill=PINK if qc.error else LIME)


def draw_shutdown(ctx):
    img, draw = _base()
    _tile(draw, HERO)
    _put(draw, HERO, (120, 120), "Bis bald", _g(20), TEXT)
    box = (14, 158, 117, 226)
    _tile(draw, box, fill=LIME)
    draw.ellipse([60, 168, 88, 196], fill=BG)
    draw.ellipse([68, 164, 96, 192], fill=LIME)
    box = (123, 158, 226, 226)
    _tile(draw, box)
    _put(draw, box, (166, 182), "Mini-Musikplayer", _g(10, 500), DIM)
    return _finish(img)
