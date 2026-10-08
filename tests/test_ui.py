"""The panel and the view, exercised in-process.

Nothing is put on screen: the panel is built but never ordered front, and
the face is rendered into an off-screen bitmap. What these tests CANNOT
cover is the window server's side of things — the actual mouse drag and the
edge resize — so they pin the contract that makes those work instead
(a movable panel whose view takes the mouse-down itself, resizable and
aspect-locked).
"""

import time

import pytest

AppKit = pytest.importorskip("AppKit")

from core import alarm, clockface, schemes, state  # noqa: E402

# A fixed "now" for alert tests: 14:00:00 local on an ordinary day, an even
# second (so the flash is in its lit half; NOON + 1 is the unlit half).
NOW = float(int(time.mktime((2026, 10, 7, 14, 0, 0, 0, 0, -1))))
assert NOW % 2 == 0


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setenv("GNOMON_DATA_DIR", str(tmp_path))
    AppKit.NSApplication.sharedApplication()
    from ui.app import Controller

    made = []

    def make():
        c = Controller.alloc().init()
        c.build(show=False)
        made.append(c)
        return c

    yield make
    for c in made:
        AppKit.NSObject.cancelPreviousPerformRequestsWithTarget_(c)
        c._panel.setDelegate_(None)
        c._panel.close()


def frame_of(c):
    f = c._panel.frame()
    return (f.origin.x, f.origin.y, f.size.width, f.size.height)


def rgb(hex_colour):
    """An sRGB hex colour as the numbers it has in a rendered bitmap.

    Off-screen renders come back in the display's colour space (P3 on a
    MacBook), where a saturated sRGB colour such as the alert red has
    different component values; greys barely move. Converting the expected
    colour the same way keeps the comparisons exact on any display.
    """
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    colour = AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)
    colour = colour.colorUsingColorSpace_(AppKit.NSScreen.screens()[0].colorSpace())
    return (colour.redComponent(), colour.greenComponent(), colour.blueComponent())


def render(view):
    rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)
    return rep


def pixel(rep, x, y):
    colour = rep.colorAtX_y_(x, y)
    return (colour.redComponent(), colour.greenComponent(), colour.blueComponent())


def distance(a, b):
    return sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5


def tile_colour(view):
    """Colour of the tile itself: a pixel in the top margin, above the
    digits and clear of the rounded corners."""
    rep = render(view)
    return pixel(rep, rep.pixelsWide() // 2, max(2, rep.pixelsHigh() // 12))


def digit_pixel_box(view, scheme_key="ink"):
    """Bounding box, in pixels, of the digit pixels in an off-screen render.

    Returns (left, top, right, bottom, width, height) with y measured from
    the top. A digit pixel is one much nearer the scheme's digit colour than
    its tile colour.
    """
    scheme = schemes.get(scheme_key)
    tile, digits = rgb(scheme.tile), rgb(scheme.digits)
    rep = render(view)
    wide, high = rep.pixelsWide(), rep.pixelsHigh()
    xs, ys = [], []
    for y in range(high):
        for x in range(wide):
            if rep.colorAtX_y_(x, y).alphaComponent() < 0.9:
                continue
            colour = pixel(rep, x, y)
            if distance(colour, digits) < 0.35 * distance(colour, tile):
                xs.append(x)
                ys.append(y)
    assert xs, "no digits were drawn"
    return min(xs), min(ys), max(xs), max(ys), wide, high


class TestPanel:
    def test_floats_above_everything_on_every_space(self, controller):
        panel = controller()._panel
        assert panel.level() == AppKit.NSStatusWindowLevel
        assert panel.isFloatingPanel()
        assert not panel.hidesOnDeactivate()
        behaviour = panel.collectionBehavior()
        assert behaviour & AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        assert behaviour & AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary

    def test_never_takes_focus_from_the_call(self, controller):
        panel = controller()._panel
        assert panel.styleMask() & AppKit.NSWindowStyleMaskNonactivatingPanel
        assert not panel.canBecomeKeyWindow()
        assert not panel.canBecomeMainWindow()

    def test_drag_anywhere_contract(self, controller):
        # The view takes every press itself (so a click can answer a flash)
        # and starts the window drag from there; the panel must be movable
        # and must deliver the first click without needing to be activated.
        c = controller()
        assert c._panel.isMovable()
        assert not c._view.mouseDownCanMoveWindow()
        assert not c._panel.isMovableByWindowBackground()
        assert c._view.acceptsFirstMouse_(None)
        assert c._view.respondsToSelector_("mouseDown:")
        assert c._panel.respondsToSelector_("performWindowDragWithEvent:")

    def test_edge_resize_contract(self, controller):
        c = controller()
        assert c._panel.styleMask() & AppKit.NSWindowStyleMaskResizable
        ratio = c._panel.contentAspectRatio()
        assert ratio.width / ratio.height == pytest.approx(c._aspect, rel=0.02)
        assert c._panel.contentMinSize().height == clockface.MIN_HEIGHT
        assert c._panel.contentMaxSize().height == clockface.MAX_HEIGHT

    def test_has_no_title_bar_and_a_clear_background(self, controller):
        panel = controller()._panel
        assert not panel.styleMask() & AppKit.NSWindowStyleMaskTitled
        assert not panel.isOpaque()


class TestPlacement:
    def test_first_launch_opens_at_top_centre(self, controller):
        c = controller()
        x, y, w, h = frame_of(c)
        assert h == clockface.DEFAULT_HEIGHT
        assert (x, y) == tuple(c.home_origin((w, h)))

    def test_saved_position_and_size_are_restored(self, controller, tmp_path):
        first = controller()
        hx, hy = first.home_origin(frame_of(first)[2:])
        state.save(state.State(x=hx - 200, y=hy - 300, height=28.0))
        c = controller()
        x, y, _w, h = frame_of(c)
        assert (x, y, h) == (hx - 200, hy - 300, 28.0)

    def test_position_on_a_missing_monitor_falls_back_to_top_centre(self, controller):
        state.save(state.State(x=-90000.0, y=-90000.0))
        c = controller()
        x, y, w, h = frame_of(c)
        assert (x, y) == tuple(c.home_origin((w, h)))

    def test_move_to_top_centre(self, controller):
        c = controller()
        c._panel.setFrameOrigin_((50, 50))
        c.moveToTopCentre_(None)
        x, y, w, h = frame_of(c)
        assert (x, y) == tuple(c.home_origin((w, h)))


class TestSizing:
    def test_presets_resize_about_the_top_centre(self, controller):
        c = controller()
        x0, y0, w0, h0 = frame_of(c)
        for index, (_label, height) in enumerate(clockface.SIZE_PRESETS):
            item = AppKit.NSMenuItem.alloc().init()
            item.setTag_(index)
            c.choosePreset_(item)
            x, y, w, h = frame_of(c)
            assert h == height
            assert y + h == y0 + h0                                 # top edge fixed
            assert x + w / 2 == pytest.approx(x0 + w0 / 2, abs=1)  # centre fixed

    def test_pinch_increments_accumulate(self, controller):
        # A pinch arrives as many ~1% steps; each alone rounds to no change.
        c = controller()
        for _ in range(30):
            c.scale_by(1.01)
        assert frame_of(c)[3] == round(clockface.DEFAULT_HEIGHT * 1.01 ** 30)

    def test_pinch_stops_at_the_limits(self, controller):
        c = controller()
        c.scale_by(100.0)
        assert frame_of(c)[3] == clockface.MAX_HEIGHT
        c.scale_by(0.0001)
        assert frame_of(c)[3] == clockface.MIN_HEIGHT


class TestFace:
    @pytest.mark.parametrize("height", [20.0, 28.0, 40.0, 60.0, 120.0])
    @pytest.mark.parametrize("scheme", ["ink", "paper"])
    def test_digits_fit_and_are_centred(self, controller, height, scheme):
        c = controller()
        c.set_scheme(scheme)
        c.set_height(height)
        c._view._text = clockface.WIDEST
        left, top, right, bottom, wide, high = digit_pixel_box(c._view, scheme)
        scale = high / height  # pixels per point (1 or 2)

        # Inside the tile with room to spare on every side.
        assert left > 0.15 * high and right < wide - 0.15 * high
        assert top > 0.15 * high and bottom < high - 0.15 * high
        # Centred both ways, to within about a point.
        assert (left + right) / 2 == pytest.approx(wide / 2, abs=1.5 * scale)
        assert (top + bottom) / 2 == pytest.approx(high / 2, abs=1.5 * scale)
        # And the digits are the intended half of the tile height.
        assert (bottom - top + 1) / high == pytest.approx(clockface.CAP_FRACTION, abs=0.08)

    @pytest.mark.parametrize("text", ["8:19:19", "9:00:00", "12:00:00"])
    @pytest.mark.parametrize("height", [28.0, 40.0, 60.0])
    def test_twelve_hour_times_are_centred_too(self, controller, text, height):
        # A one-digit hour is narrower than the widest time; it must sit in
        # the middle of the tile, not hang off the right of a wider box.
        # (Times beginning or ending in 1 are left out on purpose: the test
        # measures ink, and the numeral 1 does not fill its cell evenly. The
        # layout centres the cells, which is what keeps the digits still.)
        c = controller()
        c.set_height(height)
        c._view._text = text
        left, _top, right, _bottom, wide, high = digit_pixel_box(c._view)
        scale = high / height
        assert (left + right) / 2 == pytest.approx(wide / 2, abs=1.5 * scale)

    def test_shows_the_current_time(self, controller):
        import time

        c = controller()
        before = time.localtime()
        c.refresh()
        after = time.localtime()
        candidates = {
            clockface.format_time(t.tm_hour, t.tm_min, t.tm_sec, c.uses_24h())
            for t in (before, after)
        }
        assert c._view._text in candidates


class TestMenu:
    def test_items(self, controller):
        menu = controller().build_menu()
        titles = [menu.itemAtIndex_(i).title() for i in range(menu.numberOfItems())]
        assert titles == [
            "Session Alert\u2026", "",
            "24-Hour Time", "Colours", "Size", "Move to Top Centre", "",
            "Quit Gnomon",
        ]
        colours = menu.itemWithTitle_("Colours").submenu()
        assert [colours.itemAtIndex_(i).title() for i in range(colours.numberOfItems())] == [
            scheme.label for scheme in schemes.SCHEMES
        ]
        sizes = menu.itemWithTitle_("Size").submenu()
        assert [sizes.itemAtIndex_(i).title() for i in range(sizes.numberOfItems())] == [
            label for label, _ in clockface.SIZE_PRESETS
        ]

    def test_every_item_has_a_live_target(self, controller):
        c = controller()
        c.set_alarm(14, 50, 5, now=NOW)  # so "Turn Off Session Alert" is there too
        menu = c.build_menu()
        items = [menu.itemAtIndex_(i) for i in range(menu.numberOfItems())]
        for title in ("Colours", "Size"):
            submenu = menu.itemWithTitle_(title).submenu()
            items += [submenu.itemAtIndex_(i) for i in range(submenu.numberOfItems())]
        for item in items:
            if item.isSeparatorItem() or item.hasSubmenu():
                continue
            assert item.target().respondsToSelector_(item.action()), item.title()

    def test_hour_toggle_flips_the_face_and_the_tick(self, controller):
        c = controller()
        was = c.uses_24h()
        c.toggleHours_(None)
        assert c.uses_24h() is (not was)
        assert c._state.twenty_four is (not was)
        tick = c.build_menu().itemWithTitle_("24-Hour Time").state()
        assert (tick == AppKit.NSControlStateValueOn) is (not was)

    def test_current_preset_is_ticked(self, controller):
        c = controller()
        sizes = c.build_menu().itemWithTitle_("Size").submenu()
        ticked = [
            sizes.itemAtIndex_(i).title()
            for i in range(sizes.numberOfItems())
            if sizes.itemAtIndex_(i).state() == AppKit.NSControlStateValueOn
        ]
        assert ticked == ["Medium"]


class TestPersistence:
    def test_save_now_records_where_the_tile_is(self, controller):
        c = controller()
        c._panel.setFrameOrigin_((321, 123))
        c.set_height(60)
        c.set_scheme("paper")
        c.save_now()
        saved = state.load()
        x, y, _w, h = frame_of(c)
        assert (saved.x, saved.y, saved.height, saved.scheme) == (x, y, h, "paper")

    def test_what_was_saved_is_what_reopens(self, controller):
        first = controller()
        first._panel.setFrameOrigin_((321, 123))
        first.set_height(28)
        first.save_now()
        second = controller()
        assert frame_of(second) == frame_of(first)


class TestColours:
    @pytest.mark.parametrize("scheme", [scheme.key for scheme in schemes.SCHEMES])
    def test_every_scheme_paints_its_own_tile_and_legible_digits(self, controller, scheme):
        c = controller()
        c.set_scheme(scheme)
        c._view._text = clockface.WIDEST
        assert distance(tile_colour(c._view), rgb(schemes.get(scheme).tile)) < 0.03
        left, top, right, bottom, wide, high = digit_pixel_box(c._view, scheme)
        assert (left + right) / 2 == pytest.approx(wide / 2, abs=3)
        assert (top + bottom) / 2 == pytest.approx(high / 2, abs=3)

    def test_choosing_from_the_menu_changes_and_ticks_the_scheme(self, controller):
        c = controller()
        colours = c.build_menu().itemWithTitle_("Colours").submenu()
        c.chooseScheme_(colours.itemWithTitle_("Terminal"))
        assert c._state.scheme == c._view._scheme == "terminal"
        colours = c.build_menu().itemWithTitle_("Colours").submenu()
        ticked = [
            colours.itemAtIndex_(i).title()
            for i in range(colours.numberOfItems())
            if colours.itemAtIndex_(i).state() == AppKit.NSControlStateValueOn
        ]
        assert ticked == ["Terminal"]

    def test_scheme_survives_a_relaunch(self, controller):
        first = controller()
        first.set_scheme("witching-hour")
        first.save_now()
        assert controller()._view._scheme == "witching-hour"


class TestSessionAlert:
    """End 14:50, 5-minute warning, set at 14:00 (NOW)."""

    WARN = NOW + 45 * 60
    END = NOW + 50 * 60

    def armed(self, controller, warn=5):
        c = controller()
        c.set_alarm(14, 50, warn, now=NOW)
        return c

    def test_quiet_until_the_warning(self, controller):
        c = self.armed(controller)
        c.refresh(self.WARN - 2)
        assert c._view._flash is None
        assert c._view._armed  # the dot is showing

    def test_warning_flashes_a_second_on_a_second_off(self, controller):
        c = self.armed(controller)
        c.refresh(self.WARN)
        assert c._view._flash == alarm.WARNING
        c.refresh(self.WARN + 1)
        assert c._view._flash is None
        c.refresh(self.WARN + 2)
        assert c._view._flash == alarm.WARNING

    def test_warning_flash_swaps_the_scheme_colours(self, controller):
        c = self.armed(controller)
        ink = schemes.get("ink")
        c.refresh(self.WARN - 2)
        assert distance(tile_colour(c._view), rgb(ink.tile)) < 0.03
        c.refresh(self.WARN)
        assert distance(tile_colour(c._view), rgb(ink.digits)) < 0.03

    def test_a_click_stops_the_warning_but_keeps_the_alert(self, controller):
        c = self.armed(controller)
        c.refresh(self.WARN)
        assert c.acknowledge(self.WARN + 4)
        assert c._view._flash is None and c._view._armed
        c.refresh(self.WARN + 60)  # still quiet a minute later, lit half or not
        assert c._view._flash is None

    def test_flashes_red_again_at_the_end(self, controller):
        c = self.armed(controller)
        c.acknowledge(self.WARN)
        c.refresh(self.END)
        assert c._view._flash == alarm.ENDED
        assert distance(tile_colour(c._view), rgb(schemes.ALERT_TILE)) < 0.03

    def test_a_click_at_the_end_finishes_the_alert(self, controller):
        c = self.armed(controller)
        c.refresh(self.END)
        assert c.acknowledge(self.END + 3)
        assert c._alarm is None
        assert c._view._flash is None and not c._view._armed
        assert c.build_menu().itemAtIndex_(0).title() == "Session Alert\u2026"

    def test_an_unanswered_warning_turns_into_the_end_flash(self, controller):
        c = self.armed(controller)
        c.refresh(self.END - 2)
        assert c._view._flash == alarm.WARNING
        c.refresh(self.END)
        assert c._view._flash == alarm.ENDED

    def test_an_unanswered_end_flash_gives_up(self, controller):
        c = self.armed(controller)
        c.refresh(self.END + alarm.END_FLASH_LIMIT)
        assert c._alarm is None and c._view._flash is None and not c._view._armed

    def test_no_warning_means_only_the_end_flash(self, controller):
        c = self.armed(controller, warn=0)
        c.refresh(self.WARN)
        assert c._view._flash is None
        c.refresh(self.END)
        assert c._view._flash == alarm.ENDED

    def test_mouse_down_on_a_flashing_tile_answers_it(self, controller):
        # While flashing, the press is consumed before any drag is started
        # (which is why passing no event is safe here).
        c = self.armed(controller)
        c._alarm = alarm.Alarm(end=time.time() + 60, warn_minutes=5)  # inside the warning, for real
        c.refresh()
        c._view.mouseDown_(None)
        assert c._alarm.warn_acked
        assert c._view._flash is None

    def test_a_click_when_nothing_is_flashing_is_not_swallowed(self, controller):
        c = self.armed(controller)
        assert not c.acknowledge(NOW + 60)  # ... so mouseDown_ goes on to start a drag
        assert c._alarm is not None and not c._alarm.warn_acked

    def test_turning_it_off(self, controller):
        c = self.armed(controller)
        c.turnOffAlert_(None)
        assert c._alarm is None and not c._view._armed
        c.refresh(self.END)
        assert c._view._flash is None

    def test_menu_shows_what_is_set(self, controller):
        c = self.armed(controller)
        c._alarm = alarm.arm(alarm.next_occurrence(14, 50, time.time()), 5, time.time())
        menu = c.build_menu()
        first = menu.itemAtIndex_(0)
        assert first.title().startswith("Session Alert: ")
        assert ":50" in first.title() and "5 min warning" in first.title()
        assert first.state() == AppKit.NSControlStateValueOn
        assert menu.itemAtIndex_(1).title() == "Turn Off Session Alert"

    def test_the_dot_is_drawn_only_when_armed(self, controller):
        def margin_pixel(c):
            rep = render(c._view)
            scale = rep.pixelsHigh() / c._view.bounds().size.height
            height = c._view.bounds().size.height
            return pixel(rep, round(height * 0.14 * scale), rep.pixelsHigh() // 2)

        c = controller()
        c._view._text = "12:00:00"
        tile = rgb(schemes.get("ink").tile)
        assert distance(margin_pixel(c), tile) < 0.03
        c.set_alarm(14, 50, 5, now=NOW)
        c._view._text = "12:00:00"
        assert distance(margin_pixel(c), tile) > 0.2

    def test_alert_and_its_settings_survive_a_relaunch(self, controller):
        first = controller()
        end = alarm.next_occurrence(*time.localtime(time.time() + 3000)[3:5], time.time())
        first._alarm = alarm.Alarm(end=end, warn_minutes=3, warn_acked=True)
        first._state.warn_minutes, first._state.end_minute = 3, 20
        first.save_now()
        second = controller()
        assert second._alarm == first._alarm
        assert (second._state.warn_minutes, second._state.end_minute) == (3, 20)

    def test_an_alert_whose_session_is_over_is_not_restored(self, controller):
        state.save(state.State(alarm_end=time.time() - 5))
        c = controller()
        assert c._alarm is None and not c._view._armed

    def test_setting_remembers_the_warning_and_the_minute(self, controller):
        c = controller()
        c.set_alarm(15, 20, 2, now=NOW)
        assert (c._state.warn_minutes, c._state.end_minute) == (2, 20)


class TestAlertForm:
    def test_form_opens_on_the_values_it_was_given(self, controller):
        from ui import alert_form

        controller()  # NSApplication exists
        end = alarm.next_occurrence(14, 50, NOW)
        _form, picker, popup = alert_form.build_form(end, 3)
        assert alert_form.read_form(picker, popup) == (14, 50, 3)
        assert popup.numberOfItems() == alarm.MAX_WARN_MINUTES + 1
        assert popup.titleOfSelectedItem() == "3 minutes before"

    def test_form_fits_its_controls(self, controller):
        from ui import alert_form

        controller()
        form, picker, popup = alert_form.build_form(alarm.next_occurrence(9, 5, NOW), 0)
        bounds = form.bounds()
        for control in (picker, popup):
            frame = control.frame()
            assert frame.origin.x >= 0 and frame.origin.y >= 0
            assert frame.origin.x + frame.size.width <= bounds.size.width
            assert frame.origin.y + frame.size.height <= bounds.size.height
        assert popup.titleOfSelectedItem() == "No warning"

    @pytest.mark.parametrize("armed", [False, True])
    def test_alert_buttons(self, controller, armed):
        from ui import alert_form

        controller()
        alert, _picker, _popup = alert_form.build_alert(alarm.next_occurrence(14, 50, NOW), 5, armed)
        titles = [button.title() for button in alert.buttons()]
        assert titles == ["Set", "Cancel"] + (["Turn Off"] if armed else [])
        assert alert.buttons()[0].keyEquivalent() == "\r"      # Return sets
        assert alert.buttons()[1].keyEquivalent() == "\x1b"    # Esc cancels
        assert alert.window().level() == AppKit.NSStatusWindowLevel
