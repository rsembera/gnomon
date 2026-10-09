"""What Gnomon says about itself: the first-launch hint and the About panel.

Gnomon has no Dock icon and no menu bar, by design. For the person who
built it that is the point; for someone who has just downloaded it, it is a
small clock that offers no way to configure or quit it. The hint, shown
once, is the whole of the instruction manual: drag it, right-click it.
"""

from __future__ import annotations

from AppKit import (
    NSAlert,
    NSApplication,
    NSAttributedString,
    NSCenterTextAlignment,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
)

from core import __version__
from ui.alert_form import run_in_front

APP_NAME = "Gnomon"
COPYRIGHT = "Copyright \u00a9 2026 Richard Sembera"
CREDITS = (
    "A small always-on-top clock for timing sessions.\n\n"
    "Free software under the GNU Affero General Public License v3. "
    "It connects to nothing and collects nothing."
)

WELCOME_TITLE = "Gnomon is the small clock at the top of your screen"
WELCOME_TEXT = (
    "Drag it wherever you like.\n\n"
    "Right-click it (or click with two fingers) for everything else: colours, "
    "fonts, size, a session alert, and Quit.\n\n"
    "There is no Dock icon and no menu bar. The clock is the whole app."
)
WELCOME_BUTTON = "Got It"


def show_welcome() -> None:
    """The first-launch hint. Blocks until dismissed."""
    alert = NSAlert.alloc().init()
    alert.setMessageText_(WELCOME_TITLE)
    alert.setInformativeText_(WELCOME_TEXT)
    alert.addButtonWithTitle_(WELCOME_BUTTON)
    run_in_front(alert)


def about_options() -> dict:
    """What the standard About panel shows. Passed explicitly, so it reads
    the same from the packaged app and from `python main.py`."""
    centred = NSMutableParagraphStyle.alloc().init()
    centred.setAlignment_(NSCenterTextAlignment)
    credits = NSAttributedString.alloc().initWithString_attributes_(
        CREDITS,
        {
            NSFontAttributeName: NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()),
            NSForegroundColorAttributeName: NSColor.labelColor(),
            NSParagraphStyleAttributeName: centred,
        },
    )
    return {
        "ApplicationName": APP_NAME,
        "ApplicationVersion": __version__,
        "Version": "",  # no separate build number
        "Copyright": COPYRIGHT,
        "Credits": credits,
    }


def show_about() -> None:
    app = NSApplication.sharedApplication()
    app.activateIgnoringOtherApps_(True)
    app.orderFrontStandardAboutPanelWithOptions_(about_options())
