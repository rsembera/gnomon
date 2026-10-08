"""The panel and the view, exercised in-process.

Nothing is put on screen: the panel is built but never ordered front, and
the face is rendered into an off-screen bitmap. What these tests CANNOT
cover is the window server's side of things — the actual mouse drag and the
edge resize — so they pin the contract that makes those work instead
(movable-by-background, a view that says the mouse may move the window, a
resizable aspect-locked panel).
"""

import pytest

AppKit = pytest.importorskip("AppKit")

from core import clockface, state  # noqa: E402


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


def bright_pixel_box(view, dark):
    """Bounding box, in pixels, of the digit pixels in an off-screen render.

    Returns (left, top, right, bottom, width, height) with y measured from
    the top. Digits are the pixels much lighter (dark tile) or much darker
    (paper tile) than the tile itself.
    """
    rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)
    wide, high = rep.pixelsWide(), rep.pixelsHigh()
    xs, ys = [], []
    for y in range(high):
        for x in range(wide):
            colour = rep.colorAtX_y_(x, y)
            if colour.alphaComponent() < 0.9:
                continue
            luminance = (
                colour.redComponent() + colour.greenComponent() + colour.blueComponent()
            ) / 3.0
            if (luminance > 0.7) if dark else (luminance < 0.3):
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
        c = controller()
        assert c._panel.isMovableByWindowBackground()
        assert c._view.mouseDownCanMoveWindow()

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
    @pytest.mark.parametrize("dark", [True, False])
    def test_digits_fit_and_are_centred(self, controller, height, dark):
        c = controller()
        if c._state.dark != dark:
            c.toggleTheme_(None)
        c.set_height(height)
        c._view._text = clockface.WIDEST
        left, top, right, bottom, wide, high = bright_pixel_box(c._view, dark)
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
        left, _top, right, _bottom, wide, high = bright_pixel_box(c._view, dark=True)
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
        assert titles == ["24-Hour Time", "Dark", "Size", "Move to Top Centre", "", "Quit Gnomon"]
        sizes = menu.itemAtIndex_(2).submenu()
        assert [sizes.itemAtIndex_(i).title() for i in range(sizes.numberOfItems())] == [
            label for label, _ in clockface.SIZE_PRESETS
        ]

    def test_every_item_has_a_live_target(self, controller):
        c = controller()
        menu = c.build_menu()
        items = [menu.itemAtIndex_(i) for i in range(menu.numberOfItems())]
        items += [menu.itemAtIndex_(2).submenu().itemAtIndex_(i) for i in range(3)]
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
        tick = c.build_menu().itemAtIndex_(0).state()
        assert (tick == AppKit.NSControlStateValueOn) is (not was)

    def test_theme_toggle(self, controller):
        c = controller()
        assert c._state.dark and c._view._dark
        c.toggleTheme_(None)
        assert not c._state.dark and not c._view._dark
        assert c.build_menu().itemAtIndex_(1).state() == AppKit.NSControlStateValueOff

    def test_current_preset_is_ticked(self, controller):
        c = controller()
        sizes = c.build_menu().itemAtIndex_(2).submenu()
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
        c.toggleTheme_(None)
        c.save_now()
        saved = state.load()
        x, y, _w, h = frame_of(c)
        assert (saved.x, saved.y, saved.height, saved.dark) == (x, y, h, False)

    def test_what_was_saved_is_what_reopens(self, controller):
        first = controller()
        first._panel.setFrameOrigin_((321, 123))
        first.set_height(28)
        first.save_now()
        second = controller()
        assert frame_of(second) == frame_of(first)
