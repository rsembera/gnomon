"""Open at Login, through macOS's own login-items service.

SMAppService (macOS 13 and newer) is the supported way for an app to put
itself in System Settings > General > Login Items. The item it adds is the
same one a person would add by hand there, and can be removed from either
place. On macOS 12 the service does not exist, and the menu item is simply
not offered: the page at richardsembera.ncf.ca/gnomon.html explains the
manual route.

Only the packaged app offers it. Run from source, the "main app" macOS sees
is Python itself, and registering that would put Python in Login Items.
"""

from __future__ import annotations

from Foundation import NSBundle

BUNDLE_ID = "ca.lightinextension.gnomon"

ENABLED = 1            # SMAppServiceStatusEnabled
REQUIRES_APPROVAL = 2  # SMAppServiceStatusRequiresApproval


def _service():
    """The app's login-item service, or None where it cannot be offered."""
    if NSBundle.mainBundle().bundleIdentifier() != BUNDLE_ID:
        return None
    try:
        from ServiceManagement import SMAppService
        return SMAppService.mainAppService()
    except Exception:  # macOS 12: no SMAppService class
        return None


def available() -> bool:
    return _service() is not None


def is_on() -> bool:
    service = _service()
    return service is not None and service.status() in (ENABLED, REQUIRES_APPROVAL)


def toggle() -> bool:
    """Turn Open at Login on if it is off, off if it is on. Returns the new
    setting. If macOS wants the person to confirm it (status "requires
    approval"), or refuses, Login Items in System Settings is opened so they
    can finish it there."""
    service = _service()
    if service is None:
        return False
    if is_on():
        ok, _error = service.unregisterAndReturnError_(None)
    else:
        ok, _error = service.registerAndReturnError_(None)
    if not ok or service.status() == REQUIRES_APPROVAL:
        _open_login_items()
    return is_on()


def _open_login_items() -> None:
    try:
        from ServiceManagement import SMAppService
        SMAppService.openSystemSettingsLoginItems()
    except Exception:
        pass
