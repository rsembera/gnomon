"""
py2app build script for Gnomon
Creates a standalone macOS .app bundle

Run with: python setup_app.py py2app

Same shape as EdgeCase's and MailRepo's build scripts, minus nearly all of
it: there is no web layer, no database and no native library to chase.

First-party code is declared as PACKAGES, not as an enumerated list of
modules, for the reason EdgeCase learned the hard way: a module list rots
silently as files are added. tests/test_packaging_manifest.py asserts that
every first-party package on disk is declared here.
"""

from setuptools import setup

APP = ['main.py']
APP_NAME = 'Gnomon'
APP_VERSION = '1.2.0'

# Third-party runtime dependencies: PyObjC and nothing else.
THIRD_PARTY_PACKAGES = [
    'objc',
    'AppKit',
    'Foundation',
    'CoreFoundation',
]

FIRST_PARTY_PACKAGES = [
    'core',
    'ui',
]

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'assets/icon.icns',
    'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleIdentifier': 'ca.lightinextension.gnomon',
        'CFBundleVersion': APP_VERSION,
        'CFBundleShortVersionString': APP_VERSION,
        'NSHighResolutionCapable': True,
        # 12.0: NSScreen.safeAreaInsets, used to find the display with the camera.
        'LSMinimumSystemVersion': '12.0',
        'NSRequiresAquaSystemAppearance': False,
        # Agent app: no Dock icon, no menu bar. ui/app.py sets the same
        # policy at runtime; declaring it here as well means the Dock icon
        # never flashes up during launch.
        'LSUIElement': True,
    },
    'packages': THIRD_PARTY_PACKAGES + FIRST_PARTY_PACKAGES,
    'includes': [
        # PyObjCTools is a namespace package (no __init__.py), which py2app's
        # `packages` option cannot locate; name the one module used instead.
        'PyObjCTools.AppHelper',
    ],
    'excludes': [
        'tkinter',
        'PyQt5',
        'PyQt6',
        'pytest',
        'ruff',
    ],
}

# Guarded so the manifest above can be imported and inspected (by
# tests/test_packaging_manifest.py) without invoking setuptools, which would
# exit the interpreter. py2app runs this file directly, so the build path is
# unaffected.
if __name__ == '__main__':
    # py2app refuses to build when install_requires is set, and modern
    # setuptools can populate it from pyproject.toml. Gnomon's pyproject has
    # no [project] table today, so this is a no-op; it is kept so that adding
    # one later does not break the build (EdgeCase/MailRepo, same guard).
    from py2app.build_app import py2app as _py2app_cmd

    class py2app_from_venv(_py2app_cmd):
        def finalize_options(self):
            self.distribution.install_requires = None
            super().finalize_options()

    setup(
        app=APP,
        name=APP_NAME,
        options={'py2app': OPTIONS},
        cmdclass={'py2app': py2app_from_venv},
    )
