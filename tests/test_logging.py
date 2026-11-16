"""Test del log (T23): file a rotazione, riga per ciclo, eccezioni non gestite nel log."""
from __future__ import annotations

import logging
import os
import sys
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from voicecmd import logging_setup
from voicecmd.controller import Controller, cycle_summary
from voicecmd.events import ActionResult, AppState, Mode, Outcome
from voicecmd.schema import Config

from tests.test_app import Env, FakeTray


@pytest.fixture
def logdir(tmp_path):
    """setup_logging su una cartella temporanea; al termine ripristina logger e hook."""
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, sys.excepthook, threading.excepthook)
    path = logging_setup.setup_logging(tmp_path / "logs", stderr=False)
    yield path
    for h in logging_setup._installed:
        root.removeHandler(h)
        h.close()
    logging_setup._installed.clear()
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    sys.excepthook, threading.excepthook = saved[2], saved[3]


def flush():
    for h in logging_setup._installed:
        h.flush()


def read(path):
    flush()
    return path.read_text(encoding="utf-8")


# --- dipendenze finte del controller --------------------------------------------

class Rec:
    def __init__(self, seconds=1.5):
        self.audio = np.zeros(int(16000 * seconds), dtype=np.float32)

    def start(self):
        pass

    def stop(self):
        return self.audio


class Stt:
    def __init__(self, text):
        self.text = text

    def transcribe(self, audio, hotwords=None):
        return self.text


class Fb:
    def on_state(self, state, mode):
        pass

    def on_outcome(self, outcome):
        pass


class Opener:
    def run(self, spec):
        return ActionResult(True, "aperto")


CFG = Config.model_validate({"commands": [
    {"name": "Chrome", "phrases": ["apri chrome"], "action": {"type": "open", "target": "Google Chrome"}},
]})


def run_cycle(text, mode=Mode.COMMAND, paste=None):
    clock = [0.0]
    perf = iter([10.0, 10.42])
    c = Controller(CFG, Rec(), Stt(text), {"open": Opener()}, Fb(),
                   paste or (lambda t: ActionResult(True, "")),
                   clock=lambda: clock[0], submit=lambda fn: fn(),
                   timer_factory=lambda d, fn: type("T", (), {"start": lambda s: None, "cancel": lambda s: None})(),
                   perf_clock=lambda: next(perf))
    c.on_trigger(mode, True)
    clock[0] = 1.0
    c.on_trigger(mode, False)
    assert c.state is AppState.IDLE


def test_file_created_in_given_dir(logdir):
    assert logdir.name == "voicecmd.log" and logdir.parent.name == "logs"
    logging.getLogger("voicecmd.prova").info("ciao")
    assert "voicecmd.prova: ciao" in read(logdir)


def test_default_dir_is_user_log_dir():
    from platformdirs import user_log_dir
    assert str(logging_setup.log_path()) == os.path.join(
        user_log_dir("voicecmd", appauthor=False), "voicecmd.log")


def test_file_rotates(logdir, monkeypatch, tmp_path):
    monkeypatch.setattr(logging_setup, "MAX_BYTES", 2000)
    path = logging_setup.setup_logging(tmp_path / "logs", stderr=False, install_hooks=False)
    for i in range(200):
        logging.getLogger("voicecmd.x").info("riga %03d %s", i, "x" * 40)
    flush()
    names = sorted(f.name for f in path.parent.iterdir())
    assert names == ["voicecmd.log", "voicecmd.log.1", "voicecmd.log.2", "voicecmd.log.3"]


def test_repeated_setup_does_not_duplicate(logdir, tmp_path):
    logging_setup.setup_logging(tmp_path / "logs", stderr=False)
    logging.getLogger("voicecmd.x").info("una volta")
    assert read(logdir).count("una volta") == 1


def test_unwritable_dir_falls_back(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("")
    root = logging.getLogger()
    saved = root.handlers[:], sys.excepthook, threading.excepthook
    try:
        logging_setup.setup_logging(blocker / "sub", stderr=False, install_hooks=False)
        assert "Log su file non disponibile" in caplog.text
    finally:
        for h in logging_setup._installed:
            root.removeHandler(h)
        logging_setup._installed.clear()
        root.handlers[:] = saved[0]


def test_command_cycle_writes_summary_line(logdir):
    run_cycle("apri chrome")
    line = [l for l in read(logdir).splitlines() if "Ciclo comando" in l]
    assert len(line) == 1
    assert ("audio 1.50 s, trascrizione 0.42 s, testo 'apri chrome', comando Chrome (100/100), "
            "esito ok: Chrome - aperto") in line[0]


def test_no_match_cycle_names_closest(logdir):
    run_cycle("apri il frigorifero")
    text = read(logdir)
    assert "comando nessuno (più vicino Chrome" in text
    assert "esito errore: Nessun comando riconosciuto" in text


def test_dictation_cycle_line(logdir):
    run_cycle("ciao", mode=Mode.DICTATION,
              paste=lambda t: ActionResult(False, "Tasti del trigger ancora premuti"))
    text = read(logdir)
    assert ("Ciclo dettatura, audio 1.50 s, trascrizione 0.42 s, testo 'ciao', "
            "esito errore: Dettatura non riuscita - Tasti del trigger ancora premuti") in text


def test_summary_without_audio():
    out = Outcome(Mode.COMMAND, False, "", "Non ho sentito niente", "")
    assert cycle_summary(Mode.COMMAND, {"audio_s": 0.0}, out) == (
        "Ciclo comando, audio 0.00 s, trascrizione -, testo -, comando nessuno, "
        "esito errore: Non ho sentito niente")


def test_thread_exception_goes_to_log(logdir):
    def boom():
        raise ValueError("esploso nel thread")

    t = threading.Thread(target=boom, name="voicecmd-prova")
    t.start()
    t.join()
    text = read(logdir)
    assert "Eccezione non gestita nel thread voicecmd-prova" in text
    assert "ValueError: esploso nel thread" in text


def test_main_thread_exception_goes_to_log(logdir):
    try:
        raise RuntimeError("esploso nel main")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    text = read(logdir)
    assert "Eccezione non gestita" in text and "RuntimeError: esploso nel main" in text


# --- voce di menu "Apri log" -----------------------------------------------------

class MenuTray(FakeTray):
    def __init__(self):
        super().__init__()
        self.menu = QMenu()
        self.reload_config_action = QAction("Ricarica configurazione", self.menu)
        self.menu.addAction(self.reload_config_action)
        self.menu.addSeparator()
        self.menu.addAction(QAction("Esci", self.menu))


def test_open_log_menu(qtbot, tmp_path, monkeypatch):
    env = Env(tmp_path)
    env.tray = MenuTray()
    opened = []
    monkeypatch.setattr("voicecmd.app.open_in_editor", lambda p: opened.append(p))
    from voicecmd.app import VoiceCmdApp
    log_file = tmp_path / "voicecmd.log"
    app = VoiceCmdApp(env.cfg_path, env.factories, log_file=log_file)
    qtbot.waitUntil(lambda: app.controller is not None, timeout=3000)
    labels = [a.text() for a in env.tray.menu.actions()]
    assert labels == ["Ricarica configurazione", "Apri log", "", "Esci"]
    app.open_log_action.trigger()  # file non ancora creato
    assert opened == [] and env.notifier.messages[-1][0] == "Log non disponibile"
    log_file.write_text("x")
    app.open_log_action.trigger()
    assert opened == [log_file]
    app.shutdown()
