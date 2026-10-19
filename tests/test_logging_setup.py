import logging

import pytest

from muteme_flow import logging_setup
from muteme_flow.logging_setup import LOG_FILE_NAME, RecentLines, configure_logging, log_directory


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def test_recent_lines_keeps_only_the_newest():
    handler = RecentLines(capacity=2)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.Logger("recent-test")  # standalone: leaves no global state behind
    logger.addHandler(handler)
    for text in ("one", "two", "three"):
        logger.warning(text)
    assert handler.lines() == ["two", "three"]


def test_log_directory_is_under_the_user_library(tmp_path):
    assert log_directory(tmp_path) == tmp_path / "Library" / "Logs" / "MuteMe Flow"


def test_messages_reach_the_file_and_the_recent_lines(tmp_path):
    recent = configure_logging(home=tmp_path)
    logging.getLogger("muteme_flow.demo").info("hello from the app")
    for handler in logging.getLogger().handlers:
        handler.flush()
    log_file = log_directory(tmp_path) / LOG_FILE_NAME
    assert "hello from the app" in log_file.read_text()
    assert any("hello from the app" in line for line in recent.lines())


def test_configuring_twice_does_not_duplicate_output(tmp_path):
    configure_logging(home=tmp_path)
    recent = configure_logging(home=tmp_path)
    logging.getLogger("muteme_flow.demo").info("only once")
    assert sum("only once" in line for line in recent.lines()) == 1
    owned = [h for h in logging.getLogger().handlers if getattr(h, logging_setup._OWNED, False)]
    assert len(owned) == 3  # recent lines, stderr, file


def test_an_unwritable_log_folder_does_not_stop_the_app_and_says_so(tmp_path):
    not_a_folder = tmp_path / "file"
    not_a_folder.write_text("in the way")  # "Library" cannot be created beneath a file
    recent = configure_logging(home=not_a_folder)
    logging.getLogger("muteme_flow.demo").info("still works")
    lines = recent.lines()
    assert any("still works" in line for line in lines)
    assert any("cannot write the log file" in line for line in lines)  # reaches diagnostics


def test_the_home_folder_never_appears_in_text_meant_for_bug_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "someone"))
    recent = configure_logging(home=tmp_path)
    logging.getLogger("muteme_flow.demo").error("failed in %s/Library/thing", tmp_path / "someone")
    (line,) = [line for line in recent.lines() if "failed in" in line]
    assert "someone" not in line
    assert "~/Library/thing" in line


def test_a_missing_stderr_does_not_break_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(logging_setup.sys, "stderr", None)
    recent = configure_logging(home=tmp_path)
    logging.getLogger("muteme_flow.demo").info("quiet")
    assert any("quiet" in line for line in recent.lines())
