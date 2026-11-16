"""Test del Controller con dipendenze finte, orologio e timer controllabili, worker sincrono."""
from __future__ import annotations

import threading

import numpy as np
import pytest

from voicecmd.controller import Controller, hotwords_for
from voicecmd.events import (
    MAX_COMMAND_S,
    MAX_DICTATION_S,
    ActionResult,
    AppState,
    Mode,
    Outcome,
)
from voicecmd.schema import Config

AUDIO = np.ones(16000, dtype=np.float32) * 0.1

CONFIG = Config.model_validate({
    "commands": [
        {"name": "Safari", "phrases": ["apri safari"],
         "action": {"type": "open", "target": "Safari"}},
        {"name": "Lista file", "phrases": ["elenca i file"],
         "action": {"type": "shell", "command": "ls"}},
    ]
})


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class FakeTimer:
    def __init__(self, delay, fn):
        self.delay, self.fn = delay, fn
        self.started = self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.fn()


class FakeRecorder:
    def __init__(self, audio=AUDIO, fail_start=False):
        self.audio, self.fail_start = audio, fail_start
        self.starts = self.stops = 0

    def start(self):
        if self.fail_start:
            raise OSError("nessun microfono")
        self.starts += 1

    def stop(self):
        self.stops += 1
        return self.audio


class FakeTranscriber:
    def __init__(self, text="apri safari", exc=None):
        self.text, self.exc = text, exc
        self.calls = []

    def transcribe(self, audio, hotwords=None):
        self.calls.append(hotwords)
        if self.exc:
            raise self.exc
        return self.text


class FakeAction:
    def __init__(self, result=ActionResult(True, "fatto"), exc=None):
        self.result, self.exc = result, exc
        self.specs = []

    def run(self, spec):
        self.specs.append(spec)
        if self.exc:
            raise self.exc
        return self.result


class FakeFeedback:
    def __init__(self):
        self.events = []

    def on_state(self, state, mode):
        self.events.append(("state", state, mode))

    def on_outcome(self, outcome):
        self.events.append(("outcome", outcome))

    @property
    def states(self):
        return [e[1] for e in self.events if e[0] == "state"]

    @property
    def outcomes(self):
        return [e[1] for e in self.events if e[0] == "outcome"]


class Harness:
    def __init__(self, config=CONFIG, recorder=None, transcriber=None, open_action=None,
                 shell_action=None, paste=None, **kw):
        self.clock = Clock()
        self.timers = []
        self.recorder = recorder or FakeRecorder()
        self.transcriber = transcriber or FakeTranscriber()
        self.open = open_action or FakeAction()
        self.shell = shell_action or FakeAction()
        self.pasted = []
        self.paste_result = ActionResult(True, "")
        self.feedback = FakeFeedback()

        def default_paste(text):
            self.pasted.append(text)
            return self.paste_result

        def timer_factory(delay, fn):
            t = FakeTimer(delay, fn)
            self.timers.append(t)
            return t

        self.c = Controller(
            config, self.recorder, self.transcriber,
            {"open": self.open, "shell": self.shell}, self.feedback, paste or default_paste,
            clock=self.clock, submit=lambda fn: fn(), timer_factory=timer_factory, **kw,
        )

    def press_release(self, mode=Mode.COMMAND, seconds=1.0):
        self.c.on_trigger(mode, True)
        self.clock.t += seconds
        self.c.on_trigger(mode, False)


def test_command_recognized():
    h = Harness()
    h.press_release()
    assert len(h.open.specs) == 1 and h.open.specs[0].target == "Safari"
    assert h.shell.specs == []
    assert h.feedback.states == [AppState.LISTENING, AppState.PROCESSING, AppState.DONE, AppState.IDLE]
    (o,) = h.feedback.outcomes
    assert o == Outcome(Mode.COMMAND, True, "apri safari", "Safari", "fatto")
    assert h.c.state is AppState.IDLE
    assert h.recorder.starts == 1 and h.recorder.stops == 1


def test_mode_passed_with_states():
    h = Harness()
    h.press_release()
    modes = [e[2] for e in h.feedback.events if e[0] == "state"]
    assert modes == [Mode.COMMAND, Mode.COMMAND, Mode.COMMAND, None]


def test_no_match_reports_closest():
    h = Harness(transcriber=FakeTranscriber("che tempo fa domani"))
    h.press_release()
    assert h.open.specs == [] and h.shell.specs == []
    (o,) = h.feedback.outcomes
    assert not o.ok
    assert o.heard == "che tempo fa domani"
    assert o.title == "Nessun comando riconosciuto"
    assert "Il più vicino:" in o.detail
    assert h.feedback.states[-2:] == [AppState.ERROR, AppState.IDLE]


def test_no_commands_configured():
    h = Harness(config=Config())
    h.press_release()
    (o,) = h.feedback.outcomes
    assert o.detail == "Nessun comando configurato"


def test_silence_skips_transcription():
    h = Harness(recorder=FakeRecorder(audio=np.zeros(0, dtype=np.float32)))
    h.press_release()
    assert h.transcriber.calls == []
    (o,) = h.feedback.outcomes
    assert not o.ok and o.title == "Non ho sentito niente"
    assert h.c.state is AppState.IDLE


def test_empty_transcription_is_silence():
    h = Harness(transcriber=FakeTranscriber("  "))
    h.press_release()
    (o,) = h.feedback.outcomes
    assert o.title == "Non ho sentito niente"
    assert h.open.specs == []


def test_short_press_cancelled():
    h = Harness()
    h.press_release(seconds=0.1)
    assert h.transcriber.calls == []
    assert h.recorder.stops == 1  # audio fermato e scartato
    assert h.feedback.outcomes == []
    assert h.feedback.states == [AppState.LISTENING, AppState.IDLE]
    assert h.timers[0].cancelled
    # dopo una pressione breve si può ripartire
    h.press_release()
    assert len(h.open.specs) == 1


@pytest.mark.parametrize("mode,cap", [(Mode.COMMAND, MAX_COMMAND_S), (Mode.DICTATION, MAX_DICTATION_S)])
def test_duration_cap_closes_like_release(mode, cap):
    h = Harness(transcriber=FakeTranscriber("apri safari"))
    h.c.on_trigger(mode, True)
    (timer,) = h.timers
    assert timer.started and timer.delay == cap
    h.clock.t += cap
    timer.fire()
    assert len(h.feedback.outcomes) == 1
    assert h.c.state is AppState.IDLE
    # il rilascio vero che arriva dopo il tetto viene ignorato
    h.c.on_trigger(mode, False)
    assert len(h.feedback.outcomes) == 1
    assert h.recorder.stops == 1


def test_release_cancels_timer():
    h = Harness()
    h.press_release()
    assert h.timers[0].cancelled


def test_dictation_pastes_text():
    h = Harness(transcriber=FakeTranscriber("Ciao, come stai?"))
    h.press_release(Mode.DICTATION)
    assert h.pasted == ["Ciao, come stai?"]
    assert h.open.specs == []
    (o,) = h.feedback.outcomes
    assert o.ok and o.mode is Mode.DICTATION and o.title == "Testo incollato"


def test_dictation_paste_failure():
    h = Harness(transcriber=FakeTranscriber("ciao"))
    h.paste_result = ActionResult(False, "tasti ancora premuti")
    h.press_release(Mode.DICTATION)
    (o,) = h.feedback.outcomes
    assert not o.ok and o.title == "Dettatura non riuscita" and o.detail == "tasti ancora premuti"
    assert h.feedback.states[-2] is AppState.ERROR


def test_action_failure_is_error():
    h = Harness(open_action=FakeAction(ActionResult(False, "App non trovata")))
    h.press_release()
    (o,) = h.feedback.outcomes
    assert not o.ok and o.title == "Safari" and o.detail == "App non trovata"


def test_trigger_during_processing_ignored():
    jobs = []
    h = Harness()
    h.c._submit = jobs.append  # worker che non parte finché non lo diciamo
    h.press_release()
    assert h.c.state is AppState.PROCESSING
    h.press_release()  # ignorato
    h.press_release(Mode.DICTATION)  # ignorato
    assert h.recorder.starts == 1
    jobs.pop()()
    assert h.c.state is AppState.IDLE
    assert len(h.feedback.outcomes) == 1


def test_trigger_during_listening_ignored():
    h = Harness()
    h.c.on_trigger(Mode.COMMAND, True)
    h.c.on_trigger(Mode.DICTATION, True)   # altra modalità mentre si ascolta
    h.c.on_trigger(Mode.DICTATION, False)  # suo rilascio: ignorato
    assert h.c.state is AppState.LISTENING
    h.clock.t += 1
    h.c.on_trigger(Mode.COMMAND, False)
    assert len(h.open.specs) == 1
    assert h.recorder.starts == 1


def test_release_without_press_ignored():
    h = Harness()
    h.c.on_trigger(Mode.COMMAND, False)
    assert h.feedback.events == []
    assert h.recorder.stops == 0


def test_transcriber_exception_becomes_error():
    h = Harness(transcriber=FakeTranscriber(exc=RuntimeError("MPS esploso")))
    h.press_release()
    (o,) = h.feedback.outcomes
    assert not o.ok and o.title == "Errore" and "MPS esploso" in o.detail
    assert h.feedback.states[-2:] == [AppState.ERROR, AppState.IDLE]
    # l'app continua a funzionare
    h.transcriber.exc = None
    h.press_release()
    assert h.feedback.outcomes[-1].ok


def test_action_exception_becomes_error():
    h = Harness(open_action=FakeAction(exc=ValueError("rotto")))
    h.press_release()
    (o,) = h.feedback.outcomes
    assert not o.ok and "rotto" in o.detail
    assert h.c.state is AppState.IDLE


def test_recorder_start_failure():
    h = Harness(recorder=FakeRecorder(fail_start=True))
    h.c.on_trigger(Mode.COMMAND, True)
    (o,) = h.feedback.outcomes
    assert not o.ok and o.title == "Microfono non disponibile"
    assert h.c.state is AppState.IDLE
    assert h.timers == []
    h.c.on_trigger(Mode.COMMAND, False)  # rilascio successivo ignorato
    assert len(h.feedback.outcomes) == 1


def test_feedback_exception_not_fatal():
    h = Harness()

    def boom(*a):
        raise RuntimeError("UI rotta")

    h.feedback.on_state = boom
    h.press_release()
    assert len(h.open.specs) == 1
    assert h.c.state is AppState.IDLE


def test_reload_in_idle_applies_now():
    h = Harness()
    new = Config()
    h.c.reload(new)
    assert h.c.config is new


def test_reload_during_cycle_applied_at_idle():
    jobs = []
    h = Harness()
    h.c._submit = jobs.append
    h.press_release()
    new = Config()
    h.c.reload(new)
    assert h.c.config is CONFIG
    jobs.pop()()
    assert h.c.config is new
    # il ciclo in corso ha usato la configurazione vecchia
    assert len(h.open.specs) == 1


def test_hotwords_off_by_default():
    h = Harness()
    h.press_release()
    assert h.transcriber.calls == [None]


def test_hotwords_in_command_mode_only():
    h = Harness(use_hotwords=True, transcriber=FakeTranscriber("apri safari"))
    h.press_release()
    assert h.transcriber.calls[-1] == ["apri", "safari", "elenca", "i", "file"]
    h.press_release(Mode.DICTATION)
    assert h.transcriber.calls[-1] is None


def test_hotwords_for_dedup():
    assert hotwords_for(CONFIG) == ["apri", "safari", "elenca", "i", "file"]
    assert hotwords_for(Config()) == []


def test_shutdown_ignores_new_triggers():
    h = Harness()
    h.c.shutdown()
    h.c.on_trigger(Mode.COMMAND, True)
    assert h.recorder.starts == 0


def test_real_worker_thread_and_shutdown():
    """Con il worker vero l'elaborazione avviene fuori dal thread chiamante; shutdown non lascia thread."""
    done = threading.Event()
    seen_threads = []

    class Fb(FakeFeedback):
        def on_outcome(self, outcome):
            seen_threads.append(threading.current_thread().name)
            done.set()

    clock = Clock()
    c = Controller(CONFIG, FakeRecorder(), FakeTranscriber(), {"open": FakeAction()}, Fb(),
                   lambda t: ActionResult(True, ""), clock=clock)
    c.on_trigger(Mode.COMMAND, True)
    clock.t += 1
    c.on_trigger(Mode.COMMAND, False)
    assert done.wait(2)
    c.shutdown()
    assert seen_threads[0].startswith("voicecmd-worker")
    assert not any(t.name.startswith("voicecmd-worker") and t.is_alive() for t in threading.enumerate())
