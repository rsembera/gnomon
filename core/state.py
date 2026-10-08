"""Remembered settings: where the tile sits, how big it is, how it looks.

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

from core.clockface import DEFAULT_HEIGHT, clamp_height

STATE_FILE = "state.json"


@dataclass
class State:
    # Window origin in AppKit screen coordinates (bottom-left). None means
    # "never placed": the app puts the tile at top centre, under the camera.
    x: float | None = None
    y: float | None = None
    height: float = DEFAULT_HEIGHT
    # Dark tile by default: it sits over Meet, which is dark, and a paper
    # tile beside the camera is a small lamp.
    dark: bool = True
    # None follows the macOS 12/24-hour setting; True/False is an explicit
    # choice made from the menu.
    twenty_four: bool | None = None


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
    if isinstance(raw.get("dark"), bool):
        state.dark = raw["dark"]
    if isinstance(raw.get("twenty_four"), bool):
        state.twenty_four = raw["twenty_four"]
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
