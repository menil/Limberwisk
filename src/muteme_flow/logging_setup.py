"""Log to a rotating file and keep recent lines for Copy Diagnostics.

A bundled menu bar app has no usable stderr, so without a file a failure in the field
would leave nothing to look at. Nothing logged here includes audio or dictated text: the
app never sees either.
"""

import logging
import logging.handlers
import sys
from collections import deque
from pathlib import Path

from muteme_flow.app_info import APP_NAME

LOG_FILE_NAME = "muteme-flow.log"
_MAX_BYTES = 1_000_000
_BACKUPS = 3
RECENT_LINES = 200
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_OWNED = "_muteme_flow_handler"
_LOG_HINT = f"~/Library/Logs/{APP_NAME}"


class RecentLines(logging.Handler):
    """Keeps the last few formatted log lines in memory.

    These end up in Copy Diagnostics, which people paste into public bug reports, so the
    home folder (and with it the user name) is replaced by `~`.
    """

    def __init__(self, capacity: int = RECENT_LINES) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self._lines.append(self.format(record).replace(str(Path.home()), "~"))

    def lines(self) -> list[str]:
        return list(self._lines)


def log_directory(home: Path) -> Path:
    return home / "Library" / "Logs" / APP_NAME


def configure_logging(*, home: Path | None = None, level: int = logging.INFO) -> RecentLines:
    """Install the handlers on the root logger. Safe to call more than once."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _OWNED, False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(_FORMAT)
    recent = RecentLines()
    handlers: list[logging.Handler] = [recent]
    if sys.stderr is not None:  # a bundled app launched by the system may have none
        handlers.append(logging.StreamHandler(sys.stderr))

    directory = log_directory(home or Path.home())
    file_problem = False
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                directory / LOG_FILE_NAME, maxBytes=_MAX_BYTES, backupCount=_BACKUPS
            )
        )
    except OSError:
        # An unwritable log folder must not stop the app; the in-memory lines still work.
        file_problem = True

    for handler in handlers:
        handler.setFormatter(formatter)
        setattr(handler, _OWNED, True)
        root.addHandler(handler)
    root.setLevel(level)
    if file_problem:
        # Logged only now, so it reaches the handlers that did install.
        logging.getLogger(__name__).warning("cannot write the log file under %s", _LOG_HINT)
    return recent
