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


# --- palette (iOS dark-mode system colors) ------------------------------------
BG = (0, 0, 0)
GROUP_BG = (28, 28, 30)        # systemGray6 dark - card/group background
ROW_SELECTED = (46, 46, 50)    # focus highlight fill
SEPARATOR = (56, 56, 58)
TEXT = (255, 255, 255)
DIM = (142, 142, 147)          # systemGray
ACCENT = (49, 209, 166)
CARD_BG = (44, 44, 46)         # fallback icon badge background
DANGER = (255, 69, 58)

CATEGORY_COLORS = {
    "display": (255, 159, 10),       # orange
    "led": (255, 204, 0),            # yellow
    "connectivity": (10, 132, 255),  # blue
    "sync": (49, 209, 166),          # accent teal
    "motion": (255, 69, 58),         # red
    "about": (99, 99, 102),          # gray
}


# --- scale-aware fonts ---------------------------------------------------------
# Base point sizes as tuned at ui_scale=3 (scale factor 1.0, see UI_SCALE_STEPS).
# Loaded lazily per (key, scale) instead of once at import time, since the point
# size now depends on the user's chosen density.
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
FONT_FILES = {
    "title_l": (FONT_DIR + "DejaVuSans-Bold.ttf", 22),
    "title_s": (FONT_DIR + "DejaVuSans-Bold.ttf", 16),
    "sub_l": (FONT_DIR + "DejaVuSans.ttf", 14),
    "sub_s": (FONT_DIR + "DejaVuSans.ttf", 12),
    "header": (FONT_DIR + "DejaVuSans-Bold.ttf", 13),
    "ring_pct": (FONT_DIR + "DejaVuSans-Bold.ttf", 11),
    "icon_l": (FONT_DIR + "DejaVuSans-Bold.ttf", 30),
    "icon_s": (FONT_DIR + "DejaVuSans-Bold.ttf", 22),
    "label_title": (FONT_DIR + "DejaVuSans-Bold.ttf", 13),
    "label_artist": (FONT_DIR + "DejaVuSans.ttf", 10),
    "disc_title": (FONT_DIR + "DejaVuSans-Bold.ttf", 18),
    "disc_artist": (FONT_DIR + "DejaVuSans.ttf", 14),
    "mono": (FONT_DIR + "DejaVuSansMono-Bold.ttf", 20),
    "control": (FONT_DIR + "DejaVuSans-Bold.ttf", 15),
}


@functools.lru_cache(maxsize=None)
def _font(key, scale):
    path, base_size = FONT_FILES[key]
    size = max(8, round(base_size * scale))
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        # Only hit off-device (no DejaVu fonts installed) - keeps this module
        # importable/renderable for local smoke tests, see test_ui_render.py.
        return ImageFont.load_default()


# Lowest y a grouped settings card is allowed to reach - past this the round
# bezel narrows the card below a usable width. Derived from SAFE_R so it stays
# consistent with the hardware constant above instead of being a second magic
# number that could drift out of sync with it.
_MIN_CARD_HALF_W = 50
CARD_MAX_Y = W / 2 + (SAFE_R ** 2 - _MIN_CARD_HALF_W ** 2) ** 0.5


RING_TRACK = (58, 58, 60)
RING_OFF = (72, 72, 76)  # matches _draw_toggle_pill's "off" fill
CHARGE_GREEN = (48, 209, 88)


def _draw_status_dot(draw, deg, color, on, connected):
    x, y = _ring_point(deg)
    box = [x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R]
    # "off" must win immediately even if `connected` is a stale background-polled
    # True (StatusWorker only refreshes every ~10s) - otherwise flipping the
    # radio off in Settings can leave the dot looking "connected" for up to 10s.
    if not on:
        draw.ellipse(box, fill=RING_OFF)
    elif connected:
        draw.ellipse(box, fill=color)
    else:
        draw.ellipse(box, outline=color, width=2)


def _header(draw, y, text, font, fill):
    """Letter-spaced section header, truncated to whatever actually fits inside
    the round bezel at this y."""
    spaced = _letter_spaced(text)
    max_w = max(20, 2 * _safe_half_width(y) - 16)
    spaced = _truncate(draw, spaced, font, max_w)
    _text_centered(draw, W / 2, y, spaced, font, fill)


def _frosted_pill(img, box, radius, blur_radius=10, darken=0.5):
    """Crop the region behind `box`, blur + darken it, paste back with a rounded
    mask - a cheap approximation of iOS's frosted-glass (backdrop-filter:blur)
    material, used behind the Now-Playing controls."""
    x0, y0, x1, y1 = [int(v) for v in box]
    region = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(blur_radius))
    dark = Image.new("RGB", region.size, (0, 0, 0))
    region = Image.blend(region, dark, darken)
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, region.size[0], region.size[1]], radius=radius, fill=255)
    img.paste(region, (x0, y0), mask)


# --- home: "Quick Connect" (hold Play/Pause) overlay --------------------------
QC_RING_R = 70
QC_RING_STROKE = 10
QC_RING_TRACK = (72, 72, 74)
QC_ERROR_COLOR = (255, 69, 58)


# --- home / library / playlist: shared nav-list style -------------------------

def _render_nav_list(img, draw, entries, selected_idx, scale):
    """entries: list of dicts with keys label, sub, icon (or cover_img), color_rgb.
    Row spacing/positions and the icon/text split are all derived per-row from
    _safe_half_width() so nothing gets clipped by the round bezel, however far a
    row sits from vertical center. `scale` shrinks/grows row height, icon size,
    fonts and margins together - a smaller scale means smaller rows, which means
    more of them fit inside the same physical safe circle."""
    row_h = round(66 * scale)
    center_y = W / 2
    icon_pad = max(4, round(10 * scale))   # icon inset from the row's safe edge
    text_gap = max(3, round(8 * scale))    # gap between icon and text block
    text_pad = max(4, round(10 * scale))   # text inset from the row's safe edge
    min_half_w = max(16, round(28 * scale))
    min_text_w = max(10, round(20 * scale))
    line_gap = max(1, round(3 * scale))

    f_icon_l, f_icon_s = _font("icon_l", scale), _font("icon_s", scale)
    f_title_l, f_title_s = _font("title_l", scale), _font("title_s", scale)
    f_sub_l, f_sub_s = _font("sub_l", scale), _font("sub_s", scale)

    for i, entry in enumerate(entries):
        selected = i == selected_idx
        y = center_y + (i - selected_idx) * row_h
        half_w = _safe_half_width(y)
        if half_w < min_half_w:
            continue  # this row's vertical position is essentially off the round panel

        icon_size = round((56 if selected else 42) * scale)
        icon_font = f_icon_l if selected else f_icon_s
        title_font = f_title_l if selected else f_title_s
        sub_font = f_sub_l if selected else f_sub_s
        title_color = TEXT if selected else DIM
        sub_color = ACCENT if selected else DIM
        radius = round(icon_size * 0.28)

        safe_left = W / 2 - half_w + icon_pad
        safe_right = W / 2 + half_w - text_pad
        icon_x = safe_left
        icon_y = y - icon_size / 2
        if entry.get("cover_img") is not None:
            cover = entry["cover_img"].resize((icon_size, icon_size))
            mask = Image.new("L", (icon_size, icon_size), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, icon_size, icon_size], radius=radius, fill=255)
            img.paste(cover, (int(icon_x), int(icon_y)), mask)
        else:
            color = entry.get("color_rgb", CARD_BG)
            draw.rounded_rectangle([icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
                                    radius=radius, fill=color)
            _text_centered(draw, icon_x + icon_size / 2, y - icon_font.size / 2 - 1, entry["icon"], icon_font,
                            (255, 255, 255))

        tx = icon_x + icon_size + text_gap
        max_w = safe_right - tx
        if max_w < min_text_w:
            continue  # no room left for text at this row's extreme y - icon-only

        title_h, sub_h = title_font.size, sub_font.size
        title_y = y - (title_h + line_gap + sub_h) / 2
        sub_y = title_y + title_h + line_gap
        draw.text((tx, title_y), _truncate(draw, entry["label"], title_font, max_w), font=title_font, fill=title_color)
        draw.text((tx, sub_y), _truncate(draw, entry["sub"], sub_font, max_w), font=sub_font, fill=sub_color)


# _render_nav_list only ever draws rows that land within the round bezel
# (~3-5 depending on ui_scale, see its own half_w cutoff) - but render_library/
# render_playlist used to build (and generate cover art for) an entry for
# EVERY item in the list, real or procedural. Cover art is the expensive part
# (JPEG decode+resize from disk for a real synced cover, PIL gradient
# compositing for a procedural one) - confirmed live as the lag source on a
# 60-track playlist, since ~55 of those covers never even get drawn. This
# bounds the built window to a fixed size around the selection regardless of
# list length; generous vs. what's actually visible so it covers every
# UI_SCALE_STEPS density without having to compute the exact visible count.
NAV_LIST_WINDOW = 3


def _windowed_range(n, selected_idx):
    lo = max(0, selected_idx - NAV_LIST_WINDOW)
    hi = min(n, selected_idx + NAV_LIST_WINDOW + 1)
    return lo, hi


def _draw_circular_text(img, text, cx, cy, radius, font, fill, stroke_fill=(0, 0, 0, 220), stroke_width=1):
    """Draws `text` along a circular arc of `radius` around (cx, cy), one glyph
    at a time, each rotated to stay tangent to the circle - like a title
    silkscreened onto a vinyl record. Drawn directly onto `img` (must be RGBA)
    before it gets rotated as a whole, so the text spins together with it -
    matching a real record, whose label text is only briefly readable as it
    spins past. Centered on the top of the circle (12 o'clock).

    A dark stroke is essential, not cosmetic - real cover art is unpredictable,
    and plain white text disappears completely over light/white regions of it
    (confirmed on a real cover: readable everywhere else, invisible over its
    white background)."""
    if not text:
        return
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [measure.textlength(ch, font=font) for ch in text]
    total_angle = sum(w / radius for w in widths)
    angle = -math.pi / 2 - total_angle / 2  # start left-of-top, ends centered at top
    for ch, w in zip(text, widths):
        char_angle = w / radius
        mid_angle = angle + char_angle / 2
        x = cx + radius * math.cos(mid_angle)
        y = cy + radius * math.sin(mid_angle)
        pad = 4 + stroke_width
        char_img = Image.new("RGBA", (int(w) + pad * 2, font.size + pad * 2), (0, 0, 0, 0))
        ImageDraw.Draw(char_img).text((pad, pad), ch, font=font, fill=fill,
                                       stroke_width=stroke_width, stroke_fill=stroke_fill)
        rotated = char_img.rotate(-math.degrees(mid_angle) - 90, expand=True, resample=Image.BICUBIC)
        img.paste(rotated, (round(x - rotated.width / 2), round(y - rotated.height / 2)), rotated)
        angle += char_angle


def _compose_disc(art_img, size, title, title_font, artist, artist_font):
    """Cover art masked into a circle, with concentric groove rings, the track
    title + artist curved around two outer bands, and a label hole (the label
    itself is drawn separately on top so it can stay upright while the disc
    spins)."""
    disc = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    disc.paste(art_img, (0, 0), mask)

    draw = ImageDraw.Draw(disc)
    center = size / 2
    for r in range(int(size * 0.18), int(size * 0.49), 4):
        draw.ellipse([center - r, center - r, center + r, center + r], outline=(0, 0, 0, 60), width=1)

    _draw_circular_text(disc, title, center, center, size * 0.4, title_font, (255, 255, 255, 235))
    _draw_circular_text(disc, artist, center, center, size * 0.32, artist_font, (255, 255, 255, 235))
    return disc


def _caret(draw, x_center, y, up):
    w, h = 7, 4
    pts = [(x_center - w, y + (0 if up else h)), (x_center + w, y + (0 if up else h)), (x_center, y + (h if up else 0))]
    draw.polygon(pts, fill=DIM)


def _draw_toggle_pill(draw, x, y, on, w=34, h=18):
    bg = ACCENT if on else (72, 72, 76)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=bg)
    knob_x = x + w - h + 2 if on else x + 2
    draw.ellipse([knob_x, y + 2, knob_x + h - 4, y + h - 2], fill=(255, 255, 255))


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


# --- settings: category detail - iOS "inset grouped" list ---------------------

def draw_settings(view, ctx):
    scale = ctx.scale
    rows = view.rows

    header_y = 32
    f_header = _font("header", scale)
    img, draw = _base()
    _header(draw, header_y, view.title.upper(), f_header, DIM)

    row_h = round(38 * scale)
    # derived from the header's own height (not a flat constant) so the list -
    # and the scroll caret above it, see below - never collides with the
    # header even as its font grows with scale
    top = header_y + f_header.size + round(10 * scale)
    card_radius = round(16 * scale)
    card_pad = max(3, round(5 * scale))

    # A category's items don't all fit on screen at every scale (bigger rows at
    # higher ui_scale, or just a long category) - window/scroll the list around
    # the current selection instead of drawing every item and running off the
    # bottom of the round panel, same idea as _render_nav_list's centering.
    avail_h = CARD_MAX_Y - top
    max_visible = max(1, int(avail_h // row_h))
    n = len(rows)
    visible = min(n, max_visible)
    sel = view.sel
    start = max(0, min(sel - visible // 2, n - visible))

    card_y0 = top
    card_y1 = top + row_h * visible

    # card width is the narrowest safe width along its vertical span (top or
    # bottom edge, whichever is closer to the round bezel), not a flat margin
    half = min(_safe_half_width(card_y0), _safe_half_width(card_y1))
    card_x0 = W / 2 - half + card_pad
    card_x1 = W / 2 + half - card_pad

    draw.rounded_rectangle([card_x0, card_y0, card_x1, card_y1], radius=card_radius, fill=GROUP_BG)

    f_label_sel = _font("label_title", scale)
    f_label_uns = _font("sub_s", scale)
    f_val = _font("sub_s", scale)
    label_pad = max(4, round(10 * scale))
    value_pad = max(4, round(10 * scale))
    sep_pad = max(6, round(12 * scale))
    pill_w, pill_h = round(34 * scale), round(18 * scale)
    toggle_pad = max(6, round(14 * scale))

    for row, item in enumerate(rows[start:start + visible]):
        i = start + row
        y = top + row * row_h
        selected = i == sel
        if selected:
            draw.rectangle([card_x0 + 3, y + 2, card_x1 - 3, y + row_h - 2], fill=ROW_SELECTED)
        if row > 0:
            draw.line([(card_x0 + sep_pad, y), (card_x1 - sep_pad, y)], fill=SEPARATOR, width=1)

        val_text, val_color = _value_repr(item)
        is_toggle = item.kind == "toggle"
        toggle_x = card_x1 - toggle_pad - pill_w
        if is_toggle:
            value_x = toggle_x
        else:
            vw = draw.textbbox((0, 0), val_text, font=f_val)[2]
            value_x = card_x1 - value_pad - vw

        # selected row's label stands out (bold, like the nav-list rows
        # elsewhere), unselected rows shrink to font_sub_s - bought back
        # deliberately with font_label_title over the taller font_title_s:
        # jumping a full size up costs ~25-30% more width per character
        # (measured: "Audioausgang" 100px at font_sub_l vs 129px at
        # font_title_s), which undid the label/value collision fix above by
        # truncating the SELECTED row harder than before. Same point size,
        # just bold, costs only ~4-6% - visually bigger/heavier without
        # re-triggering the truncation it's meant to reduce.
        label_font = f_label_sel if selected else f_label_uns
        label_color = TEXT if selected else DIM
        label_max_w = max(20, value_x - (card_x0 + label_pad) - 8)
        lbl = _truncate(draw, item.label, label_font, label_max_w)
        draw.text((card_x0 + label_pad, y + row_h / 2 - label_font.size / 2 - 1), lbl, font=label_font, fill=label_color)

        if is_toggle:
            _draw_toggle_pill(draw, toggle_x, y + row_h / 2 - pill_h / 2, bool(item.value), pill_w, pill_h)
        else:
            draw.text((value_x, y + row_h / 2 - f_val.size / 2 - 1), val_text, font=f_val, fill=val_color)

    if start > 0:
        _caret(draw, W / 2, card_y0 - round(5 * scale), up=True)
    if start + visible < n:
        _caret(draw, W / 2, card_y1 + round(9 * scale), up=False)
    return img


def _value_repr(row):
    if row.kind == "stepper":
        return ("●" * row.value) + ("○" * (row.max - row.value)), ACCENT
    if row.kind == "toggle":
        return "", DIM
    return str(row.value), (ACCENT if row.on else DIM)


# --- now playing: turntable + frosted control pill -----------------------------

def draw_playing(view, ctx):
    scale = ctx.scale
    title, artist, dur = view.title, view.artist, view.duration
    progress = min(1.0, view.position / dur) if dur else 0.0

    img, draw = _base()

    # The turntable graphic (disc/label/tonearm) is a calibrated composition tuned
    # to fill the round bezel at fixed pixel positions - it does not scale with
    # ui_scale. Only the overlaid text (labels, pill) grows/shrinks for readability.
    disc_d = 210
    disc_margin = (W - disc_d) // 2
    art = ui_common.cover_image(view.cover, disc_d)

    # ~25s per rotation - a stylized slow spin (a real 33RPM record is ~1.8s/turn,
    # far too fast to read anything on a small UI element; slow and ambient reads
    # more "record player" than a literal RPM simulation would).
    disc_rotation_deg = (view.position * (360 / 25)) % 360
    f_disc_title = _font("disc_title", scale)
    f_disc_artist = _font("disc_artist", scale)
    title_arc_max_w = disc_d * 0.4 * math.radians(280)  # leave a visible gap, don't wrap the string onto itself
    artist_arc_max_w = disc_d * 0.32 * math.radians(280)
    title_for_disc = _truncate(draw, title, f_disc_title, title_arc_max_w)
    artist_for_disc = _truncate(draw, artist, f_disc_artist, artist_arc_max_w)
    disc = _compose_disc(art, disc_d, title_for_disc, f_disc_title, artist_for_disc, f_disc_artist)
    disc = disc.rotate(-disc_rotation_deg, resample=Image.BICUBIC)
    img.paste(disc, (disc_margin, disc_margin), disc)

    # label - neutral color (not the playlist accent) since it's meant to read as
    # the vinyl's paper backing, not a colored badge. No text here anymore -
    # title + artist both live on the disc itself now (see above).
    label_d = 66
    label_cx, label_cy = W / 2, W / 2
    draw.ellipse([label_cx - label_d / 2, label_cy - label_d / 2, label_cx + label_d / 2, label_cy + label_d / 2],
                 fill=(58, 56, 52))
    draw.ellipse([label_cx - 4, label_cy - 4, label_cx + 4, label_cy + 4], fill=(13, 14, 17))

    # tonearm: pivot fixed top-right, needle travels along progress (scaled from
    # the 480px beispiel.html geometry to our 240px display, i.e. halved)
    pivot = (101, 22)
    needle_start = (103, 33)
    needle_end = (71, 44)
    nx = needle_start[0] + (needle_end[0] - needle_start[0]) * progress
    ny = needle_start[1] + (needle_end[1] - needle_start[1]) * progress
    if not view.playing:
        nx -= 6
        ny -= 10
    arm_angle = math.degrees(math.atan2(ny - pivot[1], nx - pivot[0]))

    draw.ellipse([pivot[0] - 5, pivot[1] - 5, pivot[0] + 5, pivot[1] + 5], fill=(42, 45, 53), outline=(90, 94, 102))
    draw.line([pivot, (nx, ny)], fill=(210, 212, 218), width=3)
    head_pts = _rotated_rect_points(nx, ny, 9, 7, arm_angle)
    draw.polygon(head_pts, fill=(180, 184, 194))

    # frosted-glass control pill, bottom-anchored (iOS "material" style) - width
    # derived from the safe half-width at its own bottom edge, not a flat value
    # (which massively overflowed the round bezel this low on the screen)
    f_sub_s = _font("sub_s", scale)
    f_control = _font("control", scale)
    pill_h = round(46 * scale)
    pill_y1 = W - round(30 * scale)
    pill_y0 = pill_y1 - pill_h
    pill_w = min(round(190 * scale), 2 * (_safe_half_width(pill_y1) - 8))
    pill_x0 = (W - pill_w) / 2
    _frosted_pill(img, (pill_x0, pill_y0, pill_x0 + pill_w, pill_y0 + pill_h), radius=pill_h / 2)
    draw = ImageDraw.Draw(img)  # re-bind after paste

    pos_s, dur_s = _fmt_time(view.position), _fmt_time(dur)
    _text_centered(draw, W / 2, pill_y0 + round(6 * scale), f"{pos_s} / {dur_s}", f_sub_s, (210, 212, 218))

    state_label = "Pause" if view.playing else "Play"
    icon = "II" if view.playing else ">"
    row_y = pill_y0 + pill_h - f_control.size - round(4 * scale)
    _text_centered(draw, W / 2, row_y, f"{icon}  {state_label}", f_control, TEXT)
    if view.shuffle:
        icon_cx = W / 2 + round(50 * scale)
        icon_cy = row_y + f_control.size / 2
        _draw_shuffle_icon(draw, icon_cx, icon_cy, round(16 * scale), ACCENT)

    return img


# --- sync: TV-style device-flow login screen + progress ---------------------------

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


# --- wifi: password entry (encoder letter-wheel, click-wheel iPod style) ---------

def draw_password(view, ctx):
    scale = ctx.scale
    img, draw = _base()
    f_header = _font("header", scale)
    f_sub_s = _font("sub_s", scale)
    f_mono = _font("mono", scale)
    f_title_l = _font("title_l", scale)

    _header(draw, 36, view.title.upper(), f_header, DIM)
    _text_centered_fit(draw, W / 2, 58, view.ssid, [f_sub_s], DIM, max_width=160)

    # typed-so-far, shown in plain text (not masked) - there's no shoulder-surfing
    # risk worth the extra friction on a one-person device with no touch input,
    # and seeing what was actually typed matters more with only an encoder wheel
    # to correct mistakes with.
    _text_centered_fit(draw, W / 2, 92, view.typed or " ", [f_mono], TEXT, max_width=180)

    # current wheel character - what rotating the encoder changes, big since
    # it's the one thing being actively picked right now
    current = view.charset[view.char_idx]
    shown = "␣" if current == " " else current
    draw.rounded_rectangle([W / 2 - 26, 118, W / 2 + 26, 162], radius=12, fill=GROUP_BG)
    _text_centered(draw, W / 2, 128, shown, f_title_l, ACCENT)

    half_hint = _safe_half_width(172)
    _wrap_text(draw, view.hint, W / 2, 172, f_sub_s, DIM, max_width=max(60, 2 * half_hint - 20), line_height=14)
    return img


# --- overlays ---------------------------------------------------------------------

def draw_status(img, sv, ctx):
    draw = ImageDraw.Draw(img)
    # track (empty slot), rounded ends - the caps are faked with small filled
    # circles at both endpoints (a stroke-linecap of "round" is exactly a
    # semicircle of radius=width/2 at the endpoint; a full circle there looks
    # identical since the arc itself covers the rest)
    _draw_ring_arc(img, RING_ANCHOR_DEG, RING_FAR_DEG, RING_TRACK)
    for deg in (RING_ANCHOR_DEG, RING_FAR_DEG):
        x, y = _ring_point(deg)
        cap_r = RING_WIDTH / 2
        draw.ellipse([x - cap_r, y - cap_r, x + cap_r, y + cap_r], fill=RING_TRACK)

    if sv.battery_pct is not None:
        pct = max(0, min(100, round(sv.battery_pct)))
        if pct > 0:
            # Anchored at RING_FAR_DEG (bottom) and growing toward RING_ANCHOR_DEG
            # (top) as charge increases - inverted from a naive "fill from the
            # anchor" reading so the slot empties from the TOP down as the
            # battery drains, matching a real gauge (full at top, empties
            # downward) instead of draining from the bottom up.
            fill_bound = RING_FAR_DEG + (RING_ANCHOR_DEG - RING_FAR_DEG) * pct / 100
            _draw_ring_arc(img, RING_FAR_DEG, fill_bound, ACCENT)
            for deg in (RING_FAR_DEG, fill_bound):
                x, y = _ring_point(deg)
                cap_r = RING_WIDTH / 2
                draw.ellipse([x - cap_r, y - cap_r, x + cap_r, y + cap_r], fill=ACCENT)

        if sv.charging:
            bolt_x, bolt_y = _ring_point(180)
            _draw_lightning_bolt(draw, bolt_x, bolt_y, 14, CHARGE_GREEN)

        # r=100 sits inside SAFE_R (104), unlike the arc/dots above which stay
        # outside it - that's why these labels are restricted to Home-at-rest
        # and Now-Playing (sv.show_labels, see ui_views.status): drawing them on
        # any other screen, or a scrolled Home list, would paint over that
        # screen's own content. The Now-Playing disc (radius 105) just barely
        # clears r=100, checked live against the actual render.
        if sv.show_labels:
            f_pct = _font("ring_pct", 1.0)
            pct_x, pct_y = _ring_point(RING_ANCHOR_DEG, r=100)
            # Percentage is always shown - pushed up by one line's height so a
            # second line (watts/ETA) can sit at the old single-line position
            # below it without the two overlapping. Shifted 10px right of the
            # second line too - purely a legibility tweak, not tied to any ring
            # geometry.
            _text_centered(draw, pct_x + 10, pct_y - f_pct.size - 2, f"{pct}%", f_pct, DIM)

            if sv.charging and sv.watts is not None:
                _text_centered(draw, pct_x, pct_y, f"{round(sv.watts)}W", f_pct, ACCENT)
            elif not sv.charging and sv.eta_min is not None:
                _text_centered(draw, pct_x, pct_y, _format_eta(sv.eta_min), f_pct, DIM)

    _draw_status_dot(draw, WIFI_DOT_DEG, TEXT, sv.wifi_on, sv.wifi_connected)
    _draw_status_dot(draw, BT_DOT_DEG, CATEGORY_COLORS["connectivity"], sv.bt_on, sv.bt_connected)


def draw_quick_connect(img, qc, ctx):
    """Ring overlay for Home's hold-Play/Pause gesture (see ui_state.quick_connect_*).
    Darkens/blurs the whole frame (not just a circle behind the ring) for legibility."""
    cx = cy = W / 2
    blurred = img.filter(ImageFilter.GaussianBlur(3))
    dark = Image.blend(blurred, Image.new("RGB", img.size, (0, 0, 0)), 0.6)
    img.paste(dark, (0, 0))

    draw = ImageDraw.Draw(img)
    ring_box = [cx - QC_RING_R, cy - QC_RING_R, cx + QC_RING_R, cy + QC_RING_R]
    draw.ellipse(ring_box, outline=QC_RING_TRACK, width=QC_RING_STROKE)
    if qc.progress >= 1.0:
        draw.ellipse(ring_box, outline=TEXT, width=QC_RING_STROKE)
    elif qc.progress > 0:
        draw.arc(ring_box, start=-90, end=-90 + 360 * qc.progress, fill=TEXT, width=QC_RING_STROKE)

    color = QC_ERROR_COLOR if qc.error else TEXT
    _text_centered(draw, cx, cy - QC_RING_R - 28, qc.label, _font("sub_l", ctx.scale), color)


def draw_shutdown(ctx):
    """Power-button long-press message (power_button.py) - fixed scale, ctx may be None."""
    img, draw = _base()
    _text_centered(draw, W / 2, W / 2 - 12, "Shutting down", _font("title_s", 1.0), TEXT)
    _text_centered(draw, W / 2, W / 2 + 14, "...", _font("sub_l", 1.0), DIM)
    return img
