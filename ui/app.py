"""The clock: one borderless floating panel and the view that draws it.

Why this is native AppKit and not Flask + pywebview like everything else
in the portfolio: the whole job is to sit on top of a video call without
getting in its way, and a web view cannot do that properly.

  * The panel is NON-ACTIVATING. Dragging, clicking or right-clicking it
    does not take keyboard focus away from Meet. A pywebview window is an ordinary
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

import ctypes
import time

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationDidChangeScreenParametersNotification,
    NSBackingStoreBuffered,
    NSBaselineOffsetAttributeName,
    NSBezierPath,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSColor,
    NSControlStateValueOff,
    NSControlStateValueOn,
    NSCursor,
    NSEvent,
    NSEventMaskLeftMouseDragged,
    NSEventMaskLeftMouseUp,
    NSEventTypeLeftMouseUp,
    NSFont,
    NSFontAttributeName,
    NSFontDescriptorSystemDesignSerif,
    NSFontFeatureSelectorIdentifierKey,
    NSFontFeatureSettingsAttribute,
    NSFontFeatureTypeIdentifierKey,
    NSFontWeightMedium,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSMenu,
    NSMenuItem,
    NSMutableAttributedString,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSTrackingActiveAlways,
    NSTrackingArea,
    NSTrackingCursorUpdate,
    NSTrackingInVisibleRect,
    NSTrackingMouseEnteredAndExited,
    NSTrackingMouseMoved,
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

from core import alarm, clockface, fonts, schemes, sevenseg, state
from ui import about, alert_form, login

APP_NAME = "Gnomon"

# Font size at which the digits are measured once, to set the tile's
# proportions. It is the size the default tile uses, because the system
# font's metrics are NOT linear in point size (it tracks small sizes wider),
# so the proportions are exact for the default and near enough elsewhere;
# drawRect_ re-measures at the size it actually draws.
REF_SIZE = 28.0

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


def _palette(scheme_key: str, flash: str | None = None):
    """(tile, digits, hairline edge) to paint with right now.

    `flash` is None normally, and alarm.WARNING or alarm.ENDED during the
    "on" half of a flash: amber for the warning, red for the end of the
    session, the same two in every scheme.
    """
    if flash == alarm.ENDED:
        tile, digits = schemes.ALERT_TILE, schemes.ALERT_DIGITS
        return _srgb(tile), _srgb(digits), _srgb(digits, 0.25)
    if flash == alarm.WARNING:
        tile, digits = schemes.WARNING_TILE, schemes.WARNING_DIGITS
        return _srgb(tile), _srgb(digits), _srgb(digits, 0.25)
    scheme = schemes.get(scheme_key)
    return _srgb(scheme.tile), _srgb(scheme.digits), _srgb(scheme.edge, scheme.edge_alpha)


# Non-system faces, by PostScript name. All ship with macOS.
_NAMED_FACES = {
    "din": "DINAlternate-Bold",
    "typewriter": "AmericanTypewriter-Semibold",
}

# The OpenType "tabular figures" feature (number spacing: monospaced).
_TABULAR = {
    NSFontFeatureSettingsAttribute: [
        {NSFontFeatureTypeIdentifierKey: 6, NSFontFeatureSelectorIdentifierKey: 0}
    ]
}


def _tabular(font):
    descriptor = font.fontDescriptor().fontDescriptorByAddingAttributes_(_TABULAR)
    return NSFont.fontWithDescriptor_size_(descriptor, font.pointSize()) or font


def _digit_font(size: float, face: str = fonts.DEFAULT):
    """The font for `face` at `size`, with numerals of equal width.

    Equal-width DIGITS, not necessarily a monospaced face: every numeral
    takes the same space, so the time does not shimmy as the seconds
    change. A face that cannot be found falls back to the standard one
    rather than leaving the tile blank. (The LED face has no font; its
    digits are drawn by ClockView.draw_segments.)
    """
    font = None
    if face == "mono":
        font = NSFont.monospacedSystemFontOfSize_weight_(size, NSFontWeightMedium)
    elif face == "serif":
        base = NSFont.systemFontOfSize_weight_(size, NSFontWeightMedium)
        descriptor = base.fontDescriptor().fontDescriptorWithDesign_(
            NSFontDescriptorSystemDesignSerif
        )
        if descriptor is not None:
            font = NSFont.fontWithDescriptor_size_(descriptor, size)
    elif face in _NAMED_FACES:
        font = NSFont.fontWithName_size_(_NAMED_FACES[face], size)
    if font is None:
        return NSFont.monospacedDigitSystemFontOfSize_weight_(size, NSFontWeightMedium)
    return _tabular(font)


# NSCursor.frameResizeCursorFromPosition:inDirections: (macOS 15 and later)
# takes these bits; "all directions" because the tile can grow or shrink.
_CURSOR_POSITION_BITS = {"top": 1, "left": 2, "bottom": 4, "right": 8}
_CURSOR_ALL_DIRECTIONS = 3


def allow_background_cursor() -> bool:
    """Let Gnomon change the pointer although it is never the active app.

    macOS only honours NSCursor.set() from the active application, and
    Gnomon is deliberately never that, so without this the resize arrows are
    set and silently ignored (measured: 0 times out of 8). The window server
    has a per-application switch for exactly this case, "SetsCursorIn-
    Background". It is NOT a documented interface. It is used here because
    there is no documented one, and it is wrapped so that if a future macOS
    drops it the only thing lost is the arrows: resizing itself does not
    depend on it. Returns True if the switch was accepted.
    """
    try:
        cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cg._CGSDefaultConnection.restype = ctypes.c_int
        cg.CGSSetConnectionProperty.restype = ctypes.c_int
        cg.CGSSetConnectionProperty.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
        ]
        utf8 = 0x08000100  # kCFStringEncodingUTF8
        key = cf.CFStringCreateWithCString(None, b"SetsCursorInBackground", utf8)
        try:
            connection = cg._CGSDefaultConnection()
            true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
            return cg.CGSSetConnectionProperty(connection, connection, key, true) == 0
        finally:
            cf.CFRelease(key)
    except Exception:  # no such symbol, no such library: carry on without arrows
        return False


def _resize_cursor(edge: str):
    """The pointer to show over `edge`: the system's own window-resize
    arrows where it offers them, including the diagonal ones for corners.
    Before macOS 15 there are no public diagonal cursors, so a corner gets
    the left-right arrows there."""
    make = getattr(NSCursor, "frameResizeCursorFromPosition_inDirections_", None)
    if make is not None:
        position = sum(_CURSOR_POSITION_BITS[part] for part in edge.split("-"))
        return make(position, _CURSOR_ALL_DIRECTIONS)
    if edge in ("top", "bottom"):
        return NSCursor.resizeUpDownCursor()
    return NSCursor.resizeLeftRightCursor()


# How strongly the LED face shows the segments a digit is not using.
UNLIT_ALPHA = 0.10

_COLON_LIFT_CACHE: dict[str, float] = {}


def _colon_lift(face: str) -> float:
    """How far `face`'s colon must be raised to sit at the middle of the
    digits, as a fraction of the font size.

    MEASURED from a rendering, not worked out from the font's metrics. The
    system font raises a colon by itself when it sits between numerals, and
    its metrics do not say so: 1.0 trusted the metrics, lifted the colon a
    second time and left it level with the top of the digits. Most other
    faces leave the colon on the baseline. Drawing "0:0" once and looking
    at where the ink landed is right in both cases, and for any face added
    later.
    """
    if face in _COLON_LIFT_CACHE:
        return _COLON_LIFT_CACHE[face]
    size = 200.0
    wide, high = int(size * 2.6), int(size * 1.6)
    baseline = size * 0.4  # from the bottom of the bitmap
    font = _digit_font(size, face)
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, wide, high, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )
    context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(context)
    NSMutableAttributedString.alloc().initWithString_attributes_(
        "0:0", {NSFontAttributeName: font, NSForegroundColorAttributeName: NSColor.whiteColor()}
    ).drawAtPoint_((size * 0.2, baseline + font.descender()))
    NSGraphicsContext.restoreGraphicsState()

    row_bytes = rep.bytesPerRow()
    alpha = bytes(rep.bitmapData()[: row_bytes * high])[3::4]  # one byte per pixel
    per_row = row_bytes // 4
    # Runs of inked columns: digit, colon, digit.
    runs, run = [], []
    for x in range(wide):
        if any(a > 127 for a in alpha[x::per_row]):
            run.append(x)
        elif run:
            runs.append(run)
            run = []
    lift = 0.0
    if len(runs) == 3:
        rows = [
            y for y in range(high)
            if any(alpha[y * per_row + x] > 127 for x in runs[1])
        ]
        colon_middle = (high - (rows[0] + rows[-1] + 1) / 2.0 - baseline) / size
        lift = font.capHeight() / size / 2.0 - colon_middle
    if abs(lift) < 0.01:
        lift = 0.0  # already centred (the system faces): leave well alone
    _COLON_LIFT_CACHE[face] = lift
    return lift


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
        self._scheme = schemes.DEFAULT
        self._flash = None    # alarm.WARNING / alarm.ENDED while lit, else None
        self._armed = False   # a session alert is set: show the small dot
        self._controller = None
        self.set_face(fonts.DEFAULT)
        # Pointer tracking, so the edges can show resize arrows. "Active
        # always" because Gnomon is never the active app; "in visible rect"
        # so the area follows the tile as it is resized.
        self.addTrackingArea_(
            NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(),
                NSTrackingMouseEnteredAndExited
                | NSTrackingMouseMoved
                | NSTrackingCursorUpdate
                | NSTrackingActiveAlways
                | NSTrackingInVisibleRect,
                self,
                None,
            )
        )
        return self

    @objc.python_method
    def set_face(self, face: str):
        """Switch typeface and take its measurements."""
        self._face = face if fonts.is_known(face) else fonts.DEFAULT
        self.setNeedsDisplay_(True)
        if self._face == fonts.LED:
            # Drawn, not set: the proportions come straight from the
            # geometry (measured at a digit height of 1).
            self._ref_width = sevenseg.text_width(clockface.WIDEST, 1.0)
            self._ref_cap = 1.0
            self._colon_lift = 0.0
            return
        font = _digit_font(REF_SIZE, self._face)
        reference = NSMutableAttributedString.alloc().initWithString_attributes_(
            clockface.WIDEST, {NSFontAttributeName: font}
        )
        self._ref_width = reference.size().width
        self._ref_cap = font.capHeight()
        self._colon_lift = _colon_lift(self._face)

    def isOpaque(self):
        return False

    def mouseDownCanMoveWindow(self):
        # False so that mouse-downs come here (see mouseDown_) instead of
        # being turned into a window drag before the view hears of them.
        return False

    def acceptsFirstMouse_(self, event):
        return True

    @objc.python_method
    def edge_under(self, event) -> str | None:
        """The edge or corner the pointer is on, or None for the middle."""
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        size = self.bounds().size
        return clockface.edge_at((point.x, point.y), (size.width, size.height))

    @objc.python_method
    def cursor_for(self, edge: str | None):
        # While the tile is flashing a click anywhere answers the flash, so
        # it offers no resize arrows then.
        if edge is None or self._flash is not None:
            return NSCursor.arrowCursor()
        return _resize_cursor(edge)

    def mouseMoved_(self, event):
        self.cursor_for(self.edge_under(event)).set()

    def mouseEntered_(self, event):
        self.cursor_for(self.edge_under(event)).set()

    def cursorUpdate_(self, event):
        self.cursor_for(self.edge_under(event)).set()

    def mouseExited_(self, event):
        # Always hand the pointer back as an arrow. Besides being polite to
        # whatever is underneath, it keeps AppKit's idea of "the current
        # cursor" honest: AppKit skips a set() it believes is redundant, so
        # if this were left as a resize arrow, the next visit to the same
        # edge would not be sent to the window server at all.
        NSCursor.arrowCursor().set()

    def mouseDown_(self, event):
        # A click on a flashing tile answers the flash and does nothing
        # else. A press on an edge resizes. Any other press starts a drag:
        # performWindowDragWithEvent_ hands the move to the window server,
        # the same thing a title bar does, so the tile follows the pointer
        # exactly.
        if self._controller is not None and self._controller.acknowledge():
            return
        edge = self.edge_under(event)
        if edge is not None and self._controller is not None:
            self.track_resize(edge)
            return
        self.window().performWindowDragWithEvent_(event)

    @objc.python_method
    def track_resize(self, edge: str):
        """Follow the pointer until the button comes up, resizing as it goes.

        Done here rather than left to the system because a borderless panel
        gets no resize handles of its own. The loop runs in the run loop's
        event-tracking mode, in which the clock's timer still fires.
        """
        window = self.window()
        start_frame = _rect(window.frame())
        start = NSEvent.mouseLocation()
        parked = self._controller.current_anchor() is not None
        _resize_cursor(edge).set()
        while True:
            event = window.nextEventMatchingMask_(
                NSEventMaskLeftMouseDragged | NSEventMaskLeftMouseUp
            )
            if event is None or event.type() == NSEventTypeLeftMouseUp:
                break
            now = NSEvent.mouseLocation()
            self._controller.resize_from_edge(
                start_frame, edge, now.x - start.x, now.y - start.y, parked
            )

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
            font = _digit_font(point_size, self._face)
            box_width = NSMutableAttributedString.alloc().initWithString_attributes_(
                clockface.WIDEST, {NSFontAttributeName: font}
            ).size().width
            cap = font.capHeight()
        return font, box_width

    @objc.python_method
    def draw_digits(self, width, height, digits):
        """The time, set in the chosen font."""
        font, _box_width = self.fitted_font((width, height))
        if font is None:
            return
        text = NSMutableAttributedString.alloc().initWithString_attributes_(
            self._text,
            {NSFontAttributeName: font, NSForegroundColorAttributeName: digits},
        )
        # Colons at the middle of the digits. The system faces do this by
        # themselves (lift is 0 for them); the others leave the colon on
        # the baseline and are raised by a measured amount (_colon_lift).
        if self._colon_lift:
            lift = self._colon_lift * font.pointSize()
            for index, character in enumerate(self._text):
                if character == ":":
                    text.addAttribute_value_range_(
                        NSBaselineOffsetAttributeName, lift, (index, 1)
                    )
        # Centre the time as it actually reads. In 12-hour mode a one-digit
        # hour is a digit narrower than the widest time the font was sized
        # for; centring it costs one half-digit shift when 9:59:59 becomes
        # 10:00:00, which is better than sitting off-centre for nine hours.
        x = (width - text.size().width) / 2.0
        # Centre the numerals themselves (cap height), not the line box,
        # which carries descender space digits never use.
        baseline = (height - font.capHeight()) / 2.0
        text.drawAtPoint_((x, baseline + font.descender()))

    @objc.python_method
    def draw_segments(self, width, height, digits):
        """The time, as seven-segment digits (the LED face)."""
        # Same rule as for a font: digits half the tile's height, unless
        # the width says smaller. With a reference height of 1 the scale
        # factor IS the digit height.
        digit_height = clockface.digit_scale((width, height), self._ref_width, self._ref_cap)
        if digit_height <= 0:
            return
        x = (width - sevenseg.text_width(self._text, digit_height)) / 2.0
        y = (height - digit_height) / 2.0
        lit, unlit = sevenseg.polygons(self._text, digit_height)
        for shapes, alpha in ((unlit, UNLIT_ALPHA), (lit, 1.0)):
            path = NSBezierPath.bezierPath()
            for shape in shapes:
                path.moveToPoint_((x + shape[0][0], y + shape[0][1]))
                for px, py in shape[1:]:
                    path.lineToPoint_((x + px, y + py))
                path.closePath()
            digits.colorWithAlphaComponent_(alpha).setFill()
            path.fill()

    def drawRect_(self, dirty):
        bounds = self.bounds()
        width, height = bounds.size.width, bounds.size.height
        tile, digits, edge = _palette(self._scheme, self._flash)

        radius = min(height * 0.24, 16.0)
        outline = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSInsetRect(bounds, 0.5, 0.5), radius, radius
        )
        tile.setFill()
        outline.fill()
        edge.setStroke()
        outline.setLineWidth_(1.0)
        outline.stroke()

        if self._text:
            if self._face == fonts.LED:
                self.draw_segments(width, height, digits)
            else:
                self.draw_digits(width, height, digits)

        if self._armed and self._flash is None:
            # A session alert is set: a dot in the left margin, so it can be
            # checked at a glance without opening the menu. Solid and about
            # a seventh of the tile's height across; the first version was
            # smaller and half-transparent, and too easy to miss mid-session.
            # It still stops short of the digits (margin is 0.28 of height).
            r = max(2.0, height * 0.07)
            digits.setFill()
            NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(height * 0.14 - r, height / 2.0 - r, 2 * r, 2 * r)
            ).fill()


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
        # A saved alert is picked up again while it still has something to
        # do: the session has not ended, or its end flash has not yet run its
        # ten minutes (a relaunch during the flash should not swallow it).
        # Anything more than two days out is a damaged file, not an alert,
        # and would break the menu's description of it.
        self._alarm = None
        saved_end, launched = self._state.alarm_end, time.time()
        if (
            saved_end is not None
            and launched - alarm.END_FLASH_LIMIT < saved_end < launched + 2 * 86400
        ):
            self._alarm = alarm.Alarm(
                end=self._state.alarm_end,
                warn_minutes=self._state.warn_minutes,
                warn_acked=self._state.alarm_warn_acked,
            )
        return self

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @objc.python_method
    def build(self, show: bool = True):
        view = ClockView.alloc().initWithFrame_(NSMakeRect(0, 0, 144, 40))
        view._controller = self
        view._scheme = self._state.scheme
        view.set_face(self._state.font)
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
        # Dragging is started by the view (ClockView.mouseDown_), which needs
        # the press for itself when the tile is flashing.
        panel.setMovableByWindowBackground_(False)
        self.lock_aspect(panel, size)
        panel.setContentView_(view)
        panel.setDelegate_(self)

        self._panel, self._view = panel, view
        self._exact_height = size[1]
        self.refresh()
        if show:
            panel.orderFrontRegardless()

    @objc.python_method
    def lock_aspect(self, panel, size):
        # Aspect-locked: dragging any edge scales the whole clock. The
        # shape comes from the typeface, so this is redone when it changes.
        panel.setContentAspectRatio_(size)
        panel.setContentMinSize_(clockface.tile_size(clockface.MIN_HEIGHT, self._aspect))
        panel.setContentMaxSize_(clockface.tile_size(clockface.MAX_HEIGHT, self._aspect))

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
    def refresh(self, now: float | None = None):
        """Bring the face up to date: the digits, and the alert's flash."""
        now = time.time() if now is None else now
        local = time.localtime(now)
        text = clockface.format_time(
            local.tm_hour, local.tm_min, local.tm_sec, self.uses_24h()
        )

        if alarm.is_spent(self._alarm, now):
            self._alarm = None  # the end flash ran its course unclicked
            self.save_soon()
        flash = alarm.flashing(self._alarm, now)
        lit = flash if flash and alarm.flash_on(now) else None
        armed = self._alarm is not None

        view = self._view
        if (text, lit, armed) != (view._text, view._flash, view._armed):
            view._text, view._flash, view._armed = text, lit, armed
            view.setNeedsDisplay_(True)

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
        anchor = self.current_anchor()
        if anchor is not None:
            # Parked with "Move To": stay parked, so a tile in a corner
            # grows into the screen instead of off the edge of it.
            frame = (*self.anchored_origin(anchor, size), *size)
        else:
            frame = clockface.resized_frame(_rect(self._panel.frame()), size)
        self._panel.setFrame_display_(NSMakeRect(*frame), True)

    @objc.python_method
    def anchored_origin(self, anchor: str, size):
        """Where `anchor` is on the screen the tile is on now."""
        screen = self._panel.screen() or NSScreen.screens()[0]
        return clockface.anchored_origin(
            _rect(screen.frame()), _rect(screen.visibleFrame()), size, anchor
        )

    @objc.python_method
    def current_anchor(self) -> str | None:
        """The "Move To" spot the tile is parked at, or None.

        The remembered anchor only counts while the tile is still exactly
        there. Once it has been dragged anywhere else the anchor lapses:
        there is no separate "un-park" step to forget.
        """
        anchor = self._state.anchor
        if anchor is None:
            return None
        x, y, width, height = _rect(self._panel.frame())
        ax, ay = self.anchored_origin(anchor, (width, height))
        if abs(x - ax) > 1 or abs(y - ay) > 1:
            self._state.anchor = None
            return None
        return anchor

    @objc.python_method
    def move_to(self, anchor: str):
        size = _rect(self._panel.frame())[2:]
        self._state.anchor = anchor
        self._panel.setFrameOrigin_(self.anchored_origin(anchor, size))
        self.save_soon()

    @objc.python_method
    def scale_by(self, factor: float):
        self.set_height(self._exact_height * factor)

    @objc.python_method
    def resize_from_edge(self, start_frame, edge: str, dx: float, dy: float, parked: bool):
        """One step of an edge drag: `edge` has been pulled (dx, dy) from
        where the drag began, when the tile's frame was `start_frame`."""
        frame = clockface.edge_resized_frame(start_frame, edge, dx, dy, self._aspect)
        if parked:
            # Parked with "Move To": resize in place there, as the menu and
            # a pinch do, rather than un-parking it by a few points.
            self.set_height(frame[3])
        else:
            self._exact_height = frame[3]
            self._panel.setFrame_display_(NSMakeRect(*frame), True)

    @objc.python_method
    def go_home(self):
        size = _rect(self._panel.frame())[2:]
        self._state.anchor = "top-centre"
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
    # Session alert
    # ------------------------------------------------------------------

    @objc.python_method
    def set_alarm(self, hour: int, minute: int, warn_minutes: int, now: float | None = None):
        now = time.time() if now is None else now
        self._alarm = alarm.arm(alarm.session_end(hour, minute, now), warn_minutes, now)
        self._state.warn_minutes = self._alarm.warn_minutes
        self._state.end_minute = minute
        self.refresh(now)
        self.save_soon()

    @objc.python_method
    def clear_alarm(self, now: float | None = None):
        self._alarm = None
        self.refresh(now)
        self.save_soon()

    @objc.python_method
    def acknowledge(self, now: float | None = None) -> bool:
        """A click on the tile. True if it answered a flash (and so should
        not also start a drag)."""
        now = time.time() if now is None else now
        if alarm.flashing(self._alarm, now) is None:
            return False
        self._alarm = alarm.acknowledge(self._alarm, now)
        self.refresh(now)
        self.save_soon()
        return True

    def sessionAlert_(self, sender):
        now = time.time()
        # A session that has already ended (its red flash may still be
        # running) is not offered again: "Set" on it would re-arm it for the
        # same time tomorrow. The form opens on the next session instead.
        if self._alarm is not None and now < self._alarm.end:
            end, warn = self._alarm.end, self._alarm.warn_minutes
        else:
            end = alarm.default_end(self._state.end_minute, now)
            warn = self._state.warn_minutes
        answer = alert_form.ask(end, warn, armed=self._alarm is not None)
        if answer is None:
            return
        if answer[0] == alert_form.OFF:
            self.clear_alarm()
        else:
            _, hour, minute, warn_minutes = answer
            self.set_alarm(hour, minute, warn_minutes)

    def turnOffAlert_(self, sender):
        self.clear_alarm()

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

        if self._alarm is not None:
            summary = alarm.describe(self._alarm, time.time(), self.uses_24h())
            add(menu, f"Session Alert: {summary}\u2026", "sessionAlert:", checked=True)
            add(menu, "Turn Off Session Alert", "turnOffAlert:")
        else:
            add(menu, "Session Alert\u2026", "sessionAlert:")
        menu.addItem_(NSMenuItem.separatorItem())

        add(menu, "24-Hour Time", "toggleHours:", checked=self.uses_24h())

        colours = NSMenu.alloc().initWithTitle_("Colours")
        colours.setAutoenablesItems_(False)
        for index, scheme in enumerate(schemes.SCHEMES):
            if index and scheme.light != schemes.SCHEMES[index - 1].light:
                colours.addItem_(NSMenuItem.separatorItem())  # dark above, light below
            add(
                colours, scheme.label, "chooseScheme:",
                checked=scheme.key == self._state.scheme,
            ).setTag_(index)
        add(menu, "Colours", None).setSubmenu_(colours)

        faces = NSMenu.alloc().initWithTitle_("Font")
        faces.setAutoenablesItems_(False)
        for index, (face, label) in enumerate(fonts.FACES):
            add(faces, label, "chooseFace:", checked=face == self._state.font).setTag_(index)
        add(menu, "Font", None).setSubmenu_(faces)

        sizes = NSMenu.alloc().initWithTitle_("Size")
        sizes.setAutoenablesItems_(False)
        current = round(self._panel.frame().size.height)
        for index, (label, height) in enumerate(clockface.SIZE_PRESETS):
            add(sizes, label, "choosePreset:", checked=current == round(height)).setTag_(index)
        add(menu, "Size", None).setSubmenu_(sizes)

        places = NSMenu.alloc().initWithTitle_("Move To")
        places.setAutoenablesItems_(False)
        parked = self.current_anchor()
        for index, (anchor, label) in enumerate(clockface.ANCHORS):
            add(places, label, "moveTo:", checked=anchor == parked).setTag_(index)
        add(menu, "Move To", None).setSubmenu_(places)
        menu.addItem_(NSMenuItem.separatorItem())
        if login.available():
            add(menu, "Open at Login", "toggleLogin:", checked=login.is_on())
        add(menu, f"About {APP_NAME}", "aboutGnomon:")
        add(menu, f"Quit {APP_NAME}", "terminate:", target=NSApplication.sharedApplication())
        return menu

    def toggleHours_(self, sender):
        self._state.twenty_four = not self.uses_24h()
        self.refresh()
        self.save_soon()

    def chooseScheme_(self, sender):
        self.set_scheme(schemes.SCHEMES[sender.tag()].key)

    @objc.python_method
    def set_scheme(self, key: str):
        self._state.scheme = schemes.get(key).key
        self._view._scheme = self._state.scheme
        self._view.setNeedsDisplay_(True)
        self._panel.invalidateShadow()
        self.save_soon()

    def chooseFace_(self, sender):
        self.set_face(fonts.FACES[sender.tag()][0])

    @objc.python_method
    def set_face(self, face: str):
        """Change typeface. The tile keeps its height and its place; its
        width follows the new face (a monospaced one is wider)."""
        self._view.set_face(face)
        self._state.font = self._view._face
        self._aspect = clockface.aspect_ratio(self._view._ref_width, self._view._ref_cap)
        height = self._panel.frame().size.height
        # Limits first, or the old face's maximum width would clip the new tile.
        self.lock_aspect(self._panel, clockface.tile_size(height, self._aspect))
        self.set_height(height)
        self._panel.invalidateShadow()
        self.save_soon()

    def choosePreset_(self, sender):
        self.set_height(clockface.SIZE_PRESETS[sender.tag()][1])

    def moveTo_(self, sender):
        self.move_to(clockface.ANCHORS[sender.tag()][0])

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @objc.python_method
    def save_now(self):
        if self._panel is None:
            return
        x, y, _width, height = _rect(self._panel.frame())
        self._state.x, self._state.y, self._state.height = x, y, height
        self._state.alarm_end = self._alarm.end if self._alarm else None
        self._state.alarm_warn_acked = bool(self._alarm and self._alarm.warn_acked)
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

    def aboutGnomon_(self, sender):
        about.show_about()

    def toggleLogin_(self, sender):
        login.toggle()

    def showWelcome_(self, _unused):
        # Marked as shown BEFORE it goes up: if anything interrupts it, the
        # worse outcome is a hint seen for half a second, not one that
        # reappears at every launch.
        self._state.welcomed = True
        self.save_now()
        about.show_welcome()

    def applicationDidFinishLaunching_(self, notification):
        allow_background_cursor()  # so the edges can show resize arrows
        self.build()
        self.schedule_tick()
        if not self._state.welcomed:
            # A moment later, so the clock is on screen for the hint to point at.
            self.performSelector_withObject_afterDelay_("showWelcome:", None, 0.5)
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
