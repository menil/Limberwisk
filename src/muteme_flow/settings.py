"""User settings, persisted in UserDefaults."""

from typing import Any, Protocol

from muteme_flow.state_machine import Timings

HOLD_THRESHOLD_CHOICES_MS = (250, 350, 500)
DEFAULT_HOLD_THRESHOLD_MS = 350
_HOLD_KEY = "holdThresholdMs"

BACKEND_CHOICES = ("wispr-flow", "envious-wispr")
DEFAULT_BACKEND = "wispr-flow"
BACKEND_DISPLAY_NAMES = {
    "wispr-flow": "Wispr Flow",
    "envious-wispr": "EnviousWispr",
}
_BACKEND_KEY = "dictationBackend"
_AUDIO_FEEDBACK_KEY = "audioFeedbackEnabled"

INPUT_CHOICES = ("muteme",)
DEFAULT_INPUT = "muteme"
INPUT_DISPLAY_NAMES = {
    "muteme": "MuteMe",
}
_INPUT_KEY = "inputSource"


class SettingsStore(Protocol):
    def get_int(self, key: str) -> int | None: ...

    def set_int(self, key: str, value: int) -> None: ...

    def get_str(self, key: str) -> str | None: ...

    def set_str(self, key: str, value: str) -> None: ...

    def get_bool(self, key: str) -> bool | None: ...

    def set_bool(self, key: str, value: bool) -> None: ...


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

    def get_str(self, key: str) -> str | None:
        val = self._defaults.objectForKey_(key)
        return str(val) if val is not None else None

    def set_str(self, key: str, value: str) -> None:
        self._defaults.setObject_forKey_(value, key)

    def get_bool(self, key: str) -> bool | None:
        # boolForKey_ returns False for missing keys, so check for presence first.
        if self._defaults.objectForKey_(key) is None:
            return None
        return bool(self._defaults.boolForKey_(key))

    def set_bool(self, key: str, value: bool) -> None:
        self._defaults.setBool_forKey_(value, key)


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

    @property
    def dictation_backend(self) -> str:
        getter = getattr(self._store, "get_str", None)
        stored = getter(_BACKEND_KEY) if getter is not None else None
        return stored if stored in BACKEND_CHOICES else DEFAULT_BACKEND

    @property
    def dictation_backend_display_name(self) -> str:
        return BACKEND_DISPLAY_NAMES.get(self.dictation_backend, "Wispr Flow")

    def set_dictation_backend(self, value: str) -> None:
        if value not in BACKEND_CHOICES:
            raise ValueError(f"dictation backend must be one of {BACKEND_CHOICES}")
        setter = getattr(self._store, "set_str", None)
        if setter is not None:
            setter(_BACKEND_KEY, value)

    @property
    def audio_feedback_enabled(self) -> bool:
        getter = getattr(self._store, "get_bool", None)
        stored = getter(_AUDIO_FEEDBACK_KEY) if getter is not None else None
        return stored if stored is not None else False

    def set_audio_feedback_enabled(self, value: bool) -> None:
        setter = getattr(self._store, "set_bool", None)
        if setter is not None:
            setter(_AUDIO_FEEDBACK_KEY, value)

    @property
    def input_source(self) -> str:
        """Active hardware input provider choice ('muteme')."""
        getter = getattr(self._store, "get_str", None)
        stored = getter(_INPUT_KEY) if getter is not None else None
        return stored if stored in INPUT_CHOICES else DEFAULT_INPUT

    @property
    def input_source_display_name(self) -> str:
        """Human-readable display title for the active input source."""
        return INPUT_DISPLAY_NAMES.get(self.input_source, "MuteMe")

    def set_input_source(self, value: str) -> None:
        """Persist the active input provider choice."""
        if value not in INPUT_CHOICES:
            raise ValueError(f"input source must be one of {INPUT_CHOICES}")
        setter = getattr(self._store, "set_str", None)
        if setter is not None:
            setter(_INPUT_KEY, value)

    def timings(self) -> Timings:
        return Timings(hold_s=self.hold_threshold_ms / 1000)
