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
        assert y + 40 == 918 - clockface.EDGE_GAP

    def test_top_centre_on_a_second_screen_uses_that_screens_origin(self):
        screen = (1470.0, 100.0, 1920.0, 1080.0)
        visible = (1470.0, 100.0, 1920.0, 1055.0)
        x, y = clockface.top_centre_origin(screen, visible, (144.0, 40.0))
        assert x == 1470 + (1920 - 144) / 2
        assert y == 100 + 1055 - 40 - clockface.EDGE_GAP

    # The same screen with a 70pt Dock along the bottom.
    DOCKED = (0.0, 70.0, 1470.0, 848.0)

    def test_six_anchors_clockwise_from_top_centre(self):
        assert [key for key, _label in clockface.ANCHORS] == [
            "top-centre", "top-right", "bottom-right",
            "bottom-centre", "bottom-left", "top-left",
        ]
        assert all(clockface.is_anchor(key) for key, _label in clockface.ANCHORS)
        assert not clockface.is_anchor("middle") and not clockface.is_anchor(None)

    def test_each_anchor_parks_the_tile_against_its_edges(self):
        gap, size = clockface.EDGE_GAP, (144.0, 40.0)
        left, right = 0 + gap, 1470 - 144 - gap
        centre = (1470 - 144) / 2
        top, bottom = 70 + 848 - 40 - gap, 70 + gap   # under the menu bar / above the Dock
        expected = {
            "top-centre": (centre, top), "top-right": (right, top),
            "bottom-right": (right, bottom), "bottom-centre": (centre, bottom),
            "bottom-left": (left, bottom), "top-left": (left, top),
        }
        for anchor, origin in expected.items():
            assert clockface.anchored_origin(self.SCREEN, self.DOCKED, size, anchor) == origin, anchor

    def test_every_anchor_keeps_the_whole_tile_in_the_visible_frame(self):
        vx, vy, vw, vh = self.DOCKED
        for size in ((72.0, 20.0), (144.0, 40.0), (863.0, 240.0)):
            for anchor, _label in clockface.ANCHORS:
                x, y = clockface.anchored_origin(self.SCREEN, self.DOCKED, size, anchor)
                assert vx <= x and x + size[0] <= vx + vw, (anchor, size)
                assert vy <= y and y + size[1] <= vy + vh, (anchor, size)

    def test_a_dock_on_the_side_pushes_the_corners_in_but_not_the_centre(self):
        side_dock = (70.0, 0.0, 1400.0, 918.0)  # Dock on the left
        x, _y = clockface.anchored_origin(self.SCREEN, side_dock, (144.0, 40.0), "top-left")
        assert x == 70 + clockface.EDGE_GAP
        x, _y = clockface.anchored_origin(self.SCREEN, side_dock, (144.0, 40.0), "top-centre")
        assert x == (1470 - 144) / 2  # still under the camera

    def test_top_centre_is_the_top_centre_anchor(self):
        assert clockface.top_centre_origin(self.SCREEN, self.VISIBLE, (144.0, 40.0)) == (
            clockface.anchored_origin(self.SCREEN, self.VISIBLE, (144.0, 40.0), "top-centre")
        )

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


class TestEdges:
    SIZE = (144.0, 40.0)

    def test_the_middle_is_not_an_edge(self):
        assert clockface.edge_at((72, 20), self.SIZE) is None
        assert clockface.edge_at((10, 10), self.SIZE) is None

    def test_each_side_and_corner_is_found(self):
        assert clockface.edge_at((2, 20), self.SIZE) == "left"
        assert clockface.edge_at((142, 20), self.SIZE) == "right"
        assert clockface.edge_at((72, 38), self.SIZE) == "top"
        assert clockface.edge_at((72, 2), self.SIZE) == "bottom"
        assert clockface.edge_at((2, 38), self.SIZE) == "top-left"
        assert clockface.edge_at((142, 38), self.SIZE) == "top-right"
        assert clockface.edge_at((2, 2), self.SIZE) == "bottom-left"
        assert clockface.edge_at((142, 2), self.SIZE) == "bottom-right"

    def test_every_answer_is_a_known_edge(self):
        for x in range(0, 145, 4):
            for y in range(0, 41, 2):
                edge = clockface.edge_at((x, y), self.SIZE)
                assert edge is None or edge in clockface.EDGES

    def test_a_tiny_tile_still_has_a_middle_to_drag(self):
        # 20pt tall: a 6pt margin top and bottom would leave 8pt; it shrinks to 4.
        size = (72.0, 20.0)
        assert clockface.edge_at((36, 5), size) is None
        assert clockface.edge_at((36, 15), size) is None
        assert clockface.edge_at((36, 3), size) == "bottom"


class TestEdgeResize:
    ASPECT = 3.6
    FRAME = (600.0, 800.0, 144.0, 40.0)   # top edge at 840, right edge at 744

    def drag(self, edge, dx=0.0, dy=0.0):
        return clockface.edge_resized_frame(self.FRAME, edge, dx, dy, self.ASPECT)

    def test_right_edge_follows_the_pointer_and_the_left_and_top_stay(self):
        x, y, w, h = self.drag("right", dx=72)
        assert (w, h) == (216.0, 60.0)
        assert x == 600 and y + h == 840

    def test_left_edge_follows_the_pointer_and_the_right_and_top_stay(self):
        x, y, w, h = self.drag("left", dx=-72)
        assert (w, h) == (216.0, 60.0)
        assert x + w == 744 and y + h == 840

    def test_bottom_edge_grows_downward_about_the_same_centre(self):
        x, y, w, h = self.drag("bottom", dy=-20)
        assert h == 60.0 and y + h == 840
        assert x + w / 2 == 600 + 72

    def test_top_edge_grows_upward_from_a_fixed_bottom(self):
        x, y, w, h = self.drag("top", dy=20)
        assert h == 60.0 and y == 800
        assert x + w / 2 == 600 + 72

    def test_dragging_inward_shrinks(self):
        assert self.drag("right", dx=-36)[2:] == (108.0, 30.0)
        assert self.drag("top", dy=-10)[3] == 30.0

    @pytest.mark.parametrize("corner,dx,dy,fixed", [
        ("bottom-right", 72, -20, (600, 840)),    # top-left stays
        ("bottom-left", -72, -20, (744, 840)),    # top-right stays
        ("top-right", 72, 20, (600, 800)),        # bottom-left stays
        ("top-left", -72, 20, (744, 800)),        # bottom-right stays
    ])
    def test_a_corner_keeps_the_opposite_corner_where_it_was(self, corner, dx, dy, fixed):
        x, y, w, h = self.drag(corner, dx=dx, dy=dy)
        assert (w, h) == (216.0, 60.0)
        opposite_x = x if "right" in corner else x + w
        opposite_y = y if "top" in corner else y + h
        assert (opposite_x, opposite_y) == fixed

    def test_at_a_corner_the_bigger_request_wins(self):
        # Mostly sideways: the width decides.
        assert self.drag("bottom-right", dx=72, dy=-2)[2:] == (216.0, 60.0)
        # Mostly downward: the height decides.
        assert self.drag("bottom-right", dx=2, dy=-20)[2:] == (216.0, 60.0)

    def test_size_stays_within_the_limits(self):
        assert self.drag("right", dx=5000)[3] == clockface.MAX_HEIGHT
        assert self.drag("right", dx=-5000)[3] == clockface.MIN_HEIGHT

    def test_no_movement_changes_nothing(self):
        for edge in clockface.EDGES:
            assert self.drag(edge) == self.FRAME, edge
