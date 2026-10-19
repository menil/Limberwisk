import pytest

from muteme_flow.settings import (
    DEFAULT_HOLD_THRESHOLD_MS,
    HOLD_THRESHOLD_CHOICES_MS,
    Settings,
    UserDefaultsStore,
)


class DictStore:
    def __init__(self, **values):
        self.values = values

    def get_int(self, key):
        return self.values.get(key)

    def set_int(self, key, value):
        self.values[key] = value


def test_defaults_to_350_ms():
    assert Settings(DictStore()).hold_threshold_ms == DEFAULT_HOLD_THRESHOLD_MS == 350


@pytest.mark.parametrize("value", HOLD_THRESHOLD_CHOICES_MS)
def test_a_chosen_threshold_is_remembered(value):
    store = DictStore()
    Settings(store).set_hold_threshold_ms(value)
    assert Settings(store).hold_threshold_ms == value


@pytest.mark.parametrize("stored", [0, 1, 349, 10_000, -5])
def test_an_unexpected_stored_value_falls_back_to_the_default(stored):
    assert Settings(DictStore(holdThresholdMs=stored)).hold_threshold_ms == 350


def test_an_unlisted_threshold_is_rejected():
    with pytest.raises(ValueError, match="hold threshold"):
        Settings(DictStore()).set_hold_threshold_ms(123)


def test_timings_carry_the_threshold_in_seconds():
    store = DictStore()
    settings = Settings(store)
    settings.set_hold_threshold_ms(500)
    assert settings.timings().hold_s == 0.5


class FakeDefaults:
    def __init__(self):
        self.data = {}

    def objectForKey_(self, key):  # noqa: N802
        return self.data.get(key)

    def integerForKey_(self, key):  # noqa: N802
        return self.data.get(key, 0)

    def setInteger_forKey_(self, value, key):  # noqa: N802
        self.data[key] = value


def test_the_user_defaults_store_distinguishes_unset_from_zero():
    defaults = FakeDefaults()
    store = UserDefaultsStore(defaults)
    assert store.get_int("k") is None
    store.set_int("k", 0)
    assert store.get_int("k") == 0
    store.set_int("k", 250)
    assert store.get_int("k") == 250
