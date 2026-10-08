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
- **Menu:** right-click (or two-finger click) the tile — Session Alert,
  24-Hour Time, Colours, Size (Small / Medium / Large), Move to Top Centre,
  Quit Gnomon.
- **Colours:** Ink, Paper, Slate, Witching Hour, Crimson Veil, Terminal.
- **Quit:** from that menu. There is no Dock icon and no menu bar; the tile
  is the whole interface.

### Session alert

Right-click, **Session Alert…**, enter the time the session ends and how much
warning you want (none, or 1 to 5 minutes). A small dot appears at the left
of the tile while an alert is set.

- At the warning, the tile flashes: its own two colours swapped, a second on
  and a second off. **Click the tile** and it stops; the alert stays set.
- At the end of the session it flashes again, this time **red**, whatever the
  colour scheme. Click it and the alert is finished.
- To change or cancel one, open the same menu item (it shows what is set), or
  choose **Turn Off Session Alert**.

An end time that has already passed today is taken to mean tomorrow, and the
menu says so ("9:00 tomorrow"), so a mistyped time does not fail silently. An
end flash that nobody clicks stops by itself after ten minutes. The form
opens on the minute of the hour you used last (ten to the hour, the first
time) and the warning you used last.

Position, size, colours and any alert that is set are remembered between
launches. If the
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
become the key window, so dragging it, clicking it or opening its menu leaves
keyboard focus in Meet. The one exception is the session-alert form, which
has to be typed into: it takes focus while it is open and hands it back to
whatever was in front when it closes.

**Above everything, on every Space.** Status window level (above normal
windows and the menu bar), joined to all Spaces and flagged as a full-screen
auxiliary so it stays put when Meet goes full screen.

**Opens under the camera.** First launch, and "Move to Top Centre", put the
tile at the top centre of the built-in display, just below the menu bar. On a
Mac with external monitors it picks the screen with the camera housing.

**Digits that hold still.** System font with monospaced numerals, so the time
does not shimmy as seconds change. The time is centred as it reads, so a
one-digit hour in 12-hour mode sits in the middle of the tile (at the cost of
one half-digit shift when 9:59:59 becomes 10:00:00). The colons are lifted
to the middle of the digits (the font's own colon sits on the baseline).

**A tick that does not drift.** The timer is re-armed from the wall clock
after every tick instead of repeating every 1.0s, so lateness never
accumulates, and it runs in the run loop's common modes, so the clock keeps
going while it is being dragged or its menu is open.

**No AM/PM.** 12- or 24-hour follows the macOS setting until changed from the
menu; either way the tile shows digits only.

**Ink by default.** Ink and Paper are the Daybook/Palestra palette either way
round; the other four schemes take their names and colours from Libram's
themes. Ink is the default because the tile sits over Meet, which is dark,
and a pale tile beside the camera is a small lamp.

**The alert is arithmetic, not a second timer.** Once a second the tick asks
one question — given the end time, the warning, and what has been clicked,
should the tile be flashing now? — so sleep, a closed lid or a changed system
clock cannot leave it out of step. The flash is slow (one second on, one off)
because it has to catch the eye beside a camera, not startle anyone. The two
flashes look different on purpose: if the warning was never clicked, the
change to red is how you know the session has actually ended.

**A click answers a flash; anything else is a drag.** The view takes every
mouse-down itself. On a flashing tile the press is consumed; otherwise it is
handed to the window server as a window drag (`performWindowDragWithEvent_`),
the same mechanism a title bar uses.

## Data

One file: `~/Library/Application Support/Gnomon/state.json` (position, size,
colour scheme, hour mode, the alert that is set, and the last-used warning
and end minute). Written atomically, a moment after the tile stops
moving and again on quit. Delete it to reset everything.
`GNOMON_DATA_DIR` overrides the folder.

## Architecture

```
gnomon/
  main.py               # Entry point (also what the .app runs)
  core/
    clockface.py         # Time formatting, tick timing, tile geometry — no AppKit
    alarm.py             # Session alert: when to flash, what a click does — no AppKit
    schemes.py           # Colour schemes (plain data)
    state.py             # Remembered settings: load (forgiving) / save (atomic)
  ui/
    app.py               # The panel, the view that draws it, the menu, the timer
    alert_form.py        # The session-alert form (the only place that takes typing)
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
are centred at every size, that every colour scheme paints what it says, that
the menu items act, that presets and pinch resize about the top centre, and
that position, size, colours and a set alert survive a relaunch. The alert is
walked through its whole sequence against a fixed clock, including the
colours actually painted during each flash.

What the tests cannot reach is the window server's half of the gestures — the
mouse drag itself and the edge resize — or the alert form actually on screen
(it is built and inspected, never run). The tests pin the configuration those
depend on, but the gestures themselves are only ever checked by hand.
