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

from core import alarm, clockface, fonts, schemes, state  # noqa: E402

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
        c.move_to("top-centre")
        x, y, w, h = frame_of(c)
        assert (x, y) == tuple(c.home_origin((w, h)))


def menu_item_for(c, submenu_title, title):
    return c.build_menu().itemWithTitle_(submenu_title).submenu().itemWithTitle_(title)


def visible_frame(c):
    f = c._panel.screen().visibleFrame()
    return (f.origin.x, f.origin.y, f.size.width, f.size.height)


def inside(frame, bounds):
    x, y, w, h = frame
    bx, by, bw, bh = bounds
    return bx <= x and x + w <= bx + bw and by <= y and y + h <= by + bh


class TestMoveTo:
    LABELS = [label for _key, label in clockface.ANCHORS]

    def test_menu_lists_the_six_places_in_order(self, controller):
        places = controller().build_menu().itemWithTitle_("Move To").submenu()
        assert [places.itemAtIndex_(i).title() for i in range(places.numberOfItems())] == [
            "Top Centre", "Top Right", "Bottom Right",
            "Bottom Centre", "Bottom Left", "Top Left",
        ]

    @pytest.mark.parametrize("anchor,label", clockface.ANCHORS)
    def test_each_place_parks_the_tile_there_on_screen(self, controller, anchor, label):
        c = controller()
        c.moveTo_(menu_item_for(c, "Move To", label))
        x, y, w, h = frame_of(c)
        vx, vy, vw, vh = visible_frame(c)
        gap = clockface.EDGE_GAP
        assert inside((x, y, w, h), (vx, vy, vw, vh))
        vertical, horizontal = anchor.split("-")
        assert (y + h == vy + vh - gap) if vertical == "top" else (y == vy + gap)
        if horizontal == "left":
            assert x == vx + gap
        elif horizontal == "right":
            assert x + w == vx + vw - gap
        else:
            screen = c._panel.screen().frame()
            assert x + w / 2 == pytest.approx(screen.origin.x + screen.size.width / 2, abs=1)

    def test_the_six_places_are_six_different_spots(self, controller):
        c = controller()
        spots = set()
        for anchor, _label in clockface.ANCHORS:
            c.move_to(anchor)
            spots.add(frame_of(c)[:2])
        assert len(spots) == 6

    @pytest.mark.parametrize("anchor,label", clockface.ANCHORS)
    def test_a_parked_tile_stays_parked_when_resized(self, controller, anchor, label):
        # Without this a tile in a bottom corner grows down into the Dock,
        # and one in a left or right corner grows off the side.
        c = controller()
        c.move_to(anchor)
        for height in (60.0, 120.0, 28.0):
            c.set_height(height)
            x, y, w, h = frame_of(c)
            assert h == height
            assert (x, y) == tuple(c.anchored_origin(anchor, (w, h)))
            assert inside((x, y, w, h), visible_frame(c))

    def test_the_place_it_is_parked_at_is_ticked(self, controller):
        c = controller()
        c.move_to("bottom-left")
        places = c.build_menu().itemWithTitle_("Move To").submenu()
        ticked = [
            places.itemAtIndex_(i).title()
            for i in range(places.numberOfItems())
            if places.itemAtIndex_(i).state() == AppKit.NSControlStateValueOn
        ]
        assert ticked == ["Bottom Left"]

    def test_dragging_it_away_lets_go_of_the_place(self, controller):
        c = controller()
        c.move_to("bottom-right")
        x, y, w, h = frame_of(c)
        c._panel.setFrameOrigin_((x - 300, y + 200))     # what a drag does
        assert c.current_anchor() is None
        assert c.build_menu().itemWithTitle_("Move To").submenu().itemWithTitle_(
            "Bottom Right"
        ).state() == AppKit.NSControlStateValueOff
        # ... and a resize now grows from where it was dragged to, as before.
        x0, y0, w0, h0 = frame_of(c)
        c.set_height(60)
        x1, y1, w1, h1 = frame_of(c)
        assert y1 + h1 == y0 + h0
        assert x1 + w1 / 2 == pytest.approx(x0 + w0 / 2, abs=1)

    def test_the_place_survives_a_relaunch(self, controller):
        first = controller()
        first.move_to("top-right")
        first.save_now()
        second = controller()
        assert frame_of(second) == frame_of(first)
        assert second.current_anchor() == "top-right"
        second.set_height(60)   # still parked after reopening
        x, y, w, h = frame_of(second)
        assert (x, y) == tuple(second.anchored_origin("top-right", (w, h)))

    def test_a_stale_place_in_the_state_file_is_ignored(self, controller):
        # Saved as parked top-right, but the saved position is somewhere else.
        first = controller()
        hx, hy = first.home_origin(frame_of(first)[2:])
        state.save(state.State(x=hx - 200, y=hy - 300, anchor="top-right"))
        c = controller()
        assert c.current_anchor() is None
        assert frame_of(c)[:2] == (hx - 200, hy - 300)


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

    @pytest.mark.parametrize("text", ["10:41:25", "8:42:17", "00:00:00"])
    @pytest.mark.parametrize("height", [28.0, 40.0, 60.0, 120.0])
    def test_colons_are_vertically_centred_on_the_digits(self, controller, text, height):
        # Regression: through 1.2.2 the colons were lifted twice (once by the
        # font, once by hand) and ended up level with the top of the digits.
        c = controller()
        c.set_height(height)
        c._view._text = text
        rep = render(c._view)
        wide, high = rep.pixelsWide(), rep.pixelsHigh()
        tile, digits = rgb(schemes.get("ink").tile), rgb(schemes.get("ink").digits)

        columns = {}
        for x in range(wide):
            lit = [
                y for y in range(high)
                if rep.colorAtX_y_(x, y).alphaComponent() > 0.9
                and distance(pixel(rep, x, y), digits) < 0.35 * distance(pixel(rep, x, y), tile)
            ]
            if lit:
                columns[x] = (min(lit), max(lit))
        runs, run = [], []
        for x in sorted(columns):
            if run and x != run[-1] + 1:
                runs.append(run)
                run = []
            run.append(x)
        runs.append(run)

        def extent(xs):
            return min(columns[x][0] for x in xs), max(columns[x][1] for x in xs)

        # A colon is a narrow run of ink; a digit is a wide one.
        colons = [extent(xs) for xs in runs if len(xs) <= 0.12 * high]
        numerals = [extent(xs) for xs in runs if len(xs) > 0.12 * high]
        assert len(colons) == 2 and numerals
        digit_top = min(top for top, _ in numerals)
        digit_bottom = max(bottom for _, bottom in numerals)
        scale = high / height
        for top, bottom in colons:
            assert (top + bottom) / 2 == pytest.approx((digit_top + digit_bottom) / 2, abs=scale)
            # ... which also means clear space above AND below, not flush with the top.
            assert top - digit_top == pytest.approx(digit_bottom - bottom, abs=2 * scale)
            assert top - digit_top > 0.1 * (digit_bottom - digit_top)

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
            "24-Hour Time", "Colours", "Font", "Size", "Move To", "",
            "About Gnomon", "Quit Gnomon",
        ]
        colours = menu.itemWithTitle_("Colours").submenu()
        assert [colours.itemAtIndex_(i).title() for i in range(colours.numberOfItems())] == [
            "White", "Green", "Amber", "", "Black", "Blue", "Red",
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
        for title in ("Colours", "Font", "Size", "Move To"):
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
        c.chooseScheme_(colours.itemWithTitle_("Blue"))  # below the separator
        assert c._state.scheme == c._view._scheme == "navy"
        colours = c.build_menu().itemWithTitle_("Colours").submenu()
        ticked = [
            colours.itemAtIndex_(i).title()
            for i in range(colours.numberOfItems())
            if colours.itemAtIndex_(i).state() == AppKit.NSControlStateValueOn
        ]
        assert ticked == ["Blue"]

    def test_scheme_survives_a_relaunch(self, controller):
        first = controller()
        first.set_scheme("amber")
        first.save_now()
        assert controller()._view._scheme == "amber"


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

    @pytest.mark.parametrize("scheme", [scheme.key for scheme in schemes.SCHEMES])
    def test_warning_is_amber_and_the_end_is_red_in_every_scheme(self, controller, scheme):
        c = self.armed(controller)
        c.set_scheme(scheme)
        c.refresh(self.WARN - 2)
        assert distance(tile_colour(c._view), rgb(schemes.get(scheme).tile)) < 0.03
        c.refresh(self.WARN)
        assert distance(tile_colour(c._view), rgb(schemes.WARNING_TILE)) < 0.03
        c.refresh(self.END)
        assert distance(tile_colour(c._view), rgb(schemes.ALERT_TILE)) < 0.03

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

    @pytest.mark.parametrize("height", [20.0, 28.0, 40.0, 60.0, 120.0])
    def test_the_dot_is_solid_and_clear_of_the_digits(self, controller, height):
        c = controller()
        c.set_height(height)
        c.set_alarm(14, 50, 5, now=NOW)
        c._view._text = clockface.WIDEST  # 24-hour times fill the box: the tightest case
        rep = render(c._view)
        scale = rep.pixelsHigh() / height
        mid = rep.pixelsHigh() // 2
        ink = schemes.get("ink")
        # Solid: the middle of the dot is the full digit colour, not a tint of it.
        assert distance(pixel(rep, round(height * 0.14 * scale), mid), rgb(ink.digits)) < 0.03
        # Clear: a strip of bare tile, top to bottom, between the dot and the first digit.
        gap = round(height * 0.25 * scale)
        for y in range(rep.pixelsHigh() // 4, 3 * rep.pixelsHigh() // 4):
            assert distance(pixel(rep, gap, y), rgb(ink.tile)) < 0.03, (height, y)

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


FACES = [face for face, _label in fonts.FACES]
FONT_FACES = [face for face in FACES if face != fonts.LED]  # the LED face is drawn, not a font


def ink_runs(view, scheme_key="ink"):
    """Runs of inked columns in an off-screen render, left to right, each as
    (width, top, bottom) in pixels; plus the bitmap's pixel height."""
    scheme = schemes.get(scheme_key)
    tile, digits = rgb(scheme.tile), rgb(scheme.digits)
    rep = render(view)
    wide, high = rep.pixelsWide(), rep.pixelsHigh()
    columns = {}
    for x in range(wide):
        lit = [
            y for y in range(high)
            if rep.colorAtX_y_(x, y).alphaComponent() > 0.9
            and distance(pixel(rep, x, y), digits) < 0.35 * distance(pixel(rep, x, y), tile)
        ]
        if lit:
            columns[x] = (min(lit), max(lit))
    runs, run = [], []
    for x in sorted(columns):
        if run and x != run[-1] + 1:
            runs.append(run)
            run = []
        run.append(x)
    runs.append(run)
    return [
        (len(xs), min(columns[x][0] for x in xs), max(columns[x][1] for x in xs)) for xs in runs
    ], high


class TestFonts:
    def test_menu_lists_the_faces_and_ticks_the_current_one(self, controller):
        c = controller()
        faces = c.build_menu().itemWithTitle_("Font").submenu()
        assert [faces.itemAtIndex_(i).title() for i in range(faces.numberOfItems())] == [
            "Standard", "Serif", "Mono", "DIN", "Typewriter", "LED",
        ]
        c.chooseFace_(faces.itemWithTitle_("DIN"))
        assert c._state.font == c._view._face == "din"
        faces = c.build_menu().itemWithTitle_("Font").submenu()
        ticked = [
            faces.itemAtIndex_(i).title()
            for i in range(faces.numberOfItems())
            if faces.itemAtIndex_(i).state() == AppKit.NSControlStateValueOn
        ]
        assert ticked == ["DIN"]

    def test_every_face_is_installed_and_is_its_own_typeface(self, controller):
        # A face that is missing silently falls back to Standard, which would
        # leave two menu items that look the same.
        from ui.app import _digit_font

        controller()
        names = {face: _digit_font(40.0, face).fontName() for face in FONT_FACES}
        assert len(set(names.values())) == len(FONT_FACES), names

    @pytest.mark.parametrize("face", FONT_FACES)
    def test_numerals_are_all_the_same_width(self, controller, face):
        # Otherwise the time shimmies sideways as the seconds change.
        from ui.app import _digit_font

        controller()
        font = _digit_font(40.0, face)
        widths = {
            round(
                AppKit.NSAttributedString.alloc()
                .initWithString_attributes_(str(n), {AppKit.NSFontAttributeName: font})
                .size()
                .width,
                2,
            )
            for n in range(10)
        }
        assert len(widths) == 1, (face, widths)

    @pytest.mark.parametrize("face", FACES)
    @pytest.mark.parametrize("height", [28.0, 40.0, 80.0])
    def test_digits_fit_and_are_centred_in_every_face(self, controller, face, height):
        c = controller()
        c.set_face(face)
        c.set_height(height)
        c._view._text = clockface.WIDEST
        left, top, right, bottom, wide, high = digit_pixel_box(c._view)
        scale = high / height
        assert left > 0.12 * high and right < wide - 0.12 * high
        assert top > 0.12 * high and bottom < high - 0.12 * high
        assert (left + right) / 2 == pytest.approx(wide / 2, abs=1.5 * scale)
        assert (top + bottom) / 2 == pytest.approx(high / 2, abs=1.5 * scale)

    @pytest.mark.parametrize("face", FACES)
    @pytest.mark.parametrize("height", [40.0, 80.0])
    def test_colons_are_centred_on_the_digits_in_every_face(self, controller, face, height):
        # The system faces centre a colon between numerals by themselves; the
        # others leave it on the baseline. Either way it must end up centred,
        # and that can only be told by looking at what was drawn.
        c = controller()
        c.set_face(face)
        c.set_height(height)
        c._view._text = "20:45:38"   # no 1s: in some faces a 1 is as narrow as a colon
        runs, high = ink_runs(c._view)
        assert len(runs) == 8, (face, runs)
        # The colons are the two narrowest runs, in positions 3 and 6. (Found
        # by rank, not by a fixed width: a monospaced face has stout colons.)
        by_width = sorted(runs)
        colons, numerals = by_width[:2], by_width[2:]
        assert sorted(colons) == sorted([runs[2], runs[5]]), (face, runs)
        assert colons[1][0] < 0.6 * numerals[0][0], (face, runs)
        digit_top = min(top for _w, top, _b in numerals)
        digit_bottom = max(bottom for _w, _t, bottom in numerals)
        scale = high / height
        for _width, top, bottom in colons:
            assert (top + bottom) / 2 == pytest.approx(
                (digit_top + digit_bottom) / 2, abs=1.25 * scale
            ), face

    def test_changing_face_keeps_the_height_and_reshapes_the_tile(self, controller):
        c = controller()
        x0, y0, w0, h0 = frame_of(c)
        c.set_face("mono")   # monospaced colons: a wider tile
        x1, y1, w1, h1 = frame_of(c)
        assert h1 == h0 and w1 > w0
        assert y1 + h1 == y0 + h0                                  # top edge fixed
        assert x1 + w1 / 2 == pytest.approx(x0 + w0 / 2, abs=1)   # centre fixed
        ratio = c._panel.contentAspectRatio()
        assert ratio.width / ratio.height == pytest.approx(w1 / h1, rel=0.02)
        c.set_face("din")    # a narrow face: a narrower tile than Standard
        assert frame_of(c)[2] < w0

    def test_changing_face_keeps_a_parked_tile_parked(self, controller):
        c = controller()
        c.move_to("bottom-right")
        for face in ("mono", "din", "standard"):
            c.set_face(face)
            x, y, w, h = frame_of(c)
            assert (x, y) == tuple(c.anchored_origin("bottom-right", (w, h))), face
            assert inside((x, y, w, h), visible_frame(c))

    def test_the_largest_size_is_reachable_in_a_wide_face(self, controller):
        # The width limit belongs to the face; it has to move with it.
        c = controller()
        c.set_face("mono")
        c.set_height(clockface.MAX_HEIGHT)
        w, h = frame_of(c)[2:]
        assert h == clockface.MAX_HEIGHT
        assert w == clockface.tile_size(clockface.MAX_HEIGHT, c._aspect)[0]

    def test_face_survives_a_relaunch(self, controller):
        first = controller()
        first.set_face("typewriter")
        first.save_now()
        second = controller()
        assert second._view._face == "typewriter"
        assert frame_of(second) == frame_of(first)

    def test_an_unknown_face_in_the_state_file_means_standard(self, controller):
        path = state.data_dir() / state.STATE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"font": "comic-sans"}', encoding="utf-8")
        assert controller()._view._face == "standard"

    def test_the_retired_rounded_face_opens_as_standard(self, controller):
        path = state.data_dir() / state.STATE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"font": "rounded"}', encoding="utf-8")
        assert controller()._view._face == "standard"

    def test_standard_face_gets_no_colon_lift(self, controller):
        # The regression from 1.0: lifting a colon the font had already lifted.
        from ui.app import _colon_lift

        controller()
        assert _colon_lift("standard") == 0.0
        assert _colon_lift("din") > 0.1          # sits on the baseline: needs raising


class TestLedFace:
    def led(self, controller, text, height=80.0, scheme="green"):
        c = controller()
        c.set_scheme(scheme)
        c.set_face("led")
        c.set_height(height)
        c._view._text = text
        return c

    def test_digits_are_half_the_tile_height_like_every_other_face(self, controller):
        c = self.led(controller, "88:88:88", scheme="ink")
        _left, top, _right, bottom, _wide, high = digit_pixel_box(c._view)
        assert (bottom - top + 1) / high == pytest.approx(clockface.CAP_FRACTION, abs=0.03)

    def test_unlit_segments_show_faintly(self, controller):
        # In a 1, the top bar is unlit: visible, but nearer the tile than the digits.
        from core import sevenseg

        c = self.led(controller, "1")
        rep = render(c._view)
        scale = rep.pixelsHigh() / 80.0
        scheme = schemes.get("green")
        tile, digits = rgb(scheme.tile), rgb(scheme.digits)
        digit_height = 80.0 * clockface.CAP_FRACTION
        # Middle of segment "a": mid-width of the digit, just under its top
        # (nudged right for the lean at that height).
        x = rep.pixelsWide() / 2 + sevenseg.SLANT * 0.44 * digit_height * scale
        y = rep.pixelsHigh() / 2 - (0.5 - sevenseg.THICKNESS / 2) * digit_height * scale
        ghost = pixel(rep, round(x), round(y))
        assert distance(ghost, tile) > 0.03                      # it is there
        assert distance(ghost, tile) < 0.25 * distance(digits, tile)   # but only just
        # ... and a lit segment of the same 1 is the full colour.
        lit_x = rep.pixelsWide() / 2 + (sevenseg.DIGIT_WIDTH / 2 - sevenseg.THICKNESS / 2
                                        + sevenseg.SLANT * 0.25) * digit_height * scale
        lit_y = rep.pixelsHigh() / 2 - 0.25 * digit_height * scale
        assert distance(pixel(rep, round(lit_x), round(lit_y)), digits) < 0.05

    def test_an_eight_has_nothing_unlit(self, controller):
        # Every pixel is either tile or full-strength digit (bar anti-aliased edges).
        c = self.led(controller, "8", height=120.0)
        rep = render(c._view)
        scheme = schemes.get("green")
        tile, digits = rgb(scheme.tile), rgb(scheme.digits)
        span = distance(tile, digits)
        middling = 0
        inner = range(rep.pixelsHigh() // 4, 3 * rep.pixelsHigh() // 4)
        for y in inner:
            for x in range(rep.pixelsWide() // 3, 2 * rep.pixelsWide() // 3):
                d = distance(pixel(rep, x, y), tile)
                if 0.05 * span < d < 0.2 * span:
                    middling += 1
        assert middling < 0.01 * len(inner) * (rep.pixelsWide() // 3)

    @pytest.mark.parametrize("scheme", [scheme.key for scheme in schemes.SCHEMES])
    def test_led_face_works_in_every_colour_scheme(self, controller, scheme):
        c = self.led(controller, clockface.WIDEST, height=40.0, scheme=scheme)
        left, top, right, bottom, wide, high = digit_pixel_box(c._view, scheme)
        assert (left + right) / 2 == pytest.approx(wide / 2, abs=3)
        assert (top + bottom) / 2 == pytest.approx(high / 2, abs=3)

    def test_led_face_flashes_like_any_other(self, controller):
        c = controller()
        c.set_face("led")
        c.set_alarm(14, 50, 5, now=NOW)
        c.refresh(NOW + 45 * 60)
        assert distance(tile_colour(c._view), rgb(schemes.WARNING_TILE)) < 0.03


class TestFirstLaunchAndAbout:
    def test_the_hint_says_the_two_things_a_newcomer_cannot_guess(self):
        from ui import about

        text = (about.WELCOME_TITLE + " " + about.WELCOME_TEXT).lower()
        assert "right-click" in text     # where everything is
        assert "quit" in text            # and how to get rid of it
        assert "drag" in text

    def test_a_new_install_is_due_the_hint_and_gets_it_once(self, controller, monkeypatch):
        from ui import about

        shown = []
        monkeypatch.setattr(about, "show_welcome", lambda: shown.append(state.load().welcomed))
        c = controller()
        assert c._state.welcomed is False
        c.showWelcome_(None)
        # Shown once, and already recorded as shown by the time it was up.
        assert shown == [True]
        assert controller()._state.welcomed is True

    def test_about_panel_names_the_version_and_the_licence(self, controller):
        from core import __version__
        from ui import about

        controller()
        options = about.about_options()
        assert options["ApplicationName"] == "Gnomon"
        assert options["ApplicationVersion"] == __version__
        assert "Richard Sembera" in options["Copyright"]
        assert "Affero General Public License" in options["Credits"].string()


class TestEdgeResizing:
    def test_pointer_is_tracked_even_though_gnomon_is_never_the_active_app(self, controller):
        areas = controller()._view.trackingAreas()
        assert len(areas) == 1
        options = areas[0].options()
        assert options & AppKit.NSTrackingActiveAlways
        assert options & AppKit.NSTrackingMouseMoved
        assert options & AppKit.NSTrackingMouseEnteredAndExited
        assert options & AppKit.NSTrackingInVisibleRect   # follows the tile when it is resized

    def test_edges_show_resize_arrows_and_the_middle_shows_the_arrow(self, controller):
        view = controller()._view
        arrow = AppKit.NSCursor.arrowCursor()
        assert view.cursor_for(None) == arrow
        cursors = {edge: view.cursor_for(edge) for edge in clockface.EDGES}
        assert all(cursor is not None and cursor != arrow for cursor in cursors.values())
        # Sideways, up-and-down and the two diagonals are different pointers
        # (the diagonals only where macOS has them: 15 and later).
        assert cursors["left"] != cursors["top"]
        if hasattr(AppKit.NSCursor, "frameResizeCursorFromPosition_inDirections_"):
            assert cursors["top-left"] != cursors["left"]
            assert cursors["top-left"] != cursors["top-right"]

    def test_the_pointer_can_be_changed_from_the_background(self, controller):
        # The undocumented window-server switch that makes the arrows show at
        # all. If this starts failing on a new macOS, the arrows are gone
        # (resizing still works) and it is time to look for another way.
        from ui.app import allow_background_cursor

        controller()
        assert allow_background_cursor() is True
        assert allow_background_cursor() is True   # harmless to ask twice

    def test_no_resize_arrows_while_flashing(self, controller):
        # A click anywhere on a flashing tile answers the flash.
        c = controller()
        c.set_alarm(14, 50, 5, now=NOW)
        c.refresh(NOW + 45 * 60)
        assert c._view._flash is not None
        assert c._view.cursor_for("left") == AppKit.NSCursor.arrowCursor()

    def test_dragging_an_edge_resizes_from_the_opposite_side(self, controller):
        c = controller()
        c._panel.setFrameOrigin_((400, 400))
        start = frame_of(c)
        c.resize_from_edge(start, "right", 72, 0, False)
        x, y, w, h = frame_of(c)
        assert w > start[2] and h > start[3]
        assert x == start[0]                         # left edge stayed
        assert y + h == start[1] + start[3]          # top edge stayed
        assert w / h == pytest.approx(c._aspect, rel=0.02)
        # The drag is measured from where it began, so going back restores it.
        c.resize_from_edge(start, "right", 0, 0, False)
        assert frame_of(c) == start

    def test_edge_drag_is_remembered_like_any_other_resize(self, controller):
        c = controller()
        c._panel.setFrameOrigin_((400, 400))
        c.resize_from_edge(frame_of(c), "bottom", 0, -20, False)
        c.save_now()
        assert state.load().height == frame_of(c)[3] == 60.0
        c.scale_by(1.0)   # a later pinch starts from the new size, not the old one
        assert frame_of(c)[3] == 60.0

    def test_edge_drag_on_a_parked_tile_keeps_it_parked(self, controller):
        c = controller()
        c.move_to("bottom-right")
        start = frame_of(c)
        c.resize_from_edge(start, "left", -72, 0, True)
        x, y, w, h = frame_of(c)
        assert h > start[3]
        assert c.current_anchor() == "bottom-right"
        assert (x, y) == tuple(c.anchored_origin("bottom-right", (w, h)))
