"""Colour schemes for the tile: pairs of colours, digits on a background.

Three dark and three light, each named for the colour of its DIGITS, since
on a tile three centimetres wide that is the difference that shows.

  Dark   White, Green, Amber     bright digits on a dark tile
  Light  Black, Blue, Red        deep digits on a pale tile

White and Black are the Daybook/Palestra ink and paper, either way round
(the original dark and light). The light colours are the deep versions on
purpose: a bright LED green or amber is unreadable on a pale background.

Plain data, no AppKit: the view turns the hex strings into colours.
"""

from __future__ import annotations

from dataclasses import dataclass

INK = "#1D1B17"
PAPER = "#FAF7F0"
RULE = "#DFD9CC"
BLACK = "#0A0A0A"


@dataclass(frozen=True)
class Scheme:
    key: str          # stored in state.json
    label: str        # shown in the menu
    tile: str         # background, #RRGGBB
    digits: str       # numerals, #RRGGBB
    edge: str         # hairline border, #RRGGBB
    edge_alpha: float = 1.0
    light: bool = False


def _dark(key: str, label: str, colour: str) -> Scheme:
    """A bright colour on black, with a faint hairline of the same colour."""
    return Scheme(key, label, BLACK, colour, colour, 0.28)


def _light(key: str, label: str, colour: str) -> Scheme:
    """A deep colour on paper, with the portfolio's hairline rule."""
    return Scheme(key, label, PAPER, colour, RULE, light=True)


# Keys are what state.json stores and never change with the labels: "ink"
# and "paper" are the schemes now shown as White and Black.
SCHEMES: tuple[Scheme, ...] = (
    Scheme("ink", "White", INK, PAPER, PAPER, 0.16),
    _dark("green", "Green", "#33FF33"),
    _dark("amber", "Amber", "#FFB000"),
    _light("paper", "Black", INK),
    _light("navy", "Blue", "#24549A"),     # Daybook's accent
    _light("crimson", "Red", "#B3261E"),
)

# Dark by default: the tile sits over Meet, which is dark, and a pale tile
# beside the camera is a small lamp.
DEFAULT = "ink"

# Scheme names from earlier versions that no longer exist, and what each
# becomes: the nearest scheme of the same lightness.
RETIRED = {
    # 1.1.0
    "terminal": "green",
    "slate": "paper",
    "witching-hour": "ink",
    "crimson-veil": "ink",
    # 1.1.1 (a red and a light blue on black)
    "red": "amber",
    "blue": "ink",
}

# The two flashes are the same in every scheme, and mean what the colours
# mean on a traffic light: amber for the warning, red for the end. Fixed
# rather than derived from the scheme, so that no scheme's own colours can
# make one flash look like the other.
WARNING_TILE = "#FFB000"
WARNING_DIGITS = "#1D1B17"
ALERT_TILE = "#B3261E"
ALERT_DIGITS = "#FFFFFF"

_BY_KEY = {scheme.key: scheme for scheme in SCHEMES}


def resolve(key) -> str | None:
    """The current key for a stored one (following retired names), or None
    if it was never a scheme."""
    if not isinstance(key, str):
        return None
    key = RETIRED.get(key, key)
    return key if key in _BY_KEY else None


def is_known(key) -> bool:
    return isinstance(key, str) and key in _BY_KEY


def get(key: str) -> Scheme:
    """The scheme for `key`, or the default for anything unrecognised."""
    return _BY_KEY[resolve(key) or DEFAULT]
