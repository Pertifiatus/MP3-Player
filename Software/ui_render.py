"""PIL-based rendering for every front-display UI screen.

Visual language: iOS/tvOS-inspired - true-black background, iOS system-gray
palette, "inset grouped" list cards with hairline separators, vivid single-color
squircle icon badges (Settings-app style), frosted-glass control pill on the
Now-Playing screen. Focus/selection uses a lifted-background highlight (tvOS-style,
since this is D-pad/encoder navigated, not touch) rather than a heavy outline.

UI-Groesse (display.ui_scale, see settings.py) is a real layout-density knob, not
a post-render zoom: it scales fonts, row heights and internal margins in the list
screens, so a smaller setting shrinks rows/text and therefore fits *more* items in
the same round safe area, while a larger setting grows them for readability at the
cost of items on screen. SAFE_R itself never scales - it's the physical round-bezel
limit, not a style margin.
"""
import functools
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import sync_youtube
import ui_state

W = 240

# --- palette (iOS dark-mode system colors) ------------------------------------
BG = (0, 0, 0)
GROUP_BG = (28, 28, 30)        # systemGray6 dark - card/group background
ROW_SELECTED = (46, 46, 50)    # focus highlight fill
SEPARATOR = (56, 56, 58)
TEXT = (255, 255, 255)
DIM = (142, 142, 147)          # systemGray
ACCENT = (49, 209, 166)
CARD_BG = (44, 44, 46)         # fallback icon badge background

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


def _scale(state):
    return UI_SCALE_STEPS[state.settings.get("display", "ui_scale")]


# --- small drawing helpers ---------------------------------------------------

def _text_centered(draw, x_center, y, s, font, fill):
    bbox = draw.textbbox((0, 0), s, font=font)
    w = bbox[2] - bbox[0]
    draw.text((x_center - w / 2, y), s, font=font, fill=fill)


def _text_centered_fit(draw, x_center, y, s, fonts, fill, max_width):
    """Like _text_centered, but steps down through `fonts` (largest first) to the
    first one that fits max_width, truncating with the smallest as a last resort -
    used for server-provided strings (e.g. a device-flow URL) that shouldn't
    overflow their card just because a real value came in longer than the ones
    this layout was eyeballed against."""
    for font in fonts:
        if draw.textbbox((0, 0), s, font=font)[2] <= max_width:
            _text_centered(draw, x_center, y, s, font, fill)
            return
    smallest = fonts[-1]
    _text_centered(draw, x_center, y, _truncate(draw, s, smallest, max_width), smallest, fill)


def _letter_spaced(s):
    return " ".join(list(s))


# --- round-display safety -----------------------------------------------------
# The GC9A01 panel is physically circular even though the framebuffer is a square
# 240x240 - content placed via naive rectangular layout gets clipped by the bezel
# near the top/bottom/corners. SAFE_R is a little under W/2 as a small margin.
# This is a hardware constant - it does NOT scale with ui_scale.
SAFE_R = 104


def _safe_half_width(y, r=SAFE_R, cy=W / 2):
    dy = abs(y - cy)
    if dy >= r:
        return 0.0
    return (r * r - dy * dy) ** 0.5


# Lowest y a grouped settings card is allowed to reach - past this the round
# bezel narrows the card below a usable width. Derived from SAFE_R so it stays
# consistent with the hardware constant above instead of being a second magic
# number that could drift out of sync with it.
_MIN_CARD_HALF_W = 50
CARD_MAX_Y = W / 2 + (SAFE_R ** 2 - _MIN_CARD_HALF_W ** 2) ** 0.5


def _header(draw, y, text, font, fill):
    """Letter-spaced section header, truncated to whatever actually fits inside
    the round bezel at this y."""
    spaced = _letter_spaced(text)
    max_w = max(20, 2 * _safe_half_width(y) - 16)
    spaced = _truncate(draw, spaced, font, max_w)
    _text_centered(draw, W / 2, y, spaced, font, fill)


def _truncate(draw, text, font, max_width):
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), text + "…", font=font)[2] > max_width:
        text = text[:-1]
    return text + "…" if text else "…"


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _shade(rgb, pct):
    return tuple(max(0, min(255, c + round(255 * pct / 100))) for c in rgb)


def _rotated_rect_points(cx, cy, w, h, angle_deg):
    angle = math.radians(angle_deg)
    hw, hh = w / 2, h / 2
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    pts = []
    for x, y in corners:
        rx = x * math.cos(angle) - y * math.sin(angle)
        ry = x * math.sin(angle) + y * math.cos(angle)
        pts.append((cx + rx, cy + ry))
    return pts


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


# --- procedural cover art (ported from beispiel.html coverArtURI) -----------

_cover_cache = {}


def _cover_image(cover_path, seed, color_hex, size):
    """Real synced thumbnail if one exists and still loads, else the procedural
    placeholder - covers the demo library (no real files at all) and any track
    whose thumbnail download failed/was skipped during sync."""
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
    color_a = _hex_to_rgb(color_a_hex)
    color_b = _shade(_hex_to_rgb(color_b_hex), -20)

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


def render_home(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    # _render_nav_list always centers the selected row on screen middle, so
    # scrolling down past the first item pushes earlier rows up into the
    # header's y - only show the header at rest (top item selected) instead
    # of drawing over/under it once scrolled. Same pattern in the other
    # nav-list screens below (library/playlist/settings root).
    if state.home_sel == 0:
        _header(draw, 36, "MINI-MUSIKPLAYER", _font("header", scale), DIM)

    entries = []
    for item in state.home_items():
        entry = {"label": item["label"], "sub": item["sub"], "icon": item["icon"], "color_rgb": ACCENT}
        if item["key"] == "resume":
            pl_idx, tr_idx = state.last_played
            cover_path = ui_state.LIBRARY_COVERS[pl_idx]["tracks"][tr_idx]
            entry["cover_img"] = _cover_image(cover_path, item["seed"], item["color"], size=140)
        entries.append(entry)
    _render_nav_list(img, draw, entries, state.home_sel, scale)
    return img


def render_library(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    if state.library_sel == 0:
        _header(draw, 36, "BIBLIOTHEK", _font("header", scale), DIM)

    entries = []
    for i, (name, tracks) in enumerate(ui_state.LIBRARY):
        color = PLAYLIST_COLOR(i)
        cover_path = ui_state.LIBRARY_COVERS[i]["cover"]
        entries.append({
            "label": name, "sub": f"{len(tracks)} Songs",
            "cover_img": _cover_image(cover_path, f"pl-{name}", color, size=140),
        })
    _render_nav_list(img, draw, entries, state.library_sel, scale)
    return img


def render_playlist(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    name, tracks = ui_state.LIBRARY[state.current_playlist_idx]
    color = PLAYLIST_COLOR(state.current_playlist_idx)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    if state.playlist_sel == 0:
        _header(draw, 36, name.upper(), _font("header", scale), DIM)

    entries = []
    track_covers = ui_state.LIBRARY_COVERS[state.current_playlist_idx]["tracks"]
    for t_idx, (title, artist, dur) in enumerate(tracks):
        entries.append({
            "label": title, "sub": f"{artist} · {_fmt_time(dur)}",
            "cover_img": _cover_image(track_covers[t_idx], f"tr-{name}-{title}", color, size=140),
        })
    _render_nav_list(img, draw, entries, state.playlist_sel, scale)
    return img


def PLAYLIST_COLOR(idx):
    return ui_state.PLAYLIST_COLORS[idx % len(ui_state.PLAYLIST_COLORS)]


def _fmt_time(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


# --- now playing: turntable + frosted control pill -----------------------------

def render_playing(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    np = state.now_playing
    title, artist, dur = np.current()
    color_hex = PLAYLIST_COLOR(np.playlist_idx)
    playlist_name = ui_state.LIBRARY[np.playlist_idx][0]
    progress = min(1.0, np.position / dur) if dur else 0.0

    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)

    # The turntable graphic (disc/label/tonearm) is a calibrated composition tuned
    # to fill the round bezel at fixed pixel positions - it does not scale with
    # ui_scale. Only the overlaid text (labels, pill) grows/shrinks for readability.
    disc_d = 210
    disc_margin = (W - disc_d) // 2
    cover_path = ui_state.LIBRARY_COVERS[np.playlist_idx]["tracks"][np.index]
    art = _cover_image(cover_path, f"tr-{playlist_name}-{title}", color_hex, size=disc_d)

    # ~25s per rotation - a stylized slow spin (a real 33RPM record is ~1.8s/turn,
    # far too fast to read anything on a small UI element; slow and ambient reads
    # more "record player" than a literal RPM simulation would).
    disc_rotation_deg = (np.position * (360 / 25)) % 360
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
    if not np.playing:
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

    pos_s, dur_s = _fmt_time(np.position), _fmt_time(dur)
    _text_centered(draw, W / 2, pill_y0 + round(6 * scale), f"{pos_s} / {dur_s}", f_sub_s, (210, 212, 218))

    state_label = "Pause" if np.playing else "Play"
    icon = "II" if np.playing else ">"
    row_y = pill_y0 + pill_h - f_control.size - round(4 * scale)
    _text_centered(draw, W / 2, row_y, f"{icon}  {state_label}", f_control, TEXT)
    if state.shuffle:
        dot_r = max(2, round(3 * scale))
        dot_x = W / 2 + round(46 * scale)
        draw.ellipse([dot_x, row_y + dot_r, dot_x + 2 * dot_r, row_y + 3 * dot_r], fill=ACCENT)

    return img


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


# --- settings: category root (same nav-list, vivid category-colored badges) ---

def render_settings_root(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    if state.settings_root_sel == 0:
        _header(draw, 36, "EINSTELLUNGEN", _font("header", scale), DIM)

    entries = [{"label": c["label"], "sub": "", "icon": c["icon"], "color_rgb": CATEGORY_COLORS[c["key"]]}
               for c in ui_state.SETTINGS_CATEGORIES]
    _render_nav_list(img, draw, entries, state.settings_root_sel, scale)
    return img


# --- settings: category detail - iOS "inset grouped" list ---------------------

def render_settings_detail(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    cat = state.settings_category
    items = ui_state.SETTINGS_ITEMS[cat]
    label = next(c["label"] for c in ui_state.SETTINGS_CATEGORIES if c["key"] == cat)

    header_y = 32
    f_header = _font("header", scale)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    _header(draw, header_y, label.upper(), f_header, DIM)

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
    n = len(items)
    visible = min(n, max_visible)
    sel = state.settings_detail_sel
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

    for row, item in enumerate(items[start:start + visible]):
        i = start + row
        y = top + row * row_h
        selected = i == state.settings_detail_sel
        if selected:
            draw.rectangle([card_x0 + 3, y + 2, card_x1 - 3, y + row_h - 2], fill=ROW_SELECTED)
        if row > 0:
            draw.line([(card_x0 + sep_pad, y), (card_x1 - sep_pad, y)], fill=SEPARATOR, width=1)

        val_text, val_color = _value_repr(cat, item, state)
        is_toggle = val_text in ("__toggle_on__", "__toggle_off__")
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
        lbl = _truncate(draw, item["label"], label_font, label_max_w)
        draw.text((card_x0 + label_pad, y + row_h / 2 - label_font.size / 2 - 1), lbl, font=label_font, fill=label_color)

        if is_toggle:
            _draw_toggle_pill(draw, toggle_x, y + row_h / 2 - pill_h / 2, val_text == "__toggle_on__", pill_w, pill_h)
        else:
            draw.text((value_x, y + row_h / 2 - f_val.size / 2 - 1), val_text, font=f_val, fill=val_color)

    if start > 0:
        _caret(draw, W / 2, card_y0 - round(5 * scale), up=True)
    if start + visible < n:
        _caret(draw, W / 2, card_y1 + round(9 * scale), up=False)
    return img


def _caret(draw, x_center, y, up):
    w, h = 7, 4
    pts = [(x_center - w, y + (0 if up else h)), (x_center + w, y + (0 if up else h)), (x_center, y + (h if up else 0))]
    draw.polygon(pts, fill=DIM)


def _value_repr(cat, item, state):
    kind = item["type"]
    if kind == "toggle":
        return ("__toggle_on__" if state.settings.get(cat, item["key"]) else "__toggle_off__"), DIM
    if kind == "stepper":
        val = state.settings.get(cat, item["key"])
        return ("●" * val) + ("○" * (item["max"] - val)), ACCENT
    if kind == "choice":
        val = state.settings.get(cat, item["key"])
        label = next(c[1] for c in item["choices"] if c[0] == val)
        return label, ACCENT
    if kind == "info":
        if item["key"] == "storage":
            # unlike every other "info" row, this changes constantly - can't
            # be baked into SETTINGS_ITEMS as a fixed string like VERSION_STRING
            try:
                return f"{sync_youtube.free_space_gb():.1f} GB frei", DIM
            except OSError:
                return "unbekannt", DIM
        return item["detail"], DIM
    if kind == "action":
        if item["key"] == "account":
            linked = state.settings.get("sync", "account_linked")
            return ("Verknuepft" if linked else "Verbinden →"), (ACCENT if linked else DIM)
        if item["key"] == "bluetooth_menu":
            on = state.settings.get("connectivity", "bluetooth")
            return ("An" if on else "Aus"), (ACCENT if on else DIM)
        if item["key"] == "wifi_menu":
            on = state.settings.get("connectivity", "wifi")
            return ("An" if on else "Aus"), (ACCENT if on else DIM)
        return "→", DIM
    return "", DIM


def _draw_toggle_pill(draw, x, y, on, w=34, h=18):
    bg = ACCENT if on else (72, 72, 76)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=bg)
    knob_x = x + w - h + 2 if on else x + 2
    draw.ellipse([knob_x, y + 2, knob_x + h - 4, y + h - 2], fill=(255, 255, 255))


# --- sync: TV-style device-flow login screen ----------------------------------

def render_sync_login(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    f_header = _font("header", scale)
    f_sub_l = _font("sub_l", scale)
    f_sub_s = _font("sub_s", scale)
    f_mono = _font("mono", scale)

    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    _header(draw, 36, "YOUTUBE KOPPELN", f_header, DIM)

    if state.sync_login_error:
        _text_centered(draw, W / 2, 90, "Fehler:", f_sub_l, (255, 69, 58))
        _wrap_text(draw, state.sync_login_error, W / 2, 116, f_sub_s, DIM, max_width=200)
        return img

    if not state.sync_login_info:
        _text_centered(draw, W / 2, 110, "Verbinde...", f_sub_l, DIM)
        return img

    pad = max(3, round(5 * scale))
    half = min(_safe_half_width(58), _safe_half_width(178))
    card_box = [W / 2 - half + pad, 58, W / 2 + half - pad, 178]
    draw.rounded_rectangle(card_box, radius=round(20 * scale), fill=GROUP_BG)

    _text_centered(draw, W / 2, 72, "Gehe zu", f_sub_s, DIM)
    _text_centered_fit(draw, W / 2, 92, state.sync_login_info["verification_url"],
                        [f_sub_l, f_sub_s], TEXT, max_width=card_box[2] - card_box[0] - 10)
    _text_centered(draw, W / 2, 124, "und gib diesen Code ein:", f_sub_s, DIM)
    _text_centered(draw, W / 2, 144, state.sync_login_info["user_code"], f_mono, ACCENT)

    _text_centered(draw, W / 2, 198, "Warte auf Bestätigung …", f_sub_s, DIM)
    return img


def _wrap_text(draw, text, x_center, y, font, fill, max_width, line_height=16):
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
        _text_centered(draw, x_center, y + i * line_height, l, font, fill)


# --- sync: progress ------------------------------------------------------------

def render_sync_progress(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    f_header = _font("header", scale)
    f_sub_l = _font("sub_l", scale)
    f_sub_s = _font("sub_s", scale)

    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    _header(draw, 36, "SYNCHRONISIERE", f_header, DIM)

    if state.sync_error:
        _text_centered(draw, W / 2, 90, "Fehler:", f_sub_l, (255, 69, 58))
        _wrap_text(draw, state.sync_error, W / 2, 116, f_sub_s, DIM, max_width=200)
        return img

    current, total, track_name = state.sync_progress
    pct = current / total if total else 0

    bar_x0, bar_x1, bar_y = 30, W - 30, 130
    draw.rounded_rectangle([bar_x0, bar_y, bar_x1, bar_y + 10], radius=5, fill=(58, 58, 60))
    fill_x1 = bar_x0 + (bar_x1 - bar_x0) * pct
    if fill_x1 > bar_x0:
        draw.rounded_rectangle([bar_x0, bar_y, fill_x1, bar_y + 10], radius=5, fill=ACCENT)

    _text_centered(draw, W / 2, 150, f"{current} / {total}", f_sub_l, TEXT)
    if track_name:
        _text_centered(draw, W / 2, 174, track_name, f_sub_s, DIM)

    if state.sync_done():
        _text_centered(draw, W / 2, 204, "Fertig!", f_sub_l, ACCENT)
    return img


# --- bluetooth: menu (toggle + known devices + "pair new") ----------------------

def render_bt_menu(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    if state.bt_menu_sel == 0:
        _header(draw, 36, "BLUETOOTH", _font("header", scale), DIM)

    entries = []
    for item in state.bt_menu_items():
        on = item.get("on") or item.get("connected")
        entries.append({
            "label": item["label"], "sub": item["sub"],
            "icon": "+" if item["kind"] == "pair_new" else "B",
            "color_rgb": ACCENT if on else CARD_BG,
        })
    _render_nav_list(img, draw, entries, state.bt_menu_sel, scale)
    return img


# --- bluetooth: per-device connect/disconnect/remove -----------------------------

def render_bt_device(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    f_sub_l = _font("sub_l", scale)
    f_sub_s = _font("sub_s", scale)
    title = (state.bt_device_name or "").upper()

    if state.bt_action_status == "working":
        _header(draw, 36, title, _font("header", scale), DIM)
        _text_centered(draw, W / 2, 110, "Bitte warten...", f_sub_l, DIM)
        return img

    if state.bt_action_status == "error":
        _header(draw, 36, title, _font("header", scale), DIM)
        _text_centered(draw, W / 2, 90, "Fehler:", f_sub_l, (255, 69, 58))
        _wrap_text(draw, state.bt_action_error or "Unbekannter Fehler", W / 2, 116, f_sub_s, DIM, max_width=200)
        return img

    if state.bt_device_sel == 0:
        _header(draw, 36, title, _font("header", scale), DIM)
    entries = [{"label": item["label"], "sub": "", "icon": "B", "color_rgb": CARD_BG}
               for item in state.bt_device_items()]
    _render_nav_list(img, draw, entries, state.bt_device_sel, scale)
    return img


# --- bluetooth: scan + pair a NEW device -------------------------------------------

def render_bt_pairing(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    f_sub_l = _font("sub_l", scale)
    f_sub_s = _font("sub_s", scale)

    showing_list = bool(state.bt_scan_devices) and not state.bt_scanning and state.bt_pair_status is None
    # same header-hides-once-scrolled rule as the other nav-list screens, see
    # render_home et al - only the device-list state can actually scroll here
    if not showing_list or state.bt_scan_sel == 0:
        _header(draw, 36, "BLUETOOTH", _font("header", scale), DIM)

    if state.bt_pair_status == "pairing":
        _text_centered(draw, W / 2, 106, "Verbinde...", f_sub_l, DIM)
        _text_centered(draw, W / 2, 130, state.bt_pair_device_name or "", f_sub_s, ACCENT)
        return img

    if state.bt_pair_status == "done":
        _text_centered(draw, W / 2, 100, "Verbunden!", f_sub_l, ACCENT)
        _text_centered(draw, W / 2, 124, state.bt_pair_device_name or "", f_sub_s, DIM)
        return img

    if state.bt_pair_status == "error":
        _text_centered(draw, W / 2, 90, "Fehler:", f_sub_l, (255, 69, 58))
        _wrap_text(draw, state.bt_pair_error or "Unbekannter Fehler", W / 2, 116, f_sub_s, DIM, max_width=200)
        return img

    if state.bt_scanning:
        _text_centered(draw, W / 2, 106, "Suche Geräte...", f_sub_l, DIM)
        _text_centered(draw, W / 2, 130, "Kopfhörer in Pairing-Modus", f_sub_s, DIM)
        return img

    if not state.bt_scan_devices:
        _text_centered(draw, W / 2, 100, "Keine Geräte gefunden", f_sub_l, DIM)
        _text_centered(draw, W / 2, 124, "Kopfhörer in Pairing-Modus?", f_sub_s, DIM)
        return img

    entries = [{
        "label": d["name"] or d["mac"],
        "sub": "Gekoppelt" if d.get("paired") else d["mac"],
        "icon": "B",
        "color_rgb": ACCENT if d.get("paired") else CARD_BG,
    } for d in state.bt_scan_devices]
    _render_nav_list(img, draw, entries, state.bt_scan_sel, scale)
    return img


# --- wifi: menu (toggle + known networks + "connect new") -----------------------

def render_wifi_menu(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    if state.wifi_menu_sel == 0:
        _header(draw, 36, "WLAN", _font("header", scale), DIM)

    entries = []
    for item in state.wifi_menu_items():
        on = item.get("on") or item.get("connected")
        entries.append({
            "label": item["label"], "sub": item["sub"],
            "icon": "+" if item["kind"] == "connect_new" else "W",
            "color_rgb": ACCENT if on else CARD_BG,
        })
    _render_nav_list(img, draw, entries, state.wifi_menu_sel, scale)
    return img


# --- wifi: per-network connect/disconnect/forget ---------------------------------

def render_wifi_device(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    f_sub_l = _font("sub_l", scale)
    f_sub_s = _font("sub_s", scale)
    title = (state.wifi_device_ssid or "").upper()

    if state.wifi_action_status == "working":
        _header(draw, 36, title, _font("header", scale), DIM)
        _text_centered(draw, W / 2, 110, "Bitte warten...", f_sub_l, DIM)
        return img

    if state.wifi_action_status == "error":
        _header(draw, 36, title, _font("header", scale), DIM)
        _text_centered(draw, W / 2, 90, "Fehler:", f_sub_l, (255, 69, 58))
        _wrap_text(draw, state.wifi_action_error or "Unbekannter Fehler", W / 2, 116, f_sub_s, DIM, max_width=200)
        return img

    if state.wifi_device_sel == 0:
        _header(draw, 36, title, _font("header", scale), DIM)
    entries = [{"label": item["label"], "sub": "", "icon": "W", "color_rgb": CARD_BG}
               for item in state.wifi_device_items()]
    _render_nav_list(img, draw, entries, state.wifi_device_sel, scale)
    return img


# --- wifi: scan + connect a NEW network -------------------------------------------

def render_wifi_scan(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    f_sub_l = _font("sub_l", scale)
    f_sub_s = _font("sub_s", scale)

    showing_list = bool(state.wifi_scan_networks) and not state.wifi_scanning and state.wifi_connect_status is None
    if not showing_list or state.wifi_scan_sel == 0:
        _header(draw, 36, "WLAN", _font("header", scale), DIM)

    if state.wifi_connect_status == "connecting":
        _text_centered(draw, W / 2, 106, "Verbinde...", f_sub_l, DIM)
        _text_centered(draw, W / 2, 130, state.wifi_pending_ssid or "", f_sub_s, ACCENT)
        return img

    if state.wifi_connect_status == "error":
        _text_centered(draw, W / 2, 90, "Fehler:", f_sub_l, (255, 69, 58))
        _wrap_text(draw, state.wifi_connect_error or "Unbekannter Fehler", W / 2, 116, f_sub_s, DIM, max_width=200)
        return img

    if state.wifi_scanning:
        _text_centered(draw, W / 2, 106, "Suche Netzwerke...", f_sub_l, DIM)
        return img

    if not state.wifi_scan_networks:
        _text_centered(draw, W / 2, 100, "Keine Netzwerke gefunden", f_sub_l, DIM)
        return img

    known_ssids = {n["ssid"] for n in state.wifi_known_networks}
    entries = [{
        "label": n["ssid"],
        "sub": "Gespeichert" if n["ssid"] in known_ssids else ("Gesichert" if n["secured"] else "Offen"),
        "icon": "W",
        "color_rgb": ACCENT if n["ssid"] in known_ssids else CARD_BG,
    } for n in state.wifi_scan_networks]
    _render_nav_list(img, draw, entries, state.wifi_scan_sel, scale)
    return img


# --- wifi: password entry (encoder letter-wheel, click-wheel iPod style) ---------

def render_wifi_password(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    f_header = _font("header", scale)
    f_sub_s = _font("sub_s", scale)
    f_mono = _font("mono", scale)
    f_title_l = _font("title_l", scale)

    _header(draw, 36, "WLAN-PASSWORT", f_header, DIM)
    _text_centered_fit(draw, W / 2, 58, state.wifi_pending_ssid or "", [f_sub_s], DIM, max_width=160)

    # Submitting (Play/Pause) doesn't leave this screen while the connect is in
    # flight or failed - it needs its own feedback here, same as render_wifi_scan
    # does for the analogous "already known network" connect path. Without this,
    # pressing Play/Pause after a wrong password (or any failure) looked like it
    # did nothing at all - confirmed live: repeated presses, screen never changed.
    if state.wifi_connect_status == "connecting":
        _text_centered(draw, W / 2, 106, "Verbinde...", _font("sub_l", scale), DIM)
        _text_centered(draw, W / 2, 130, state.wifi_pending_ssid or "", f_sub_s, ACCENT)
        return img

    if state.wifi_connect_status == "error":
        _text_centered(draw, W / 2, 90, "Fehler:", _font("sub_l", scale), (255, 69, 58))
        _wrap_text(draw, state.wifi_connect_error or "Unbekannter Fehler", W / 2, 116, f_sub_s, DIM, max_width=200)
        _text_centered(draw, W / 2, 178, "Play: erneut versuchen", f_sub_s, DIM)
        return img

    # typed-so-far, shown in plain text (not masked) - there's no shoulder-surfing
    # risk worth the extra friction on a one-person device with no touch input,
    # and seeing what was actually typed matters more with only an encoder wheel
    # to correct mistakes with.
    typed = state.wifi_password_text()
    _text_centered_fit(draw, W / 2, 92, typed or " ", [f_mono], TEXT, max_width=180)

    # current wheel character - what rotating the encoder changes, big since
    # it's the one thing being actively picked right now
    current = state.wifi_password_current_char()
    shown = "␣" if current == " " else current
    draw.rounded_rectangle([W / 2 - 26, 118, W / 2 + 26, 162], radius=12, fill=GROUP_BG)
    _text_centered(draw, W / 2, 128, shown, f_title_l, ACCENT)

    half_hint = _safe_half_width(172)
    _wrap_text(draw, "Dreh: Zeichen  ·  Klick: uebernehmen  ·  Shuffle: Loeschen  ·  Play: Fertig",
               W / 2, 172, f_sub_s, DIM, max_width=max(60, 2 * half_hint - 20), line_height=14)
    return img


# --- playlist management: exclude from sync / delete to free space -----------

def render_playlist_manage(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    if state.playlist_manage_sel == 0:
        _header(draw, 36, "PLAYLISTS", _font("header", scale), DIM)

    if not ui_state.LIBRARY:
        _text_centered(draw, W / 2, 106, "Keine Playlists", _font("sub_l", scale), DIM)
        return img

    excluded = set(state.settings.get("sync", "excluded_playlists"))
    entries = [{
        "label": name, "sub": "Ausgeschlossen" if name in excluded else f"{len(tracks)} Songs",
        "icon": "♪", "color_rgb": CARD_BG if name in excluded else ACCENT,
    } for name, tracks in ui_state.LIBRARY]
    _render_nav_list(img, draw, entries, state.playlist_manage_sel, scale)
    return img


def render_playlist_manage_detail(state: ui_state.UIState) -> Image.Image:
    scale = _scale(state)
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    title = state.playlist_manage_detail_name().upper()
    if state.playlist_manage_detail_sel == 0:
        _header(draw, 36, title, _font("header", scale), DIM)

    entries = [{"label": item["label"], "sub": "", "icon": "!" if item["key"] == "delete" else "S",
                "color_rgb": (255, 69, 58) if (item["key"] == "delete" and state.playlist_manage_confirm_delete)
                else CARD_BG}
               for item in state.playlist_manage_detail_items()]
    _render_nav_list(img, draw, entries, state.playlist_manage_detail_sel, scale)
    return img


# --- dispatch -------------------------------------------------------------------

_RENDERERS = {
    ui_state.SCREEN_HOME: render_home,
    ui_state.SCREEN_LIBRARY: render_library,
    ui_state.SCREEN_PLAYLIST: render_playlist,
    ui_state.SCREEN_PLAYING: render_playing,
    ui_state.SCREEN_SETTINGS_ROOT: render_settings_root,
    ui_state.SCREEN_SETTINGS_DETAIL: render_settings_detail,
    ui_state.SCREEN_SYNC_LOGIN: render_sync_login,
    ui_state.SCREEN_SYNC_PROGRESS: render_sync_progress,
    ui_state.SCREEN_BT_PAIRING: render_bt_pairing,
    ui_state.SCREEN_BT_MENU: render_bt_menu,
    ui_state.SCREEN_BT_DEVICE: render_bt_device,
    ui_state.SCREEN_WIFI_MENU: render_wifi_menu,
    ui_state.SCREEN_WIFI_DEVICE: render_wifi_device,
    ui_state.SCREEN_WIFI_SCAN: render_wifi_scan,
    ui_state.SCREEN_WIFI_PASSWORD: render_wifi_password,
    ui_state.SCREEN_PLAYLIST_MANAGE: render_playlist_manage,
    ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL: render_playlist_manage_detail,
}

# UI-Groesse setting (1-5 stepper) -> layout density multiplier. 3 = 100%, matches
# every pixel constant used throughout this file as designed/tuned. Below 1.0
# shrinks fonts/rows/margins so more list content fits on screen; above 1.0 grows
# them for readability at the cost of items visible at once.
UI_SCALE_STEPS = {1: 0.75, 2: 0.88, 3: 1.0, 4: 1.15, 5: 1.3}


def render_shutdown() -> Image.Image:
    """Standalone message screen for the power-button long-press, see power_button.py.
    Not part of the normal screen/state machine (nothing to navigate back from), so
    it bypasses _RENDERERS/render() instead of getting its own ui_state.SCREEN_*."""
    img = Image.new("RGB", (W, W), BG)
    draw = ImageDraw.Draw(img)
    _text_centered(draw, W / 2, W / 2 - 12, "Shutting down", _font("title_s", 1.0), TEXT)
    _text_centered(draw, W / 2, W / 2 + 14, "...", _font("sub_l", 1.0), DIM)
    return img


def render(state: ui_state.UIState) -> Image.Image:
    return _RENDERERS[state.screen](state)
