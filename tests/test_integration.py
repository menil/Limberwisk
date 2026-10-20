"""Fake device -> HID thread -> controller -> state machine -> fake Wispr, end to end."""

import threading

import pytest
from support import sequences as seq
from support.fake_hid import FakeHidDevice, opened
from support.fake_scheduler import FakeScheduler
from support.main_loop import ManualMainLoop
from support.waiting import wait_until

from muteme_flow.commands import Command
from muteme_flow.controller import Controller
from muteme_flow.hid_io import DeviceError, DeviceNotFoundError
from muteme_flow.hid_worker import HidWorker
from muteme_flow.led import Color, LedMailbox, led_report
from muteme_flow.runtime import Runtime
from muteme_flow.state_machine import ERROR_FLASH_S, State, Timings

HOLD = Timings().hold_s


class FakeDispatcher:
    def __init__(self, main: ManualMainLoop) -> None:
        self._main = main
        self.sent: list[Command] = []
        self.threads: set[int] = set()
        self.error: Exception | None = None
        self.hold_completions = False
        self.held: list = []

    def dispatch(self, command, on_complete):
        self.sent.append(command)
        self.threads.add(threading.get_ident())
        error = self.error
        if self.hold_completions:
            self.held.append(lambda: on_complete(error))
        else:
            self._main.post(lambda: on_complete(error))


class Recorder:
    """A component with start/stop that records the order it was called in."""

    def __init__(self, name: str, order: list[str]) -> None:
        self._name, self._order = name, order

    def start(self) -> None:
        self._order.append(f"start {self._name}")

    def stop(self) -> None:
        self._order.append(f"stop {self._name}")


class System:
    """The whole app wired to fakes, with Wispr Flow running."""

    def __init__(self) -> None:
        self.main = ManualMainLoop()
        self.scheduler = FakeScheduler()
        self.dispatcher = FakeDispatcher(self.main)
        self.led = LedMailbox()
        self.device = FakeHidDevice(read_pause_s=0.001)
        self.controller = Controller(
            dispatcher=self.dispatcher,
            led=self.led,
            scheduler=self.scheduler,
            post_to_main=self.main.post,
        )
        self.available = [self.device]
        self.connect_error: Exception | None = None
        self.worker = HidWorker(self._connect, self.led, self.controller.on_device_event)
        self.machine = self.controller.machine
        self.controller.wispr_running_changed(True)

    def _connect(self):
        if self.connect_error:
            raise self.connect_error
        if not self.available:
            raise DeviceNotFoundError("nothing plugged in")
        # Opened here, on the worker thread, exactly as the real adapter is.
        return opened(self.available.pop(0))

    def start(self):
        self.worker.start()
        assert self.main.run_until(lambda: self.machine.device_connected)

    def wait_for_commands(self, count):
        assert self.main.run_until(lambda: len(self.dispatcher.sent) >= count), self.dispatcher.sent

    def wait_for_state(self, state):
        assert self.main.run_until(lambda: self.machine.state is state), self.machine.state

    def wait_until_device_drained(self):
        assert self.main.run_until(lambda: self.device.pending_reports == 0)
        self.main.settle(0.05)  # let the last decoded events reach the main thread

    def led_on_device(self, color):
        return wait_until(lambda: led_report(color) in self.device.writes)

    def make_runtime(self, pump=lambda seconds: None, order=None, audio_sink=None):
        order = order if order is not None else []
        self.power_callbacks = {}

        def make_power(on_sleep, on_wake):
            self.power_callbacks = {"sleep": on_sleep, "wake": on_wake}
            return Recorder("power", order)

        def make_backend(choice):
            class MockBackend:
                name = "EnviousWispr" if choice == "envious-wispr" else "Wispr Flow"

                def is_running(self):
                    return True

            return MockBackend(), Recorder(f"presence-{choice}", order)

        return Runtime(
            controller=self.controller,
            worker=self.worker,
            presence=Recorder("presence", order),
            make_power=make_power,
            pump=pump,
            audio_sink=audio_sink,
            backend_factory=make_backend,
        )


@pytest.fixture
def system():
    s = System()
    s.start()
    yield s
    s.worker.stop()
    assert not s.worker.running


def test_a_tap_starts_recording_and_lights_the_led_green(system):
    system.device.feed(*seq.tap())
    system.wait_for_commands(1)
    assert system.dispatcher.sent == [Command.START]
    system.wait_for_state(State.RECORDING_LOCKED)
    assert system.led_on_device(Color.GREEN)


def test_a_second_tap_stops_recording_and_restores_the_red_led(system):
    system.device.feed(*seq.tap())
    system.wait_for_state(State.RECORDING_LOCKED)
    system.scheduler.advance(0.5)
    system.device.feed(*seq.tap())
    system.wait_for_commands(2)
    assert system.dispatcher.sent == [Command.START, Command.STOP]
    system.wait_for_state(State.IDLE)
    assert wait_until(lambda: system.device.writes[-1] == led_report(Color.RED))


def test_holding_records_only_while_the_button_is_down(system):
    system.device.feed(seq.report(seq.TOUCH_BEGIN))
    system.wait_for_commands(1)
    system.scheduler.advance(HOLD + 0.2)
    assert system.machine.state is State.RECORDING_MOMENTARY
    system.device.feed(seq.report(seq.TOUCH_HELD), seq.report(seq.TOUCH_END), seq.report(0))
    system.wait_for_commands(2)
    assert system.dispatcher.sent == [Command.START, Command.STOP]


def test_unplugging_mid_recording_stops_wispr(system):
    system.device.feed(*seq.tap())
    system.wait_for_state(State.RECORDING_LOCKED)
    system.device.disconnect()
    system.wait_for_commands(2)
    assert system.dispatcher.sent == [Command.START, Command.STOP]
    assert system.main.run_until(lambda: not system.machine.device_connected)


def test_touches_do_nothing_while_wispr_is_not_running(system):
    system.controller.wispr_running_changed(False)
    system.device.feed(*seq.tap(), *seq.hold())
    system.wait_until_device_drained()
    assert system.dispatcher.sent == []
    assert system.led_on_device(Color.BLUE)


def test_a_dispatch_failure_flashes_yellow_then_returns_to_red(system):
    system.dispatcher.error = RuntimeError("LaunchServices said no")
    system.device.feed(*seq.tap())
    assert system.main.run_until(lambda: system.machine.command_failed)
    system.wait_until_device_drained()
    assert system.led_on_device(Color.YELLOW)
    system.scheduler.advance(ERROR_FLASH_S + 0.1)
    assert wait_until(lambda: system.device.writes[-1] == led_report(Color.RED))


def test_a_device_that_cannot_be_opened_is_reported_and_lights_yellow():
    s = System()
    s.available.clear()
    s.connect_error = DeviceError("cannot open 0x3603:0x0001: permission denied")
    s.worker.start()
    try:
        assert s.main.run_until(lambda: s.machine.open_failed)
        assert s.machine.open_failed
    finally:
        s.worker.stop()


def test_state_changes_and_dispatches_happen_on_the_main_thread_and_io_on_the_worker(system):
    system.device.feed(*seq.tap())
    system.wait_for_commands(1)
    assert system.led_on_device(Color.GREEN)
    assert system.dispatcher.threads == {system.main.thread_id}
    assert len(system.device.call_threads) == 1
    assert system.main.thread_id not in system.device.call_threads


def test_dispatch_latency_is_recorded_for_each_touch_driven_command(system):
    system.device.feed(*seq.tap())
    system.wait_for_state(State.RECORDING_LOCKED)
    summary = system.controller.latency.summary()
    assert summary is not None
    assert summary.count == 1


def test_a_replugged_device_gets_the_current_led_colour_back(system):
    system.device.feed(*seq.tap())
    system.wait_for_state(State.RECORDING_LOCKED)
    assert system.led_on_device(Color.GREEN)

    replacement = FakeHidDevice(read_pause_s=0.001)
    system.available.append(replacement)
    system.device.disconnect()
    system.wait_for_commands(2)  # the unplug stops Wispr; state is idle, LED red
    assert wait_until(lambda: led_report(Color.RED) in replacement.writes)


# --- runtime: start/stop order, sleep/wake, quitting -----------------------------------


def test_runtime_starts_and_stops_every_component_in_order():
    s = System()
    order = []
    runtime = s.make_runtime(order=order)
    runtime.start()
    runtime.stop()
    assert order == ["start presence", "start power", "stop power", "stop presence"]
    assert not s.worker.running


def test_runtime_stop_is_repeatable():
    s = System()
    order = []
    runtime = s.make_runtime(order=order)
    runtime.start()
    runtime.stop()
    runtime.stop()
    assert order.count("stop power") == 1
    assert not s.worker.running


def test_the_worker_is_stopped_even_if_an_earlier_stop_step_fails():
    s = System()

    class Broken(Recorder):
        def stop(self):
            raise RuntimeError("cannot unsubscribe")

    runtime = Runtime(
        controller=s.controller,
        worker=s.worker,
        presence=Recorder("presence", []),
        make_power=lambda on_sleep, on_wake: Broken("power", []),
        pump=lambda seconds: None,
    )
    runtime.start()
    with pytest.raises(RuntimeError):
        runtime.stop()
    assert not s.worker.running  # the final LED write still had its chance
    assert s.machine.wispr_running  # and the machine was shut down first


def test_the_connected_model_is_available_for_diagnostics():
    from muteme_flow.devices import DeviceId

    s = System()
    runtime = s.make_runtime()
    assert runtime.connected_device_id is None
    assert runtime.connected_device_name == "MuteMe"
    runtime.start()
    assert s.main.run_until(lambda: s.machine.device_connected)

    # Real DeviceId object
    s.device.device_id = DeviceId(0x3603, 0x0001, "MuteMe Original")
    assert runtime.connected_device_name == "MuteMe Original"

    # Duck-typed string fallback
    s.device.device_id = "the model"
    assert runtime.connected_device_id == "the model"
    assert runtime.connected_device_name == "the model"
    runtime.stop()


def test_runtime_switch_backend_stops_active_recording_and_updates_presence():
    s = System()
    runtime = s.make_runtime()
    runtime.start()
    assert s.main.run_until(lambda: s.machine.device_connected)

    # Start recording
    s.device.feed(*seq.tap())
    s.wait_for_state(State.RECORDING_LOCKED)
    assert s.machine.recording is True
    assert s.dispatcher.sent == [Command.START]

    # Switch backend to envious-wispr while recording is active
    runtime.switch_backend("envious-wispr")

    # Verify active recording was cleanly halted on outgoing backend
    assert s.dispatcher.sent == [Command.START, Command.STOP]
    assert s.machine.recording is False
    assert runtime.backend_name == "EnviousWispr"

    runtime.stop()


def test_runtime_audio_feedback_toggle():
    s = System()

    class FakeAudioSink:
        def __init__(self):
            self.enabled = False

    sink = FakeAudioSink()
    runtime = s.make_runtime(audio_sink=sink)
    runtime.set_audio_feedback(True)
    assert sink.enabled is True
    runtime.set_audio_feedback(False)
    assert sink.enabled is False


def test_runtime_stop_stops_a_recording_and_leaves_the_led_red():
    s = System()
    pumped = []
    runtime = s.make_runtime(pump=lambda seconds: (pumped.append(seconds), s.main.settle(0.02)))
    runtime.start()
    assert s.main.run_until(lambda: s.machine.device_connected)
    s.device.feed(*seq.tap())
    s.wait_for_state(State.RECORDING_LOCKED)

    runtime.stop()
    assert s.dispatcher.sent == [Command.START, Command.STOP]
    assert s.device.writes[-1] == led_report(Color.RED)
    assert pumped, "the run loop should be given time to deliver the final stop"
    assert not s.worker.running


def test_runtime_stop_waits_for_the_final_stop_to_be_delivered():
    s = System()
    s.dispatcher.hold_completions = True
    pumps = []

    def pump(seconds):
        pumps.append(seconds)
        if len(pumps) == 3:  # the system finally reports the stop as delivered
            for complete in s.dispatcher.held:
                complete()
        s.main.settle(0.01)

    runtime = s.make_runtime(pump=pump)
    runtime.start()
    assert s.main.run_until(lambda: s.machine.device_connected)
    s.device.feed(*seq.tap())
    s.wait_for_state(State.RECORDING_LOCKED)

    runtime.stop()
    assert len(pumps) == 3
    assert s.controller.outstanding_dispatches == 0


def test_a_touch_while_quitting_cannot_start_a_new_recording():
    s = System()
    s.dispatcher.hold_completions = True
    runtime = s.make_runtime(pump=lambda seconds: s.main.settle(0.01))
    runtime.start()
    assert s.main.run_until(lambda: s.machine.device_connected)
    s.device.feed(*seq.tap())
    s.wait_for_state(State.RECORDING_LOCKED)

    s.controller.shutdown()
    s.device.feed(*seq.tap())  # the user taps while the app is still draining
    s.wait_until_device_drained()
    assert s.dispatcher.sent == [Command.START, Command.STOP]
    runtime.stop()


def test_sleeping_releases_the_device_and_waking_reconnects_then_resyncs_wispr():
    s = System()
    runtime = s.make_runtime()
    runtime.start()
    assert s.main.run_until(lambda: s.machine.device_connected)
    s.device.feed(*seq.tap())
    s.wait_for_state(State.RECORDING_LOCKED)

    replacement = FakeHidDevice(read_pause_s=0.001)
    s.available.append(replacement)
    s.power_callbacks["sleep"]()
    assert not s.device.is_open  # released before the machine sleeps
    s.power_callbacks["wake"]()
    assert s.main.run_until(lambda: replacement.is_open)
    assert s.dispatcher.sent == [Command.START, Command.STOP]  # the resync stop
    assert s.machine.state is State.IDLE
    assert wait_until(lambda: led_report(Color.RED) in replacement.writes)
    runtime.stop()


def test_runtime_switch_input_stops_active_recording():
    s = System()
    runtime = s.make_runtime()
    runtime.start()
    assert s.main.run_until(lambda: s.machine.device_connected)
    s.device.feed(*seq.tap())
    s.wait_for_state(State.RECORDING_LOCKED)
    assert s.machine.recording

    class DummyInput:
        name = "Pedal"
        conflicting_bundle_ids = frozenset()
        conflicting_app_names = frozenset()

        def start(self, on_event):
            pass

        def stop(self):
            pass

    runtime._input_factory = lambda choice: DummyInput()
    runtime.switch_input("pedal")

    # State machine stops recording when input is switched and resets device connection state
    assert not s.machine.recording
    assert s.machine.device_connected is False
    assert s.dispatcher.sent == [Command.START, Command.STOP]
    assert runtime.input_source_name == "Pedal"
    runtime.stop()


def test_runtime_switch_input_stops_previous_source_and_preserves_on_failure():
    s = System()
    runtime = s.make_runtime()
    runtime.start()

    stopped = []

    class TrackedInput:
        def __init__(self, name):
            self.name = name
            self.conflicting_bundle_ids = frozenset()
            self.conflicting_app_names = frozenset()

        def start(self, on_event):
            pass

        def stop(self):
            stopped.append(self.name)

    inputs = {"in1": TrackedInput("in1"), "in2": TrackedInput("in2")}
    runtime._input_factory = lambda choice: inputs[choice]

    runtime.switch_input("in1")
    assert runtime.input_source_name == "in1"
    assert stopped == []

    runtime.switch_input("in2")
    assert runtime.input_source_name == "in2"
    assert stopped == ["in1"]

    # Switching to an invalid input raises ValueError without stopping in2
    with pytest.raises(KeyError):
        runtime.switch_input("invalid")
    assert runtime.input_source_name == "in2"
    assert stopped == ["in1"]
    runtime.stop()


def test_runtime_default_input_factory_and_create_default_validation():
    s = System()
    runtime = s.make_runtime()

    # Valid default input produces MuteMeInputSource
    muteme_src = runtime._default_input_factory("muteme")
    assert muteme_src.name == "MuteMe"

    with pytest.raises(ValueError, match="Unknown input source"):
        runtime._default_input_factory("invalid-device")

    # create_default validates input_choice
    with pytest.raises(ValueError, match="Unknown input source"):
        Runtime.create_default(input_choice="unsupported")


def test_runtime_conflict_monitor_setter_syncs_with_existing_input_source():
    s = System()
    runtime = s.make_runtime()

    class MockConflictInput:
        name = "Keyboard"
        conflicting_bundle_ids = frozenset({"com.test.app"})
        conflicting_app_names = frozenset({"TestApp"})

        def start(self, on_event):
            pass

        def stop(self):
            pass

    runtime._input_source = MockConflictInput()

    class MockConflictMonitor:
        def __init__(self):
            self.conflicts = []

        def set_conflicts(self, bundle_ids, app_names):
            self.conflicts.append((bundle_ids, app_names))

    monitor = MockConflictMonitor()
    # Assigning to setter immediately syncs declared conflicts
    runtime.conflict_monitor = monitor
    assert monitor.conflicts == [(frozenset({"com.test.app"}), frozenset({"TestApp"}))]


def test_runtime_switch_input_updates_conflict_monitor():
    s = System()
    runtime = s.make_runtime()

    class MockConflictMonitor:
        def __init__(self):
            self.conflicts = []

        def set_conflicts(self, bundle_ids, app_names):
            self.conflicts.append((bundle_ids, app_names))

    monitor = MockConflictMonitor()
    runtime.conflict_monitor = monitor

    class ConflictInput:
        name = "SpecialDevice"
        conflicting_bundle_ids = frozenset({"com.vendor.special"})
        conflicting_app_names = frozenset({"SpecialApp"})

        def start(self, on_event):
            pass

        def stop(self):
            pass

    runtime._input_factory = lambda choice: ConflictInput()
    runtime.switch_input("special")

    assert (frozenset({"com.vendor.special"}), frozenset({"SpecialApp"})) in monitor.conflicts
    runtime.stop()
