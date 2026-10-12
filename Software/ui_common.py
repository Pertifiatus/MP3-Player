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


W = 240


# --- round-display safety -----------------------------------------------------
# The GC9A01 panel is physically circular even though the framebuffer is a square
# 240x240 - content placed via naive rectangular layout gets clipped by the bezel
# near the top/bottom/corners. SAFE_R is a little under W/2 as a small margin.
# This is a hardware constant - it does NOT scale with ui_scale.
SAFE_R = 104


def safe_half_width(y, r=SAFE_R, cy=W / 2):
    dy = abs(y - cy)
    if dy >= r:
        return 0.0
    return (r * r - dy * dy) ** 0.5


# --- text -----------------------------------------------------------------------


def text_centered(draw, x_center, y, s, font, fill):
    bbox = draw.textbbox((0, 0), s, font=font)
    w = bbox[2] - bbox[0]
    draw.text((x_center - w / 2, y), s, font=font, fill=fill)


def text_centered_fit(draw, x_center, y, s, fonts, fill, max_width):
    """Like text_centered, but steps down through `fonts` (largest first) to the
    first one that fits max_width, truncating with the smallest as a last resort -
    used for server-provided strings (e.g. a device-flow URL) that shouldn't
    overflow their card just because a real value came in longer than the ones
    this layout was eyeballed against."""
    for font in fonts:
        if draw.textbbox((0, 0), s, font=font)[2] <= max_width:
            text_centered(draw, x_center, y, s, font, fill)
            return
    smallest = fonts[-1]
    text_centered(draw, x_center, y, truncate(draw, s, smallest, max_width), smallest, fill)


def letter_spaced(s):
    return " ".join(list(s))


def truncate(draw, text, font, max_width):
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), text + "…", font=font)[2] > max_width:
        text = text[:-1]
    return text + "…" if text else "…"


def wrap_text(draw, text, x_center, y, font, fill, max_width, line_height=16):
    words = text.split(" ")
    line = ""
    lines = []
    for word in words:
        test = (line + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    for i, l in enumerate(lines):
        text_centered(draw, x_center, y + i * line_height, l, font, fill)


# --- color / geometry -------------------------------------------------------------


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shade(rgb, pct):
    return tuple(max(0, min(255, c + round(255 * pct / 100))) for c in rgb)


def rotated_rect_points(cx, cy, w, h, angle_deg):
    angle = math.radians(angle_deg)
    hw, hh = w / 2, h / 2
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    pts = []
    for x, y in corners:
        rx = x * math.cos(angle) - y * math.sin(angle)
        ry = x * math.sin(angle) + y * math.cos(angle)
        pts.append((cx + rx, cy + ry))
    return pts


def format_eta(minutes):
    total_min = max(0, round(minutes))
    if total_min >= 60:
        return f"{total_min // 60}h{total_min % 60:02d}"
    return f"{total_min}min"


# --- status ring (battery + WLAN/BT) -----------------------------------------
# Fixed hardware-margin element, like SAFE_R - does NOT scale with ui_scale.
# Concentric with the screen (not edge-pinned - see reverted commit 96998b6),
# but pushed out so RING_R sits exactly ON the physical bezel radius (120):
# the outer half of the 12px-wide band (r=120 to r=126) falls beyond the
# visible round glass and is physically covered by the bezel, while the inner
# half (r=114 to r=120) stays visible and well clear of SAFE_R (104) - so the
# band itself reads as "cut in half by the edge" without needing to move its
# center off-screen. RING_ANCHOR_DEG is the 0%-charge/text-anchor end (top),
# RING_FAR_DEG the 100%-charge end (bottom); which one is numerically larger
# doesn't matter - ring_arc sorts its two angle args itself. Re-centered
# exactly on 180deg/9-o'clock, so the screen's own horizontal midline bisects
# it into two equal halves top/bottom too. See
# docs/superpowers/specs/2026-09-16-status-ring-design.md for the original
# (smaller-radius) layout this evolved from.
RING_R = 120
RING_WIDTH = 12
RING_ANCHOR_DEG = 210  # top-left, 30deg above 9-o'clock - 0% / text anchor
RING_FAR_DEG = 150     # bottom-left, 30deg below 9-o'clock - 100% end
WIFI_DOT_DEG = 142     # continuing past RING_FAR_DEG in the same direction
BT_DOT_DEG = 134
DOT_R = 6


def ring_point(deg, r=RING_R):
    rad = math.radians(deg)
    return (W / 2 + r * math.cos(rad), W / 2 + r * math.sin(rad))


def lightning_bolt(draw, cx, cy, size, color):
    """Small zigzag bolt polygon, `size` = total height. Drawn as a plain
    filled polygon (not a font glyph) - this project already avoids relying
    on Unicode symbols for icons since several are missing from DejaVu, the
    only font confirmed present on-device (see NOTES_FOR_PER.md)."""
    s = size / 14.0
    pts = [(1, -7), (-4, 1), (-1, 1), (-2, 7), (4, -1), (1, -1)]
    draw.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=color)


def ring_arc(img, start_deg, end_deg, color, r=RING_R, width=RING_WIDTH):
    """A filled annular sector (donut slice) from start_deg to end_deg at the
    ring's radius/width, via two masked pieslices (outer wedge minus inner
    wedge) - NOT draw.arc(..., width=RING_WIDTH). Confirmed live on hardware:
    PIL's thick-arc rendering visibly kinks/seams partway through a 12px-wide
    arc at this radius (it rasterizes a thick arc as several slightly-offset
    thin arcs, which don't perfectly overlap). A pieslice difference is a
    single filled polygon - mathematically exact, no seam possible."""
    lo, hi = sorted((start_deg, end_deg))
    outer_r = r + width / 2
    inner_r = r - width / 2
    mask = Image.new("L", img.size, 0)
    mdraw = ImageDraw.Draw(mask)
    outer_box = [W / 2 - outer_r, W / 2 - outer_r, W / 2 + outer_r, W / 2 + outer_r]
    inner_box = [W / 2 - inner_r, W / 2 - inner_r, W / 2 + inner_r, W / 2 + inner_r]
    mdraw.pieslice(outer_box, lo, hi, fill=255)
    mdraw.pieslice(inner_box, lo, hi, fill=0)
    img.paste(Image.new("RGB", img.size, color), (0, 0), mask)


def shuffle_icon(draw, cx, cy, size, color):
    """Two crossing arrows - the standard shuffle pictogram, drawn as plain
    lines/polygons rather than a font glyph (same reasoning as this project's
    other custom icons: several Unicode symbols are missing from DejaVu, the
    only font confirmed present on-device, see NOTES_FOR_PER.md). `size` is
    the icon's approximate width; centered on (cx, cy)."""
    s = size / 16.0
    lw = max(1, round(1.5 * s))
    draw.line([(cx - 8 * s, cy - 3 * s), (cx + 6 * s, cy + 3 * s)], fill=color, width=lw)
    draw.polygon([(cx + 8 * s, cy + 3 * s), (cx + 2 * s, cy + 1 * s), (cx + 4 * s, cy + 6 * s)], fill=color)
    draw.line([(cx - 8 * s, cy + 3 * s), (cx + 6 * s, cy - 3 * s)], fill=color, width=lw)
    draw.polygon([(cx + 8 * s, cy - 3 * s), (cx + 2 * s, cy - 1 * s), (cx + 4 * s, cy - 6 * s)], fill=color)


# --- procedural cover art (ported from beispiel.html coverArtURI) -----------

_cover_cache = {}


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


def cover_art(seed, color_a_hex, color_b_hex, size=210):
    cache_key = (seed, color_a_hex, color_b_hex, size)
    if cache_key in _cover_cache:
        return _cover_cache[cache_key]

    rng = random.Random(seed)
    color_a = hex_to_rgb(color_a_hex)
    color_b = shade(hex_to_rgb(color_b_hex), -20)

    # vectorized diagonal gradient (numpy) instead of a pure-Python per-pixel loop -
    # the latter took seconds per cover on a CM4 (up to size*size Python iterations),
    # which was the main cause of the multi-second input lag on real hardware.
    t = (np.add.outer(np.arange(size), np.arange(size)) / (2 * size))[..., None]
    ca = np.array(color_a, dtype=np.float32)
    cb = np.array(color_b, dtype=np.float32)
    grad = np.round(ca + (cb - ca) * t).astype(np.uint8)
    img = Image.fromarray(grad, "RGB")

    blob_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(blob_layer)
    n_blobs = 2 + rng.randint(0, 1)
    for i in range(n_blobs):
        cx = rng.uniform(size * 0.12, size * 0.88)
        cy = rng.uniform(size * 0.12, size * 0.88)
        r = rng.uniform(size * 0.22, size * 0.32)
        color = color_b if i % 2 == 0 else color_a
        alpha = round(255 * rng.uniform(0.38, 0.66))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))
    blob_layer = blob_layer.filter(ImageFilter.GaussianBlur(size * 0.11))

    img = Image.alpha_composite(img.convert("RGBA"), blob_layer).convert("RGB")
    overlay = Image.new("RGB", (size, size), (0, 0, 0))
    img = Image.blend(img, overlay, 0.10)

    _cover_cache[cache_key] = img
    return img


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


@functools.lru_cache(maxsize=8192)
def text_len(s, f):
    """Cached advance width. Measuring is surprisingly slow for the heavily
    hinted bundled fonts (ShareTechMono, Rajdhani: ~0.4 ms per call, measured),
    and menus measure the same strings every frame."""
    return f.getlength(s)


@functools.lru_cache(maxsize=4096)
def fit(text, f, max_w):
    """glyph_safe `text`, cut with an ellipsis so it is at most max_w px wide."""
    s = glyph_safe(text, f)
    if text_len(s, f) <= max_w:
        return s
    ell = glyph_safe("…", f)
    lo, hi = 0, len(s)  # binary search: longest prefix that fits with the ellipsis
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_len(s[:mid].rstrip() + ell, f) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return (s[:lo].rstrip() + ell) if lo else ell


@functools.lru_cache(maxsize=1024)
def _text_mask(s, f, anchor, mode):
    """Rendered text as an L mask + its offset from the anchor point. Cached for
    the same reason as text_len: rendering one line costs up to ~1.7 ms with the
    hinted fonts, and most strings repeat from frame to frame."""
    x0, y0, x1, y1 = f.getbbox(s, anchor=anchor)
    m = Image.new("L", (max(1, x1 - x0), max(1, y1 - y0)), 0)
    d = ImageDraw.Draw(m)
    d.fontmode = mode
    d.text((-x0, -y0), s, font=f, fill=255, anchor=anchor)
    return m, x0, y0


def text(draw, xy, s, f, fill, anchor="la", max_w=None):
    """draw.text with glyph fallback (+ ellipsis fit if max_w), via the cached
    mask above. Respects draw.fontmode ("1" = no antialiasing). Returns the
    drawn width."""
    s = fit(s, f, max_w) if max_w is not None else glyph_safe(s, f)
    if s:
        m, ox, oy = _text_mask(s, f, anchor, draw.fontmode)
        draw.bitmap((round(xy[0] + ox), round(xy[1] + oy)), m, fill=fill)
    return text_len(s, f)


def wrap(text_, f, max_w, max_lines=None):
    """Word-wrapped lines (glyph-safe), each <= max_w; the last kept line gets an
    ellipsis when max_lines cuts the rest off."""
    words, lines, line = glyph_safe(text_, f).split(), [], ""
    for word in words:
        test = (line + " " + word).strip()
        if text_len(test, f) > max_w and line:
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
        pts = [p((8 if k % 2 == 0 else 5.8) * math.cos(math.pi * k / 8),
                 (8 if k % 2 == 0 else 5.8) * math.sin(math.pi * k / 8)) for k in range(16)]
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
            draw.line([p(5.5 * math.cos(a), 5.5 * math.sin(a)), p(8 * math.cos(a), 8 * math.sin(a))],
                      fill=color, width=lw)
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
      track (None = no track), low (<= 20 %), bolt, segments (0 = continuous
      with round caps), dot ("circle" | "square" | "diamond")."""
    draw = ImageDraw.Draw(img)
    seg = st.get("segments", 0)
    if st.get("track") is not None:
        _ring_band(img, RING_FAR_DEG, RING_ANCHOR_DEG, st["track"], seg)
    if sv.battery_pct is not None:
        pct = max(0, min(100, round(sv.battery_pct)))
        if pct > 0:
            bound = RING_FAR_DEG + (RING_ANCHOR_DEG - RING_FAR_DEG) * pct / 100
            _ring_band(img, RING_FAR_DEG, bound, st.get("low", st["fill"]) if pct <= 20 else st["fill"], seg)
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
    text(draw, (x_center, y), s, f, fill, anchor="ma")


def _ring_band(img, a, b, color, segments):
    lo, hi = sorted((a, b))
    img.paste(color, (0, 0, W, W), _band_mask(round(lo, 2), round(hi, 2), segments))


@functools.lru_cache(maxsize=256)
def _band_mask(lo, hi, segments):
    """L mask of one ring band from lo to hi degrees: continuous with round caps,
    or `segments` separated ticks. Cached and pasted once - drawing ~30
    pieslices with a full-frame paste each per frame was the single biggest
    render cost of a segmented ring (measured)."""
    m = Image.new("L", (W, W), 0)
    d = ImageDraw.Draw(m)
    outer = RING_R + RING_WIDTH / 2
    box = [W / 2 - outer, W / 2 - outer, W / 2 + outer, W / 2 + outer]
    if not segments:
        d.pieslice(box, lo, hi, fill=255)
    else:
        span = (RING_ANCHOR_DEG - RING_FAR_DEG) / segments
        for k in range(segments):
            s0 = max(lo, RING_FAR_DEG + k * span + 1.2)
            s1 = min(hi, RING_FAR_DEG + (k + 1) * span - 1.2)
            if s1 > s0:
                d.pieslice(box, s0, s1, fill=255)
    inner = RING_R - RING_WIDTH / 2
    d.ellipse([W / 2 - inner, W / 2 - inner, W / 2 + inner, W / 2 + inner], fill=0)
    if not segments:
        cap = RING_WIDTH / 2
        for deg in (lo, hi):
            x, y = ring_point(deg)
            d.ellipse([x - cap, y - cap, x + cap, y + cap], fill=255)
    return m


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
