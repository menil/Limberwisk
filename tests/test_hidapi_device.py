import sys
import threading

import pytest
from support.fake_hid_module import FakeHidModule, FakeRawDevice

from limberwisk import hidapi_device
from limberwisk.hid_io import DeviceError, DeviceNotFoundError, HidDevice
from limberwisk.hidapi_device import HidapiDevice, open_first_known

ORIGINAL = {"vendor_id": 0x3603, "product_id": 0x0001}
UNRELATED = {"vendor_id": 0x0BDA, "product_id": 0x1100}


@pytest.fixture
def hid_module():
    return FakeHidModule([UNRELATED, ORIGINAL])


@pytest.fixture
def opened(hid_module):
    device = HidapiDevice(hid_module)
    device.open(0x3603, 0x0001)
    return device, hid_module.created[0]


def test_satisfies_the_hid_device_protocol(hid_module):
    assert isinstance(HidapiDevice(hid_module), HidDevice)


def test_open_uses_blocking_reads(opened):
    _, raw = opened
    assert raw.opened_with == (0x3603, 0x0001)
    assert raw.nonblocking == 0


def test_open_failure_becomes_device_error(hid_module):
    hid_module.next_device_factory = lambda: _failing_open(OSError("unplugged"))
    with pytest.raises(DeviceError, match="cannot open 0x3603:0x0001"):
        HidapiDevice(hid_module).open(0x3603, 0x0001)


def _failing_open(error):
    raw = FakeRawDevice()
    raw.open_error = error
    return raw


def test_a_failure_after_open_does_not_leak_the_handle(hid_module):
    leaked = FakeRawDevice()
    leaked.set_nonblocking = _raise_oserror
    hid_module.next_device_factory = lambda: leaked
    with pytest.raises(DeviceError, match="cannot open"):
        HidapiDevice(hid_module).open(0x3603, 0x0001)
    assert leaked.closed


def _raise_oserror(_value):
    raise OSError("set_nonblocking failed")


def test_read_returns_the_report_as_a_list(opened):
    device, raw = opened
    raw.reports.append([0, 0, 0, 4, 0, 0, 0, 0])
    assert device.read(64, 50) == [0, 0, 0, 4, 0, 0, 0, 0]


def test_read_timeout_is_an_empty_list(opened):
    device, _ = opened
    assert device.read(64, 50) == []


@pytest.mark.parametrize("error", [OSError("read error"), ValueError("closed")])
def test_read_errors_become_device_error(opened, error):
    device, raw = opened
    raw.read_error = error
    with pytest.raises(DeviceError, match="read failed"):
        device.read(64, 50)


def test_write_returns_the_byte_count(opened):
    device, raw = opened
    assert device.write(bytes([0, 2])) == 2
    assert raw.written == [bytes([0, 2])]


def test_write_exceptions_become_device_error(opened):
    device, raw = opened
    raw.write_error = OSError("write error")
    with pytest.raises(DeviceError, match="write failed"):
        device.write(bytes([0, 2]))


@pytest.mark.parametrize("result", [-1, 1])
def test_a_failed_or_short_write_becomes_device_error(opened, result):
    device, raw = opened
    raw.write_result = result
    with pytest.raises(DeviceError, match="write failed"):
        device.write(bytes([0, 2]))


def test_io_before_open_fails(hid_module):
    device = HidapiDevice(hid_module)
    with pytest.raises(DeviceError, match="not open"):
        device.read(64, 50)
    with pytest.raises(DeviceError, match="not open"):
        device.write(bytes([0, 1]))


def test_close_is_idempotent_and_swallows_errors_from_a_vanished_device(opened):
    device, raw = opened
    raw.close_error = OSError("gone")
    device.close()
    device.close()
    assert raw.closed
    with pytest.raises(DeviceError, match="not open"):
        device.read(64, 50)


def test_open_first_known_opens_the_listed_muteme_not_the_unrelated_device(hid_module):
    open_first_known(hid_module)
    assert hid_module.created[0].opened_with == (0x3603, 0x0001)


def test_open_first_known_fails_when_nothing_matches():
    with pytest.raises(DeviceNotFoundError, match="no MuteMe"):
        open_first_known(FakeHidModule([UNRELATED]))


def test_first_hidapi_import_off_the_main_thread_is_refused(monkeypatch):
    # Importing hid on a worker thread crashes the process at exit on macOS.
    monkeypatch.delitem(sys.modules, "hid", raising=False)
    errors = []

    def import_from_worker():
        try:
            hidapi_device._load_hid()
        except RuntimeError as error:
            errors.append(error)

    thread = threading.Thread(target=import_from_worker)
    thread.start()
    thread.join()
    assert len(errors) == 1
    assert "main thread" in str(errors[0])


def test_enumeration_is_limited_to_known_vendors(hid_module):
    requested = []
    original = hid_module.enumerate
    hid_module.enumerate = lambda vid=0, pid=0: requested.append(vid) or original(vid, pid)
    open_first_known(hid_module)
    assert 0 not in requested
    assert set(requested) <= {0x3603, 0x20A0}


def test_the_opened_device_remembers_which_known_model_it_is(opened):
    device, _ = opened
    assert device.device_id.model == "MuteMe Original"
    assert device.device_id.verified


def test_the_model_is_forgotten_by_a_device_that_was_never_opened(hid_module):
    assert HidapiDevice(hid_module).device_id is None
