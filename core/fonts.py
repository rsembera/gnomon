"""Typefaces for the digits.

Plain data, no AppKit: ui/app.py turns a key into an actual font. Every
font here ships with macOS, so nothing is bundled, and every one has (or
can be given) numerals of equal width, without which the time would shimmy
as the seconds change. tests/test_ui.py checks both on the machine it runs
on. The last face, LED, is not a font at all: its seven-segment digits are
drawn (core/sevenseg.py).
"""

from __future__ import annotations

# (key stored in state.json, label shown in the menu)
FACES: tuple[tuple[str, str], ...] = (
    ("standard", "Standard"),      # the system font, as in 1.0
    ("serif", "Serif"),            # New York
    ("mono", "Mono"),              # SF Mono
    ("din", "DIN"),                # DIN Alternate Bold: the signage face
    ("typewriter", "Typewriter"),  # American Typewriter
    ("led", "LED"),                # seven-segment digits, drawn
)

DEFAULT = "standard"
LED = "led"

# 1.3.0 also had "rounded" (the system font's rounded cut), dropped because
# at this size it could not be told from Standard. A state file that still
# names it is simply not a known face any more and opens in the default.


def is_known(key) -> bool:
    return isinstance(key, str) and any(key == face for face, _label in FACES)
