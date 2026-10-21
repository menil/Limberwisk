import pytest
from support import sequences as seq
from support.fake_hid import FakeHidDevice

from limberwisk.devices import MUTEME_ORIGINAL_PID, MUTEME_VID
from limberwisk.hid_io import DeviceError, HidDevice

READ_SIZE = 64
TIMEOUT_MS = 100


def drain(device: FakeHidDevice, count: int) -> list[list[int]]:
    return [device.read(READ_SIZE, TIMEOUT_MS) for _ in range(count)]


def test_fake_satisfies_the_hid_device_protocol():
    assert isinstance(FakeHidDevice(), HidDevice)


def test_replays_queued_reports_in_order(fake_device):
    fake_device.feed(*seq.tap())
    assert drain(fake_device, len(seq.tap())) == seq.tap()


def test_fed_reports_are_copied(fake_device):
    report = seq.report(seq.TOUCH_BEGIN)
    fake_device.feed(report)
    report[3] = seq.IDLE
    assert fake_device.read(READ_SIZE, TIMEOUT_MS)[3] == seq.TOUCH_BEGIN


def test_empty_queue_behaves_like_a_read_timeout(fake_device):
    assert fake_device.read(READ_SIZE, TIMEOUT_MS) == []


def test_open_records_the_requested_identifiers():
    device = FakeHidDevice()
    device.open(MUTEME_VID, MUTEME_ORIGINAL_PID)
    assert device.opened_with == (MUTEME_VID, MUTEME_ORIGINAL_PID)


def test_writes_are_recorded(fake_device):
    assert fake_device.write(bytes([0x00, 0x02])) == 2
    assert fake_device.writes == [bytes([0x00, 0x02])]


def test_disconnect_makes_reads_and_writes_fail(fake_device):
    fake_device.disconnect()
    with pytest.raises(DeviceError):
        fake_device.read(READ_SIZE, TIMEOUT_MS)
    with pytest.raises(DeviceError):
        fake_device.write(bytes([0x00, 0x01]))


def test_disconnect_after_serves_the_requested_reads_then_fails(fake_device):
    fake_device.feed(*seq.tap())
    fake_device.disconnect_after(2)
    assert [r[3] for r in drain(fake_device, 2)] == [seq.TOUCH_BEGIN, seq.TOUCH_HELD]
    with pytest.raises(DeviceError):
        fake_device.read(READ_SIZE, TIMEOUT_MS)


def test_cannot_open_a_disconnected_device():
    device = FakeHidDevice()
    device.disconnect()
    with pytest.raises(DeviceError):
        device.open(MUTEME_VID, MUTEME_ORIGINAL_PID)


def test_reading_before_open_fails():
    with pytest.raises(DeviceError, match="not open"):
        FakeHidDevice().read(READ_SIZE, TIMEOUT_MS)


def test_close_is_idempotent_and_blocks_further_io(fake_device):
    fake_device.close()
    fake_device.close()
    with pytest.raises(DeviceError, match="not open"):
        fake_device.read(READ_SIZE, TIMEOUT_MS)
