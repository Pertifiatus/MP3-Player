"""Neumorphism: soft UI - everything is pressed out of (or into) one pale
blue-gray material, lit from the top-left: raised shapes cast a light shadow
up-left and a dark one down-right, pressed-in wells the reverse. The whole round
screen reads as one shallow dish; Now Playing is the classic soft-UI dial with an
inset progress groove and a knob riding it. Low contrast by design, one calm
blue accent. Nunito.
"""
import functools
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

import ui_common
from ui_common import W

BASE = (224, 229, 236)
LIGHT = (255, 255, 255)
DARK = (163, 177, 198)
TEXT = (68, 76, 96)
DIM = (140, 150, 170)
FAINT = (190, 196, 210)
ACCENT = (91, 124, 250)
DANGER = (235, 87, 87)

HEADER_Y = 36
HEADER_BOTTOM = 52


def _nf(size, scale=1.0, weight=700):
    return ui_common.font("Nunito[wght].ttf", size * scale, weight=weight)


def _half(y):
    return ui_common.safe_half_width(y)


# --- primitives -------------------------------------------------------------------

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
    out.paste(BASE + (255,), (0, 0, size[0], size[1]), face)
    return out, pad


def _inset_from_shape(shape, d):
    """Pressed-in well for an L mask `shape`: dark inner shadow from the top-left
    edge, light from the bottom-right. ImageChops.offset wraps around - fine,
    the padding around the shape is uniformly 'outside'."""
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


@functools.lru_cache(maxsize=1)
def _status_groove():
    groove = _inset_ring(126, 114)
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).pieslice([0, 0, W - 1, W - 1], 146, 214, fill=255)
    groove.putalpha(ImageChops.multiply(groove.getchannel("A"), mask))
    return groove


def _paste(img, sprite_pad, x, y):
    sprite, pad = sprite_pad
    img.paste(sprite, (int(round(x)) - pad, int(round(y)) - pad), sprite)


def _emboss(draw, xy, s, f, fill, anchor="mm", max_w=None):
    """Letterpress text: a light copy 1 px down-right under the real one."""
    ui_common.text(draw, (xy[0] + 1, xy[1] + 1), s, f, LIGHT, anchor=anchor, max_w=max_w)
    return ui_common.text(draw, xy, s, f, fill, anchor=anchor, max_w=max_w)


def _header(draw, title, scale):
    f, max_w = _nf(13, scale, 800), 2 * _half(HEADER_Y) - 16
    spaced = ui_common.letter_spaced(title.upper())
    _emboss(draw, (120, HEADER_Y), spaced if ui_common.text_len(spaced, f) <= max_w else title.upper(), f, TEXT,
            max_w=max_w)


def _tone_color(item):
    return {"accent": ACCENT, "muted": DIM, "danger": DANGER}[item.tone]


# --- views ------------------------------------------------------------------------

def draw_list(view, ctx):
    s = ctx.scale
    img = _bowl().copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    n = len(view.items)
    sel = max(0, min(view.sel, n - 1))
    for i, y, half, off in ui_common.list_rows(n, sel, 60 * s, center_y=124, min_half=56):
        item = view.items[i]
        if off == 0:
            h = round(54 * s)
            w = 2 * half - 28
            x0 = 120 - half + 14
            _paste(img, _raised(w, h, h // 2), x0, y - h / 2)
            well = round(40 * s)
            wx = x0 + 8
            _paste(img, _inset(well, well, well // 2), wx, y - well / 2)
            if item.cover is not None:
                d = round(34 * s)
                img.paste(ui_common.cover_image(item.cover, d), (int(wx + (well - d) / 2), int(y - d / 2)),
                          ui_common.circle_mask(d))
            else:
                ui_common.icon(ImageDraw.Draw(img), ui_common.icon_for(item, view.screen), wx + well / 2, y,
                               18 * s, _tone_color(item))
            draw = ImageDraw.Draw(img)
            tx = wx + well + 10
            max_w = x0 + w - 14 - tx
            if item.sub:
                ui_common.text(draw, (tx, y - 1), item.label, _nf(15, s, 800), TEXT, anchor="ls", max_w=max_w)
                ui_common.text(draw, (tx, y + 3), item.sub, _nf(11, s, 600), ACCENT, anchor="la", max_w=max_w)
            else:
                ui_common.text(draw, (tx, y), item.label, _nf(15, s, 800), TEXT, anchor="lm", max_w=max_w)
        elif y - 8 > HEADER_BOTTOM:
            ui_common.text(draw, (120, y), item.label, _nf(12, s, 700), DIM if abs(off) == 1 else FAINT,
                           anchor="mm", max_w=2 * half - 40)
    if n > 1:
        _paste(img, _inset(6, 70, 3, d=2), 214, 86)
        draw = ImageDraw.Draw(img)
        ky = 86 + (70 - 8) * sel / (n - 1)
        draw.ellipse([213, ky, 221, ky + 8], fill=ACCENT)
    return img


def _settings_value(img, row, x_right, y, s):
    draw = ImageDraw.Draw(img)
    if row.kind == "toggle":
        w, h = round(36 * s), round(20 * s)
        x = x_right - w
        _paste(img, _inset(w, h, h // 2, d=3), x, y - h / 2)
        k = h - 6
        kx = x + w - k - 3 if row.value else x + 3
        _paste(img, _raised(k, k, k // 2, d=3), kx, y - k / 2)
        if row.value:
            ImageDraw.Draw(img).ellipse([kx + 2, y - k / 2 + 2, kx + k - 2, y + k / 2 - 2], fill=ACCENT)
        return x
    if row.kind == "stepper":
        v = max(0, min(row.value, row.max))
        w, h = round(56 * s), 8
        x = x_right - w
        _paste(img, _inset(w, h, h // 2, d=2), x, y - h / 2)
        fw = w * v / max(1, row.max)
        draw = ImageDraw.Draw(img)
        if fw >= h:
            draw.rounded_rectangle([x, y - h / 2, x + fw, y + h / 2], radius=h // 2, fill=ACCENT)
        k = 12
        _paste(img, _raised(k, k, k // 2, d=3), x + fw - k / 2, y - k / 2)
        return x - 6
    w = ui_common.text(draw, (x_right, y), str(row.value), _nf(11, s, 700), ACCENT if row.on else DIM, anchor="rm",
                       max_w=90 * s)
    return x_right - w


def draw_settings(view, ctx):
    s = ctx.scale
    img = _bowl().copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    n = len(view.rows)
    sel = max(0, min(view.sel, n - 1))
    for i, y, half, off in ui_common.window_rows(n, sel, HEADER_BOTTOM + 4, 206, 34 * s):
        h = round(30 * s)
        row = view.rows[i]
        x0, x1 = 120 - half + 13, 120 + half - 13
        if off == 0:
            _paste(img, _raised(x1 - x0, h, h // 2), x0, y - h / 2)
        value_left = _settings_value(img, row, x1 - 12, y, s)
        draw = ImageDraw.Draw(img)
        ui_common.text(draw, (x0 + 12, y), row.label, _nf(12, s, 800 if off == 0 else 700),
                       TEXT if off == 0 else DIM, anchor="lm", max_w=max(20, value_left - x0 - 22))
    return img


def _mood_icon(draw, cx, cy, mood):
    if mood == "busy":
        a = ui_common.busy_phase(0.25, 8) * 45
        draw.arc([cx - 18, cy - 18, cx + 18, cy + 18], a, a + 90, fill=ACCENT, width=4)
    elif mood == "error":
        ui_common.text(draw, (cx, cy), "!", _nf(30, 1, 900), DANGER, anchor="mm")
    elif mood == "success":
        draw.line([(cx - 10, cy), (cx - 3, cy + 8), (cx + 11, cy - 8)], fill=ACCENT, width=4, joint="curve")
    else:
        ui_common.text(draw, (cx, cy), "i", _nf(30, 1, 900), DIM, anchor="mm")


def draw_message(view, ctx):
    s = ctx.scale
    img = _bowl().copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    if view.subtitle:
        ui_common.text(draw, (120, 52), view.subtitle, _nf(11, s, 700), DIM, anchor="mm", max_w=150)
    _paste(img, _raised(84, 84, 42), 78, 64)
    draw = ImageDraw.Draw(img)
    _mood_icon(draw, 120, 106, view.mood)
    _emboss(draw, (120, 164), view.text, _nf(14, s, 800), TEXT, max_w=170)
    f = _nf(11, s, 600)
    y = 180
    for ln in ui_common.wrap(view.detail or view.hint, f, 2 * _half(y + 16) - 24, 2):
        ui_common.text(draw, (120, y), ln, f, DIM, anchor="ma")
        y += f.size + 3
    if view.detail and view.hint:
        ui_common.text(draw, (120, y + 2), view.hint, _nf(10, s, 600), DIM, anchor="ma", max_w=2 * _half(y + 10) - 24)
    return img


def draw_playing(view, ctx):
    s = ctx.scale
    img = _bowl().copy()
    groove = _inset_ring(103, 89)
    img.paste(groove, (0, 0), groove)
    draw = ImageDraw.Draw(img)
    progress = max(0.0, min(1.0, view.position / view.duration)) if view.duration else 0.0
    if progress > 0:
        draw.arc([21, 21, 219, 219], -90, -90 + 360 * progress, fill=ACCENT, width=6)
    a = math.radians(-90 + 360 * progress)
    _paste(img, _raised(16, 16, 8, d=3), 120 + 96 * math.cos(a) - 8, 120 + 96 * math.sin(a) - 8)
    _paste(img, _raised(156, 156, 78), 42, 42)
    _paste(img, _inset(92, 92, 46), 74, 46)
    img.paste(ui_common.cover_image(view.cover, 84), (78, 50), ui_common.circle_mask(84))
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 150), view.title, _nf(13, s, 800), TEXT, anchor="mm", max_w=118)
    ui_common.text(draw, (120, 166), view.artist, _nf(10, s, 600), DIM, anchor="mm", max_w=104)
    if view.playing:
        _paste(img, _raised(24, 24, 12, d=3), 108, 172)
    else:
        _paste(img, _inset(24, 24, 12, d=3), 108, 172)
    draw = ImageDraw.Draw(img)
    ui_common.icon(draw, "pause" if view.playing else "play", 120, 184, 10, ACCENT)
    if view.shuffle:
        ui_common.icon(draw, "sync", 146, 184, 9, ACCENT)
    return img


def draw_code(view, ctx):
    s = ctx.scale
    img = _bowl().copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    ui_common.text(draw, (120, 70), "Gehe zu", _nf(11, s, 700), DIM, anchor="mm")
    ui_common.text(draw, (120, 88), view.url, _nf(12, s, 800), TEXT, anchor="mm", max_w=170)
    _paste(img, _inset(150, 44, 14), 45, 108)
    draw = ImageDraw.Draw(img)
    _emboss(draw, (120, 130), view.code, _nf(22, s, 900), ACCENT, max_w=140)
    ui_common.text(draw, (120, 172), "Warte auf Bestätigung …", _nf(10, s, 600), DIM, anchor="mm", max_w=150)
    return img


def draw_progress(view, ctx):
    s = ctx.scale
    img = _bowl().copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    _paste(img, _inset(150, 14, 7), 45, 112)
    frac = max(0.0, min(1.0, view.current / view.total)) if view.total else 0.0
    fw = 150 * frac
    draw = ImageDraw.Draw(img)
    if fw >= 14:
        draw.rounded_rectangle([45, 112, 45 + fw, 126], radius=7, fill=ACCENT)
    _paste(img, _raised(18, 18, 9, d=3), 45 + fw - 9, 110)
    draw = ImageDraw.Draw(img)
    _emboss(draw, (120, 148), f"{view.current}/{view.total}", _nf(22, s, 900), TEXT)
    if view.track:
        ui_common.text(draw, (120, 172), view.track, _nf(11, s, 600), DIM, anchor="mm", max_w=150)
    if view.done:
        ui_common.text(draw, (120, 190), "Fertig!", _nf(13, s, 800), ACCENT, anchor="mm")
    return img


def draw_password(view, ctx):
    s = ctx.scale
    img = _bowl().copy()
    draw = ImageDraw.Draw(img)
    _header(draw, view.title, s)
    ui_common.text(draw, (120, 52), view.ssid, _nf(11, s, 700), DIM, anchor="mm", max_w=150)
    _paste(img, _inset(160, 26, 13), 40, 62)
    f = _nf(14, s, 800)
    typed = view.typed
    if ui_common.text_len(typed, f) > 140:
        k = len(typed)
        while k > 1 and ui_common.text_len("…" + typed[-k:], f) > 140:
            k -= 1
        typed = "…" + typed[-k:]
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (52, 75), typed, f, TEXT, anchor="lm")
    _paste(img, _raised(52, 52, 14), 94, 100)
    draw = ImageDraw.Draw(img)
    n = len(view.charset)
    for k, x, font, color in ((-2, 36, _nf(11, s, 700), FAINT), (-1, 72, _nf(16, s, 700), DIM),
                              (1, 168, _nf(16, s, 700), DIM), (2, 204, _nf(11, s, 700), FAINT),
                              (0, 120, _nf(26, s, 900), ACCENT)):
        ch = view.charset[(view.char_idx + k) % n]
        ui_common.text(draw, (x, 126), "_" if ch == " " else ch, font, color, anchor="mm")
    f = _nf(9, s, 700)
    y = 168
    for ln in ui_common.wrap(view.hint, f, 150, 3):
        ui_common.text(draw, (120, y), ln, f, DIM, anchor="ma")
        y += f.size + 3
    return img


def draw_status(img, sv, ctx):
    groove = _status_groove()
    img.paste(groove, (0, 0), groove)
    ui_common.draw_ring_status(img, sv, {"track": None, "fill": ACCENT, "low": DANGER, "off": (200, 206, 216),
                                         "wifi": TEXT, "bt": ACCENT, "text": DIM, "accent": ACCENT,
                                         "font": _nf(10, 1, 800), "segments": 0})


def draw_quick_connect(img, qc, ctx):
    img.paste(Image.blend(img, Image.new("RGB", img.size, BASE), 0.6), (0, 0))
    _paste(img, _raised(150, 150, 75), 45, 45)
    ring = _inset_ring(66, 56)
    img.paste(ring, (0, 0), ring)
    draw = ImageDraw.Draw(img)
    color = DANGER if qc.error else ACCENT
    if qc.progress >= 1.0:
        draw.ellipse([56, 56, 184, 184], outline=color, width=6)
    elif qc.progress > 0:
        draw.arc([56, 56, 184, 184], -90, -90 + 360 * qc.progress, fill=color, width=6)
    _emboss(draw, (120, 120), qc.label, _nf(13, ctx.scale, 800), DANGER if qc.error else TEXT, max_w=96)


def draw_shutdown(ctx):
    img = _bowl().copy()
    _paste(img, _raised(110, 110, 55), 65, 65)
    draw = ImageDraw.Draw(img)
    _emboss(draw, (120, 120), "Gute Nacht", _nf(15, 1, 800), TEXT)
    return img
