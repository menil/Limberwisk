import logging

from muteme_flow.guarded import guarded


def test_calls_through_with_its_arguments():
    seen = []
    guarded(lambda *args: seen.append(args), "demo")(1, 2)
    assert seen == [(1, 2)]


def test_an_exception_is_logged_and_not_raised(caplog):
    def boom():
        raise ValueError("bug")

    with caplog.at_level(logging.ERROR):
        guarded(boom, "the demo callback")()
    assert "the demo callback" in caplog.text
    assert "bug" in caplog.text
