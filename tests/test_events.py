import dataclasses
import sys

import pytest

from voicecmd import events as ev


def test_import_senza_dipendenze_pesanti() -> None:
    for name in ("PySide6", "pynput", "faster_whisper", "numpy"):
        # il test runner potrebbe averli già caricati: controlliamo solo che events non li importi
        assert not hasattr(ev, name)


def test_enum_e_costanti() -> None:
    assert {s.name for s in ev.AppState} == {"IDLE", "LISTENING", "PROCESSING", "DONE", "ERROR"}
    assert {m.name for m in ev.Mode} == {"COMMAND", "DICTATION"}
    assert ev.SAMPLE_RATE == 16000
    assert ev.MIN_PRESS_S == 0.3
    assert ev.MAX_COMMAND_S == 30
    assert ev.MAX_DICTATION_S == 120


def test_dataclass() -> None:
    r = ev.ActionResult(True, "ok")
    m = ev.MatchResult(None, 0.0, "ciao", "browser", 55.0)
    o = ev.Outcome(ev.Mode.COMMAND, False, "ciao", "Nessun comando", "")
    assert m.command is None and m.closest == "browser"
    for obj in (r, m, o):
        with pytest.raises(dataclasses.FrozenInstanceError):
            obj.__setattr__(dataclasses.fields(obj)[0].name, None)


def test_protocol_soddisfatti() -> None:
    class T:
        def start(self, on_event): ...
        def stop(self): ...

    class R:
        def start(self): ...
        def stop(self): ...

    class S:
        def transcribe(self, audio, hotwords=None): ...

    class A:
        def run(self, spec): ...

    class F:
        def on_state(self, state, mode): ...
        def on_outcome(self, outcome): ...

    assert isinstance(T(), ev.Trigger)
    assert isinstance(R(), ev.Recorder)
    assert isinstance(S(), ev.Transcriber)
    assert isinstance(A(), ev.Action)
    assert isinstance(F(), ev.Feedback)
    assert not isinstance(object(), ev.Trigger)
    assert not isinstance(R(), ev.Transcriber)


def test_events_non_importa_qt_pynput_whisper() -> None:
    import subprocess
    code = ("import sys, voicecmd.events;"
            "bad=[m for m in ('PySide6','pynput','faster_whisper','numpy') if m in sys.modules];"
            "sys.exit(1 if bad else 0)")
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0
