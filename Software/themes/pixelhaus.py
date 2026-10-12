"""Pixelhaus: every menu is a room in a pixel-art house (2D cross-section, Per's
assets/pixelhaus.png, used 1:1 - one room fills the round screen), and the camera
floats from room to room in a straight line - through walls and ceilings, slight
zoom-out mid-flight - whenever the screen changes. After the flight the frame
stands still (no idle animation); the menu itself is an RPG dialog box in a
pixel font (Pixelify Sans, rendered without antialiasing). Fixed layout:
ignores UI-Groesse.
"""
import functools
import math
import os
import time

from PIL import Image, ImageDraw

import ui_common
import ui_state
from ui_common import W
from ui_views import fmt_time

ASSET_PATH = os.path.join(ui_common.HERE, "assets", "pixelhaus.png")

# Room centers in the asset (measured: floor beams at y~233/380/544/730, walls per floor).
ROOMS = {
    "schlafzimmer": (352, 303), "saal": (644, 303), "kinderzimmer": (1160, 303),
    "arbeitszimmer": (372, 462), "treppenhalle": (645, 462), "bibliothek": (934, 462),
    "bibliothek_regal": (896, 462), "musikzimmer": (1200, 462),
    "wohnzimmer": (228, 637), "eingangshalle": (644, 637), "kueche": (915, 637), "werkstatt": (1216, 637),
    "kellerlager": (232, 850),
}
SCREEN_ROOM = {
    ui_state.SCREEN_HOME: "wohnzimmer", ui_state.SCREEN_LIBRARY: "bibliothek",
    ui_state.SCREEN_PLAYLIST: "bibliothek_regal", ui_state.SCREEN_PLAYING: "musikzimmer",
    ui_state.SCREEN_SETTINGS_ROOT: "werkstatt",
    ui_state.SCREEN_SYNC_LOGIN: "kinderzimmer", ui_state.SCREEN_SYNC_PROGRESS: "kinderzimmer",
    ui_state.SCREEN_BT_MENU: "arbeitszimmer", ui_state.SCREEN_BT_DEVICE: "arbeitszimmer",
    ui_state.SCREEN_BT_PAIRING: "arbeitszimmer", ui_state.SCREEN_WIFI_MENU: "arbeitszimmer",
    ui_state.SCREEN_WIFI_DEVICE: "arbeitszimmer", ui_state.SCREEN_WIFI_SCAN: "arbeitszimmer",
    ui_state.SCREEN_WIFI_PASSWORD: "arbeitszimmer",
    ui_state.SCREEN_PLAYLIST_MANAGE: "kellerlager", ui_state.SCREEN_PLAYLIST_MANAGE_DETAIL: "kellerlager",
}
CATEGORY_ROOM = {"display": "saal", "led": "treppenhalle", "connectivity": "arbeitszimmer",
                 "sync": "kinderzimmer", "motion": "kueche", "about": "eingangshalle"}
HOME_TARGET = {"library": "bibliothek", "resume": "musikzimmer", "settings": "werkstatt"}
DRIFT_PX = 30
# The camera looks a bit below each room's center, so the furniture sits above
# the dialog box (bottom third of the round screen) instead of behind it.
VIEW_DY = 40

NIGHT = (22, 18, 34)
BOX = (24, 20, 48)
BOX_EDGE = (240, 226, 196)
BOX_SHADE = (60, 50, 96)
CREAM = (248, 236, 210)
DIMC = (150, 140, 172)
GOLD = (255, 210, 90)
RED = (255, 96, 96)
GREEN = (130, 230, 120)

_clock = time.monotonic  # tests and preview_themes swap in a fake clock


class Camera:
    """Floats between rooms in a straight line, smoothstep easing, slight zoom-out
    mid-flight. Pure function of the `now` passed in."""
    MIN_S, MAX_S, BASE_S, SPEED = 0.4, 1.0, 0.35, 1500.0
    ZOOM_DIP, ZOOM_MIN_DIST = 0.2, 120

    def __init__(self):
        self.start = self.target = None
        self.t0 = self.dur = self.dist = 0.0
        self.settled = True

    def aim(self, target, now):
        if self.target is None:  # very first frame: no flight from nowhere
            self.start = self.target = target
            self.dur = self.dist = 0.0
            self.settled = False
            return
        if target == self.target:
            return
        x, y, _, _ = self.frame(now)
        self.start, self.target, self.t0 = (x, y), target, now
        self.dist = math.hypot(target[0] - x, target[1] - y)
        self.dur = min(self.MAX_S, max(self.MIN_S, self.BASE_S + self.dist / self.SPEED))
        self.settled = False

    def frame(self, now):
        """(x, y, zoom, arrived). Arriving collapses the flight, so any later (or,
        with a swapped test clock, earlier) time keeps returning the target."""
        t = 1.0 if self.dur <= 0 else max(0.0, min(1.0, (now - self.t0) / self.dur))
        if t >= 1.0:
            self.start, self.dur, self.dist = self.target, 0.0, 0.0
            return self.target[0], self.target[1], 1.0, True
        e = t * t * (3 - 2 * t)
        x = self.start[0] + (self.target[0] - self.start[0]) * e
        y = self.start[1] + (self.target[1] - self.start[1]) * e
        z = 1.0 - self.ZOOM_DIP * math.sin(math.pi * t) if self.dist >= self.ZOOM_MIN_DIST else 1.0
        return x, y, z, False


_CAM = Camera()


def animating():
    return not _CAM.settled


@functools.lru_cache(maxsize=1)
def _house():
    try:
        return Image.open(ASSET_PATH).convert("RGB")
    except OSError:
        return None  # not deployed - plain background instead, see _crop()


def _room_of(view):
    if getattr(view, "KIND", "") == "settings":
        return CATEGORY_ROOM.get(view.category, "werkstatt")
    return SCREEN_ROOM.get(view.screen, "wohnzimmer")


def _focus_room(view):
    """On Home/Werkstatt the camera leans toward the room the selection leads to."""
    if getattr(view, "KIND", "") != "list" or not 0 <= view.sel < len(view.items):
        return None
    kind = view.items[view.sel].kind
    if view.screen == ui_state.SCREEN_HOME:
        return HOME_TARGET.get(kind)
    if view.screen == ui_state.SCREEN_SETTINGS_ROOT:
        return CATEGORY_ROOM.get(kind)
    return None


def _target(view):
    room = _room_of(view)
    cx, cy = ROOMS[room]
    cy += VIEW_DY
    focus = _focus_room(view)
    if focus and focus != room:
        fx, fy = ROOMS[focus]
        fy += VIEW_DY
        d = math.hypot(fx - cx, fy - cy) or 1.0
        cx, cy = cx + (fx - cx) / d * DRIFT_PX, cy + (fy - cy) / d * DRIFT_PX
    return (round(cx), round(cy))


def _crop(x, y, z=1.0):
    house = _house()
    if house is None:
        return Image.new("RGB", (W, W), NIGHT)
    size = W / z
    img = house.crop((round(x - size / 2), round(y - size / 2), round(x + size / 2), round(y + size / 2)))
    return img if img.size == (W, W) else img.resize((W, W), Image.BILINEAR)


def _scene(view):
    now = _clock()
    _CAM.aim(_target(view), now)
    x, y, z, arrived = _CAM.frame(now)
    if arrived:
        _CAM.settled = True
    return _crop(x, y, z), arrived


# --- pixel UI ---------------------------------------------------------------------------

def _pf():
    return ui_common.font("PixelifySans[wght].ttf", 10)  # 1 font px = 1 screen px: crisp with fontmode "1"


def _ptext(draw, xy, s, fill, max_w=None, anchor="la"):
    draw.fontmode = "1"
    return ui_common.text(draw, xy, s, _pf(), fill, anchor=anchor, max_w=max_w)


@functools.lru_cache(maxsize=256)
def _big_mask(s):
    f = _pf()
    w = max(1, math.ceil(f.getlength(s)))
    m = Image.new("L", (w, 14), 0)
    d = ImageDraw.Draw(m)
    d.fontmode = "1"
    d.text((0, 0), s, font=f, fill=255)
    return m.resize((w * 2, 28), Image.NEAREST)


def _big(img, xy, s, fill, max_w=None):
    """2x pixel text: rendered at 1 px per font pixel, NEAREST-doubled - uniform 2 px pixels."""
    s = ui_common.fit(s, _pf(), max_w / 2) if max_w else ui_common.glyph_safe(s, _pf())
    m = _big_mask(s)
    x, y = int(xy[0]), int(xy[1])
    img.paste(fill, (x, y, x + m.width, y + m.height), m)
    return m.width


DIALOG = (34, 134, 206, 204)


def _box(draw, box):
    """RPG window: cream 2 px border, darker inner line, navy fill, stepped corners."""
    x0, y0, x1, y1 = box
    for inset, color in ((0, BOX_EDGE), (2, BOX_SHADE), (4, BOX)):
        c = 4
        a0, b0, a1, b1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
        draw.polygon([(a0 + c, b0), (a1 - c, b0), (a1, b0 + c), (a1, b1 - c), (a1 - c, b1), (a0 + c, b1),
                      (a0, b1 - c), (a0, b0 + c)], fill=color)


def _row_w(y, right=DIALOG[2] - 8, left=DIALOG[0] + 8):
    """Usable text width of a dialog row at y (the round bezel cuts the box corners)."""
    half = ui_common.safe_half_width(y + 6)
    return max(20, min(right, W / 2 + half - 4) - max(left, W / 2 - half + 4))


def _label(img, xy, s, fill, max_w):
    """Selected-row text: 2x pixel font when the whole string fits, otherwise the
    crisp 1x size (vertically centered on the same line) - a full song title
    beats a big truncated one."""
    if ui_common.text_len(ui_common.glyph_safe(s, _pf()), _pf()) * 2 <= max_w:
        return _big(img, xy, s, fill)
    return _ptext(ImageDraw.Draw(img), (xy[0], xy[1] + 8), s, fill, max_w=max_w)


def _cursor(draw, x, y, color=GOLD):
    draw.polygon([(x, y), (x, y + 10), (x + 5, y + 5)], fill=color)


def _strip(img, y, text):
    """Small title strip (Task 12 swaps this for the wooden room sign)."""
    draw = ImageDraw.Draw(img)
    w = min(150, ui_common.text_len(ui_common.glyph_safe(text, _pf()), _pf()) + 16)
    _box(draw, (120 - w / 2, y - 9, 120 + w / 2, y + 9))
    _ptext(draw, (120, y), text, CREAM, max_w=w - 12, anchor="mm")


def _tail(s, max_w):
    f = _pf()
    if ui_common.text_len(s, f) <= max_w:
        return s
    k = len(s)
    while k > 1 and ui_common.text_len("…" + s[-k:], f) > max_w:
        k -= 1
    return "…" + s[-k:]


def _value_text(row):
    if row.kind == "toggle":
        return "AN" if row.value else "AUS"
    if row.kind == "stepper":
        return f"{max(0, min(row.value, row.max))}/{row.max}"
    return str(row.value)


# --- views ------------------------------------------------------------------------

def draw_list(view, ctx):
    img, arrived = _scene(view)
    if not arrived:
        return img
    draw = ImageDraw.Draw(img)
    n = len(view.items)
    sel = max(0, min(view.sel, n - 1))
    item = view.items[sel]
    _box(draw, DIALOG)
    if sel > 0:
        _ptext(draw, (44, 139), view.items[sel - 1].label, DIMC, max_w=_row_w(139) - 30)
    _ptext(draw, (198, 139), f"{sel + 1}/{n}", DIMC, anchor="ra")
    color = RED if item.tone == "danger" else (DIMC if item.tone == "muted" else CREAM)
    _cursor(draw, 40, 156)
    _label(img, (50, 148), item.label, color, _row_w(158) - 10)
    if item.sub:
        _ptext(draw, (50, 173), item.sub, GOLD, max_w=_row_w(173) - 10)
    if sel + 1 < n:
        _ptext(draw, (44, 187), view.items[sel + 1].label, DIMC, max_w=_row_w(187))
    return img


def draw_message(view, ctx):
    img, arrived = _scene(view)
    if not arrived:
        return img
    if view.subtitle:
        _strip(img, 120, view.subtitle)
    draw = ImageDraw.Draw(img)
    _box(draw, DIALOG)
    color = {"busy": CREAM, "error": RED, "success": GREEN, "info": CREAM}[view.mood]
    text = view.text
    if view.mood == "busy":
        text = text.rstrip(".") + "." * (ui_common.busy_phase(0.5, 3) + 1)
    _label(img, (44, 142), text, color, _row_w(150) - 4)
    y = 170
    for ln in ui_common.wrap(view.detail, _pf(), _row_w(176), 1 if view.hint else 2):
        _ptext(draw, (44, y), ln, CREAM)
        y += 12
    if view.hint:
        _ptext(draw, (44, 187), view.hint, DIMC, max_w=_row_w(187))
    return img


def draw_settings(view, ctx):
    img, arrived = _scene(view)
    if not arrived:
        return img
    _strip(img, 120, view.title)
    draw = ImageDraw.Draw(img)
    n = len(view.rows)
    sel = max(0, min(view.sel, n - 1))
    row = view.rows[sel]
    _box(draw, DIALOG)
    if sel > 0:
        prev = view.rows[sel - 1]
        _ptext(draw, (44, 139), f"{prev.label}: {_value_text(prev)}", DIMC, max_w=_row_w(139) - 30)
    _ptext(draw, (198, 139), f"{sel + 1}/{n}", DIMC, anchor="ra")
    _cursor(draw, 40, 156)
    _label(img, (50, 148), row.label, CREAM, _row_w(158) - 10)
    _ptext(draw, (50, 173), _value_text(row), GOLD, max_w=_row_w(173) - 10)
    if sel + 1 < n:
        nxt = view.rows[sel + 1]
        _ptext(draw, (44, 187), f"{nxt.label}: {_value_text(nxt)}", DIMC, max_w=_row_w(187))
    return img


def _bar(draw, x0, y0, cells, frac, cell=3):
    lit = round(cells * max(0.0, min(1.0, frac)))
    for k in range(cells):
        x = x0 + k * cell
        draw.rectangle([x, y0, x + cell - 2, y0 + 5], fill=GOLD if k < lit else BOX_SHADE)


def draw_playing(view, ctx):
    img, arrived = _scene(view)
    if not arrived:
        return img
    draw = ImageDraw.Draw(img)
    _box(draw, DIALOG)
    _label(img, (44, 140), view.title, CREAM, _row_w(148) - 4)
    _ptext(draw, (44, 165), view.artist, GOLD, max_w=_row_w(165))
    progress = view.position / view.duration if view.duration else 0.0
    _bar(draw, 48, 178, 40, progress)
    _ptext(draw, (48, 187), f"{fmt_time(view.position)}/{fmt_time(view.duration)}", DIMC)
    if view.playing:
        draw.rectangle([178, 177, 180, 185], fill=CREAM)
        draw.rectangle([184, 177, 186, 185], fill=CREAM)
    else:
        _cursor(draw, 178, 176, CREAM)
    return img


def draw_code(view, ctx):
    img, arrived = _scene(view)
    if not arrived:
        return img
    draw = ImageDraw.Draw(img)
    _box(draw, (34, 112, 206, 204))
    _ptext(draw, (44, 118), "Gehe zu", DIMC)
    _ptext(draw, (44, 131), view.url, CREAM, max_w=_row_w(131))
    _ptext(draw, (44, 147), "Code:", DIMC)
    _big(img, (44, 158), view.code, GOLD, max_w=_row_w(166))
    _ptext(draw, (44, 188), "Warte auf Bestätigung …", DIMC, max_w=_row_w(188))
    return img


def draw_progress(view, ctx):
    img, arrived = _scene(view)
    if not arrived:
        return img
    draw = ImageDraw.Draw(img)
    _box(draw, DIALOG)
    _big(img, (44, 140), f"{view.current}/{view.total}", CREAM)
    _bar(draw, 48, 167, 40, view.current / view.total if view.total else 0.0)
    if view.done:
        _big(img, (44, 175), "Fertig!", GREEN)
    elif view.track:
        _ptext(draw, (44, 180), view.track, DIMC, max_w=_row_w(180))
    return img


def draw_password(view, ctx):
    img, arrived = _scene(view)
    if not arrived:
        return img
    draw = ImageDraw.Draw(img)
    _box(draw, (34, 112, 206, 204))
    _ptext(draw, (44, 118), view.ssid, DIMC, max_w=_row_w(118))
    _ptext(draw, (44, 131), _tail(view.typed + "_", _row_w(131)), CREAM)
    n = len(view.charset)
    for k, x in ((-2, 78), (-1, 94), (1, 140), (2, 156)):
        ch = view.charset[(view.char_idx + k) % n]
        _ptext(draw, (x, 157), "_" if ch == " " else ch, DIMC, anchor="mm")
    ch = view.charset[view.char_idx]
    ch = "_" if ch == " " else ch
    w = _big_mask(ui_common.glyph_safe(ch, _pf())).width
    draw.rectangle([117 - w / 2 - 4, 143, 117 + w / 2 + 4, 171], outline=CREAM, width=2)
    _big(img, (117 - w / 2, 144), ch, GOLD)
    _ptext(draw, (44, 186), "Dreh / Klick / Shuffle=Lösch / Play=OK", DIMC, max_w=_row_w(186))
    return img


def draw_status(img, sv, ctx):
    ui_common.draw_ring_status(img, sv, {"track": (60, 50, 70), "fill": GOLD, "low": RED, "off": (90, 80, 100),
                                         "wifi": CREAM, "bt": (120, 170, 255), "text": CREAM, "accent": GREEN,
                                         "font": _pf(), "segments": 10, "dot": "square"})


def draw_quick_connect(img, qc, ctx):
    draw = ImageDraw.Draw(img)
    _box(draw, (40, 62, 200, 120))  # above the dialog box, which stays visible underneath
    _label(img, (52, 69), qc.label, RED if qc.error else CREAM, 136)
    _bar(draw, 52, 103, 45, qc.progress)


def draw_shutdown(ctx):
    x, y = ROOMS["schlafzimmer"]
    img = _crop(x, y + VIEW_DY)
    draw = ImageDraw.Draw(img)
    _box(draw, DIALOG)
    _big(img, (52, 152), "Gute Nacht…", CREAM)
    return img
