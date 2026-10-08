"""The py2app manifest covers the code that actually exists.

A packaged build that silently omits a package fails only when that code is
first reached, on a machine with no terminal attached. This keeps
setup_app.py honest as the project grows.
"""

from pathlib import Path

import setup_app

ROOT = Path(__file__).resolve().parent.parent
NOT_SHIPPED = {"tests", "venv", "build", "dist", "scripts"}


def test_every_first_party_package_is_declared():
    on_disk = {
        path.parent.name
        for path in ROOT.glob("*/__init__.py")
        if path.parent.name not in NOT_SHIPPED
    }
    assert on_disk == set(setup_app.FIRST_PARTY_PACKAGES)


def test_declared_packages_are_bundled():
    bundled = set(setup_app.OPTIONS["packages"])
    assert set(setup_app.FIRST_PARTY_PACKAGES) <= bundled
    assert set(setup_app.THIRD_PARTY_PACKAGES) <= bundled


def test_entry_point_and_icon_exist():
    assert all((ROOT / script).is_file() for script in setup_app.APP)
    assert (ROOT / setup_app.OPTIONS["iconfile"]).is_file()


def test_bundle_is_an_agent_app():
    # No Dock icon: the clock itself is the interface.
    assert setup_app.OPTIONS["plist"]["LSUIElement"] is True
