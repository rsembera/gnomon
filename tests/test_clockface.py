"""Clock-face logic: formatting, tick timing and tile geometry."""

import pytest

from core import clockface


class TestFormatTime:
    def test_24_hour_is_zero_padded(self):
        assert clockface.format_time(9, 5, 3, True) == "09:05:03"
        assert clockface.format_time(0, 0, 0, True) == "00:00:00"
        assert clockface.format_time(23, 59, 59, True) == "23:59:59"

    def test_12_hour_has_no_leading_zero_and_no_am_pm(self):
        assert clockface.format_time(9, 5, 3, False) == "9:05:03"
        assert clockface.format_time(21, 5, 3, False) == "9:05:03"

    def test_12_hour_midnight_and_noon_read_twelve(self):
        assert clockface.format_time(0, 0, 0, False) == "12:00:00"
        assert clockface.format_time(12, 30, 0, False) == "12:30:00"

    def test_nothing_is_wider_than_the_reference_string(self):
        for hour in range(24):
            for mode in (True, False):
                assert len(clockface.format_time(hour, 59, 59, mode)) <= len(clockface.WIDEST)


class TestTick:
    @pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.999])
    def test_lands_just_after_the_next_whole_second(self, fraction):
        now = 1_800_000_000 + fraction
        landing = now + clockface.seconds_to_next_tick(now)
        assert 1_800_000_001 <= landing < 1_800_000_001.01

    def test_a_late_tick_is_followed_by_a_short_wait(self):
        # Fired 30ms late: the next wait is ~970ms, so lateness never piles up.
        assert clockface.seconds_to_next_tick(1_800_000_000.03) == pytest.approx(0.974, abs=1e-3)


class TestTileGeometry:
    ASPECT = clockface.aspect_ratio(ref_width=430.0, ref_cap=70.0)

    def test_height_is_clamped(self):
        assert clockface.clamp_height(1) == clockface.MIN_HEIGHT
        assert clockface.clamp_height(10_000) == clockface.MAX_HEIGHT
        assert clockface.clamp_height(40) == 40.0

    def test_tile_size_is_whole_points_at_the_font_aspect(self):
        width, height = clockface.tile_size(40.4, self.ASPECT)
        assert height == 40.0
        assert width == round(40 * self.ASPECT)

    def test_presets_are_within_limits(self):
        for _label, height in clockface.SIZE_PRESETS:
            assert clockface.MIN_HEIGHT <= height <= clockface.MAX_HEIGHT

    def test_digits_fill_the_ideal_tile_exactly(self):
        size = (40 * self.ASPECT, 40.0)
        scale = clockface.digit_scale(size, 430.0, 70.0)
        assert scale * 70.0 == pytest.approx(clockface.CAP_FRACTION * 40)
        assert scale * 430.0 == pytest.approx(size[0] - 2 * clockface.PAD_FRACTION * 40)

    def test_a_narrow_tile_shrinks_the_digits_rather_than_clipping(self):
        ideal = clockface.digit_scale((40 * self.ASPECT, 40.0), 430.0, 70.0)
        narrow = clockface.digit_scale((80.0, 40.0), 430.0, 70.0)
        assert 0 < narrow < ideal
        assert narrow * 430.0 <= 80.0 - 2 * clockface.PAD_FRACTION * 40

    def test_degenerate_tile_scales_to_zero_not_negative(self):
        assert clockface.digit_scale((5.0, 40.0), 430.0, 70.0) == 0.0


class TestPlacement:
    # A 1470x956 MacBook Air screen with a 38pt menu bar and no Dock.
    SCREEN = (0.0, 0.0, 1470.0, 956.0)
    VISIBLE = (0.0, 0.0, 1470.0, 918.0)

    def test_top_centre_is_centred_and_just_under_the_menu_bar(self):
        x, y = clockface.top_centre_origin(self.SCREEN, self.VISIBLE, (144.0, 40.0))
        assert x == (1470 - 144) / 2
        assert y + 40 == 918 - clockface.TOP_GAP

    def test_top_centre_on_a_second_screen_uses_that_screens_origin(self):
        screen = (1470.0, 100.0, 1920.0, 1080.0)
        visible = (1470.0, 100.0, 1920.0, 1055.0)
        x, y = clockface.top_centre_origin(screen, visible, (144.0, 40.0))
        assert x == 1470 + (1920 - 144) / 2
        assert y == 100 + 1055 - 40 - clockface.TOP_GAP

    def test_on_screen_tile_is_reachable(self):
        assert clockface.is_reachable((600.0, 800.0, 144.0, 40.0), [self.SCREEN])

    def test_tile_in_the_menu_bar_is_reachable(self):
        # Above the visible frame but still on the screen: a legitimate spot.
        assert clockface.is_reachable((900.0, 925.0, 100.0, 28.0), [self.SCREEN])

    def test_tile_on_a_vanished_monitor_is_not_reachable(self):
        assert not clockface.is_reachable((2000.0, 500.0, 144.0, 40.0), [self.SCREEN])

    def test_a_sliver_left_on_screen_is_not_enough(self):
        assert not clockface.is_reachable((1460.0, 500.0, 144.0, 40.0), [self.SCREEN])

    def test_reachable_on_any_one_of_several_screens(self):
        second = (1470.0, 0.0, 1920.0, 1080.0)
        assert clockface.is_reachable((2000.0, 500.0, 144.0, 40.0), [self.SCREEN, second])

    def test_tiny_tile_needs_only_itself_on_screen(self):
        assert clockface.is_reachable((10.0, 10.0, 66.0, 20.0), [self.SCREEN])

    def test_resizing_keeps_the_top_edge_and_horizontal_centre(self):
        x, y, w, h = clockface.resized_frame((600.0, 800.0, 144.0, 40.0), (216.0, 60.0))
        assert (w, h) == (216.0, 60.0)
        assert y + h == 800 + 40          # top edge unmoved
        assert x + w / 2 == 600 + 144 / 2  # centre unmoved
