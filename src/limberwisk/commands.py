"""The two Wispr Flow hands-free commands (specs/spec.md section 4.2)."""

from enum import Enum

WISPR_BUNDLE_ID = "com.electron.wispr-flow"


class Command(Enum):
    START = "wispr-flow://start-hands-free"
    STOP = "wispr-flow://stop-hands-free"

    @property
    def url(self) -> str:
        return self.value
