"""Session alert: when the tile flashes, and what a click does about it.

The sequence, for a session ending at 2:50 with a 5-minute warning:

    2:45  the tile starts flashing amber
          click it: flashing stops, the alert stays armed
    2:50  the tile starts flashing again, red
          click it: flashing stops, the alert is finished

A warning of 0 minutes skips the first half. Everything here is a pure
function of the alarm and the wall-clock time, so nothing needs its own
timer: the once-a-second tick asks "should the tile be flashing right now?"
and that is the whole mechanism. It is also why sleep, a lid close or a
changed system clock cannot confuse it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

MAX_WARN_MINUTES = 5
DEFAULT_WARN_MINUTES = 5

# Minute of the hour first offered as the session end: the 50-minute hour.
# After that the form offers whatever minute was last used.
DEFAULT_END_MINUTE = 50

# The form never proposes an end time closer than this.
MIN_LEAD = 5 * 60.0

# An end-of-session flash nobody clicks gives up after this long, so a clock
# left running after the last session is not still flashing in the morning.
END_FLASH_LIMIT = 10 * 60.0

IDLE = "idle"
WARNING = "warning"
ENDED = "ended"


@dataclass(frozen=True)
class Alarm:
    end: float                 # session end, seconds since the epoch
    warn_minutes: int = DEFAULT_WARN_MINUTES
    warn_acked: bool = False   # the warning flash has been clicked away

    @property
    def warn_at(self) -> float:
        return self.end - 60.0 * self.warn_minutes


def clamp_warn(minutes) -> int:
    return max(0, min(MAX_WARN_MINUTES, int(minutes)))


def next_occurrence(hour: int, minute: int, now: float) -> float:
    """The next time the local clock reads hour:minute, strictly after now."""
    candidate = datetime.fromtimestamp(now).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if candidate.timestamp() <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def default_end(minute: int, now: float) -> float:
    """End time to offer in the form: the next hh:`minute` that is at least
    MIN_LEAD away."""
    candidate = datetime.fromtimestamp(now).replace(
        minute=minute % 60, second=0, microsecond=0
    )
    while candidate.timestamp() - now < MIN_LEAD:
        candidate += timedelta(hours=1)
    return candidate.timestamp()


def arm(end: float, warn_minutes: int, now: float) -> Alarm:
    """A new alarm. If it is set when the warning point has already passed
    (end in 3 minutes, warning of 5), the warning counts as seen: whoever
    just typed the end time does not need to be told it is close."""
    warn_minutes = clamp_warn(warn_minutes)
    already_inside = warn_minutes > 0 and now >= end - 60.0 * warn_minutes
    return Alarm(end=end, warn_minutes=warn_minutes, warn_acked=already_inside)


def phase(alarm: Alarm | None, now: float) -> str:
    if alarm is None:
        return IDLE
    if now >= alarm.end:
        return ENDED
    if alarm.warn_minutes > 0 and now >= alarm.warn_at:
        return WARNING
    return IDLE


def is_spent(alarm: Alarm | None, now: float) -> bool:
    """True once the end flash has run its full course unclicked."""
    return alarm is not None and now - alarm.end >= END_FLASH_LIMIT


def flashing(alarm: Alarm | None, now: float) -> str | None:
    """WARNING or ENDED if the tile should be flashing now, else None."""
    current = phase(alarm, now)
    if current == ENDED:
        return None if is_spent(alarm, now) else ENDED
    if current == WARNING and not alarm.warn_acked:
        return WARNING
    return None


def acknowledge(alarm: Alarm | None, now: float) -> Alarm | None:
    """The alarm after a click on a flashing tile.

    Clicking the warning keeps the alarm (the end flash is still to come);
    clicking the end flash finishes it, hence None.
    """
    current = flashing(alarm, now)
    if current == ENDED:
        return None
    if current == WARNING:
        return replace(alarm, warn_acked=True)
    return alarm


def flash_on(now: float) -> bool:
    """Which half of the flash the tile is in: a second on, a second off.
    Slow on purpose. It has to catch the eye, not startle anyone."""
    return int(now) % 2 == 0


def describe(alarm: Alarm, now: float, twenty_four: bool) -> str:
    """Menu wording, e.g. "2:50 p.m., 5 min warning" or "9:00 a.m. tomorrow,
    no warning".

    The tile itself never shows a.m./p.m., but here it is spelled out: this
    line is where a time entered in the wrong half of the day gets caught.
    (24-hour times cannot be ambiguous, so they are left bare.)
    """
    end = datetime.fromtimestamp(alarm.end)
    if twenty_four:
        when = f"{end.hour:02d}:{end.minute:02d}"
    else:
        half = "a.m." if end.hour < 12 else "p.m."
        when = f"{end.hour % 12 or 12}:{end.minute:02d} {half}"
    if end.date() != datetime.fromtimestamp(now).date():
        when += " tomorrow"
    warning = f"{alarm.warn_minutes} min warning" if alarm.warn_minutes else "no warning"
    return f"{when}, {warning}"
