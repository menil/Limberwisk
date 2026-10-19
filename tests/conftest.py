import pytest
from support.fake_hid import FakeHidDevice, opened


@pytest.fixture
def fake_device() -> FakeHidDevice:
    return opened(FakeHidDevice())
