"""Gnomon — entry point.

    python main.py

A small always-on-top clock with seconds. Drag it anywhere; drag an edge or
pinch to resize; right-click for the menu (including Quit). The packaged
app (see setup_app.py) starts here too.
"""

import sys
from pathlib import Path

# Make the project importable however this file is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui.app import run

if __name__ == "__main__":
    run()
