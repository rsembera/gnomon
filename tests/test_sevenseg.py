"""Seven-segment geometry for the LED face."""

import pytest

from core import sevenseg

# What each numeral lights on any seven-segment display ever made.
EXPECTED = {
    "0": {"a", "b", "c", "d", "e", "f"},
    "1": {"b", "c"},
    "2": {"a", "b", "g", "e", "d"},
    "3": {"a", "b", "g", "c", "d"},
    "4": {"f", "g", "b", "c"},
    "5": {"a", "f", "g", "c", "d"},
    "6": {"a", "f", "g", "e", "c", "d"},
    "7": {"a", "b", "c"},
    "8": {"a", "b", "c", "d", "e", "f", "g"},
    "9": {"a", "b", "c", "d", "f", "g"},
}


def bounds(shapes):
    xs = [x for shape in shapes for x, _y in shape]
    ys = [y for shape in shapes for _x, y in shape]
    return min(xs), min(ys), max(xs), max(ys)


def test_every_numeral_lights_the_right_segments():
    assert {digit: set(on) for digit, on in sevenseg.SEGMENTS.items()} == EXPECTED


def test_no_two_numerals_look_alike():
    assert len({frozenset(on) for on in sevenseg.SEGMENTS.values()}) == 10


def test_every_digit_is_the_same_width():
    assert len({sevenseg.advance(str(n)) for n in range(10)}) == 1
    widths = {sevenseg.text_width(f"{n}{n}:{n}{n}:{n}{n}", 20.0) for n in range(10)}
    assert len(widths) == 1


def test_a_colon_is_narrower_than_a_digit():
    assert sevenseg.advance(":") < sevenseg.advance("0") / 2


def test_text_width_scales_with_height_and_counts_the_gaps():
    assert sevenseg.text_width("", 20.0) == 0.0
    assert sevenseg.text_width("8", 20.0) == pytest.approx(20 * sevenseg.DIGIT_WIDTH)
    assert sevenseg.text_width("88", 20.0) == pytest.approx(
        20 * (2 * sevenseg.DIGIT_WIDTH + sevenseg.SPACING)
    )
    assert sevenseg.text_width("00:00:00", 40.0) == pytest.approx(
        2 * sevenseg.text_width("00:00:00", 20.0)
    )


@pytest.mark.parametrize("name", list(sevenseg.ALL_SEGMENTS))
def test_each_segment_stays_inside_the_digit_cell(name):
    left, bottom, right, top = bounds([sevenseg.segment(name)])
    assert 0 <= left and right <= sevenseg.DIGIT_WIDTH + 1e-9
    assert 0 <= bottom and top <= 1 + 1e-9


def test_the_eight_fills_its_cell_exactly():
    left, bottom, right, top = bounds([sevenseg.segment(n) for n in sevenseg.ALL_SEGMENTS])
    assert (left, bottom) == pytest.approx((0.0, 0.0))
    assert (right, top) == pytest.approx((sevenseg.DIGIT_WIDTH, 1.0))


def test_segments_do_not_touch_their_neighbours():
    # Top bar and the two upper uprights: daylight between them at the corners.
    a, f, b = (sevenseg.segment(n) for n in "afb")
    assert min(x for x, _ in a) > min(x for x, _ in f) + sevenseg.THICKNESS / 2
    assert max(y for _, y in f) < max(y for _, y in a)
    assert max(y for _, y in b) < 1.0


def test_unknown_segment_is_an_error():
    with pytest.raises(ValueError):
        sevenseg.segment("h")


def test_lit_and_unlit_make_seven_per_digit():
    for digit, on in sevenseg.SEGMENTS.items():
        lit, unlit = sevenseg.polygons(digit, 20.0)
        assert len(lit) == len(on) and len(lit) + len(unlit) == 7, digit


def test_a_colon_is_two_lit_dots_and_nothing_unlit():
    lit, unlit = sevenseg.polygons(":", 20.0)
    assert len(lit) == 2 and unlit == []


def test_colon_dots_are_symmetric_about_mid_height():
    lit, _ = sevenseg.polygons(":", 20.0)
    _l, bottom, _r, top = bounds(lit)
    assert (bottom + top) / 2 == pytest.approx(10.0)


def test_the_time_is_as_tall_as_asked_and_centred_on_its_box():
    for text in ("00:00:00", "8:42:17", "12:34:56"):
        lit, unlit = sevenseg.polygons(text, 20.0)
        left, bottom, right, top = bounds(lit + unlit)
        assert (bottom, top) == pytest.approx((0.0, 20.0))
        # The lean is about mid-height, so the slanted text overhangs its
        # upright box equally on both sides.
        width = sevenseg.text_width(text, 20.0)
        assert -left == pytest.approx(right - width)
        assert 0 < -left <= 20 * sevenseg.SLANT / 2 + 1e-9


def test_neighbouring_glyphs_never_overlap_despite_the_lean():
    lit, unlit = sevenseg.polygons("88", 20.0)
    shapes = lit + unlit
    first, second = shapes[:7], shapes[7:]
    assert bounds(first)[2] < bounds(second)[0]
