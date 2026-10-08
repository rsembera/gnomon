"""Clock-face logic: what the digits say, when they next change, and where
the tile sits. No AppKit in here, so all of it is unit-tested.

Rectangles are (x, y, width, height) tuples in AppKit screen coordinates:
origin at the BOTTOM-left, y increasing upward. That is the convention
NSWindow frames and NSScreen frames already use, so nothing is flipped on
the way in or out.
"""

from __future__ import annotations

import math

Rect = tuple[float, float, float, float]
Size = tuple[float, float]

# Tile height in points. Everything else (width, digit size, padding) is
# derived from it, so "how big is the clock" is always this one number.
MIN_HEIGHT = 20.0
MAX_HEIGHT = 240.0
DEFAULT_HEIGHT = 40.0
SIZE_PRESETS: tuple[tuple[str, float], ...] = (
    ("Small", 28.0),
    ("Medium", 40.0),
    ("Large", 60.0),
)

# Proportions, as fractions of tile height.
CAP_FRACTION = 0.50  # height of the digits themselves
PAD_FRACTION = 0.28  # breathing room left and right of the digits

# The widest string the face ever shows. Digits are drawn monospaced, so
# every time of day fits in the box this one occupies.
WIDEST = "00:00:00"

# Gap between the tile and the bottom of the menu bar at the default spot.
TOP_GAP = 6.0

# How much of the tile must remain on a screen for it to count as
# reachable (i.e. there is something to grab and drag back).
GRAB_MARGIN = 24.0


def format_time(hour: int, minute: int, second: int, twenty_four: bool) -> str:
    """HH:MM:SS in 24-hour mode; H:MM:SS without AM/PM in 12-hour mode.

    No AM/PM: the tile is meant to be as small as it can be, and nobody
    timing a session is unsure which half of the day it is.
    """
    if twenty_four:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{hour % 12 or 12}:{minute:02d}:{second:02d}"


def seconds_to_next_tick(now: float) -> float:
    """Delay until just after the next whole second of wall-clock time.

    The timer is re-armed from the wall clock after every tick rather than
    repeating at a fixed 1.0s, so lateness never accumulates: a tick that
    fires 30ms late is followed by one 970ms later, not 1000ms. The few
    milliseconds of cushion keep an early-firing timer from landing just
    BEFORE the boundary and repainting the second that is already showing.
    """
    return (1.0 - math.fmod(now, 1.0)) + 0.004


def clamp_height(height: float) -> float:
    return max(MIN_HEIGHT, min(MAX_HEIGHT, float(height)))


def aspect_ratio(ref_width: float, ref_cap: float) -> float:
    """Tile width / tile height, from the font's own metrics.

    ref_width is the width of WIDEST and ref_cap the cap height, both
    measured at the same font size. Deriving the ratio from the font means
    a different typeface or weight still gets a tile that fits.
    """
    return CAP_FRACTION * (ref_width / ref_cap) + 2.0 * PAD_FRACTION


def tile_size(height: float, aspect: float) -> Size:
    """Whole-point tile size for a given height."""
    height = round(clamp_height(height))
    return (float(round(height * aspect)), float(height))


def digit_scale(size: Size, box_width: float, cap: float) -> float:
    """Factor to apply to a font size so its digits fit a tile of `size`.

    box_width and cap are the width of WIDEST and the cap height as measured
    at the font size being corrected. Normally height decides (the window
    is aspect-locked), but width gets a veto so the digits can never be
    clipped: by a tile narrower than its ideal ratio, or by small sizes,
    which the system font sets proportionally wider.
    """
    width, height = size
    by_height = CAP_FRACTION * height / cap
    by_width = (width - 2.0 * PAD_FRACTION * height) / box_width
    return max(0.0, min(by_height, by_width))


def top_centre_origin(screen: Rect, visible: Rect, size: Size) -> tuple[float, float]:
    """Origin that puts the tile at the top centre of a screen.

    Centred on the full screen frame (on a MacBook that is where the camera
    is) and tucked just under the menu bar, whose bottom edge is the top of
    the visible frame.
    """
    sx, _sy, sw, _sh = screen
    _vx, vy, _vw, vh = visible
    width, height = size
    return (round(sx + (sw - width) / 2.0), round(vy + vh - height - TOP_GAP))


def is_reachable(frame: Rect, screens: list[Rect], margin: float = GRAB_MARGIN) -> bool:
    """True if enough of the tile is on some screen to grab it.

    Guards against a saved position on a monitor that is no longer plugged
    in: the clock would otherwise open somewhere it cannot be seen or
    dragged back from.
    """
    x, y, w, h = frame
    need_w = min(margin, w)
    need_h = min(margin, h)
    for sx, sy, sw, sh in screens:
        overlap_w = min(x + w, sx + sw) - max(x, sx)
        overlap_h = min(y + h, sy + sh) - max(y, sy)
        if overlap_w >= need_w and overlap_h >= need_h:
            return True
    return False


def resized_frame(frame: Rect, size: Size) -> Rect:
    """New frame of `size` that keeps the top edge and horizontal centre.

    The clock usually lives at the top of the screen under the camera, so
    growing it downward from a fixed top-centre keeps it where it was put.
    """
    x, y, w, h = frame
    new_w, new_h = size
    return (round(x + (w - new_w) / 2.0), round(y + h - new_h), new_w, new_h)
