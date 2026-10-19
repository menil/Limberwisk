"""The menu bar app: rumps glue around the tested logic (specs/spec.md section 6).

Decisions live in `menu_model`, `settings`, `login_item` and the state machine; this
module only maps them onto menu items and AppKit calls.
"""

import logging
import sys
import webbrowser
from collections.abc import Callable
from typing import Any

import rumps
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationWillTerminateNotification,
    NSPasteboard,
    NSPasteboardTypeString,
)
from Foundation import NSNotificationCenter

from muteme_flow.app_info import APP_NAME, DOCUMENTATION_URL
from muteme_flow.conflict import ConflictMonitor, describe_apps
from muteme_flow.diagnostics import collect_info, format_diagnostics
from muteme_flow.guarded import guarded
from muteme_flow.logging_setup import RecentLines, configure_logging
from muteme_flow.login_item import LoginItem
from muteme_flow.main_thread import post_to_main
from muteme_flow.menu_model import (
    CONFLICT_ITEM,
    MENU_TITLE,
    MODE_LINE,
    menu_title,
    status_message,
    status_text,
)
from muteme_flow.runtime import Runtime
from muteme_flow.settings import HOLD_THRESHOLD_CHOICES_MS, Settings, UserDefaultsStore
from muteme_flow.termination import install_termination_handlers, keep_interpreter_responsive

log = logging.getLogger(__name__)

_SELECTED, _UNSELECTED = 1, 0


def _set_hidden(item: rumps.MenuItem, hidden: bool) -> None:
    # rumps has no public way to hide a row. This relies on its `_menuitem` attribute,
    # which a contract test pins (and rumps itself is pinned to an exact version).
    item._menuitem.setHidden_(hidden)


class MuteMeFlowApp(rumps.App):
    def __init__(
        self,
        *,
        runtime: Runtime,
        settings: Settings,
        login_item: LoginItem,
        conflict: ConflictMonitor,
        recent_lines: RecentLines,
    ) -> None:
        super().__init__(APP_NAME, title=MENU_TITLE, quit_button=None)
        self._runtime = runtime
        self._machine = runtime.controller.machine
        self._settings = settings
        self._login_item = login_item
        self._conflict = conflict
        self._recent_lines = recent_lines
        self._stopping = False
        # Asking the system for the login-item status is an IPC round trip, so it is read
        # here and after a change rather than on every refresh.
        self._login_enabled = login_item.is_enabled()

        # Informational rows have no callback, so rumps leaves them disabled.
        self._status = rumps.MenuItem("Status: starting")
        self._conflict_row = rumps.MenuItem(
            CONFLICT_ITEM, callback=self._action(self._quit_official)
        )
        self._threshold_menu = rumps.MenuItem("Hold Threshold")
        self._threshold_rows = {
            ms: rumps.MenuItem(f"{ms} ms", callback=self._action(self._threshold_choice(ms)))
            for ms in HOLD_THRESHOLD_CHOICES_MS
        }
        for row in self._threshold_rows.values():
            self._threshold_menu.add(row)
        self._login_row = rumps.MenuItem("Start at Login")
        if login_item.available:
            self._login_row.set_callback(self._action(self._toggle_login))
        else:
            self._login_row.title = "Start at Login (installed app only)"

        self.menu = [
            self._status,
            self._conflict_row,
            rumps.MenuItem(MODE_LINE),
            self._threshold_menu,
            None,
            self._login_row,
            rumps.MenuItem("Copy Diagnostics", callback=self._action(self._copy_diagnostics)),
            rumps.MenuItem("Documentation & Help", callback=self._action(self._open_docs)),
            None,
            rumps.MenuItem(f"Quit {APP_NAME}", callback=self._action(self.quit_gracefully)),
        ]
        self.refresh()

    def refresh(self) -> None:
        """Bring every row in line with the current state. Main thread only."""
        self.title = menu_title(self._machine)
        self._status.title = status_text(self._machine)
        # Hidden rather than removed: rumps keys rows by title, and this row comes and goes.
        _set_hidden(self._conflict_row, not self._machine.conflict)

        current = self._settings.hold_threshold_ms
        for ms, row in self._threshold_rows.items():
            row.state = _SELECTED if ms == current else _UNSELECTED
        if self._login_item.available:
            self._login_row.state = _SELECTED if self._login_enabled else _UNSELECTED

    def shutdown(self) -> None:
        """Stop everything in order. Quit paths can overlap, so this must be repeatable."""
        if self._stopping:
            return
        self._stopping = True
        try:
            self._conflict.stop()
        finally:
            # Always reached: it stops Wispr and leaves the LED red.
            self._runtime.stop()

    def quit_gracefully(self) -> None:
        already_stopping = self._stopping
        self.shutdown()
        # Another quit path may be mid-way through shutting down (it pumps the run loop
        # while it waits); terminating now would cut it short before the LED is set.
        if not already_stopping:
            rumps.quit_application()

    # --- menu actions -------------------------------------------------------------

    @staticmethod
    def _action(fn: Callable[..., None]) -> Callable[[Any], None]:
        """Menu callbacks run inside AppKit, where an exception would only reach stderr."""
        run = guarded(fn, "menu action")
        return lambda _sender: run()

    def _threshold_choice(self, ms: int) -> Callable[[], None]:
        def choose() -> None:
            self._settings.set_hold_threshold_ms(ms)
            self._machine.timings = self._settings.timings()
            self.refresh()

        return choose

    def _toggle_login(self) -> None:
        if self._login_item.requires_approval():
            self._login_item.open_settings()  # only the user can approve it there
            return
        error = self._login_item.set_enabled(not self._login_enabled)
        if error is not None:
            log.error("could not change Start at Login: %s", error)
            rumps.alert(title="Could not change Start at Login", message=str(error))
        self._login_enabled = self._login_item.is_enabled()
        self.refresh()

    def _quit_official(self) -> None:
        apps = self._conflict.official_apps()
        if not apps:
            self.refresh()
            return
        confirmed = rumps.alert(
            title="Quit the official MuteMe app?",
            message=(
                f"{describe_apps(apps)}\n\n"
                "It competes with MuteMe Flow for the button and resets its light."
            ),
            ok="Quit It",
            cancel="Cancel",
        )
        if confirmed:
            self._conflict.terminate(apps)  # exactly the apps that were shown

    def _copy_diagnostics(self) -> None:
        info = collect_info(status_message(self._machine), self._runtime.connected_device_id)
        text = format_diagnostics(info, self._recent_lines.lines())
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, NSPasteboardTypeString)

    @staticmethod
    def _open_docs() -> None:
        webbrowser.open(DOCUMENTATION_URL)


def _log_uncaught(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
    log.critical("uncaught exception", exc_info=(exc_type, exc, tb))


def run() -> None:
    recent_lines = configure_logging()
    # A bundled app has no terminal, so crashes must reach the log file.
    sys.excepthook = _log_uncaught
    try:
        _run(recent_lines)
    except Exception:
        log.exception("MuteMe Flow failed to start")
        raise


def _run(recent_lines: RecentLines) -> None:
    # No Dock icon, even when launched from source rather than the packaged app.
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    settings = Settings(UserDefaultsStore())
    runtime = Runtime.create_default(timings=settings.timings())
    conflict = ConflictMonitor.for_current_app(runtime.controller.conflict_changed)
    app = MuteMeFlowApp(
        runtime=runtime,
        settings=settings,
        login_item=LoginItem.for_current_app(),
        conflict=conflict,
        recent_lines=recent_lines,
    )
    runtime.controller.on_change = app.refresh

    # Every way out of the app must stop Wispr and leave the LED red first.
    install_termination_handlers(app.quit_gracefully, post_to_main)
    NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
        NSApplicationWillTerminateNotification,
        None,
        None,
        guarded(lambda _notification: app.shutdown(), "terminate handler"),
    )

    runtime.start()
    conflict.start()
    keep_interpreter_responsive()
    app.refresh()
    try:
        app.run()
    finally:
        # Reached when the loop ends by a route other than our own quit paths.
        app.shutdown()
