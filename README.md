# Gnomon

**A small always-on-top clock with seconds, for timing sessions without looking away from the camera.**

Google Meet has no clock. The menu-bar clock is in the corner of the screen,
where a glance at it is a glance the client can see. Apple's Clock app is
enormous. Gnomon is a tile about three centimetres wide that floats over
everything, opens directly under the camera, and can be dragged anywhere,
including into the menu bar beside the notch.

(A gnomon is the part of a sundial that casts the shadow.)

## Install

Requires a Mac with Apple Silicon (M1 or later) and macOS 12 or newer.

1. Download `Gnomon-1.5.3.dmg` from the
   [Releases page](https://github.com/rsembera/gnomon/releases).
2. Open it and drag Gnomon to Applications.
3. Open Gnomon. The clock appears at the top centre of the screen, under the
   camera. Drag it wherever you like; right-click it for everything else,
   including Quit.

The app is signed and notarized by Apple, so it opens without a security
warning. It makes no network connections and collects nothing.

SHA-256 of `Gnomon-1.5.3.dmg`:
`99ff5b5604259b33cc26244b6fe975d6025f8a536f6d23e79fef734c4ff11979`

## Using it

- **Move:** drag it, anywhere on the tile.
- **Resize:** drag any edge or corner (the pointer turns into resize arrows
  there), or pinch on the trackpad with the pointer over the tile. The shape
  is locked, so the whole clock scales; 20 to 240 points tall.
- **Menu:** right-click (or two-finger click) the tile — Session Alert,
  24-Hour Time, Colours, Font, Size (Small / Medium / Large), Move To,
  Open at Login, About Gnomon, Quit Gnomon.
- **Open at Login:** tick it and Gnomon starts whenever you log in. It adds
  Gnomon to System Settings > General > Login Items, and can be undone from
  either place. macOS 13 and newer; on macOS 12, add Gnomon to System
  Preferences > Users & Groups > Login Items by hand.
- **Colours:** three dark (White, Green or Amber digits on black) and three
  light (Black, Blue or Red digits on a pale tile).
- **Font:** Standard, Serif, Mono, DIN, Typewriter, LED. The tile keeps its
  height and changes width to suit the face.
- **Move To:** Top Centre, Top Right, Bottom Right, Bottom Centre, Bottom
  Left, Top Left, on whichever screen the tile is on. A tile parked this way
  stays parked when it is resized; dragging it anywhere else lets go.
- **Quit:** from that menu. There is no Dock icon and no menu bar; the tile
  is the whole interface. The first time it runs, Gnomon says so.

### Session alert

Right-click, **Session Alert…**, enter the time the session ends and how much
warning you want (none, or 1 to 5 minutes). A small dot appears at the left
of the tile while an alert is set.

- At the warning, the tile flashes **amber**, a second on and a second off.
  **Click the tile** and it stops; the alert stays set.
- At the end of the session it flashes again, this time **red**. Click it and
  the alert is finished. Both flashes are the same in every colour scheme.
- To change or cancel one, open the same menu item (it shows what is set), or
  choose **Turn Off Session Alert**.

A session alert is never more than twelve hours away, so the end time is
taken in whichever half of the day comes first: at 11:30 a.m., 12:20 means
12:20 p.m. even if the form still says AM, and at 11:30 p.m., 12:10 means ten
past midnight. The menu shows what is set with a.m. or p.m. spelled out
("2:50 p.m., 5 min warning", "12:10 a.m. tomorrow"). An end flash that nobody
clicks stops by itself after ten minutes, and it carries on if Gnomon is
restarted in the meantime. The form opens on the alert that is set, or, once
a session has ended, on the next one: the minute of the hour you used last
(ten to the hour, the first time) and the warning you used last.

Position, size, colours, font and any alert that is set are remembered
between launches. If the remembered spot is on a monitor that is no longer
attached, the clock opens at top centre instead.

## Running it

```sh
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py
```

## Building the app

There are two builds, and the difference matters.

**For this Mac** (quick, while developing):

```sh
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python setup_app.py py2app       # -> dist/Gnomon.app
```

**For anyone else** (the one to release):

```sh
./scripts/build_release.sh                  # -> dist/Gnomon.app
```

The first uses the everyday venv, which is Homebrew's Python. Homebrew
compiles Python for the Mac it is installed on, so an app bundled from it
opens only on that Mac's version of macOS or newer, whatever its Info.plist
says. The release script builds from the Python published at python.org
instead (install its macOS universal installer once; it sits beside
Homebrew's), which is built to run on older systems. The script then drops
the Intel half of every compiled file and refuses to finish unless everything
in the bundle is Apple Silicon and runs on the macOS version the app
declares.

**Requirements for the released app: Apple Silicon, macOS 12 or newer.**

Either build is ad-hoc signed, which is all an app needs on the machine that
built it.

## Releasing

```sh
./scripts/build_release.sh      # dist/Gnomon.app
./scripts/release.sh            # dist/Gnomon-<version>.dmg
```

`release.sh` signs the app with the Developer ID certificate (every library
first, then the bundle, hardened runtime), has Apple notarize it, staples the
ticket, builds the disk image with `dmgbuild` (`packaging/dmg_settings.py`,
background drawn by `scripts/make_dmg_background.py`), then signs, notarizes
and staples the image too. It stops if Apple does not answer "Accepted" or if
Gatekeeper would refuse the result, and finishes by printing the image's
SHA-256. It is the EdgeCase/MailRepo recipe written down as a script; the
certificate and notarization profile it expects are described at the top of
the file. The version number comes from `core/__init__.py`.

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

**Opens under the camera.** First launch puts the tile at the top centre of
the built-in display, just below the menu bar. On a Mac with external
monitors it picks the screen with the camera housing.

**Move To parks; dragging un-parks.** The six places are measured from the
screen's visible frame, so a parked tile sits just under the menu bar, just
above the Dock and clear of a Dock on the side; "centre" is the centre of the
whole screen, where the camera is. The place is remembered only so that a
resize can keep the tile there (a tile in a corner grows into the screen, not
off it). There is no un-park command: the remembered place counts only while
the tile is still exactly at it.

**Digits that hold still.** Every face is set with numerals of equal width,
so the time does not shimmy as seconds change. The time is centred as it
reads, so a one-digit hour in 12-hour mode sits in the middle of the tile (at
the cost of one half-digit shift when 9:59:59 becomes 10:00:00).

**Five fonts already on the Mac, and one that is drawn.** Standard, Serif
(New York) and Mono (SF Mono) are the system's own; DIN Alternate and
American Typewriter ship with macOS. The LED face is not a font: macOS has no
seven-segment typeface, so its digits are drawn, seven hexagons apiece
(`core/sevenseg.py`), with the segments a digit is not using shown faintly as
on a real display. Either way nothing is bundled, so there is nothing to
license. The tile's proportions come from the face's own measurements, which
is why a monospaced face makes a wider tile and DIN a narrower one.

**Colons at the middle of the digits, by measurement.** The system faces
raise a colon by themselves when it sits between numerals; the others leave
it on the baseline. The font's metrics do not say which (1.0 trusted them
and ended up with colons level with the top of the digits), so each face's
colon is drawn once off-screen and raised by however far it actually fell
short. (The LED face's colon dots are symmetric by construction.)

**A tick that does not drift.** The timer is re-armed from the wall clock
after every tick instead of repeating every 1.0s, so lateness never
accumulates, and it runs in the run loop's common modes, so the clock keeps
going while it is being dragged or its menu is open.

**No AM/PM.** 12- or 24-hour follows the macOS setting until changed from the
menu; either way the tile shows digits only.

**Colour schemes are pairs, named for the digits.** Three dark, three light.
White and Black are the Daybook/Palestra ink and paper either way round.
Green and Amber are LED-clock colours on black; Blue and Red on the pale tile
are the most saturated versions that stay readable there (an LED green or
amber would wash out on a pale background altogether). (1.1.0 borrowed
Libram's themes, which vary the tint of a dark background: on a tile this
size they were indistinguishable.) White is the default because the tile sits
over Meet, which is dark, and a pale tile beside the camera is a small lamp.

**The alert is arithmetic, not a second timer.** Once a second the tick asks
one question — given the end time, the warning, and what has been clicked,
should the tile be flashing now? — so sleep, a closed lid or a changed system
clock cannot leave it out of step. The flash is slow (one second on, one off)
because it has to catch the eye beside a camera, not startle anyone. The two
flashes are amber and red in every scheme, like a traffic light: fixed, so
no scheme's own colours can blur them, and different, so that if the
warning was never clicked the change to red is how you know the session has
actually ended.

**A click answers a flash; an edge resizes; anything else is a drag.** The
view takes every mouse-down itself. On a flashing tile the press is consumed.
Within six points of an edge it starts a resize, which the view follows
itself (a borderless panel gets no resize handles from the system), with the
opposite side held still. Anywhere else it is handed to the window server as
a window drag (`performWindowDragWithEvent_`), the same mechanism a title bar
uses.

**Resize arrows, by an undocumented switch.** macOS lets only the active app
change the pointer, and Gnomon is never the active app, so its resize arrows
were being set and ignored. The window server has a per-app switch for this
("SetsCursorInBackground") which is not a documented interface; Gnomon turns
it on at launch (`allow_background_cursor` in `ui/app.py`) because there is
no documented way. If a future macOS removes it, the arrows stop appearing
and nothing else changes: resizing does not depend on it, and a test says so
out loud.

## Data

One file: `~/Library/Application Support/Gnomon/state.json` (position, size,
Move To place, colour scheme, typeface, hour mode, the alert that is set, the
last-used warning and end minute, and whether the first-launch hint has been
shown). Written atomically, a moment after the tile stops moving and again on
quit. Delete it to reset everything. `GNOMON_DATA_DIR` overrides the folder.

## Architecture

```
gnomon/
  main.py               # Entry point (also what the .app runs)
  core/
    clockface.py         # Time formatting, tick timing, tile geometry — no AppKit
    alarm.py             # Session alert: when to flash, what a click does — no AppKit
    schemes.py           # Colour schemes (plain data)
    fonts.py             # Typefaces (plain data)
    sevenseg.py          # Seven-segment geometry for the LED face — no AppKit
    state.py             # Remembered settings: load (forgiving) / save (atomic)
  ui/
    app.py               # The panel, the view that draws it, the menu, the timer
    alert_form.py        # The session-alert form (the only place that takes typing)
    about.py             # First-launch hint and the About panel
  scripts/
    make_icon.py         # Draws assets/icon.icns with AppKit + iconutil
    make_dmg_background.py  # Draws packaging/dmg_background.tiff
    build_release.sh     # The build other people can run (python.org Python)
    release.sh           # Sign, notarize, package: dist/Gnomon-<version>.dmg
  packaging/
    dmg_settings.py      # Installer window layout for dmgbuild
    dmg_background.tiff
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
are centred at every size and in every face, that the colons sit at the
middle of the digits, that every colour scheme paints what it says, that the
menu items act, that presets and pinch resize about the top centre, that each
Move To place lands on screen, and that position, size, colours, font and a
set alert survive a relaunch. The alert is walked through its whole sequence
against a fixed clock, including the colours actually painted during each
flash.

What the tests cannot reach is the window server's half of the gestures — the
mouse drag itself and the edge resize — or the alert form actually on screen
(it is built and inspected, never run). The tests pin the configuration those
depend on, but the gestures themselves are only ever checked by hand.

## Privacy

Gnomon makes no network connections and collects nothing. Its only file is
the settings file described under Data.

## Credits

Gnomon was designed by Richard Sembera and coded with Anthropic's Claude (Fable 5.1).

## License

GNU Affero General Public License v3.0. See [LICENSE](LICENSE) for details.
