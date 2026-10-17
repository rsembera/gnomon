"""Open at Login: offered only where it can work, and toggles both ways."""

import pytest

pytest.importorskip("Foundation")

from ui import login  # noqa: E402


class FakeService:
    def __init__(self, status=0, approve=False, fail=False):
        self._status, self.approve, self.fail = status, approve, fail

    def status(self):
        return self._status

    def registerAndReturnError_(self, _err):
        if self.fail:
            return False, "refused"
        self._status = login.REQUIRES_APPROVAL if self.approve else login.ENABLED
        return True, None

    def unregisterAndReturnError_(self, _err):
        self._status = 0
        return True, None


@pytest.fixture
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(login, "_open_login_items", lambda: calls.append(1))
    return calls


def use(monkeypatch, service):
    monkeypatch.setattr(login, "_service", lambda: service)


def test_not_offered_when_run_from_source():
    # Under pytest the main bundle is Python's, not Gnomon's.
    assert login._service() is None
    assert not login.available() and not login.is_on()


def test_turns_on_then_off(monkeypatch, opened):
    use(monkeypatch, FakeService())
    assert login.toggle() is True and login.is_on()
    assert login.toggle() is False and not login.is_on()
    assert opened == []


def test_needing_approval_counts_as_on_and_opens_settings(monkeypatch, opened):
    use(monkeypatch, FakeService(approve=True))
    assert login.toggle() is True
    assert opened == [1]


def test_a_refusal_opens_settings_and_stays_off(monkeypatch, opened):
    use(monkeypatch, FakeService(fail=True))
    assert login.toggle() is False
    assert opened == [1]


def test_no_service_means_nothing_happens(monkeypatch, opened):
    use(monkeypatch, None)
    assert login.toggle() is False and opened == []

