"""Colour schemes for the tile.

Ink and Paper are the Daybook/Palestra palette, either way round. The other
four take their names and their colours from Libram's themes (card
background, text and border of the theme of the same name), so "Witching
Hour" here is the Witching Hour there.

Plain data, no AppKit: the view turns the hex strings into colours.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scheme:
    key: str          # stored in state.json
    label: str        # shown in the menu
    tile: str         # background, #RRGGBB
    digits: str       # numerals, #RRGGBB
    edge: str         # hairline border, #RRGGBB
    edge_alpha: float = 1.0


SCHEMES: tuple[Scheme, ...] = (
    Scheme("ink", "Ink", "#1D1B17", "#FAF7F0", "#FAF7F0", 0.16),
    Scheme("paper", "Paper", "#FAF7F0", "#1D1B17", "#DFD9CC"),
    Scheme("slate", "Slate", "#F0F2F4", "#4A6080", "#C0C8D0"),
    Scheme("witching-hour", "Witching Hour", "#1C1E2A", "#E8E6F0", "#6878B0"),
    Scheme("crimson-veil", "Crimson Veil", "#1A1214", "#F0E8EA", "#802040"),
    Scheme("terminal", "Terminal", "#0A0A0A", "#33FF33", "#1A401A"),
)

# Dark by default: the tile sits over Meet, which is dark, and a pale tile
# beside the camera is a small lamp.
DEFAULT = "ink"

# The end-of-session flash is the same red in every scheme, so it cannot be
# mistaken for the warning flash (which is the scheme's own colours swapped).
ALERT_TILE = "#B3261E"
ALERT_DIGITS = "#FFFFFF"

_BY_KEY = {scheme.key: scheme for scheme in SCHEMES}


def is_known(key) -> bool:
    return isinstance(key, str) and key in _BY_KEY


def get(key: str) -> Scheme:
    """The scheme for `key`, or the default for anything unrecognised."""
    return _BY_KEY.get(key, _BY_KEY[DEFAULT])
