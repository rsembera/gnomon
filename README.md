# Gnomon

**A small always-on-top clock with seconds, for timing sessions without looking away from the camera.**

Google Meet has no clock. The menu-bar clock is in the corner of the screen,
where a glance at it is a glance the client can see. Apple's Clock app is
enormous. Gnomon is a tile about three centimetres wide that floats over
everything, opens directly under the camera, and can be dragged anywhere,
including into the menu bar beside the notch.

(A gnomon is the part of a sundial that casts the shadow.)

## Using it

- **Move:** drag it, anywhere on the tile.
- **Resize:** drag any edge, or pinch on the trackpad with the pointer over
  the tile. The shape is locked, so the whole clock scales; 20 to 240 points
  tall.
- **Menu:** right-click (or two-finger click) the tile — 24-Hour Time, Dark,
  Size (Small / Medium / Large), Move to Top Centre, Quit Gnomon.
- **Quit:** from that menu. There is no Dock icon and no menu bar; the tile
  is the whole interface.

Position, size and appearance are remembered between launches. If the
remembered spot is on a monitor that is no longer attached, the clock opens
at top centre instead.

## Running it

```sh
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py
```

## Building the app

```sh
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python setup_app.py py2app       # -> dist/Gnomon.app
cp -R dist/Gnomon.app /Applications/
```

The build is ad-hoc signed, which is all a locally built app needs on the
machine that built it. To hand it to anyone else it would have to go through
the Developer ID sign / notarize steps in `edgecase/docs/Mac_Packaging_Guide.md`.

## Design decisions

**Native AppKit, not Flask + pywebview.** Every other app in the portfolio is
a web UI in a native shell. This one is a single native panel, because its
whole job is to sit on top of a video call without getting in the way, and a
web view cannot do that properly: a pywebview window is an ordinary window
that takes focus when clicked, its frameless-drag code throws the window
off-screen when dragged against the top edge (where this clock lives), and a
WebKit process is a lot of machinery to keep running through a session for
eight glyphs. PyObjC is the only dependency.

**It never takes focus.** The tile is a non-activating panel that refuses to
become the key window, so dragging it or opening its menu leaves keyboard
focus in Meet.

**Above everything, on every Space.** Status window level (above normal
windows and the menu bar), joined to all Spaces and flagged as a full-screen
auxiliary so it stays put when Meet goes full screen.

**Opens under the camera.** First launch, and "Move to Top Centre", put the
tile at the top centre of the built-in display, just below the menu bar. On a
Mac with external monitors it picks the screen with the camera housing.

**Digits that hold still.** System font with monospaced numerals, so the time
does not shimmy as seconds change; right-aligned in a fixed box, so the
seconds do not jump when 9:59:59 becomes 10:00:00. The colons are lifted to
the middle of the digits (the font's own colon sits on the baseline).

**A tick that does not drift.** The timer is re-armed from the wall clock
after every tick instead of repeating every 1.0s, so lateness never
accumulates, and it runs in the run loop's common modes, so the clock keeps
going while it is being dragged or its menu is open.

**No AM/PM.** 12- or 24-hour follows the macOS setting until changed from the
menu; either way the tile shows digits only.

**Ink on paper, inverted by default.** The Daybook/Palestra palette. Dark is
the default because the tile sits over Meet, which is dark, and a paper tile
beside the camera is a small lamp. "Dark" in the menu switches to paper.

## Data

One file: `~/Library/Application Support/Gnomon/state.json` (position, size,
appearance, hour mode). Written atomically, a moment after the tile stops
moving and again on quit. Delete it to reset everything.
`GNOMON_DATA_DIR` overrides the folder.

## Architecture

```
gnomon/
  main.py               # Entry point (also what the .app runs)
  core/
    clockface.py         # Time formatting, tick timing, tile geometry — no AppKit
    state.py             # Remembered settings: load (forgiving) / save (atomic)
  ui/
    app.py               # The panel, the view that draws it, the menu, the timer
  scripts/
    make_icon.py         # Draws assets/icon.icns with AppKit + iconutil
  assets/
    icon.icns
  setup_app.py           # py2app build
  tests/
```

## Tests

```sh
./venv/bin/python -m pytest
./venv/bin/ruff check .
```

`core/` is tested directly. `tests/test_ui.py` builds the real panel without
showing it and renders the face off-screen: it checks that the digits fit and
are centred at every size in both appearances, that the menu items act, that
presets and pinch resize about the top centre, and that position and size
survive a relaunch.

What the tests cannot reach is the window server's half of the gestures — the
mouse drag itself and the edge resize. Those are AppKit's stock behaviour for
a panel configured this way, and the tests pin that configuration
(movable-by-background, resizable, aspect-locked), but the gestures
themselves are only ever checked by hand.
