import pytest

from limberwisk import devices


def entry(vid, pid):
    return {"vendor_id": vid, "product_id": pid}


def test_original_is_the_only_verified_device():
    verified = [d for d in devices.KNOWN_DEVICES if d.verified]
    assert [(d.vid, d.pid) for d in verified] == [(0x3603, 0x0001)]


def test_known_pairs_are_unique():
    pairs = [(d.vid, d.pid) for d in devices.KNOWN_DEVICES]
    assert len(pairs) == len(set(pairs))


@pytest.mark.parametrize(
    ("vid", "pid"),
    [(0x3603, 0x0001), (0x3603, 0x0004), (0x20A0, 0x42DA), (0x20A0, 0x42DB)],
)
def test_lookup_finds_listed_pairs(vid, pid):
    assert devices.lookup(vid, pid) is not None


@pytest.mark.parametrize(
    ("vid", "pid"),
    [
        (0x3603, 0x0005),  # right vendor, unlisted product: not a cross-product match
        (0x20A0, 0x0001),  # pids from one vendor must not match the other
        (0x0BDA, 0x1100),  # the hub HID seen on the dev machine
    ],
)
def test_lookup_rejects_unlisted_pairs(vid, pid):
    assert devices.lookup(vid, pid) is None


def test_first_connected_skips_unrelated_devices():
    listing = [entry(0x0BDA, 0x1100), entry(0x3603, 0x0001), entry(0x20A0, 0x42DA)]
    assert devices.first_connected(listing).pid == 0x0001


def test_first_connected_is_none_when_nothing_matches():
    assert devices.first_connected([entry(0x0BDA, 0x1100)]) is None
    assert devices.first_connected([]) is None
