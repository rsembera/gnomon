"""Remembered settings: where the tile sits, how big it is, how it looks,
and the session alert if one is armed.

One small JSON file in the OS's application-data folder, the same place
EdgeCase and MailRepo keep theirs, so replacing the .app never loses it.
Writes are atomic (tmp + rename), as everywhere else in the portfolio.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from core import alarm, schemes
from core.clockface import DEFAULT_HEIGHT, clamp_height

STATE_FILE = "state.json"


@dataclass
class State:
    # Window origin in AppKit screen coordinates (bottom-left). None means
    # "never placed": the app puts the tile at top centre, under the camera.
    x: float | None = None
    y: float | None = None
    height: float = DEFAULT_HEIGHT
    scheme: str = schemes.DEFAULT
    # None follows the macOS 12/24-hour setting; True/False is an explicit
    # choice made from the menu.
    twenty_four: bool | None = None
    # The armed session alert, if any (see core/alarm.py). Kept here so that
    # quitting and reopening mid-session does not lose it.
    alarm_end: float | None = None
    alarm_warn_acked: bool = False
    # What the alert form offers next time: the warning last chosen, and the
    # minute of the hour sessions last ended on.
    warn_minutes: int = alarm.DEFAULT_WARN_MINUTES
    end_minute: int = alarm.DEFAULT_END_MINUTE


def data_dir() -> Path:
    """Folder the state file lives in. GNOMON_DATA_DIR overrides (tests)."""
    override = os.environ.get("GNOMON_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Gnomon"


def _number(value) -> float | None:
    """A finite float, or None for anything that is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def load(path: Path | None = None) -> State:
    """Read the state file. A missing, unreadable or nonsensical file is
    not an error: the clock just opens with defaults for whatever is bad."""
    path = path or data_dir() / STATE_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return State()
    if not isinstance(raw, dict):
        return State()

    state = State()
    x, y = _number(raw.get("x")), _number(raw.get("y"))
    if x is not None and y is not None:  # a position is both or neither
        state.x, state.y = x, y
    height = _number(raw.get("height"))
    if height is not None:
        state.height = clamp_height(height)
    if schemes.is_known(raw.get("scheme")):
        state.scheme = raw["scheme"]
    elif raw.get("dark") is False:
        # 1.0 stored a dark/paper switch instead of a scheme name.
        state.scheme = "paper"
    if isinstance(raw.get("twenty_four"), bool):
        state.twenty_four = raw["twenty_four"]

    alarm_end = _number(raw.get("alarm_end"))
    if alarm_end is not None:
        state.alarm_end = alarm_end
        state.alarm_warn_acked = raw.get("alarm_warn_acked") is True
    warn = _number(raw.get("warn_minutes"))
    if warn is not None:
        state.warn_minutes = alarm.clamp_warn(warn)
    end_minute = _number(raw.get("end_minute"))
    if end_minute is not None and 0 <= end_minute < 60:
        state.end_minute = int(end_minute)
    return state


def save(state: State, path: Path | None = None) -> None:
    """Write the state file atomically."""
    path = path or data_dir() / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(asdict(state), handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
