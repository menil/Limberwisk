import pytest
from support.fake_hid import FakeHidDevice

from muteme_flow.devices import MUTEME_ORIGINAL_PID, MUTEME_VID


@pytest.fixture
def fake_device() -> FakeHidDevice:
    device = FakeHidDevice()
    device.open(MUTEME_VID, MUTEME_ORIGINAL_PID)
    return device
