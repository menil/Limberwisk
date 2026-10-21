import logging

from limberwisk.scheduler import NSTimerScheduler


class FakeTimer:
    def __init__(self):
        self.invalidated = False

    def invalidate(self):
        self.invalidated = True


class FakeTimerClass:
    def __init__(self):
        self.created = []

    def timerWithTimeInterval_repeats_block_(self, delay, repeats, block):  # noqa: N802
        timer = FakeTimer()
        self.created.append((delay, repeats, block, timer))
        return timer


class FakeRunLoop:
    def __init__(self):
        self.added = []

    def addTimer_forMode_(self, timer, mode):  # noqa: N802
        self.added.append((timer, mode))


COMMON_MODES = object()


def make():
    timer_class, run_loop = FakeTimerClass(), FakeRunLoop()
    scheduler = NSTimerScheduler(
        timer_class=timer_class, run_loop=run_loop, common_modes=COMMON_MODES
    )
    return scheduler, timer_class, run_loop


def test_timers_are_one_shot_and_use_common_run_loop_modes():
    scheduler, timer_class, run_loop = make()
    scheduler.call_later(0.35, lambda: None)
    delay, repeats, _, timer = timer_class.created[0]
    assert (delay, repeats) == (0.35, False)
    assert run_loop.added == [(timer, COMMON_MODES)]


def test_the_callback_runs_when_the_timer_fires():
    scheduler, timer_class, _ = make()
    fired = []
    scheduler.call_later(1, lambda: fired.append(True))
    _, _, block, timer = timer_class.created[0]
    block(timer)
    assert fired == [True]


def test_a_failing_callback_is_logged_not_raised(caplog):
    scheduler, timer_class, _ = make()

    def boom():
        raise RuntimeError("timer bug")

    scheduler.call_later(1, boom)
    _, _, block, timer = timer_class.created[0]
    with caplog.at_level(logging.ERROR):
        block(timer)
    assert "timer bug" in caplog.text


def test_cancel_invalidates_the_timer():
    scheduler, timer_class, _ = make()
    handle = scheduler.call_later(1, lambda: None)
    handle.cancel()
    assert timer_class.created[0][3].invalidated


def test_now_is_monotonic():
    scheduler, _, _ = make()
    first = scheduler.now()
    assert scheduler.now() >= first
