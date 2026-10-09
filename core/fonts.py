"""Typefaces for the digits.

Plain data, no AppKit: ui/app.py turns a key into an actual font. Every
face here ships with macOS, so nothing is bundled, and every one has (or
can be given) numerals of equal width, without which the time would shimmy
as the seconds change. tests/test_ui.py checks both on the machine it runs
on.
"""

from __future__ import annotations

# (key stored in state.json, label shown in the menu)
FACES: tuple[tuple[str, str], ...] = (
    ("standard", "Standard"),      # the system font, as in 1.0
    ("rounded", "Rounded"),        # the system font's rounded cut
    ("serif", "Serif"),            # New York
    ("mono", "Mono"),              # SF Mono
    ("din", "DIN"),                # DIN Alternate Bold: the signage face
    ("typewriter", "Typewriter"),  # American Typewriter
)

DEFAULT = "standard"


def is_known(key) -> bool:
    return isinstance(key, str) and any(key == face for face, _label in FACES)
