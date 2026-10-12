"""Cyberpunk: Night City HUD - black and signal yellow with red/cyan accents,
panels with cut-off corners, hazard stripes, barcodes, microtext; the selection
is a solid yellow panel with an RGB-split glitch on its text, the cover sits in
a chamfered frame that glitches now and then, the WLAN password wheel becomes a
"breach protocol" code column. Rajdhani + Share Tech Mono microtext.
"""
import functools
import math
import random

import numpy as np
from PIL import Image, ImageDraw

import ui_common
from ui_common import W
from ui_views import fmt_time

BG = (5, 5, 8)
YELLOW = (252, 238, 10)
RED = (255, 0, 60)
CYAN = (0, 240, 255)
DIM = (130, 124, 40)
WHITE = (240, 240, 230)
PANEL = (20, 20, 12)
OFF = (50, 48, 20)

HEADER_Y = 38
HEADER_BOTTOM = 60


def _rb(size, scale=1.0):  # Rajdhani Bold
    return ui_common.font("Rajdhani-Bold.ttf", size * scale)


def _rm(size, scale=1.0):  # Rajdhani Medium
    return ui_common.font("Rajdhani-Medium.ttf", size * scale)


def _micro(size=9):
    return ui_common.font("ShareTechMono-Regular.ttf", size)


def _half(y):
    return ui_common.safe_half_width(y)


# --- primitives -------------------------------------------------------------------

def _chamfer(x0, y0, x1, y1, c):
    """Panel outline with the top-left and bottom-right corners cut off."""
    return [(x0 + c, y0), (x1, y0), (x1, y1 - c), (x1 - c, y1), (x0, y1), (x0, y0 + c)]


def _glitch(draw, xy, s, f, fill, shift=2, anchor="la", max_w=None):
    """RGB-split text: red copy left, cyan copy right, real text on top."""
    s = ui_common.fit(s, f, max_w) if max_w else ui_common.glyph_safe(s, f)
    x, y = xy
    ui_common.text(draw, (x - shift, y), s, f, RED, anchor=anchor)
    ui_common.text(draw, (x + shift, y), s, f, CYAN, anchor=anchor)
    return ui_common.text(draw, (x, y), s, f, fill, anchor=anchor)


def _hazard(img, box, color, step=7):
    """Diagonal warning stripes clipped to `box`."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    tile = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(tile)
    for x in range(-h, w + h, step * 2):
        d.polygon([(x, h), (x + step, h), (x + step + h, 0), (x + h, 0)], fill=color)
    img.paste(tile, (x0, y0))


def _slants(draw, x0, y, n, w, h, lit, gap=1, slant=3, on=YELLOW, off=OFF, outline=False):
    """Row of slanted segments (parallelograms); the first `lit` are filled."""
    for k in range(n):
        x = x0 + k * (w + gap)
        pts = [(x + slant, y), (x + w + slant, y), (x + w, y + h), (x, y + h)]
        if k < lit:
            draw.polygon(pts, fill=on)
        elif outline:
            draw.polygon(pts, outline=off)
        else:
            draw.polygon(pts, fill=off)


@functools.lru_cache(maxsize=1)
def _bg():
    """Black, corner brackets on the bezel, microtext, barcode, scanlines."""
    img = Image.new("RGB", (W, W), BG)
    d = ImageDraw.Draw(img)
    for a in (60, 120, 240, 300):  # clear of the status ring's labels at the top-left
        d.arc([10, 10, 230, 230], a - 9, a + 9, fill=YELLOW, width=3)
    rng = random.Random(2077)
    x = 100
    while x < 140:
        bw = rng.choice((1, 1, 2, 3))
        d.rectangle([x, 212, x + bw - 1, 218], fill=DIM)
        x += bw + rng.choice((1, 2))
    arr = np.asarray(img).copy()
    arr[::3] = (arr[::3] * 0.7).astype(np.uint8)
    return Image.fromarray(arr)


def _base():
    img = _bg().copy()
    return img, ImageDraw.Draw(img)


def _header(draw, title, micro, scale):
    ui_common.text(draw, (120, 24), "SYS//MP3-2077", _micro(8), DIM, anchor="mm")
    half = _half(HEADER_Y)
    x0, x1 = 120 - half + 12, 120 + half - 10
    f = _rb(18, scale)
    if ui_common.text_len(ui_common.glyph_safe(title.upper(), f), f) > x1 - x0 - 12:
        f = _rb(15, scale)  # a size down before truncating
    w = min(ui_common.text_len(ui_common.glyph_safe(title.upper(), f), f), x1 - x0 - 12)
    tx = 120 - (w + 12) / 2 + 12  # tab + title centered as one block
    draw.rectangle([tx - 12, HEADER_Y - 9, tx - 6, HEADER_Y + 9], fill=RED)
    ui_common.text(draw, (tx, HEADER_Y), title.upper(), f, YELLOW, anchor="lm", max_w=x1 - tx)
    if micro:
        ui_common.text(draw, (120, 52), micro, _micro(9), DIM, anchor="mm", max_w=2 * _half(52) - 24)


@functools.lru_cache(maxsize=32)
def _chamfer_mask(w, h, c):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(_chamfer(0, 0, w - 1, h - 1, c), fill=255)
    return m


def _thumb(img, item, screen, x, cy, size, ink):
    size = int(size)
    y = int(cy - size / 2)
    draw = ImageDraw.Draw(img)
    if item.cover is not None:
        draw.polygon(_chamfer(x + 2, y + 2, x + size + 1, y + size + 1, 6), outline=CYAN)
        draw.polygon(_chamfer(x - 2, y - 2, x + size - 3, y + size - 3, 6), outline=RED)
        img.paste(ui_common.cover_image(item.cover, size), (int(x), y), _chamfer_mask(size, size, 6))
    else:
        ui_common.icon(draw, ui_common.icon_for(item, screen), x + size / 2, cy, size * 0.56, ink)


# --- views ------------------------------------------------------------------------

def draw_list(view, ctx):
    s = ctx.scale
    img, draw = _base()
    n = len(view.items)
    sel = max(0, min(view.sel, n - 1))
    _header(draw, view.title, f"// {sel + 1:02d} OF {n:02d}", s)
    for i, y, half, off in ui_common.list_rows(n, sel, 42 * s, center_y=128, min_half=56):
        item = view.items[i]
        x0, x1 = 120 - half + 10, 120 + half - 10
        if off == 0:
            danger = item.tone == "danger"
            fill, ink = (RED, WHITE) if danger else (YELLOW, BG)
            draw.polygon(_chamfer(x0, y - 21 * s, x1, y + 21 * s, 8), fill=fill)
            ui_common.text(draw, (x0 + 5, y - 21 * s + 4), f"{i + 1:02d}", _micro(8), ink)
            thumb = round(32 * s)
            _thumb(img, item, view.screen, x0 + 20, y, thumb, ink)
            draw = ImageDraw.Draw(img)
            tx = x0 + 20 + thumb + 8
            max_w = x1 - 8 - tx
            if item.sub:
                _glitch(draw, (tx, y + 1), item.label.upper(), _rb(17, s), ink, 1, "ls", max_w)
                ui_common.text(draw, (tx, y + 3), item.sub, _rm(12, s), ink, anchor="la", max_w=max_w)
            else:
                _glitch(draw, (tx, y), item.label.upper(), _rb(17, s), ink, 1, "lm", max_w)
        elif y - 10 * s > HEADER_BOTTOM:
            color = (DIM if item.tone == "muted" else YELLOW) if abs(off) == 1 else DIM
            if abs(off) == 1:
                draw.polygon(_chamfer(x0 + 8, y - 13 * s, x1 - 8, y + 13 * s, 6), outline=color)
            ui_common.text(draw, (120, y), f"{i + 1:02d} > {item.label.upper()}", _rb(14, s), color, anchor="mm",
                           max_w=2 * half - 44)
    if n > 1:
        lit = round(5 * sel / (n - 1))
        for k in range(6):
            y = 92 + k * 12
            draw.polygon([(212, y), (217, y), (215, y + 9), (210, y + 9)], fill=YELLOW if k == lit else OFF)
    return img


def _settings_value(draw, row, x_right, y, selected, s):
    if row.kind == "toggle":
        cw, ch = 22, 14
        x = x_right - 2 * cw
        for k, label in enumerate(("ON", "OFF")):
            box = [x + k * cw, y - ch / 2, x + (k + 1) * cw - 2, y + ch / 2]
            active = (k == 0) == bool(row.value)
            if active:
                draw.rectangle(box, fill=(BG if selected else YELLOW) if k == 0 else RED)
                ink = (YELLOW if selected else BG) if k == 0 else WHITE
            else:
                draw.rectangle(box, outline=BG if selected else DIM)
                ink = BG if selected else DIM
            ui_common.text(draw, ((box[0] + box[2]) / 2, y), label, _micro(8), ink, anchor="mm")
        return x
    if row.kind == "stepper":
        v = max(0, min(row.value, row.max))
        w = row.max * 8 + 3
        x = x_right - w
        _slants(draw, x, y - 6, row.max, 7, 12, v, on=BG if selected else YELLOW, off=BG if selected else DIM,
                outline=True)
        return x
    w = ui_common.text(draw, (x_right, y), str(row.value), _rm(12, s), BG if selected else (CYAN if row.on else DIM),
                       anchor="rm", max_w=90 * s)
    return x_right - w


def draw_settings(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, f"// CFG.{view.category.upper()}", s)
    n = len(view.rows)
    sel = max(0, min(view.sel, n - 1))
    for i, y, half, off in ui_common.window_rows(n, sel, HEADER_BOTTOM + 4, 206, 28 * s):
        row = view.rows[i]
        x0, x1 = 120 - half + 12, 120 + half - 12
        selected = off == 0
        if selected:
            draw.polygon(_chamfer(x0 - 4, y - 12 * s, x1 + 4, y + 12 * s, 6), fill=YELLOW)
        value_left = _settings_value(draw, row, x1 - 4, y, selected, s)
        ui_common.text(draw, (x0 + 4, y), row.label.upper() if selected else row.label,
                       _rb(13, s) if selected else _rm(13, s), BG if selected else YELLOW, anchor="lm",
                       max_w=max(20, value_left - x0 - 12))
    return img


def draw_message(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, None, s)
    if view.subtitle:
        ui_common.text(draw, (120, 60), view.subtitle, _rm(12, s), CYAN, anchor="mm", max_w=160)
    error = view.mood == "error"
    edge = RED if error else YELLOW
    draw.polygon(_chamfer(30, 72, 210, 182, 10), fill=PANEL, outline=edge)
    draw.polygon(_chamfer(31, 73, 209, 181, 10), outline=edge)
    _hazard(img, (40, 75, 208, 88), edge)
    draw = ImageDraw.Draw(img)
    tag = "// " + {"busy": "CONNECTING", "error": "ERROR", "success": "COMPLETE", "info": "STATUS"}[view.mood]
    w = ui_common.text_len(tag, _micro(9))
    draw.rectangle([42, 76, 48 + w, 87], fill=BG)
    ui_common.text(draw, (45, 81), tag, _micro(9), edge, anchor="lm")
    _glitch(draw, (120, 108), view.text.upper(), _rb(17, s), RED if error else YELLOW, 1, "mm", 160)
    y = 122
    f = _rm(12, s)
    for ln in ui_common.wrap(view.detail, f, 160, 3):
        ui_common.text(draw, (120, y), ln, f, WHITE, anchor="ma")
        y += f.size + 2
    if view.mood == "busy":
        _slants(draw, 54, 164, 8, 14, 6, 0, gap=3)
        k = ui_common.busy_phase(0.5, 8)
        x = 54 + k * 17
        draw.polygon([(x + 3, 164), (x + 17, 164), (x + 14, 170), (x, 170)], fill=YELLOW)
    if view.hint:
        ui_common.text(draw, (120, 194), view.hint.upper(), _micro(9), DIM, anchor="mm", max_w=140)
    return img


def draw_playing(view, ctx):
    s = ctx.scale
    img, draw = _base()
    x0, y0, size = 62, 26, 116
    cover = ui_common.cover_image(view.cover, size).copy()
    rng = random.Random(int(view.position * 3))
    if view.playing and rng.random() < 0.12:  # an occasional glitch burst, deterministic per 1/3 s
        for _ in range(3):
            sy, sh = rng.randint(0, size - 12), rng.randint(6, 12)
            strip = cover.crop((0, sy, size, sy + sh))
            cover.paste(strip, (rng.choice((-1, 1)) * rng.randint(3, 8), sy))
    draw.polygon(_chamfer(x0 + 3, y0 + 3, x0 + size + 2, y0 + size + 2, 12), outline=CYAN)
    draw.polygon(_chamfer(x0 - 3, y0 - 3, x0 + size - 4, y0 + size - 4, 12), outline=RED)
    img.paste(cover, (x0, y0), _chamfer_mask(size, size, 12))
    draw = ImageDraw.Draw(img)
    draw.polygon(_chamfer(x0, y0, x0 + size - 1, y0 + size - 1, 12), outline=YELLOW)
    draw.polygon(_chamfer(x0 + 1, y0 + 1, x0 + size - 2, y0 + size - 2, 12), outline=YELLOW)
    draw.rectangle([62, 132, 124, 146], fill=RED)
    ui_common.icon(draw, "pause" if view.playing else "play", 71, 139, 8, WHITE)
    ui_common.text(draw, (79, 139), "PLAYING" if view.playing else "PAUSED", _micro(9), WHITE, anchor="lm")
    if view.shuffle:
        draw.rectangle([148, 132, 178, 146], fill=CYAN)
        ui_common.text(draw, (163, 139), "SHF", _micro(9), BG, anchor="mm")
    ui_common.text(draw, (120, 158), view.title.upper(), _rb(19, s), YELLOW, anchor="mm", max_w=2 * _half(166) - 16)
    ui_common.text(draw, (120, 176), view.artist, _rm(13, s), CYAN, anchor="mm", max_w=2 * _half(182) - 20)
    progress = max(0.0, min(1.0, view.position / view.duration)) if view.duration else 0.0
    _slants(draw, 64, 186, 16, 6, 7, round(16 * progress))
    ui_common.text(draw, (120, 202), f"{fmt_time(view.position)} // {fmt_time(view.duration)}", _micro(9), DIM,
                   anchor="mm")
    return img


def draw_code(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, "NETLINK REQUEST", s)
    ui_common.text(draw, (120, 80), "> " + view.url, _rm(12, s), CYAN, anchor="mm", max_w=180)
    draw.polygon(_chamfer(36, 98, 204, 152, 10), outline=YELLOW)
    w = _glitch(draw, (120, 124), view.code, _rb(28, s), YELLOW, 2, "mm", 150)
    draw.rectangle([120 - w / 2, 140, 120 + w / 2, 141], fill=RED)
    ui_common.text(draw, (120, 168), "AWAITING HANDSHAKE", _micro(9), DIM, anchor="mm")
    _slants(draw, 70, 180, 8, 10, 5, 0, gap=3)
    k = ui_common.busy_phase(0.5, 8)
    draw.polygon([(70 + k * 13 + 3, 180), (70 + k * 13 + 13, 180), (70 + k * 13 + 10, 185), (70 + k * 13, 185)],
                 fill=YELLOW)
    return img


def draw_progress(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, "DATA TRANSFER", s)
    frac = max(0.0, min(1.0, view.current / view.total)) if view.total else 0.0
    _slants(draw, 40, 104, 20, 7, 12, round(20 * frac))
    ui_common.text(draw, (120, 140), f"{view.current:02d}/{view.total:02d}", _rb(28, s), YELLOW, anchor="mm")
    if view.track:
        ui_common.text(draw, (120, 164), view.track, _micro(9), DIM, anchor="mm", max_w=150)
    if view.done:
        _glitch(draw, (120, 186), "TRANSFER COMPLETE", _rb(14, s), CYAN, 1, "mm", 160)
    return img


def draw_password(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, "BREACH PROTOCOL", s)
    f = _rb(15, s)
    typed = view.typed + "_"
    if ui_common.text_len(typed, f) > 150:
        k = len(typed)
        while k > 1 and ui_common.text_len("…" + typed[-k:], f) > 150:
            k -= 1
        typed = "…" + typed[-k:]
    ui_common.text(draw, (120, 72), typed, f, YELLOW, anchor="mm")
    n = len(view.charset)
    for k, y in zip(range(-2, 3), (100, 122, 146, 170, 192)):
        ch = view.charset[(view.char_idx + k) % n]
        ch = "_" if ch == " " else ch
        if k == 0:
            draw.polygon(_chamfer(103, y - 13, 137, y + 13, 6), fill=YELLOW)
            ui_common.text(draw, (120, y), ch, _rb(18, s), BG, anchor="mm")
        else:
            draw.polygon(_chamfer(106, y - 10, 134, y + 10, 5), outline=DIM)
            ui_common.text(draw, (120, y), ch, _rb(15, s), YELLOW if abs(k) == 1 else DIM, anchor="mm")
    ui_common.text(draw, (60, 146), "ROT", _micro(8), DIM, anchor="mm")
    ui_common.text(draw, (180, 146), "PLAY=OK", _micro(8), DIM, anchor="mm")
    return img


def draw_status(img, sv, ctx):
    ui_common.draw_ring_status(img, sv, {"track": (40, 38, 16), "fill": YELLOW, "low": RED, "off": (60, 58, 30),
                                         "wifi": CYAN, "bt": YELLOW, "text": DIM, "accent": CYAN,
                                         "font": _micro(9), "segments": 12, "dot": "diamond"})


def draw_quick_connect(img, qc, ctx):
    img.paste(Image.blend(img, Image.new("RGB", img.size, BG), 0.9), (0, 0))
    draw = ImageDraw.Draw(img)
    box = [50, 50, 190, 190]
    lit_deg = 360 * max(0.0, min(1.0, qc.progress))
    color = RED if qc.error else YELLOW
    for k in range(4):
        a0 = -90 + 5 + k * 90
        draw.arc(box, a0, a0 + 80, fill=OFF, width=6)
        span = max(0.0, min(80.0, lit_deg - k * 90))
        if span > 0:
            draw.arc(box, a0, a0 + span, fill=color, width=6)
    draw.rectangle([64, 108, 176, 132], fill=BG)
    _glitch(draw, (120, 120), qc.label.upper(), _rb(16, ctx.scale), color, 2, "mm", 108)


def draw_shutdown(ctx):
    img, draw = _base()
    _hazard(img, (40, 92, 200, 100), YELLOW)
    draw = ImageDraw.Draw(img)
    _glitch(draw, (120, 120), "SYSTEM OFFLINE", _rb(20), YELLOW, 2, "mm")
    _hazard(img, (40, 140, 200, 148), YELLOW)
    return img
