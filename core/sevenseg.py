"""Seven-segment digits, drawn rather than set in a font.

macOS has no LED-clock typeface, and bundling one would mean shipping (and
licensing) somebody else's font file. A seven-segment digit is seven
hexagons, so the LED face is simply drawn: this module works out the
shapes, ui/app.py fills them.

Everything is plain geometry (no AppKit) in the tile's own coordinates:
x to the right, y UP, with the origin at the bottom-left of the text.
All proportions are fractions of the digit height.

Segment names are the standard ones:

         aaa
        f   b
        f   b
         ggg
        e   c
        e   c
         ddd
"""

from __future__ import annotations

Point = tuple[float, float]
Polygon = list[Point]

DIGIT_WIDTH = 0.56   # width of a digit
THICKNESS = 0.13     # thickness of a segment, and the side of a colon dot
GAP = 0.02           # daylight between neighbouring segments
SPACING = 0.20       # space between one glyph and the next
# Lean to the right, as on a real display: horizontal shift per unit of
# height (about 6 degrees), applied about mid-height so the text as a whole
# stays centred where it was put.
SLANT = 0.105

COLON_DOTS = (0.3, 0.7)  # heights of the two dots: symmetric about the middle

SEGMENTS = {
    "0": "abcdef",
    "1": "bc",
    "2": "abdeg",
    "3": "abcdg",
    "4": "bcfg",
    "5": "acdfg",
    "6": "acdefg",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
}
ALL_SEGMENTS = "abcdefg"


def advance(character: str) -> float:
    """Width a character occupies, as a fraction of the digit height. Every
    digit is the same width, so the time cannot shimmy."""
    return THICKNESS if character == ":" else DIGIT_WIDTH


def text_width(text: str, height: float) -> float:
    """Width of `text` (unslanted box) at digit height `height`."""
    if not text:
        return 0.0
    return height * (sum(advance(c) for c in text) + SPACING * (len(text) - 1))


def _horizontal(y: float) -> Polygon:
    """A horizontal segment centred on height y: a flat hexagon."""
    half = THICKNESS / 2.0
    x0, x1 = half + GAP, DIGIT_WIDTH - half - GAP
    return [
        (x0, y), (x0 + half, y + half), (x1 - half, y + half),
        (x1, y), (x1 - half, y - half), (x0 + half, y - half),
    ]


def _vertical(x: float, y0: float, y1: float) -> Polygon:
    """A vertical segment centred on x, running from y0 up to y1."""
    half = THICKNESS / 2.0
    return [
        (x, y0), (x + half, y0 + half), (x + half, y1 - half),
        (x, y1), (x - half, y1 - half), (x - half, y0 + half),
    ]


def segment(name: str) -> Polygon:
    """One segment of a digit of height 1, upright, origin bottom-left."""
    half = THICKNESS / 2.0
    left, right = half, DIGIT_WIDTH - half
    upper = (0.5 + GAP, 1.0 - half - GAP)
    lower = (half + GAP, 0.5 - GAP)
    if name == "a":
        return _horizontal(1.0 - half)
    if name == "g":
        return _horizontal(0.5)
    if name == "d":
        return _horizontal(half)
    if name == "f":
        return _vertical(left, *upper)
    if name == "b":
        return _vertical(right, *upper)
    if name == "e":
        return _vertical(left, *lower)
    if name == "c":
        return _vertical(right, *lower)
    raise ValueError(f"no such segment: {name!r}")


def _colon() -> list[Polygon]:
    half = THICKNESS / 2.0
    return [
        [(0.0, y - half), (THICKNESS, y - half), (THICKNESS, y + half), (0.0, y + half)]
        for y in COLON_DOTS
    ]


def polygons(text: str, height: float) -> tuple[list[Polygon], list[Polygon]]:
    """(lit, unlit) polygons for `text` at digit height `height`.

    `unlit` is the segments each digit is NOT using. A real display shows
    them faintly, and drawing them that way is most of what makes this
    read as an LED clock rather than as an odd font.
    """
    lit: list[Polygon] = []
    unlit: list[Polygon] = []
    x = 0.0

    def place(shape: Polygon) -> Polygon:
        return [((x + px + SLANT * (py - 0.5)) * height, py * height) for px, py in shape]

    for character in text:
        if character == ":":
            lit.extend(place(dot) for dot in _colon())
        elif character in SEGMENTS:
            on = SEGMENTS[character]
            for name in ALL_SEGMENTS:
                (lit if name in on else unlit).append(place(segment(name)))
        x += advance(character) + SPACING
    return lit, unlit
