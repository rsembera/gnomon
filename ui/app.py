"""The clock: one borderless floating panel and the view that draws it.

Why this is native AppKit and not Flask + pywebview like everything else
in the portfolio: the whole job is to sit on top of a video call without
getting in its way, and a web view cannot do that properly.

  * The panel is NON-ACTIVATING. Dragging or right-clicking it does not
    take keyboard focus away from Meet. A pywebview window is an ordinary
    NSWindow; clicking it activates the app behind it.
  * pywebview's own frameless-drag code flings the window off-screen when
    it is dragged against the top edge, which is exactly where this
    clock is meant to live.
  * Eight glyphs do not need a WebKit process running through a session.

PyObjC note for anyone editing this file: on a class that inherits from an
Objective-C class, a method name with underscores is read as a selector
(`foo_bar_` -> `foo:bar:`). Plain-Python helpers are therefore marked
@objc.python_method, and everything AppKit calls back into keeps its
selector spelling (`tick_`, `windowDidMove_`, ...).
"""

from __future__ import annotations

import time

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationDidChangeScreenParametersNotification,
    NSBackingStoreBuffered,
    NSBaselineOffsetAttributeName,
    NSBezierPath,
    NSColor,
    NSControlStateValueOff,
    NSControlStateValueOn,
    NSFont,
    NSFontAttributeName,
    NSFontWeightMedium,
    NSForegroundColorAttributeName,
    NSMenu,
    NSMenuItem,
    NSMutableAttributedString,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskResizable,
)
from Foundation import (
    NSDateFormatter,
    NSInsetRect,
    NSLocale,
    NSMakeRect,
    NSNotificationCenter,
    NSObject,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSTimer,
)
from PyObjCTools import AppHelper

from core import clockface, state

APP_NAME = "Gnomon"

# Font size at which the digits are measured once, to set the tile's
# proportions. It is the size the default tile uses, because the system
# font's metrics are NOT linear in point size (it tracks small sizes wider),
# so the proportions are exact for the default and near enough elsewhere;
# drawRect_ re-measures at the size it actually draws.
REF_SIZE = 28.0

# Ink on paper, the Daybook/Palestra palette. "Ink" is the same two colours
# the other way round.
INK = "#1D1B17"
PAPER = "#FAF7F0"
RULE = "#DFD9CC"

PANEL_STYLE = (
    NSWindowStyleMaskBorderless
    | NSWindowStyleMaskResizable
    | NSWindowStyleMaskNonactivatingPanel
)

# Every Space, including another app's full-screen Space (Meet in full
# screen is the case that matters); not part of Mission Control's shuffle
# or the Cmd-` window cycle.
PANEL_BEHAVIOUR = (
    NSWindowCollectionBehaviorCanJoinAllSpaces
    | NSWindowCollectionBehaviorFullScreenAuxiliary
    | NSWindowCollectionBehaviorStationary
    | NSWindowCollectionBehaviorIgnoresCycle
)


def _srgb(hex_colour: str, alpha: float = 1.0):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, alpha)


def _palette(dark: bool):
    """(tile, digits, hairline edge) for the chosen appearance."""
    if dark:
        return _srgb(INK), _srgb(PAPER), _srgb(PAPER, 0.16)
    return _srgb(PAPER), _srgb(INK), _srgb(RULE)


def _digit_font(size: float):
    # Monospaced DIGITS (not a monospaced face): every numeral is the same
    # width, so the time does not shimmy as the seconds change.
    return NSFont.monospacedDigitSystemFontOfSize_weight_(size, NSFontWeightMedium)


def _rect(ns_rect) -> clockface.Rect:
    return (
        ns_rect.origin.x,
        ns_rect.origin.y,
        ns_rect.size.width,
        ns_rect.size.height,
    )


def system_uses_24h() -> bool:
    """Whether macOS is set to 24-hour time (Settings > General > Date & Time)."""
    pattern = NSDateFormatter.dateFormatFromTemplate_options_locale_(
        "j", 0, NSLocale.currentLocale()
    )
    return "a" not in (pattern or "")


class ClockPanel(NSPanel):
    """A panel that never takes keyboard focus. Meet keeps it."""

    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


class ClockView(NSView):
    """Draws the tile and the digits; hands gestures to the controller."""

    def initWithFrame_(self, frame):
        self = objc.super(ClockView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._text = ""
        self._dark = True
        self._controller = None
        font = _digit_font(REF_SIZE)
        reference = NSMutableAttributedString.alloc().initWithString_attributes_(
            clockface.WIDEST, {NSFontAttributeName: font}
        )
        self._ref_width = reference.size().width
        self._ref_cap = font.capHeight()
        # The system font's colon sits on the baseline, which is right in a
        # sentence and looks dropped between numerals. Measure how far its
        # middle is below the middle of the digits; drawRect_ lifts it by
        # that much (as a fraction of font size).
        colon = font.boundingRectForGlyph_(font.glyphWithName_("colon"))
        colon_middle = colon.origin.y + colon.size.height / 2.0
        self._colon_lift = (self._ref_cap / 2.0 - colon_middle) / REF_SIZE
        return self

    def isOpaque(self):
        return False

    def mouseDownCanMoveWindow(self):
        # With the panel's movableByWindowBackground, this is the whole
        # drag implementation: the window server moves the tile itself.
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def menuForEvent_(self, event):
        return self._controller.build_menu() if self._controller else None

    def magnifyWithEvent_(self, event):
        if self._controller:
            self._controller.scale_by(1.0 + event.magnification())

    @objc.python_method
    def fitted_font(self, size):
        """(font, width of the widest time in it) for a tile of `size`.

        Starts from the reference measurement and corrects against what
        each candidate size really measures: because the metrics are not
        linear in point size, one multiplication is a few percent out at
        sizes far from the reference. Three rounds settle well under a
        tenth of a point.
        """
        point_size, box_width, cap = REF_SIZE, self._ref_width, self._ref_cap
        font = None
        for _ in range(3):
            point_size *= clockface.digit_scale(size, box_width, cap)
            if point_size <= 0:
                return None, 0.0
            font = _digit_font(point_size)
            box_width = NSMutableAttributedString.alloc().initWithString_attributes_(
                clockface.WIDEST, {NSFontAttributeName: font}
            ).size().width
            cap = font.capHeight()
        return font, box_width

    def drawRect_(self, dirty):
        bounds = self.bounds()
        width, height = bounds.size.width, bounds.size.height
        tile, digits, edge = _palette(self._dark)

        radius = min(height * 0.24, 16.0)
        outline = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSInsetRect(bounds, 0.5, 0.5), radius, radius
        )
        tile.setFill()
        outline.fill()
        edge.setStroke()
        outline.setLineWidth_(1.0)
        outline.stroke()

        font, box_width = self.fitted_font((width, height))
        if font is None or not self._text:
            return
        text = NSMutableAttributedString.alloc().initWithString_attributes_(
            self._text,
            {NSFontAttributeName: font, NSForegroundColorAttributeName: digits},
        )
        lift = self._colon_lift * font.pointSize()
        for index, character in enumerate(self._text):
            if character == ":":
                text.addAttribute_value_range_(NSBaselineOffsetAttributeName, lift, (index, 1))
        # Right-align inside the box the widest time occupies, so the
        # seconds stay put when 9:59:59 becomes 10:00:00 in 12-hour mode.
        x = (width + box_width) / 2.0 - text.size().width
        # Centre the numerals themselves (cap height), not the line box,
        # which carries descender space digits never use.
        baseline = (height - font.capHeight()) / 2.0
        text.drawAtPoint_((x, baseline + font.descender()))


class Controller(NSObject):
    """Owns the panel, the once-a-second timer and the remembered state."""

    def init(self):
        self = objc.super(Controller, self).init()
        if self is None:
            return None
        self._state = state.load()
        self._panel = None
        self._view = None
        self._timer = None
        self._aspect = 1.0
        self._exact_height = self._state.height
        return self

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @objc.python_method
    def build(self, show: bool = True):
        view = ClockView.alloc().initWithFrame_(NSMakeRect(0, 0, 144, 40))
        view._controller = self
        view._dark = self._state.dark
        self._aspect = clockface.aspect_ratio(view._ref_width, view._ref_cap)

        size = clockface.tile_size(self._state.height, self._aspect)
        panel = ClockPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(*self.initial_frame(size)),
            PANEL_STYLE,
            NSBackingStoreBuffered,
            False,
        )
        panel.setReleasedWhenClosed_(False)
        panel.setFloatingPanel_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        # Status level sits above ordinary windows AND the menu bar, so the
        # tile can be parked in the menu bar right beside the camera notch.
        panel.setLevel_(NSStatusWindowLevel)
        panel.setCollectionBehavior_(PANEL_BEHAVIOUR)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setMovableByWindowBackground_(True)
        # Aspect-locked: dragging any edge scales the whole clock.
        panel.setContentAspectRatio_(size)
        panel.setContentMinSize_(clockface.tile_size(clockface.MIN_HEIGHT, self._aspect))
        panel.setContentMaxSize_(clockface.tile_size(clockface.MAX_HEIGHT, self._aspect))
        panel.setContentView_(view)
        panel.setDelegate_(self)

        self._panel, self._view = panel, view
        self._exact_height = size[1]
        self.refresh()
        if show:
            panel.orderFrontRegardless()

    @objc.python_method
    def screen_rects(self) -> list:
        return [_rect(screen.frame()) for screen in NSScreen.screens()]

    @objc.python_method
    def home_origin(self, size):
        """Top centre of the built-in display if there is one (the screen
        with a camera housing reports a top safe-area inset), otherwise of
        the primary display."""
        screens = list(NSScreen.screens())
        home = screens[0] if screens else NSScreen.mainScreen()
        for screen in screens:
            if screen.safeAreaInsets().top > 0:
                home = screen
                break
        return clockface.top_centre_origin(
            _rect(home.frame()), _rect(home.visibleFrame()), size
        )

    @objc.python_method
    def initial_frame(self, size) -> clockface.Rect:
        saved = self._state
        if saved.x is not None and saved.y is not None:
            frame = (saved.x, saved.y, size[0], size[1])
            if clockface.is_reachable(frame, self.screen_rects()):
                return frame
        x, y = self.home_origin(size)
        return (x, y, size[0], size[1])

    # ------------------------------------------------------------------
    # Time
    # ------------------------------------------------------------------

    @objc.python_method
    def uses_24h(self) -> bool:
        chosen = self._state.twenty_four
        return system_uses_24h() if chosen is None else chosen

    @objc.python_method
    def refresh(self):
        now = time.localtime()
        text = clockface.format_time(
            now.tm_hour, now.tm_min, now.tm_sec, self.uses_24h()
        )
        if text != self._view._text:
            self._view._text = text
            self._view.setNeedsDisplay_(True)

    @objc.python_method
    def schedule_tick(self):
        timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            clockface.seconds_to_next_tick(time.time()), self, "tick:", None, False
        )
        timer.setTolerance_(0.005)
        # Common modes, not just the default one: the clock keeps ticking
        # while it is being dragged or while its menu is open.
        NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
        self._timer = timer

    def tick_(self, timer):
        try:
            self.refresh()
        finally:
            self.schedule_tick()  # whatever happened, the clock keeps going

    # ------------------------------------------------------------------
    # Size and position
    # ------------------------------------------------------------------

    @objc.python_method
    def set_height(self, height: float):
        # The unrounded height is kept so that a pinch, which arrives as
        # many tiny increments, is not rounded away one step at a time.
        self._exact_height = clockface.clamp_height(height)
        size = clockface.tile_size(self._exact_height, self._aspect)
        frame = clockface.resized_frame(_rect(self._panel.frame()), size)
        self._panel.setFrame_display_(NSMakeRect(*frame), True)

    @objc.python_method
    def scale_by(self, factor: float):
        self.set_height(self._exact_height * factor)

    @objc.python_method
    def go_home(self):
        size = _rect(self._panel.frame())[2:]
        self._panel.setFrameOrigin_(self.home_origin(size))

    def windowDidResize_(self, notification):
        if self._panel is None:
            return
        height = self._panel.frame().size.height
        if round(self._exact_height) != round(height):  # resized by its edge
            self._exact_height = height
        self._panel.invalidateShadow()
        self._view.setNeedsDisplay_(True)
        self.save_soon()

    def windowDidMove_(self, notification):
        if self._panel is not None:
            self.save_soon()

    def screensChanged_(self, notification):
        # A monitor was unplugged or rearranged: if that left the tile
        # somewhere it cannot be grabbed, bring it back.
        if self._panel is None:
            return
        if not clockface.is_reachable(_rect(self._panel.frame()), self.screen_rects()):
            self.go_home()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    @objc.python_method
    def build_menu(self):
        menu = NSMenu.alloc().initWithTitle_(APP_NAME)
        menu.setAutoenablesItems_(False)

        def add(target_menu, title, action, target=self, checked=None):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(target)
            if checked is not None:
                item.setState_(NSControlStateValueOn if checked else NSControlStateValueOff)
            target_menu.addItem_(item)
            return item

        add(menu, "24-Hour Time", "toggleHours:", checked=self.uses_24h())
        add(menu, "Dark", "toggleTheme:", checked=self._state.dark)

        sizes = NSMenu.alloc().initWithTitle_("Size")
        sizes.setAutoenablesItems_(False)
        current = round(self._panel.frame().size.height)
        for index, (label, height) in enumerate(clockface.SIZE_PRESETS):
            add(sizes, label, "choosePreset:", checked=current == round(height)).setTag_(index)
        add(menu, "Size", None).setSubmenu_(sizes)

        add(menu, "Move to Top Centre", "moveToTopCentre:")
        menu.addItem_(NSMenuItem.separatorItem())
        add(menu, f"Quit {APP_NAME}", "terminate:", target=NSApplication.sharedApplication())
        return menu

    def toggleHours_(self, sender):
        self._state.twenty_four = not self.uses_24h()
        self.refresh()
        self.save_soon()

    def toggleTheme_(self, sender):
        self._state.dark = not self._state.dark
        self._view._dark = self._state.dark
        self._view.setNeedsDisplay_(True)
        self._panel.invalidateShadow()
        self.save_soon()

    def choosePreset_(self, sender):
        self.set_height(clockface.SIZE_PRESETS[sender.tag()][1])

    def moveToTopCentre_(self, sender):
        self.go_home()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @objc.python_method
    def save_now(self):
        if self._panel is None:
            return
        x, y, _width, height = _rect(self._panel.frame())
        self._state.x, self._state.y, self._state.height = x, y, height
        try:
            state.save(self._state)
        except OSError:
            pass  # a clock that cannot remember its place is still a clock

    @objc.python_method
    def save_soon(self):
        # Moves and resizes arrive in bursts; write once, after they stop.
        NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(
            self, "saveState:", None
        )
        self.performSelector_withObject_afterDelay_("saveState:", None, 0.5)

    def saveState_(self, _unused):
        self.save_now()

    # ------------------------------------------------------------------
    # Application lifecycle
    # ------------------------------------------------------------------

    def applicationDidFinishLaunching_(self, notification):
        self.build()
        self.schedule_tick()
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "screensChanged:", NSApplicationDidChangeScreenParametersNotification, None
        )

    def applicationWillTerminate_(self, notification):
        self.save_now()


def run() -> None:
    app = NSApplication.sharedApplication()
    # Accessory: no Dock icon, no menu bar of its own. The clock is the
    # whole interface; right-click it for the menu, including Quit.
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    controller = Controller.alloc().init()
    app.setDelegate_(controller)  # NSApp holds its delegate weakly; `controller` keeps it alive
    AppHelper.installMachInterrupt()  # Ctrl-C works when run from a terminal
    app.run()
