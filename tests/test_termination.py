import signal

from muteme_flow.termination import install_termination_handlers


class FakeSignalModule:
    def __init__(self):
        self.handlers = {}

    def signal(self, signum, handler):
        self.handlers[signum] = handler
        return None


def test_term_and_int_are_both_handled():
    fake = FakeSignalModule()
    install_termination_handlers(lambda: None, lambda fn: None, signal_module=fake)
    assert set(fake.handlers) == {signal.SIGTERM, signal.SIGINT}


def test_a_signal_posts_the_quit_to_the_main_thread_instead_of_running_it_inline():
    fake, posted, quit_calls = FakeSignalModule(), [], []
    install_termination_handlers(lambda: quit_calls.append(1), posted.append, signal_module=fake)
    fake.handlers[signal.SIGTERM](signal.SIGTERM, None)
    assert quit_calls == []
    posted[0]()
    assert quit_calls == [1]


def test_a_second_signal_gets_the_default_action_so_a_hung_app_can_still_be_killed():
    fake = FakeSignalModule()
    install_termination_handlers(lambda: None, lambda fn: None, signal_module=fake)
    fake.handlers[signal.SIGTERM](signal.SIGTERM, None)
    assert fake.handlers[signal.SIGTERM] == signal.SIG_DFL
    assert callable(fake.handlers[signal.SIGINT])  # the other signal is untouched
