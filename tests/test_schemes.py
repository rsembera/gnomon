"""Colour schemes: well-formed, visibly distinct, and legible."""

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
    assert contrast(schemes.WARNING_TILE, schemes.WARNING_DIGITS) >= 4.5


def test_both_flashes_change_the_tile_in_every_scheme():
    # A flash is the TILE changing colour. If a scheme's tile were already
    # the flash colour, that flash would be invisible in that scheme.
    flashes = {schemes.WARNING_TILE.lower(), schemes.ALERT_TILE.lower()}
    for s in schemes.SCHEMES:
        assert s.tile.lower() not in flashes, s.key


def test_the_two_flashes_cannot_be_mistaken_for_each_other():
    assert schemes.WARNING_TILE.lower() != schemes.ALERT_TILE.lower()
    assert contrast(schemes.WARNING_TILE, schemes.ALERT_TILE) >= 3.0  # amber is far lighter


def test_three_dark_then_three_light():
    assert [s.light for s in schemes.SCHEMES] == [False] * 3 + [True] * 3
    for s in schemes.SCHEMES:
        # "Light" and "dark" describe the tile: pale tile, deep digits, or the reverse.
        assert (luminance(s.tile) > luminance(s.digits)) is s.light, s.key


def test_schemes_differ_where_it_shows():
    # 1.1.0 had three dark schemes with near-identical off-white digits.
    # Within a group the tiles are (nearly) the same, so the digits must not be.
    for light in (False, True):
        digits = [s.digits.lower() for s in schemes.SCHEMES if s.light is light]
        assert len(set(digits)) == len(digits) == 3


def test_stored_keys_are_unchanged_by_the_relabelling():
    # Ink and Paper are shown as White and Black; saved settings still say ink/paper.
    assert schemes.get("ink").label == "White"
    assert schemes.get("paper").label == "Black"


def test_retired_names_resolve_to_a_current_scheme():
    for old, new in schemes.RETIRED.items():
        assert not schemes.is_known(old)
        assert schemes.is_known(new)
        assert schemes.resolve(old) == new and schemes.get(old).key == new
    assert schemes.resolve("plaid") is None and schemes.resolve(7) is None


def test_default_exists_and_unknown_keys_fall_back_to_it():
    assert schemes.is_known(schemes.DEFAULT)
    assert schemes.get("plaid").key == schemes.DEFAULT
    assert not schemes.is_known(None) and not schemes.is_known(3)
