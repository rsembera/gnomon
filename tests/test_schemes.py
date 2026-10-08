"""Colour schemes: well-formed, distinct, and legible."""

import re

from core import schemes

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def luminance(hex_colour):
    def channel(value):
        value /= 255.0
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(int(hex_colour[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_keys_and_labels_are_unique():
    assert len({s.key for s in schemes.SCHEMES}) == len(schemes.SCHEMES)
    assert len({s.label for s in schemes.SCHEMES}) == len(schemes.SCHEMES)


def test_colours_are_well_formed():
    for s in schemes.SCHEMES:
        assert all(HEX.match(c) for c in (s.tile, s.digits, s.edge)), s.key
        assert 0 < s.edge_alpha <= 1


def test_digits_are_legible_on_every_tile():
    # WCAG AA for normal text is 4.5:1; a clock read at a glance wants at least that.
    for s in schemes.SCHEMES:
        assert contrast(s.tile, s.digits) >= 4.5, s.key
    assert contrast(schemes.ALERT_TILE, schemes.ALERT_DIGITS) >= 4.5


def test_the_end_flash_is_unlike_every_scheme_and_its_inverse():
    # Red must read as "the end", not as this scheme or its warning flash.
    for s in schemes.SCHEMES:
        assert schemes.ALERT_TILE.lower() not in (s.tile.lower(), s.digits.lower()), s.key


def test_default_exists_and_unknown_keys_fall_back_to_it():
    assert schemes.is_known(schemes.DEFAULT)
    assert schemes.get("plaid").key == schemes.DEFAULT
    assert not schemes.is_known(None) and not schemes.is_known(3)
