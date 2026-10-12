"""Glassmorphism: frosted glass over colored light - deep navy with big blurred
color orbs (tinted by the selected playlist in the library), translucent glass
cards with a thin light rim and a soft shadow, the selected card large and
bright in the middle with its neighbors smaller and fainter for depth. Now
Playing puts the sharp cover over its own blurred self (Apple-Music style).
Poppins.
"""
import functools
import math

from PIL import Image, ImageDraw, ImageFilter

import ui_common
from ui_common import W
from ui_views import fmt_time

NAVY = (10, 12, 30)
ORBS = ((123, 47, 247), (241, 7, 163), (0, 210, 255), (255, 138, 0))
TEXT = (255, 255, 255)
DIM = (196, 202, 230)
FAINT = (150, 156, 190)
ACCENT = (110, 231, 249)
RED = (255, 99, 132)
GREEN = (74, 222, 128)
ORB_SPOTS = ((60, 58, 82), (192, 70, 72), (64, 190, 76), (186, 186, 86))  # (cx, cy, r)
CAT_TINTS = {"display": (255, 159, 10), "led": (255, 214, 10), "connectivity": (10, 132, 255),
             "sync": (110, 231, 249), "motion": (255, 99, 132), "about": (180, 180, 200)}
HEADER_Y = 36


def _semi(size, scale=1.0):
    return ui_common.font("Poppins-SemiBold.ttf", size * scale)


def _reg(size, scale=1.0):
    return ui_common.font("Poppins-Regular.ttf", size * scale)


def _half(y):
    return ui_common.safe_half_width(y)


# --- primitives -------------------------------------------------------------------

@functools.lru_cache(maxsize=16)
def _orb_bg(colors):
    """Navy + four big orbs, blurred into colored light (cached per color set)."""
    img = Image.new("RGB", (W, W), NAVY)
    d = ImageDraw.Draw(img)
    for (cx, cy, r), c in zip(ORB_SPOTS, colors):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    # Darkened a little so white text on light glass keeps its contrast over the brightest orbs.
    return Image.blend(img.filter(ImageFilter.GaussianBlur(34)), Image.new("RGB", (W, W), NAVY), 0.3)


def _bg_for(view):
    """Library/playlist views tint two orbs with the selected item's playlist color."""
    color = None
    items = getattr(view, "items", None)
    if items and 0 <= view.sel < len(items) and items[view.sel].cover:
        color = ui_common.hex_to_rgb(items[view.sel].cover[2])
    return _orb_bg(ORBS if color is None else (color, ORBS[1], ORBS[2], color)).copy()


@functools.lru_cache(maxsize=8)
def _playing_bg(ref):
    """Now Playing backdrop: the cover blurred full-screen, darkened, a little orb light on top."""
    img = ui_common.cover_image(ref, W).filter(ImageFilter.GaussianBlur(20))
    img = Image.blend(img, Image.new("RGB", (W, W), NAVY), 0.45)
    return Image.blend(img, _orb_bg(ORBS), 0.25)


@functools.lru_cache(maxsize=48)
def _shadow(w, h, r, blur=8, alpha=90):
    pad = blur * 2
    m = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(m).rounded_rectangle([pad, pad, pad + w, pad + h], radius=r, fill=alpha)
    out = Image.new("RGBA", m.size, (0, 0, 0, 0))
    out.putalpha(m.filter(ImageFilter.GaussianBlur(blur)))
    return out, pad


@functools.lru_cache(maxsize=48)
def _panel(w, h, r, fill_a, edge_a):
    panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=(255, 255, 255, fill_a), outline=(255, 255, 255, edge_a))
    d.line([(r, 1), (w - r, 1)], fill=(255, 255, 255, min(255, edge_a + 30)))  # top-edge light catch
    return panel


def _glass(img, box, r, strength=1.0, selected=False, shadow=True):
    """Frosted panel: soft shadow, translucent white fill, thin light rim. `strength`
    (0-1) fades it for depth (neighbors of the selection)."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = max(4, x1 - x0), max(4, y1 - y0)
    r = min(int(r), h // 2)
    if shadow:
        sh, pad = _shadow(w, h, r)
        img.paste(sh, (x0 - pad, y0 - pad + 4), sh)
    panel = _panel(w, h, r, int((64 if selected else 38) * strength), int((150 if selected else 90) * strength))
    img.paste(panel, (x0, y0), panel)


def _glass_circle(img, cx, cy, r, tint):
    layer = Image.new("RGBA", (2 * r + 2, 2 * r + 2), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([0, 0, 2 * r, 2 * r], fill=tint + (110,), outline=(255, 255, 255, 140))
    img.paste(layer, (int(cx - r), int(cy - r)), layer)


def _glow(img, cx, cy, r, color):
    layer = Image.new("RGBA", (4 * r, 4 * r), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([r, r, 3 * r, 3 * r], fill=color + (200,))
    layer = layer.filter(ImageFilter.GaussianBlur(r / 2))
    img.paste(layer, (int(cx - 2 * r), int(cy - 2 * r)), layer)


def _tint(item):
    if item.kind in CAT_TINTS:
        return CAT_TINTS[item.kind]
    return {"accent": ACCENT, "muted": (255, 255, 255), "danger": RED}[item.tone]


def _header(draw, title, scale, y=HEADER_Y):
    f, max_w = _semi(12, scale), 2 * _half(y) - 16
    spaced = ui_common.letter_spaced(title.upper())  # letter-spaced if it fits, plain before truncating
    s = spaced if ui_common.text_len(spaced, f) <= max_w else title.upper()
    ui_common.text(draw, (120, y), s, f, TEXT, anchor="mm", max_w=max_w)


def _thumb(img, item, screen, x, cy, size):
    size = int(size)
    if item.cover is not None:
        img.paste(ui_common.cover_image(item.cover, size), (int(x), int(cy - size / 2)),
                  ui_common.rounded_mask(size, size, size // 4))
    else:
        r = size // 2
        _glass_circle(img, x + r, cy, r, _tint(item))
        ui_common.icon(ImageDraw.Draw(img), ui_common.icon_for(item, screen), x + r, cy, size * 0.45, TEXT)


# --- views ------------------------------------------------------------------------

def draw_list(view, ctx):
    s = ctx.scale
    img = _bg_for(view)
    draw = ImageDraw.Draw(img)
    n = len(view.items)
    sel = max(0, min(view.sel, n - 1))
    # Like iOS: the title only shows at the top of the list - once scrolled, the
    # card above the selection takes its place.
    if sel == 0:
        _header(draw, view.title, s)
    rows = sorted(ui_common.list_rows(n, sel, 66 * s, center_y=124, min_half=60), key=lambda r: -abs(r[3]))
    for i, y, half, off in rows:  # far neighbors first, so the selected card sits on top
        item = view.items[i]
        selected = off == 0
        w = (2 * half - 14) * (1 if selected else 0.86)
        h = (60 if selected else 48) * s
        x0 = 120 - w / 2
        _glass(img, (x0, y - h / 2, x0 + w, y + h / 2), 18, 1.0 if selected else 0.6, selected)
        thumb = (44 if selected else 32) * s
        _thumb(img, item, view.screen, x0 + 9, y, thumb)
        draw = ImageDraw.Draw(img)
        tx = x0 + 9 + thumb + 10
        max_w = x0 + w - 12 - tx
        if selected and item.sub:
            ui_common.text(draw, (tx, y - 1), item.label, _semi(15, s), TEXT, anchor="ls", max_w=max_w)
            ui_common.text(draw, (tx, y + 3), item.sub, _reg(11, s), DIM, anchor="la", max_w=max_w)
        else:
            ui_common.text(draw, (tx, y), item.label, _semi(15 if selected else 12, s), TEXT if selected else DIM,
                           anchor="lm", max_w=max_w)
    return img


def _settings_value(img, row, x_right, y, s):
    draw = ImageDraw.Draw(img)
    if row.kind == "toggle":
        w, h = round(36 * s), round(20 * s)
        x = x_right - w
        _glass(img, (x, y - h / 2, x + w, y + h / 2), h // 2, shadow=False)
        k = round(14 * s)
        kx = x + w - k - 3 if row.value else x + 3
        if row.value:
            _glow(img, kx + k / 2, y, round(6 * s), ACCENT)
        ImageDraw.Draw(img).ellipse([kx, y - k / 2, kx + k, y + k / 2], fill=ACCENT if row.value else TEXT)
        return x
    if row.kind == "stepper":
        v = max(0, min(row.value, row.max))
        r, gap = 4, 5
        x = x_right - row.max * (2 * r + gap) + gap
        for k in range(row.max):
            bx = x + k * (2 * r + gap)
            if k < v:
                draw.ellipse([bx, y - r, bx + 2 * r, y + r], fill=ACCENT)
            else:
                draw.ellipse([bx, y - r, bx + 2 * r, y + r], outline=FAINT)
        return x
    w = ui_common.text(draw, (x_right, y), str(row.value), _reg(11, s), ACCENT if row.on else DIM, anchor="rm",
                       max_w=90 * s)
    return x_right - w


def draw_settings(view, ctx):
    s = ctx.scale
    img = _orb_bg(ORBS).copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    panel = (26, 54, 214, 194)
    _glass(img, panel, 22)
    n = len(view.rows)
    sel = max(0, min(view.sel, n - 1))
    pitch = 30 * s
    # Fill the panel from its top and scroll around the selection (like Klassik's
    # card) instead of centering, which left the panel's top half empty.
    visible = max(1, int((panel[3] - panel[1] - 8) // pitch))
    start = max(0, min(sel - visible // 2, n - visible))
    for i in range(start, min(n, start + visible)):
        off = i - sel
        y = panel[1] + 4 + (i - start + 0.5) * pitch
        half = _half(y)
        row = view.rows[i]
        x0, x1 = max(panel[0] + 8, 120 - half + 10), min(panel[2] - 8, 120 + half - 10)
        if off == 0:
            _glass(img, (x0 - 4, y - pitch / 2 + 2, x1 + 4, y + pitch / 2 - 2), 12, selected=True, shadow=False)
        elif off == -1 or off == 1:
            sep_y = y - pitch / 2 if off == 1 else y + pitch / 2
            ImageDraw.Draw(img).line([(x0 + 6, sep_y), (x1 - 6, sep_y)], fill=(120, 124, 160))
        value_left = _settings_value(img, row, x1 - 4, y, s)
        draw = ImageDraw.Draw(img)
        ui_common.text(draw, (x0 + 6, y), row.label, _semi(12, s) if off == 0 else _reg(12, s),
                       TEXT if off == 0 else DIM, anchor="lm", max_w=max(20, value_left - x0 - 16))
    return img


def _mood_icon(img, cx, cy, mood):
    draw = ImageDraw.Draw(img)
    if mood == "busy":
        a = ui_common.busy_phase(0.25, 8) * 45
        draw.arc([cx - 14, cy - 14, cx + 14, cy + 14], a, a + 270, fill=ACCENT, width=3)
        return
    color = {"error": RED, "success": GREEN, "info": (255, 255, 255)}[mood]
    if mood == "info":
        draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=TEXT, width=2)
        draw.ellipse([cx - 2, cy - 8, cx + 2, cy - 4], fill=TEXT)
        draw.rectangle([cx - 1.5, cy - 1, cx + 1.5, cy + 8], fill=TEXT)
        return
    _glow(img, cx, cy, 10, color)
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=color)
    if mood == "error":
        draw.rectangle([cx - 1.5, cy - 8, cx + 1.5, cy + 3], fill=TEXT)
        draw.ellipse([cx - 2, cy + 5, cx + 2, cy + 9], fill=TEXT)
    else:
        draw.line([(cx - 6, cy), (cx - 2, cy + 5), (cx + 7, cy - 5)], fill=TEXT, width=3, joint="curve")


def draw_message(view, ctx):
    s = ctx.scale
    img = _orb_bg(ORBS).copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    if view.subtitle:
        ui_common.text(draw, (120, 52), view.subtitle, _reg(11, s), DIM, anchor="mm", max_w=150)
    _glass(img, (38, 62, 202, 184), 22)
    _mood_icon(img, 120, 88, view.mood)
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 118), view.text, _semi(14, s), TEXT, anchor="mm", max_w=150)
    y = 132
    f = _reg(11, s)
    for ln in ui_common.wrap(view.detail, f, 146, 3):
        ui_common.text(draw, (120, y), ln, f, DIM, anchor="ma")
        y += f.size + 4
    if view.hint:
        ui_common.text(draw, (120, 196), view.hint, _reg(10, s), DIM, anchor="mm", max_w=140)
    return img


def draw_playing(view, ctx):
    s = ctx.scale
    img = _playing_bg(view.cover).copy()
    sh, pad = _shadow(112, 112, 18, 10, 140)
    img.paste(sh, (64 - pad, 30 - pad + 6), sh)
    img.paste(ui_common.cover_image(view.cover, 112), (64, 30), ui_common.rounded_mask(112, 112, 18))
    draw = ImageDraw.Draw(img)
    progress = max(0.0, min(1.0, view.position / view.duration)) if view.duration else 0.0
    draw.line([(72, 150), (168, 150)], fill=(150, 154, 190), width=2)
    if progress > 0:
        draw.line([(72, 150), (72 + 96 * progress, 150)], fill=ACCENT, width=3)
    ui_common.text(draw, (72, 155), fmt_time(view.position), _reg(9, s), DIM, anchor="la")
    ui_common.text(draw, (168, 155), fmt_time(view.duration), _reg(9, s), DIM, anchor="ra")
    ui_common.text(draw, (120, 176), view.title, _semi(15, s), TEXT, anchor="mm", max_w=2 * _half(184) - 20)
    ui_common.text(draw, (120, 194), view.artist, _reg(11, s), DIM, anchor="mm", max_w=2 * _half(200) - 20)
    _glass(img, (100, 204, 140, 222), 9, shadow=False)
    draw = ImageDraw.Draw(img)
    ui_common.icon(draw, "pause" if view.playing else "play", 120, 213, 10, TEXT)
    if view.shuffle:
        ui_common.icon(draw, "sync", 152, 213, 10, ACCENT)
    return img


def draw_code(view, ctx):
    s = ctx.scale
    img = _orb_bg(ORBS).copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    _glass(img, (30, 56, 210, 192), 22)
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 76), "Gehe zu", _reg(11, s), DIM, anchor="mm")
    ui_common.text(draw, (120, 94), view.url, _semi(12, s), TEXT, anchor="mm", max_w=166)
    ui_common.text(draw, (120, 118), "Code", _reg(11, s), DIM, anchor="mm")
    f = _semi(24, s)
    glow = Image.new("RGBA", (180, 48), (0, 0, 0, 0))
    ui_common.text(ImageDraw.Draw(glow), (90, 24), view.code, f, ACCENT + (255,), anchor="mm", max_w=160)
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    img.paste(glow, (30, 118), glow)
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 142), view.code, f, ACCENT, anchor="mm", max_w=160)
    ui_common.text(draw, (120, 176), "Warte auf Bestätigung …", _reg(10, s), DIM, anchor="mm", max_w=150)
    return img


@functools.lru_cache(maxsize=2)
def _gradient_bar(w, h):
    bar = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(bar)
    for x in range(w):
        t = x / max(1, w - 1)
        d.line([(x, 0), (x, h)], fill=tuple(round(a + (b - a) * t) for a, b in zip(ACCENT, (123, 47, 247))))
    return bar


def draw_progress(view, ctx):
    s = ctx.scale
    img = _orb_bg(ORBS).copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    _glass(img, (34, 72, 206, 180), 22)
    _glass(img, (54, 108, 186, 122), 7, shadow=False)
    frac = max(0.0, min(1.0, view.current / view.total)) if view.total else 0.0
    fw = int(132 * frac)
    if fw >= 14:
        _glow(img, 54 + fw / 2, 115, 6, ACCENT)
        img.paste(_gradient_bar(132, 14).crop((0, 0, fw, 14)), (54, 108), ui_common.rounded_mask(fw, 14, 7))
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 142), f"{view.current} / {view.total}", _semi(16, s), TEXT, anchor="mm")
    if view.done:
        ui_common.text(draw, (120, 162), "Fertig!", _semi(13, s), GREEN, anchor="mm")
    elif view.track:
        ui_common.text(draw, (120, 162), view.track, _reg(11, s), DIM, anchor="mm", max_w=150)
    return img


def draw_password(view, ctx):
    s = ctx.scale
    img = _orb_bg(ORBS).copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    ui_common.text(draw, (120, 52), view.ssid, _reg(11, s), DIM, anchor="mm", max_w=150)
    _glass(img, (40, 62, 200, 88), 12, shadow=False)
    f = _semi(14, s)
    typed = view.typed
    if ui_common.text_len(typed, f) > 144:
        k = len(typed)
        while k > 1 and ui_common.text_len("…" + typed[-k:], f) > 144:
            k -= 1
        typed = "…" + typed[-k:]
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (50, 75), typed, f, TEXT, anchor="lm")
    n = len(view.charset)
    for k, size, strength, font in ((-2, 24, 0.4, _reg(11, s)), (2, 24, 0.4, _reg(11, s)),
                                    (-1, 34, 0.7, _reg(15, s)), (1, 34, 0.7, _reg(15, s))):
        x = 120 + (86 if abs(k) == 2 else 50) * (1 if k > 0 else -1)
        _glass(img, (x - size / 2, 126 - size / 2, x + size / 2, 126 + size / 2), 8, strength, shadow=False)
        ch = view.charset[(view.char_idx + k) % n]
        ui_common.text(ImageDraw.Draw(img), (x, 126), "_" if ch == " " else ch, font, DIM, anchor="mm")
    _glass(img, (96, 102, 144, 150), 14, selected=True)
    ch = view.charset[view.char_idx]
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 126), "_" if ch == " " else ch, _semi(28, s), TEXT, anchor="mm")
    fh = _reg(9, s)
    y = 164
    for ln in ui_common.wrap(view.hint, fh, 150, 3):
        ui_common.text(draw, (120, y), ln, fh, DIM, anchor="ma")
        y += fh.size + 4
    return img


def draw_status(img, sv, ctx):
    ui_common.draw_ring_status(img, sv, {"track": (70, 72, 104), "fill": ACCENT, "low": RED, "off": (90, 92, 120),
                                         "wifi": TEXT, "bt": (140, 170, 255), "text": DIM, "accent": GREEN,
                                         "font": _reg(10), "segments": 0})


def draw_quick_connect(img, qc, ctx):
    blurred = img.filter(ImageFilter.GaussianBlur(6))
    img.paste(Image.blend(blurred, Image.new("RGB", img.size, NAVY), 0.4), (0, 0))
    _glass(img, (42, 42, 198, 198), 78)
    draw = ImageDraw.Draw(img)
    box = [56, 56, 184, 184]
    draw.ellipse(box, outline=(90, 92, 120), width=5)
    color = RED if qc.error else ACCENT
    if qc.progress >= 1.0:
        draw.ellipse(box, outline=color, width=5)
    elif qc.progress > 0:
        draw.arc(box, -90, -90 + 360 * qc.progress, fill=color, width=5)
    ui_common.text(draw, (120, 120), qc.label, _semi(13, ctx.scale), RED if qc.error else TEXT, anchor="mm",
                   max_w=118)


def draw_shutdown(ctx):
    img = _orb_bg(ORBS).copy()
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 110), "Bis bald", _semi(18), TEXT, anchor="mm")
    ui_common.text(draw, (120, 134), "Mini-Musikplayer", _reg(11), DIM, anchor="mm")
    return img
