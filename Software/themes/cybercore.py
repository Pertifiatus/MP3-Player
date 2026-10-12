"""Cybercore: late-90s cyber/computer culture - you are inside the mainframe.
Electric cyan on navy-black, radar rings + crosshair, a Tron wireframe floor,
binary columns, scanlines; terminal menus with HUD target brackets, covers
screen-printed as two-tone Bayer dither. Orbitron for titles, Share Tech Mono
for everything else.
"""
import functools
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import ui_common
from ui_common import W
from ui_views import fmt_time

BG = (2, 6, 14)
GRID = (0, 64, 84)
GRID_DIM = (0, 34, 46)
CYAN = (0, 234, 255)
CYAN_DIM = (0, 128, 150)
WHITE = (226, 248, 255)
DIM = (86, 136, 156)
GREEN = (124, 255, 79)
RED = (255, 72, 72)

HEADER_BOTTOM = 64  # list rows above this would collide with the header


def _t(size, scale=1.0):  # titles
    return ui_common.font("Orbitron[wght].ttf", size * scale, weight=700)


def _m(size, scale=1.0):  # everything else
    return ui_common.font("ShareTechMono-Regular.ttf", size * scale)


def _half(y):
    return ui_common.safe_half_width(y)


# --- primitives -------------------------------------------------------------------

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


def _base():
    img = _bg().copy()
    return img, ImageDraw.Draw(img)


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


def _header(draw, title, sub=None, scale=1.0):
    ui_common.text(draw, (120, 40), "[ " + title.upper() + " ]", _t(12, scale), CYAN, anchor="mm",
                   max_w=2 * _half(40) - 16)
    if sub:
        ui_common.text(draw, (120, 54), sub, _m(9, scale), DIM, anchor="mm", max_w=2 * _half(54) - 20)


def _spinner():
    return "|/-\\"[ui_common.busy_phase(0.5, 4)]


# --- views ------------------------------------------------------------------------

def draw_list(view, ctx):
    s = ctx.scale
    img, draw = _base()
    n = len(view.items)
    sel = max(0, min(view.sel, n - 1))
    _header(draw, view.title, f"0x{sel + 1:02X}/{n:02X} :: {view.screen.upper()}", s)
    bh = round(19 * s)
    for i, y, half, off in ui_common.list_rows(n, sel, 38 * s, center_y=126):
        item = view.items[i]
        if off == 0:
            x0, x1 = 120 - half + 12, 120 + half - 12
            _brackets(draw, (x0, y - bh, x1, y + bh), RED if item.tone == "danger" else CYAN)
            tx = x0 + 6
            thumb = round(28 * s)
            if item.cover is not None:
                img.paste(_duotone(item.cover, thumb), (int(tx), int(y - thumb / 2)))
            else:
                draw.rectangle([tx, y - thumb / 2, tx + thumb, y + thumb / 2], outline=CYAN)
                ui_common.icon(draw, ui_common.icon_for(item, view.screen), tx + thumb / 2, y, thumb * 0.62,
                               DIM if item.tone == "muted" else CYAN)
            lx = tx + thumb + 8
            label_color = DIM if item.tone == "muted" else WHITE
            _glow_text(img, (lx, y - bh + 2), item.label, _m(16, s), label_color, max_w=x1 - 8 - lx)
            if item.sub:
                ui_common.text(draw, (lx, y + 3 * s), "> " + item.sub, _m(11, s), CYAN_DIM, max_w=x1 - 8 - lx)
        elif y - 8 * s > HEADER_BOTTOM:
            ui_common.text(draw, (120, y), f"{i + 1:02d} // {item.label.upper()}", _m(12, s),
                           DIM if abs(off) == 1 else GRID, anchor="mm", max_w=2 * half - 24)
    if n > 1:  # scroll position
        draw.rectangle([213, 74, 215, 166], fill=GRID)
        th = max(8, 92 / n)
        ty = 74 + (92 - th) * sel / (n - 1)
        draw.rectangle([213, ty, 215, ty + th], fill=CYAN)
    return img


def _value(draw, row, x_right, y, selected, s):
    """Draws a settings value right-aligned at x_right; returns its left x."""
    if row.kind == "stepper":
        v = max(0, min(row.value, row.max))
        cw, gap = round(6 * s), 2
        x = x_right - row.max * (cw + gap) + gap
        for k in range(row.max):
            box = [x + k * (cw + gap), y - 4 * s, x + k * (cw + gap) + cw - 1, y + 4 * s]
            if k < v:
                draw.rectangle(box, fill=BG if selected else CYAN)
            else:
                draw.rectangle(box, outline=BG if selected else GRID)
        return x
    if row.kind == "toggle":
        s_txt, color = ("[ON ]", GREEN) if row.value else ("[OFF]", DIM)
    else:
        s_txt, color = str(row.value), (CYAN if row.on else DIM)
    f = _m(12, s)
    w = ui_common.text(draw, (x_right, y), s_txt, f, BG if selected else color, anchor="rm", max_w=90 * s)
    return x_right - w


def draw_settings(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, f"SYS.CFG :: {view.category.upper()}", s)
    n = len(view.rows)
    sel = max(0, min(view.sel, n - 1))
    f = _m(12, s)
    for i, y, half, off in ui_common.window_rows(n, sel, HEADER_BOTTOM + 4, 202, 26 * s):
        row = view.rows[i]
        x0, x1 = 120 - half + 10, 120 + half - 10
        selected = off == 0
        if selected:
            draw.rectangle([x0 - 2, y - 11 * s, x1 + 2, y + 11 * s], fill=CYAN)
        value_left = _value(draw, row, x1, y, selected, s)
        label_w = ui_common.text(draw, (x0, y), row.label.upper() if selected else row.label, f,
                                 BG if selected else WHITE, anchor="lm", max_w=max(20, value_left - x0 - 10))
        leader_x0, leader_x1 = x0 + label_w + 4, value_left - 4
        if leader_x1 - leader_x0 > 6:
            for x in range(int(leader_x0), int(leader_x1), 4):
                draw.point((x, y + 3), fill=BG if selected else GRID)
    return img


def draw_message(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, None, s)
    if view.subtitle:
        ui_common.text(draw, (120, 58), view.subtitle, _m(11, s), DIM, anchor="mm", max_w=170)
    color = {"busy": CYAN, "success": GREEN, "info": WHITE, "error": RED}[view.mood]
    line = ("!! " if view.mood == "error" else "> ") + view.text.upper()
    if view.mood == "busy":
        line += " " + _spinner()
    f = _m(15, s)
    w = ui_common.text(draw, (120, 96), line, f, color, anchor="mm", max_w=184)
    if view.mood in ("busy", "info"):  # terminal block cursor
        draw.rectangle([120 + w / 2 + 3, 96 - f.size / 2 + 2, 120 + w / 2 + 3 + 7 * s, 96 + f.size / 2 - 1], fill=color)
    y = 114
    fd = _m(12, s)
    for ln in ui_common.wrap(view.detail, fd, 180, 3):
        ui_common.text(draw, (120, y), ln, fd, CYAN if view.mood == "busy" else WHITE, anchor="ma")
        y += fd.size + 4
    fh = _m(10, s)
    for ln in ui_common.wrap(view.hint, fh, 170, 2):
        ui_common.text(draw, (120, y + 2), ln, fh, DIM, anchor="ma")
        y += fh.size + 4
    return img


def draw_playing(view, ctx):
    s = ctx.scale
    img, draw = _base()
    cx, cy = 120, 92
    progress = max(0.0, min(1.0, view.position / view.duration)) if view.duration else 0.0
    for k in range(60):
        a = np.radians(-90 + 6 * k)
        p0 = (cx + 60 * np.cos(a), cy + 60 * np.sin(a))
        p1 = (cx + 68 * np.cos(a), cy + 68 * np.sin(a))
        draw.line([p0, p1], fill=CYAN if k / 60 < progress else GRID, width=2)
    img.paste(_duotone(view.cover, 100), (cx - 50, cy - 50), ui_common.circle_mask(100))
    sweep = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sweep)
    a = (view.position * 45) % 360
    for k, alpha in enumerate((140, 110, 80, 55, 35, 20)):
        sd.pieslice([0, 0, 99, 99], a - 6 * (k + 1), a - 6 * k, fill=CYAN + (alpha,))
    sweep.putalpha(Image.composite(sweep.getchannel("A"), Image.new("L", (100, 100), 0), ui_common.circle_mask(100)))
    img.paste(sweep, (cx - 50, cy - 50), sweep)
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=BG, outline=CYAN)
    ui_common.icon(draw, "pause" if view.playing else "play", cx, cy, 12, CYAN)
    time_s = f"{fmt_time(view.position)} / {fmt_time(view.duration)}"
    w = ui_common.text(draw, (120, 166), time_s, _m(12, s), CYAN, anchor="mm")
    if view.shuffle:
        ui_common.text(draw, (120 + w / 2 + 8, 166), "SHF", _m(10, s), GREEN, anchor="lm")
    ui_common.text(draw, (120, 184), view.title, _m(15, s), WHITE, anchor="mm", max_w=2 * _half(192) - 16)
    ui_common.text(draw, (120, 202), view.artist, _m(11, s), DIM, anchor="mm", max_w=2 * _half(208) - 16)
    return img


def draw_code(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, None, s)
    ui_common.text(draw, (120, 66), "> GOTO", _m(11, s), DIM, anchor="mm")
    ui_common.text(draw, (120, 84), view.url, _m(12, s), CYAN, anchor="mm", max_w=186)
    ui_common.text(draw, (120, 106), "> ENTER CODE", _m(11, s), DIM, anchor="mm")
    _brackets(draw, (40, 114, 200, 150), CYAN)
    ui_common.text(draw, (120, 132), view.code, _t(20, s), WHITE, anchor="mm", max_w=150)
    ui_common.text(draw, (120, 172), "> AWAITING AUTH " + _spinner(), _m(11, s), DIM, anchor="mm")
    return img


def draw_progress(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, None, s)
    frac = max(0.0, min(1.0, view.current / view.total)) if view.total else 0.0
    lit = round(12 * frac)
    x = 120 - (12 * 11 + 11 * 2) / 2
    for k in range(12):
        box = [x + k * 13, 97, x + k * 13 + 10, 111]
        if k < lit:
            draw.rectangle(box, fill=CYAN)
        else:
            draw.rectangle(box, outline=GRID)
    ui_common.text(draw, (120, 136), f"{view.current:02d}/{view.total:02d}", _t(20, s), WHITE, anchor="mm")
    if view.track:
        ui_common.text(draw, (120, 162), view.track, _m(11, s), DIM, anchor="mm", max_w=170)
    if view.done:
        ui_common.text(draw, (120, 184), "> COMPLETE", _m(13, s), GREEN, anchor="mm")
    return img


def draw_password(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(draw, view.title, None, s)
    ui_common.text(draw, (120, 56), view.ssid, _m(11, s), DIM, anchor="mm", max_w=150)
    f = _m(15, s)
    typed = view.typed + "_"
    if f.getlength(typed) > 170:  # keep the end - that's where the cursor is
        k = len(typed)
        while k > 1 and f.getlength("…" + typed[-k:]) > 170:
            k -= 1
        typed = "…" + typed[-k:]
    ui_common.text(draw, (120, 76), typed, f, WHITE, anchor="mm")
    n = len(view.charset)
    for k, y, font, color in ((-2, 104, _m(11, s), GRID), (-1, 120, _m(14, s), CYAN_DIM), (0, 140, _t(22, s), WHITE),
                              (1, 160, _m(14, s), CYAN_DIM), (2, 176, _m(11, s), GRID)):
        ch = view.charset[(view.char_idx + k) % n]
        ui_common.text(draw, (120, y), "_" if ch == " " else ch, font, color, anchor="mm")
    _brackets(draw, (102, 124, 138, 156), CYAN, 6)
    fh = _m(9, s)
    y = 192
    for ln in ui_common.wrap(view.hint, fh, 150, 2):
        ui_common.text(draw, (120, y), ln, fh, DIM, anchor="ma")
        y += fh.size + 3
    return img


def draw_status(img, sv, ctx):
    ui_common.draw_ring_status(img, sv, {"track": GRID_DIM, "fill": CYAN, "low": RED, "off": (30, 50, 60),
                                         "wifi": WHITE, "bt": CYAN, "text": DIM, "accent": GREEN,
                                         "font": _m(10), "segments": 18, "dot": "square"})


def draw_quick_connect(img, qc, ctx):
    img.paste(Image.blend(img, Image.new("RGB", img.size, BG), 0.85), (0, 0))
    draw = ImageDraw.Draw(img)
    _brackets(draw, (40, 40, 200, 200), RED if qc.error else CYAN, 14, 2)
    box = [50, 50, 190, 190]
    draw.ellipse(box, outline=GRID, width=4)
    if qc.progress >= 1.0:
        draw.ellipse(box, outline=RED if qc.error else CYAN, width=4)
    elif qc.progress > 0:
        draw.arc(box, -90, -90 + 360 * qc.progress, fill=CYAN, width=4)
    draw.rectangle([62, 110, 178, 130], fill=BG)  # the list below still shows through the dimmed frame
    ui_common.text(draw, (120, 120), qc.label.upper(), _m(14, ctx.scale), RED if qc.error else WHITE,
                   anchor="mm", max_w=112)


def draw_shutdown(ctx):
    img, draw = _base()
    ui_common.text(draw, (120, 110), "> SHUTDOWN_", _m(16), CYAN, anchor="mm")
    ui_common.text(draw, (120, 132), "SESSION TERMINATED", _m(10), DIM, anchor="mm")
    return img
