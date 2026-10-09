"""The session-alert form: the one place Gnomon asks for typing.

The clock tile cannot take keyboard focus (that is the point of it), so the
end time is entered in a small standard alert instead. Opening it makes
Gnomon the active app for as long as it is up; when it closes, whichever
app was in front before — Meet, in practice — is brought back.
"""

from __future__ import annotations

import os
from datetime import datetime

from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSAlertThirdButtonReturn,
    NSApplication,
    NSDatePicker,
    NSDatePickerElementFlagHourMinute,
    NSDatePickerStyleTextFieldAndStepper,
    NSPopUpButton,
    NSStatusWindowLevel,
    NSTextAlignmentRight,
    NSTextField,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWorkspace,
)
from Foundation import NSDate, NSMakeRect

from core import alarm

WARN_TITLES = ["No warning", "1 minute before"] + [
    f"{minutes} minutes before" for minutes in range(2, alarm.MAX_WARN_MINUTES + 1)
]

SET = "set"
OFF = "off"


def build_form(end: float, warn_minutes: int):
    """(container view, time picker, warning pop-up), filled with defaults."""
    form = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 292, 62))

    def label(text, y):
        field = NSTextField.labelWithString_(text)
        field.setAlignment_(NSTextAlignmentRight)
        field.setFrame_(NSMakeRect(0, y, 108, 20))
        form.addSubview_(field)

    label("Session ends at", 37)
    picker = NSDatePicker.alloc().initWithFrame_(NSMakeRect(116, 34, 120, 26))
    picker.setDatePickerStyle_(NSDatePickerStyleTextFieldAndStepper)
    picker.setDatePickerElements_(NSDatePickerElementFlagHourMinute)
    picker.setDateValue_(NSDate.dateWithTimeIntervalSince1970_(end))
    picker.sizeToFit()
    form.addSubview_(picker)

    label("Warning", 5)
    popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(113, 0, 179, 26), False)
    popup.addItemsWithTitles_(WARN_TITLES)
    popup.selectItemAtIndex_(alarm.clamp_warn(warn_minutes))
    form.addSubview_(popup)
    return form, picker, popup


def read_form(picker, popup) -> tuple[int, int, int]:
    """(hour, minute, warning minutes) as currently shown in the form."""
    chosen = datetime.fromtimestamp(picker.dateValue().timeIntervalSince1970())
    return chosen.hour, chosen.minute, int(popup.indexOfSelectedItem())


def build_alert(end: float, warn_minutes: int, armed: bool):
    """(alert, time picker, warning pop-up), ready to run."""
    form, picker, popup = build_form(end, warn_minutes)

    alert = NSAlert.alloc().init()
    alert.setMessageText_("Session alert")
    alert.setInformativeText_(
        "The clock flashes at the warning and again when the session ends. "
        "Click the clock to stop the flashing."
    )
    alert.addButtonWithTitle_("Set")      # Return
    alert.addButtonWithTitle_("Cancel")   # Esc
    if armed:
        alert.addButtonWithTitle_("Turn Off")
    alert.setAccessoryView_(form)
    window = alert.window()
    window.setInitialFirstResponder_(picker)
    # Same reach as the tile itself, so the form also appears over a
    # full-screen call instead of on some other Space.
    window.setLevel_(NSStatusWindowLevel)
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorFullScreenAuxiliary
    )
    return alert, picker, popup


def run_in_front(alert):
    """Run `alert` as the frontmost thing on screen and return its answer.

    Gnomon is normally never the active app, so it has to step forward to be
    typed into or clicked through, and step back afterwards: whichever app
    was in front before (Meet, in practice) is brought back. The alert gets
    the tile's own reach, so it also appears over a full-screen call instead
    of on some other Space.
    """
    window = alert.window()
    window.setLevel_(NSStatusWindowLevel)
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorFullScreenAuxiliary
    )
    app = NSApplication.sharedApplication()
    previous = NSWorkspace.sharedWorkspace().frontmostApplication()
    app.activateIgnoringOtherApps_(True)
    try:
        return alert.runModal()
    finally:
        if previous is not None and previous.processIdentifier() != os.getpid():
            previous.activateWithOptions_(0)


def ask(end: float, warn_minutes: int, armed: bool):
    """Show the form and wait for an answer.

    Returns (SET, hour, minute, warn_minutes), (OFF,) or None for Cancel.
    The clock keeps ticking behind it: its timer runs in the common run-loop
    modes, which include the modal one.
    """
    alert, picker, popup = build_alert(end, warn_minutes, armed)

    response = run_in_front(alert)
    if response == NSAlertFirstButtonReturn:
        return (SET, *read_form(picker, popup))
    if armed and response == NSAlertThirdButtonReturn:
        return (OFF,)
    return None
