"""
dmgbuild settings for the Gnomon installer image.

Usage (after scripts/build_release.sh and signing; scripts/release.sh does
all of it):

    ./venv-release/bin/dmgbuild -s packaging/dmg_settings.py "Gnomon" dist/Gnomon-<version>.dmg

GEOMETRY CONTRACT with scripts/make_dmg_background.py: window 540x320,
icon size 100, app icon centred at (140, 105), Applications alias at
(400, 105). The arrow in the background is drawn between those two slots:
move one, move both. (MailRepo's installer layout, 20 points higher.)
"""

# dmgbuild exec()s this file without __file__, so paths are relative to
# the working directory: RUN FROM THE REPO ROOT (as the usage line does).
import os.path

if not os.path.isdir("packaging"):
    raise SystemExit("run dmgbuild from the repo root (packaging/ not found here)")

application = os.path.join("dist", "Gnomon.app")

files = [application]
symlinks = {"Applications": "/Applications"}

background = os.path.join("packaging", "dmg_background.tiff")

window_rect = ((200, 200), (540, 320))
default_view = "icon-view"
icon_size = 100
text_size = 12

icon_locations = {
    "Gnomon.app": (140, 105),
    "Applications": (400, 105),
}

# Show nothing else: no toolbar, no sidebar, no status bar.
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False

format = "UDZO"  # compressed, read-only
