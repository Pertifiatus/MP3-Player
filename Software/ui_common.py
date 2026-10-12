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
