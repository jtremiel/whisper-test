"""Test di app.py con moduli finti: ciclo completo, consegna sul main thread, uscita pulita."""
from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal

from voicecmd.app import Factories, VoiceCmdApp, trigger_maps
from voicecmd.events import ActionResult, AppState, Mode
from voicecmd.schema import Config

CONFIG_YAML = """
triggers:
  command:
    hotkey: "<ctrl>+<alt>+space"
  dictation:
    mouse_button: x2
commands:
  - name: Safari
    phrases: ["apri safari"]
    action: {type: open, target: Safari}
"""


class FakeTray(QObject):
    open_config_requested = Signal()
    reload_config_requested = Signal()
    quit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.tray_icon = object()
        self.states, self.status, self.visible = [], [], False
        self.threads = []

    def set_state(self, state, mode):
        self.threads.append(threading.current_thread())
        self.states.append(state)

    def set_status_text(self, text):
        self.status.append(text)

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


class FakeOverlay:
    def __init__(self):
        self.states, self.outcomes, self.hidden = [], [], False
        self.threads = []

    def show_state(self, state, mode):
        self.threads.append(threading.current_thread())
        self.states.append(state)

    def show_outcome(self, outcome):
        self.threads.append(threading.current_thread())
        self.outcomes.append(outcome)

    def hide(self):
        self.hidden = True


class FakeSounds:
    def __init__(self):
        self.enabled = True
        self.played = []

    def play(self, name):
        if self.enabled:
            self.played.append(name)


class FakeNotifier:
    def __init__(self):
        self.enabled = True
        self.outcomes, self.messages = [], []

    def notify(self, outcome):
        if self.enabled:
            self.outcomes.append(outcome)

    def show(self, title, text, error=False):
        if self.enabled:
            self.messages.append((title, text, error))


class FakeTrigger:
    def __init__(self, mapping, fail_start=False):
        self.mapping, self.fail_start = mapping, fail_start
        self.on_event = None
        self.stopped = False

    def start(self, on_event):
        if self.fail_start:
            raise RuntimeError("Permesso Monitoraggio input mancante")
        self.on_event = on_event

    def stop(self):
        self.stopped = True

    def keys_released(self):
        return True


class FakeRecorder:
    def __init__(self):
        self.closed = False

    def start(self):
        pass

    def stop(self):
        return np.ones(16000, dtype=np.float32)

    def close(self):
        self.closed = True


class FakeTranscriber:
    def __init__(self, text="apri safari"):
        self.text = text

    def transcribe(self, audio, hotwords=None):
        return self.text


class FakeOpen:
    def __init__(self):
        self.specs = []

    def run(self, spec):
        self.specs.append(spec)
        return ActionResult(True, "aperto")


class Env:
    def __init__(self, tmp_path, yaml_text=CONFIG_YAML, text="apri safari", missing=(),
                 mouse_fail=False, transcriber_exc=None):
        self.cfg_path = tmp_path / "config.yaml"
        self.cfg_path.write_text(yaml_text, encoding="utf-8")
        self.tray, self.overlay = FakeTray(), FakeOverlay()
        self.sounds, self.notifier = FakeSounds(), FakeNotifier()
        self.recorder = FakeRecorder()
        self.open = FakeOpen()
        self.hk = self.mouse = None
        self.pasted = []

        def transcriber(cfg):
            if transcriber_exc:
                raise transcriber_exc
            return FakeTranscriber(text)

        def hotkey(m):
            self.hk = FakeTrigger(m)
            return self.hk

        def mouse(m):
            self.mouse = FakeTrigger(m, fail_start=mouse_fail)
            return self.mouse

        def paste(keys_released):
            self.keys_released = keys_released

            def do(text):
                self.pasted.append(text)
                return ActionResult(True, "")
            return do

        self.factories = Factories(
            transcriber=transcriber,
            recorder=lambda cfg: self.recorder,
            actions=lambda: {"open": self.open},
            paste=paste,
            hotkey_trigger=hotkey,
            mouse_trigger=mouse,
            permissions=lambda: list(missing),
            ui=lambda: (self.tray, self.overlay, self.sounds, self.notifier),
        )

    def make(self, qtbot, background_load=True):
        app = VoiceCmdApp(self.cfg_path, self.factories, background_load=background_load)
        # pronto quando il controller esiste, oppure il caricamento è fallito (icona in ERROR)
        qtbot.waitUntil(
            lambda: app.controller is not None
            or bool(self.tray.states and self.tray.states[-1] is AppState.ERROR),
            timeout=3000,
        )
        return app


def test_trigger_maps_split():
    cfg = Config.model_validate({"triggers": {"command": {"hotkey": "f13"},
                                              "dictation": {"mouse_button": "x1"}}})
    assert trigger_maps(cfg) == ({Mode.COMMAND: "f13"}, {Mode.DICTATION: "x1"})


def test_startup_builds_and_starts_triggers(qtbot, tmp_path):
    env = Env(tmp_path)
    app = env.make(qtbot)
    assert env.tray.visible
    assert env.tray.status[0] == "Caricamento del modello…"
    assert env.hk.mapping == {Mode.COMMAND: "<ctrl>+<alt>+space"}
    assert env.mouse.mapping == {Mode.DICTATION: "x2"}
    assert env.hk.on_event is not None and env.mouse.on_event is not None
    assert env.keys_released() is True  # delega al trigger da tastiera in uso
    env.hk.keys_released = lambda: False
    assert env.keys_released() is False
    assert env.tray.states[-1] is AppState.IDLE
    app.shutdown()


def test_full_cycle_updates_ui_on_main_thread(qtbot, tmp_path):
    env = Env(tmp_path)
    app = env.make(qtbot)
    main = threading.current_thread()
    clock = [0.0]
    app.controller._clock = lambda: clock[0]

    # pressione e rilascio arrivano da un thread "listener", come con pynput
    def listener():
        env.hk.on_event(Mode.COMMAND, True)
        clock[0] += 1.0
        env.hk.on_event(Mode.COMMAND, False)

    t = threading.Thread(target=listener)
    t.start()
    t.join()
    qtbot.waitUntil(lambda: len(env.overlay.outcomes) == 1, timeout=3000)
    qtbot.waitUntil(lambda: env.tray.states[-1] is AppState.IDLE, timeout=3000)

    assert len(env.open.specs) == 1
    assert env.overlay.outcomes[0].ok and env.overlay.outcomes[0].title == "Safari"
    assert env.notifier.outcomes == env.overlay.outcomes
    assert env.sounds.played == ["start", "done"]
    assert env.tray.states[-4:] == [AppState.LISTENING, AppState.PROCESSING, AppState.DONE, AppState.IDLE]
    assert all(th is main for th in env.tray.threads + env.overlay.threads)
    app.shutdown()


def test_dictation_via_mouse_trigger(qtbot, tmp_path):
    env = Env(tmp_path, text="ciao a tutti")
    app = env.make(qtbot)
    clock = [0.0]
    app.controller._clock = lambda: clock[0]
    env.mouse.on_event(Mode.DICTATION, True)
    clock[0] += 1.0
    env.mouse.on_event(Mode.DICTATION, False)
    qtbot.waitUntil(lambda: env.pasted == ["ciao a tutti"], timeout=3000)
    app.shutdown()


def test_feedback_switches_respected(qtbot, tmp_path):
    yaml_text = CONFIG_YAML + "feedback: {tray: false, sounds: false, overlay: false, notifications: false}\n"
    env = Env(tmp_path, yaml_text=yaml_text)
    app = env.make(qtbot)
    n_tray = len(env.tray.states)
    clock = [0.0]
    app.controller._clock = lambda: clock[0]
    env.hk.on_event(Mode.COMMAND, True)
    clock[0] += 1.0
    env.hk.on_event(Mode.COMMAND, False)
    qtbot.waitUntil(lambda: app.controller.state is AppState.IDLE and len(env.open.specs) == 1, timeout=3000)
    qtbot.wait(50)
    assert env.overlay.states == [] and env.overlay.outcomes == []
    assert env.sounds.played == []
    assert env.notifier.outcomes == []
    assert len(env.tray.states) == n_tray
    app.shutdown()


def test_quit_stops_everything(qtbot, tmp_path):
    env = Env(tmp_path)
    app = env.make(qtbot)
    env.tray.quit_requested.emit()
    assert env.hk.stopped and env.mouse.stopped
    assert env.recorder.closed
    assert not env.tray.visible and env.overlay.hidden
    assert app.triggers == []
    alive = [t.name for t in threading.enumerate()
             if t.is_alive() and t.name.startswith(("voicecmd-worker", "voicecmd-loader"))]
    assert alive == []
    app.shutdown()  # idempotente


def test_missing_permissions_notified(qtbot, tmp_path):
    class Missing:
        message = "Manca il permesso 'Microfono'."

    env = Env(tmp_path, missing=[Missing()])
    app = env.make(qtbot)
    assert ("Permessi mancanti", "Manca il permesso 'Microfono'.", True) in env.notifier.messages
    app.shutdown()


def test_invalid_config_at_startup_uses_defaults(qtbot, tmp_path):
    env = Env(tmp_path, yaml_text="matching: {threshold: 500}\n")
    app = env.make(qtbot)
    assert app.config == Config()
    title, text, error = env.notifier.messages[0]
    assert title == "Configurazione non valida" and "matching.threshold" in text and error
    app.shutdown()


def test_trigger_start_failure_notified(qtbot, tmp_path):
    env = Env(tmp_path, mouse_fail=True)
    app = env.make(qtbot)
    assert any(m[0] == "Trigger non attivi" for m in env.notifier.messages)
    assert app.triggers == [env.hk]
    app.shutdown()


def test_model_load_failure_shows_error(qtbot, tmp_path):
    env = Env(tmp_path, transcriber_exc=RuntimeError("modello non trovato"))
    app = env.make(qtbot)
    assert app.controller is None
    assert env.tray.states[-1] is AppState.ERROR
    assert any("modello non trovato" in m[1] for m in env.notifier.messages)
    app.shutdown()


def test_reload_menu_valid_and_invalid(qtbot, tmp_path):
    env = Env(tmp_path)
    app = env.make(qtbot)
    env.cfg_path.write_text(CONFIG_YAML + "matching: {threshold: 70}\n", encoding="utf-8")
    env.tray.reload_config_requested.emit()
    assert app.config.matching.threshold == 70
    assert app.controller.config.matching.threshold == 70
    env.cfg_path.write_text("commands: [{name: x}]\n", encoding="utf-8")
    env.tray.reload_config_requested.emit()
    assert app.config.matching.threshold == 70  # configurazione precedente mantenuta
    assert env.notifier.messages[-1][0] == "Configurazione non valida"
    app.shutdown()


def test_synchronous_load(qtbot, tmp_path):
    env = Env(tmp_path)
    app = VoiceCmdApp(env.cfg_path, env.factories, background_load=False)
    qtbot.waitUntil(lambda: app.controller is not None, timeout=3000)
    app.shutdown()


def test_real_paste_builds_keyboard_on_calling_thread(monkeypatch):
    # regressione: il controller pynput creato sul worker faceva crashare macOS (SIGTRAP)
    import voicecmd.actions.dictation as dictation
    from voicecmd.app import _real_paste

    built_on = []

    class FakeKb:
        def __init__(self):
            built_on.append(threading.current_thread())

    monkeypatch.setattr(dictation, "PynputKeyboard", FakeKb)
    fn = _real_paste(lambda: True)
    assert built_on == [threading.current_thread()]
    assert isinstance(fn.keywords["keyboard"], FakeKb)
