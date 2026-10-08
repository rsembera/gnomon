"""Colour schemes for the tile: pairs of colours, digits on a background.

Ink and Paper are the Daybook/Palestra palette either way round (the
original dark and light). The rest are the LED-clock pairs: one bright
colour on black. The difference between schemes is carried by the DIGITS,
because on a tile three centimetres wide that is the only difference that
shows; 1.1.0's schemes varied the tint of a dark tile and all looked alike.

Plain data, no AppKit: the view turns the hex strings into colours.
"""

from __future__ import annotations

from dataclasses import dataclass

BLACK = "#0A0A0A"


@dataclass(frozen=True)
class Scheme:
    key: str          # stored in state.json
    label: str        # shown in the menu
    tile: str         # background, #RRGGBB
    digits: str       # numerals, #RRGGBB
    edge: str         # hairline border, #RRGGBB
    edge_alpha: float = 1.0


def _led(key: str, label: str, colour: str) -> Scheme:
    """A bright colour on black, with a faint hairline of the same colour."""
    return Scheme(key, label, BLACK, colour, colour, 0.28)


SCHEMES: tuple[Scheme, ...] = (
    Scheme("ink", "Ink", "#1D1B17", "#FAF7F0", "#FAF7F0", 0.16),
    Scheme("paper", "Paper", "#FAF7F0", "#1D1B17", "#DFD9CC"),
    _led("green", "Green", "#33FF33"),
    _led("amber", "Amber", "#FFB000"),
    _led("red", "Red", "#FF453A"),
    # A light blue: pure blue on black is the one LED colour that cannot be
    # read at a glance.
    _led("blue", "Blue", "#4FC3F7"),
)

# Dark by default: the tile sits over Meet, which is dark, and a pale tile
# beside the camera is a small lamp.
DEFAULT = "ink"

# Scheme names from 1.1.0 that no longer exist, and what each becomes.
RETIRED = {
    "terminal": "green",
    "slate": "paper",
    "witching-hour": "ink",
    "crimson-veil": "ink",
}

# The two flashes are the same in every scheme, and mean what the colours
# mean on a traffic light: amber for the warning, red for the end. Fixed
# rather than derived from the scheme, so that the Red and Amber schemes
# cannot make one flash look like the other.
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
