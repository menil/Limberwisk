import pytest
from support.fake_hid import FakeHidDevice, opened


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every test away from the real home folder (logs, preferences)."""
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def fake_device() -> FakeHidDevice:
    return opened(FakeHidDevice())
