"""User settings, persisted in UserDefaults."""

from typing import Any, Protocol

from muteme_flow.state_machine import Timings

HOLD_THRESHOLD_CHOICES_MS = (250, 350, 500)
DEFAULT_HOLD_THRESHOLD_MS = 350
_HOLD_KEY = "holdThresholdMs"


class SettingsStore(Protocol):
    def get_int(self, key: str) -> int | None: ...

    def set_int(self, key: str, value: int) -> None: ...


class UserDefaultsStore:
    def __init__(self, defaults: Any = None) -> None:
        if defaults is None:
            # Imported here so the module loads where Foundation is unavailable.
            from Foundation import NSUserDefaults

            defaults = NSUserDefaults.standardUserDefaults()
        self._defaults = defaults

    def get_int(self, key: str) -> int | None:
        # integerForKey_ cannot tell "unset" from 0, so check for presence first.
        if self._defaults.objectForKey_(key) is None:
            return None
        return int(self._defaults.integerForKey_(key))

    def set_int(self, key: str, value: int) -> None:
        self._defaults.setInteger_forKey_(value, key)


class Settings:
    def __init__(self, store: SettingsStore) -> None:
        self._store = store

    @property
    def hold_threshold_ms(self) -> int:
        stored = self._store.get_int(_HOLD_KEY)
        # A hand-edited or stale value falls back to the default rather than breaking.
        return stored if stored in HOLD_THRESHOLD_CHOICES_MS else DEFAULT_HOLD_THRESHOLD_MS

    def set_hold_threshold_ms(self, value: int) -> None:
        if value not in HOLD_THRESHOLD_CHOICES_MS:
            raise ValueError(f"hold threshold must be one of {HOLD_THRESHOLD_CHOICES_MS}")
        self._store.set_int(_HOLD_KEY, value)

    def timings(self) -> Timings:
        return Timings(hold_s=self.hold_threshold_ms / 1000)
