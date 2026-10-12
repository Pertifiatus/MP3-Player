"""Y2K: bubblegum future, circa 2001 - an iridescent pastel holo background with
sparkles and soap bubbles, glossy "Aqua" candy pill buttons, chrome bubble
titles, XP-style pop-up windows, a barber-pole progress bar, and Now Playing as
a spinning CD whose rainbow sheen stays put while the disc turns under it.
Righteous (chrome titles) + Nunito (text).
"""
import functools
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import ui_common
from ui_common import W
from ui_views import fmt_time

HOLO = ((255, 196, 232), (182, 226, 255), (196, 255, 232), (220, 200, 255))  # TL, TR, BL, BR
HOT = (255, 46, 151)
PINK = (255, 120, 196)
AQUA = (0, 176, 255)
LILAC = (176, 150, 255)
INK = (52, 28, 110)
WHITE = (255, 255, 255)
SILVER = (206, 212, 228)
RED = (235, 40, 70)
GREEN = (52, 199, 89)
CHROME_STOPS = ((0.0, (255, 255, 255)), (0.45, (205, 215, 235)), (0.55, (104, 112, 150)), (1.0, (236, 240, 250)))

HEADER_Y = 38
HEADER_BOTTOM = 52


def _title_font(size, scale=1.0):
    return ui_common.font("Righteous-Regular.ttf", size * scale)


def _body(size, scale=1.0, weight=800):
    return ui_common.font("Nunito[wght].ttf", size * scale, weight=weight)


def _half(y):
    return ui_common.safe_half_width(y)


# --- primitives -------------------------------------------------------------------

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


def _base():
    img = _bg().copy()
    return img, ImageDraw.Draw(img)


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
    if w >= 16:
        sh = max(2, int(h * 0.42))
        band = Image.new("L", (w - 12, sh), 0)
        ImageDraw.Draw(band).rounded_rectangle([0, 0, w - 13, sh - 1], radius=sh // 2, fill=255)
        fade = Image.fromarray((np.linspace(200, 30, sh)[:, None] * np.ones((1, w - 12))).astype(np.uint8), "L")
        spec = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        spec.paste((255, 255, 255, 255), (6, 2, w - 6, 2 + sh), ImageChops.multiply(band, fade))
        body = Image.alpha_composite(body, spec)
    return body


def _paste(img, sprite, x, y):
    img.paste(sprite, (int(round(x)), int(round(y))), sprite)


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


def _chrome_fit(s, size, max_w):
    """Chrome title, shrinking (then truncating) until it fits max_w."""
    for k in (1.0, 0.88, 0.76, 0.66):
        im = _chrome(s, round(size * k, 1))
        if im.width - 8 <= max_w:
            return im
    small = round(size * 0.66, 1)
    return _chrome(ui_common.fit(s, _title_font(small), max_w), small)


def _header(img, draw, title, scale):
    im = _chrome_fit(title, 18 * scale, 2 * _half(HEADER_Y) - 24)
    _paste(img, im, 120 - im.width / 2, HEADER_Y - im.height / 2)
    for x in (120 - im.width / 2 - 6, 120 + im.width / 2 + 6):
        _sparkle(draw, x, HEADER_Y, 4, WHITE)


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
    _paste(img, bar, x0 + 2, y0 + 2)
    ui_common.text(d, (x0 + 12, y0 + 13), title, _body(11, scale), WHITE, anchor="lm", max_w=x1 - x0 - 44)
    d.rounded_rectangle([x1 - 22, y0 + 6, x1 - 8, y0 + 20], 3, fill=(232, 76, 58), outline=WHITE)
    d.line([(x1 - 18, y0 + 10), (x1 - 12, y0 + 16)], fill=WHITE, width=2)
    d.line([(x1 - 12, y0 + 10), (x1 - 18, y0 + 16)], fill=WHITE, width=2)
    return d


def _barber(img, box, frac, phase):
    """Aqua progress bar: glossy track, blue fill with diagonal stripes shifted by `phase` (0-1)."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    _paste(img, _gloss_pill(w, h, SILVER), x0, y0)
    fw = int(w * max(0.0, min(1.0, frac)))
    if fw < h:
        return
    fill = _gloss_pill(fw, h, AQUA).copy()
    stripes = Image.new("L", (fw, h), 0)
    sd = ImageDraw.Draw(stripes)
    off = int(phase * 2 * h)
    for x in range(-2 * h + off, fw + h, 2 * h):
        sd.polygon([(x, h), (x + h, h), (x + 2 * h, 0), (x + h, 0)], fill=70)
    fill.paste((255, 255, 255, 255), (0, 0, fw, h), ImageChops.multiply(stripes, fill.getchannel("A")))
    _paste(img, fill, x0, y0)


def _orb(img, x, y, d, item, screen, scale):
    """Glass bead holding the cover or the item's icon."""
    d = int(d)
    if item.cover is not None:
        cover = ui_common.cover_image(item.cover, d).convert("RGBA")
        img.paste(cover, (int(x), int(y)), ui_common.circle_mask(d))
    else:
        color = {"accent": AQUA, "muted": SILVER, "danger": RED}[item.tone]
        if item.kind in ("display", "led", "connectivity", "sync", "motion", "about"):
            color = LILAC
        _paste(img, _gloss_pill(d, d, color), x, y)
        ui_common.icon(ImageDraw.Draw(img), ui_common.icon_for(item, screen), x + d / 2, y + d / 2, d * 0.5, WHITE)
    ImageDraw.Draw(img).ellipse([x + d * 0.2, y + d * 0.12, x + d * 0.42, y + d * 0.3], fill=(255, 255, 255))


# --- views ------------------------------------------------------------------------

def draw_list(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(img, draw, view.title, s)
    n = len(view.items)
    sel = max(0, min(view.sel, n - 1))
    for i, y, half, off in ui_common.list_rows(n, sel, 56 * s, center_y=126, min_half=56):
        item = view.items[i]
        if off == 0:
            h = round(50 * s)
            w = 2 * half - 20
            x0 = 120 - w / 2
            _paste(img, _gloss_pill(w, h, RED if item.tone == "danger" else HOT), x0, y - h / 2)
            d = round(36 * s)
            _orb(img, x0 + 8, y - d / 2, d, item, view.screen, s)
            draw = ImageDraw.Draw(img)
            tx = x0 + 8 + d + 8
            max_w = x0 + w - 16 - tx
            if item.sub:
                ui_common.text(draw, (tx, y - 1), item.label, _body(15, s), WHITE, anchor="ls", max_w=max_w)
                ui_common.text(draw, (tx, y + 2), item.sub, _body(11, s, 700), (255, 230, 245), anchor="la", max_w=max_w)
            else:
                ui_common.text(draw, (tx, y), item.label, _body(15, s), WHITE, anchor="lm", max_w=max_w)
            _sparkle(draw, x0 + w - 14, y - h / 2 + 5, 6, WHITE)
        else:
            h = round(36 * s)
            if y - h / 2 < HEADER_BOTTOM:
                continue
            w = 2 * half - 28
            _paste(img, _gloss_pill(w, h, WHITE, 150), 120 - w / 2, y - h / 2)
            draw = ImageDraw.Draw(img)
            ui_common.text(draw, (120, y), item.label, _body(12, s), INK, anchor="mm", max_w=w - 24)
    return img


def _settings_value(img, row, x_right, y, selected, s):
    """Draws a settings value right-aligned at x_right; returns its left x."""
    draw = ImageDraw.Draw(img)
    if row.kind == "toggle":
        w, h = round(34 * s), round(18 * s)
        x = x_right - w
        _paste(img, _gloss_pill(w, h, HOT if row.value else SILVER), x, y - h / 2)
        k = h - 4
        kx = x + w - k - 2 if row.value else x + 2
        draw = ImageDraw.Draw(img)
        draw.ellipse([kx, y - k / 2, kx + k, y + k / 2], fill=WHITE, outline=(200, 200, 215))
        return x
    if row.kind == "stepper":
        v = max(0, min(row.value, row.max))
        r = 5
        x = x_right - row.max * (2 * r + 3) + 3
        for k in range(row.max):
            bx = x + k * (2 * r + 3)
            if k < v:
                _paste(img, _gloss_pill(2 * r, 2 * r, HOT), bx, y - r)
            else:
                ImageDraw.Draw(img).ellipse([bx, y - r, bx + 2 * r, y + r], fill=WHITE, outline=INK)
        return x
    color = WHITE if selected else (HOT if row.on else INK)
    w = ui_common.text(draw, (x_right, y), str(row.value), _body(11, s), color, anchor="rm", max_w=90 * s)
    return x_right - w


def draw_settings(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(img, draw, view.title, s)
    n = len(view.rows)
    sel = max(0, min(view.sel, n - 1))
    for i, y, half, off in ui_common.list_rows(n, sel, 34 * s, center_y=128, min_half=56):
        h = round(30 * s)
        if y - h / 2 < HEADER_BOTTOM:
            continue
        row = view.rows[i]
        selected = off == 0
        w = 2 * half - 24
        x0 = 120 - w / 2
        _paste(img, _gloss_pill(w, h, AQUA) if selected else _gloss_pill(w, h, WHITE, 150), x0, y - h / 2)
        value_left = _settings_value(img, row, x0 + w - 12, y, selected, s)
        draw = ImageDraw.Draw(img)
        ui_common.text(draw, (x0 + 12, y), row.label, _body(12, s), WHITE if selected else INK, anchor="lm",
                       max_w=max(20, value_left - x0 - 22))
    return img


def _mood_icon(draw, cx, cy, mood):
    if mood == "busy":
        active = ui_common.busy_phase(0.5, 8)
        for k in range(8):
            a = math.pi * 2 * k / 8
            x, y = cx + 9 * math.cos(a), cy + 9 * math.sin(a)
            draw.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=HOT if k == active else SILVER)
        return
    color = {"error": RED, "success": GREEN, "info": AQUA}[mood]
    draw.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=color)
    if mood == "error":
        draw.rectangle([cx - 1.5, cy - 8, cx + 1.5, cy + 3], fill=WHITE)
        draw.ellipse([cx - 2, cy + 5, cx + 2, cy + 9], fill=WHITE)
    elif mood == "success":
        draw.line([(cx - 6, cy), (cx - 2, cy + 5), (cx + 7, cy - 5)], fill=WHITE, width=3, joint="curve")
    else:
        draw.ellipse([cx - 2, cy - 9, cx + 2, cy - 5], fill=WHITE)
        draw.rectangle([cx - 1.5, cy - 2, cx + 1.5, cy + 8], fill=WHITE)


def draw_message(view, ctx):
    s = ctx.scale
    img, draw = _base()
    if view.subtitle:
        ui_common.text(draw, (120, 50), view.subtitle, _body(11, s), INK, anchor="mm", max_w=150)
    draw = _window(img, (32, 66, 208, 182), view.title, s)
    _mood_icon(draw, 56, 112, view.mood)
    ui_common.text(draw, (76, 104), view.text, _body(14, s), INK, anchor="lm", max_w=124)
    y = 122
    f = _body(11, s, 600)
    for ln in ui_common.wrap(view.detail, f, 128, 3):
        ui_common.text(draw, (76, y), ln, f, INK)
        y += f.size + 3
    if view.hint:
        ui_common.text(draw, (120, 196), view.hint, _body(10, s, 600), (120, 110, 150), anchor="mm", max_w=150)
    return img


def draw_playing(view, ctx):
    s = ctx.scale
    img, draw = _base()
    d = 124
    cx, cy = 120, 90
    disc = _cd(view.cover, d).rotate(-(view.position * 60) % 360, resample=Image.BICUBIC)
    _paste(img, disc, cx - d / 2, cy - d / 2)
    _paste(img, _sheen(d), cx - d / 2, cy - d / 2)
    draw = ImageDraw.Draw(img)
    rng = random.Random(7)
    for k in range(5):
        a = rng.uniform(0, 2 * math.pi)
        r = 70 + rng.uniform(0, 8)
        _sparkle(draw, cx + r * math.cos(a), cy + r * math.sin(a) * 0.9,
                 3 + 2 * abs(math.sin(view.position * 2 + k)), WHITE)
    title = _chrome_fit(view.title, 17 * s, 2 * _half(168) - 20)
    _paste(img, title, 120 - title.width / 2, 166 - title.height / 2)
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 187), view.artist, _body(11, s, 700), INK, anchor="mm", max_w=150)
    pill = _gloss_pill(96, 20, AQUA)
    _paste(img, pill, 72, 196)
    draw = ImageDraw.Draw(img)
    ui_common.icon(draw, "pause" if view.playing else "play", 90, 206, 10, WHITE)
    ui_common.text(draw, (126, 206), fmt_time(view.position), _body(10, s), WHITE, anchor="mm")
    if view.shuffle:
        _sparkle(draw, 176, 206, 5, HOT)
    return img


def draw_code(view, ctx):
    s = ctx.scale
    img, draw = _base()
    draw = _window(img, (30, 56, 210, 192), view.title, s)
    ui_common.text(draw, (120, 92), "Gehe zu", _body(11, s, 700), INK, anchor="mm")
    ui_common.text(draw, (120, 108), view.url, _body(12, s), AQUA, anchor="mm", max_w=170)
    ui_common.text(draw, (120, 128), "Code:", _body(11, s, 700), INK, anchor="mm")
    draw.rectangle([54, 138, 186, 168], fill=WHITE, outline=INK)
    code = _chrome_fit(view.code, 20 * s, 124)
    _paste(img, code, 120 - code.width / 2, 153 - code.height / 2)
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 180), "Warte auf Bestätigung …", _body(10, s, 600), INK, anchor="mm", max_w=150)
    return img


def draw_progress(view, ctx):
    s = ctx.scale
    img, draw = _base()
    if view.done:
        done = _chrome_fit("Fertig!", 18, 120)
        _paste(img, done, 120 - done.width / 2, 44 - done.height / 2)
        draw = ImageDraw.Draw(img)
        _sparkle(draw, 120 - done.width / 2 - 8, 44, 5, HOT)
        _sparkle(draw, 120 + done.width / 2 + 8, 44, 5, AQUA)
    draw = _window(img, (30, 62, 210, 186), view.title, s)
    frac = view.current / view.total if view.total else 0.0
    _barber(img, (46, 108, 194, 124), frac, ui_common.busy_phase(0.5, 8) / 8)
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 144), f"{view.current} / {view.total}", _body(15, s), INK, anchor="mm")
    if view.track:
        ui_common.text(draw, (120, 166), view.track, _body(11, s, 600), INK, anchor="mm", max_w=160)
    return img


def draw_password(view, ctx):
    s = ctx.scale
    img, draw = _base()
    _header(img, draw, view.title, s)
    ui_common.text(draw, (120, 58), view.ssid, _body(11, s, 700), INK, anchor="mm", max_w=150)
    draw.rounded_rectangle([40, 68, 200, 92], 8, fill=WHITE, outline=INK)
    f = _body(14, s)
    typed = view.typed
    if ui_common.text_len(typed, f) > 148:
        k = len(typed)
        while k > 1 and ui_common.text_len("…" + typed[-k:], f) > 148:
            k -= 1
        typed = "…" + typed[-k:]
    ui_common.text(draw, (48, 80), typed, f, INK, anchor="lm")
    n = len(view.charset)
    for k, x, size, color, font_size in ((-2, 32, 24, (255, 255, 255), 11), (-1, 70, 34, (255, 255, 255), 16),
                                         (1, 170, 34, (255, 255, 255), 16), (2, 208, 24, (255, 255, 255), 11)):
        ch = view.charset[(view.char_idx + k) % n]
        _paste(img, _gloss_pill(size, size, color, 110 if abs(k) == 2 else 150), x - size / 2, 128 - size / 2)
        ui_common.text(ImageDraw.Draw(img), (x, 128), "_" if ch == " " else ch, _body(font_size, s), INK, anchor="mm")
    _paste(img, _gloss_pill(52, 52, HOT), 94, 102)
    ch = view.charset[view.char_idx]
    draw = ImageDraw.Draw(img)
    ui_common.text(draw, (120, 128), "_" if ch == " " else ch, _title_font(28, s), WHITE, anchor="mm")
    fh = _body(9, s, 700)
    y = 166
    for ln in ui_common.wrap(view.hint, fh, 150, 3):
        ui_common.text(draw, (120, y), ln, fh, INK, anchor="ma")
        y += fh.size + 3
    return img


def draw_status(img, sv, ctx):
    ui_common.draw_ring_status(img, sv, {"track": (236, 220, 248), "fill": HOT, "low": RED, "off": (205, 205, 215),
                                         "wifi": AQUA, "bt": LILAC, "text": INK, "accent": AQUA,
                                         "font": _body(10), "segments": 0, "dot": "circle"})


def draw_quick_connect(img, qc, ctx):
    img.paste(Image.blend(img, Image.new("RGB", img.size, WHITE), 0.82), (0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([58, 104, 182, 136], 16, fill=WHITE, outline=SILVER)
    for k in range(12):
        a = -math.pi / 2 + 2 * math.pi * k / 12
        x, y = 120 + 70 * math.cos(a), 120 + 70 * math.sin(a)
        lit = k / 12 < qc.progress
        _sparkle(draw, x, y, 7 if lit else 4, (RED if qc.error else HOT) if lit else SILVER)
    if qc.error:
        ui_common.text(draw, (120, 120), qc.label, _body(14, ctx.scale), RED, anchor="mm", max_w=110)
    else:
        label = _chrome_fit(qc.label, 16 * ctx.scale, 110)
        _paste(img, label, 120 - label.width / 2, 120 - label.height / 2)


def draw_shutdown(ctx):
    img, draw = _base()
    bye = _chrome_fit("Bye bye!", 24, 170)
    _paste(img, bye, 120 - bye.width / 2, 106 - bye.height / 2)
    draw = ImageDraw.Draw(img)
    for x, y, r in ((62, 92, 6), (178, 88, 5), (150, 140, 4)):
        _sparkle(draw, x, y, r, WHITE)
    ui_common.text(draw, (120, 140), "bis bald", _body(12), INK, anchor="mm")
    return img
