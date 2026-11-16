"""Avvio di voicecmd e collegamento fra Controller e interfaccia Qt.

Qt occupa il main thread. Il Controller viene chiamato dai thread dei trigger e
lavora sul suo worker; tutto ciò che tocca i widget passa per `FeedbackBridge`,
che riemette le chiamate come segnali Qt consegnati sul main thread.
"""
from __future__ import annotations

import logging
import signal
import sys
import threading
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from voicecmd.config import ConfigError, ensure_config, load_config, open_in_editor
from voicecmd.controller import Controller
from voicecmd.events import AppState, Mode, Outcome, Recorder, Transcriber, Trigger
from voicecmd.logging_setup import log_path, setup_logging
from voicecmd.schema import Config

log = logging.getLogger(__name__)

SOUND_FOR_STATE = {AppState.LISTENING: "start", AppState.DONE: "done", AppState.ERROR: "error"}

# Gli editor salvano con più eventi ravvicinati (troncamento, scrittura, rename): si aspetta
# che si calmino prima di rileggere il file.
RELOAD_DEBOUNCE_MS = 300


def restart_required(old: Config, new: Config) -> list[str]:
    """Sezioni che valgono solo dopo il riavvio: modello, lingua e microfono si creano all'avvio."""
    changed = []
    if old.language != new.language:
        changed.append("language")
    for name in type(old.stt).model_fields:
        if getattr(old.stt, name) != getattr(new.stt, name):
            changed.append(f"stt.{name}")
    for name in type(old.audio).model_fields:
        if getattr(old.audio, name) != getattr(new.audio, name):
            changed.append(f"audio.{name}")
    return changed


# --- ponte Feedback -> Qt ----------------------------------------------------

class FeedbackBridge(QObject):
    """Implementa `events.Feedback`: chiamabile da qualunque thread, consegna sul main thread."""

    state_changed = Signal(object, object)  # AppState, Mode | None
    outcome_ready = Signal(object)          # Outcome

    def on_state(self, state: AppState, mode: Mode | None) -> None:
        self.state_changed.emit(state, mode)

    def on_outcome(self, outcome: Outcome) -> None:
        self.outcome_ready.emit(outcome)


# --- costruzione dei moduli reali (sostituibile nei test) ----------------------

def _real_transcriber(config: Config) -> Transcriber:
    from voicecmd.stt import FasterWhisperTranscriber
    return FasterWhisperTranscriber(config.stt, language=config.language)


def _real_recorder(config: Config) -> Recorder:
    from voicecmd.audio import SoundDeviceRecorder
    return SoundDeviceRecorder(config.audio)


def _real_actions() -> dict[str, Any]:
    from voicecmd.actions.open import OpenActionRunner
    from voicecmd.actions.shell import ShellActionRunner
    return {"open": OpenActionRunner(), "shell": ShellActionRunner()}


def _real_paste(keys_released: Callable[[], bool] | None) -> Callable[[str], Any]:
    from voicecmd.actions.dictation import PynputKeyboard, paste_text
    # Il controller di pynput va creato sul main thread: su macOS il suo __init__ chiama
    # TSMGetInputSourceProperty, che fuori dalla main queue fa terminare il processo (SIGTRAP).
    # _real_paste è chiamata da _on_loaded, sul main thread; l'incolla poi gira sul worker.
    keyboard = None
    try:
        keyboard = PynputKeyboard()
    except Exception:  # noqa: BLE001 - paste_text riproverà e restituirà un errore leggibile
        log.exception("Impossibile preparare la tastiera per la dettatura")
    return partial(paste_text, keys_released=keys_released, keyboard=keyboard)


def _real_hotkey_trigger(hotkeys: dict[Mode, str]) -> Trigger:
    from voicecmd.triggers.hotkey import HotkeyTrigger
    return HotkeyTrigger(hotkeys)


def _real_mouse_trigger(buttons: dict[Mode, str]) -> Trigger:
    from voicecmd.triggers.mouse import MouseTrigger
    return MouseTrigger(buttons)


def _real_permissions() -> list[Any]:
    from voicecmd.permissions import check_permissions
    return check_permissions()


def _real_ui() -> tuple[Any, Any, Any, Any]:
    from voicecmd.ui.notify import Notifier
    from voicecmd.ui.overlay import Overlay
    from voicecmd.ui.sounds import Sounds
    from voicecmd.ui.tray import Tray
    tray = Tray()
    return tray, Overlay(), Sounds(), Notifier(tray.tray_icon)


@dataclass
class Factories:
    """Come si costruiscono i moduli. I test passano versioni finte."""
    transcriber: Callable[[Config], Transcriber] = _real_transcriber
    recorder: Callable[[Config], Recorder] = _real_recorder
    actions: Callable[[], dict[str, Any]] = _real_actions
    paste: Callable[[Callable[[], bool] | None], Callable[[str], Any]] = _real_paste
    hotkey_trigger: Callable[[dict[Mode, str]], Trigger] = _real_hotkey_trigger
    mouse_trigger: Callable[[dict[Mode, str]], Trigger] = _real_mouse_trigger
    permissions: Callable[[], list[Any]] = _real_permissions
    ui: Callable[[], tuple[Any, Any, Any, Any]] = _real_ui
    controller_kwargs: dict[str, Any] = field(default_factory=dict)


def trigger_maps(config: Config) -> tuple[dict[Mode, str], dict[Mode, str]]:
    """Divide i trigger della config in (hotkey per modalità, pulsante del mouse per modalità)."""
    hotkeys: dict[Mode, str] = {}
    buttons: dict[Mode, str] = {}
    for mode, tc in ((Mode.COMMAND, config.triggers.command), (Mode.DICTATION, config.triggers.dictation)):
        if tc.hotkey is not None:
            hotkeys[mode] = tc.hotkey
        elif tc.mouse_button is not None:
            buttons[mode] = tc.mouse_button
    return hotkeys, buttons


# --- applicazione ------------------------------------------------------------

class VoiceCmdApp(QObject):
    """Possiede UI, Controller, recorder e trigger. Va creata sul main thread."""

    _loaded = Signal(object)  # dal thread di caricamento: (transcriber, recorder) oppure Exception

    def __init__(
        self,
        config_path: Path | None = None,
        factories: Factories | None = None,
        background_load: bool = True,
        reload_debounce_ms: int = RELOAD_DEBOUNCE_MS,
        log_file: Path | None = None,
    ) -> None:
        super().__init__()
        self.f = factories or Factories()
        self.log_file = log_file if log_file is not None else log_path()
        self.config_path = ensure_config(config_path)
        self.config, startup_error = self._load_initial_config()

        self.bridge = FeedbackBridge()
        self.tray, self.overlay, self.sounds, self.notifier = self.f.ui()
        self.bridge.state_changed.connect(self._on_state, Qt.ConnectionType.QueuedConnection)
        self.bridge.outcome_ready.connect(self._on_outcome, Qt.ConnectionType.QueuedConnection)
        self.tray.open_config_requested.connect(self.open_config)
        self.tray.reload_config_requested.connect(self.reload_config)
        self.tray.quit_requested.connect(self.quit)
        self.open_log_action = self._add_open_log_action()
        self._loaded.connect(self._on_loaded, Qt.ConnectionType.QueuedConnection)

        self.controller: Controller | None = None
        self.recorder: Recorder | None = None
        self.triggers: list[Trigger] = []
        self._loader: threading.Thread | None = None
        self._quitting = False
        self._hotkey: Trigger | None = None
        self._triggers_dirty = False  # binding cambiati durante un ciclo: riavvio al ritorno in IDLE
        self._apply_feedback_switches()

        # Osservazione del file: si guarda anche la cartella, perché molti editor salvano
        # scrivendo un file nuovo e rinominandolo, e il watcher perde il percorso originale.
        self._last_text = self._read_text()
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(reload_debounce_ms)
        self._reload_timer.timeout.connect(self._on_file_settled)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_event)
        self.watcher.directoryChanged.connect(self._on_file_event)
        self._watch()

        self.tray.show()
        self.tray.set_status_text("Caricamento del modello…")
        if startup_error:
            self._notify("Configurazione non valida", f"{startup_error}\n\nUso i valori predefiniti.", True)
        self._check_permissions()

        if background_load:
            self._loader = threading.Thread(target=self._load_models, name="voicecmd-loader", daemon=True)
            self._loader.start()
        else:
            self._load_models()

    # --- avvio ---------------------------------------------------------------

    def _load_initial_config(self) -> tuple[Config, str | None]:
        try:
            return load_config(self.config_path), None
        except ConfigError as e:
            log.error("%s", e)
            return Config(), str(e)

    def _check_permissions(self) -> None:
        try:
            missing = self.f.permissions()
        except Exception:  # noqa: BLE001
            log.exception("Controllo dei permessi non riuscito")
            return
        if missing:
            text = "\n\n".join(m.message for m in missing)
            log.warning("Permessi mancanti:\n%s", text)
            self._notify("Permessi mancanti", text, True)

    def _load_models(self) -> None:
        """Carica modello e microfono (operazioni lente). Gira sul thread di caricamento."""
        try:
            transcriber = self.f.transcriber(self.config)
            recorder = self.f.recorder(self.config)
            result: Any = (transcriber, recorder)
        except Exception as e:  # noqa: BLE001
            log.exception("Caricamento non riuscito")
            result = e
        self._loaded.emit(result)

    @Slot(object)
    def _on_loaded(self, result: Any) -> None:
        if self._quitting:
            if isinstance(result, tuple):
                self._close_recorder(result[1])
            return
        if isinstance(result, Exception):
            self.tray.set_state(AppState.ERROR, None)
            self.tray.set_status_text("Errore di caricamento")
            self._notify("Impossibile avviare voicecmd", f"{type(result).__name__}: {result}", True)
            return
        transcriber, self.recorder = result
        self.controller = Controller(
            self.config, self.recorder, transcriber, self.f.actions(), self.bridge,
            self.f.paste(self._keys_released), **self.f.controller_kwargs,
        )
        self.tray.set_state(AppState.IDLE, None)
        self._start_triggers()

    def _keys_released(self) -> bool:
        """Per l'incolla: delega al trigger da tastiera in uso, che cambia se si ricarica."""
        hk = self._hotkey
        fn = getattr(hk, "keys_released", None)
        return True if fn is None else bool(fn())

    def _start_triggers(self) -> None:
        """Crea e avvia i trigger della config in uso. Va chiamata sul main thread."""
        assert self.controller is not None
        hotkeys, buttons = trigger_maps(self.config)
        built: list[Trigger] = []
        errors: list[str] = []
        hotkey = None
        if hotkeys:
            try:
                hotkey = self.f.hotkey_trigger(hotkeys)
                built.append(hotkey)
            except Exception as e:  # noqa: BLE001 - HotkeyError
                errors.append(f"Hotkey: {e}")
        if buttons:
            try:
                built.append(self.f.mouse_trigger(buttons))
            except Exception as e:  # noqa: BLE001
                errors.append(f"Mouse: {e}")
        for t in built:
            try:
                t.start(self.controller.on_trigger)
                self.triggers.append(t)
            except Exception as e:  # noqa: BLE001 - es. permessi mancanti per l'event tap
                log.exception("Avvio del trigger non riuscito")
                errors.append(str(e))
        self._hotkey = hotkey if hotkey in self.triggers else None
        if errors:
            self._notify("Trigger non attivi", "\n".join(errors), True)
        log.info("voicecmd pronto (%d trigger attivi)", len(self.triggers))

    def _stop_triggers(self) -> None:
        for t in self.triggers:
            try:
                t.stop()
            except Exception:  # noqa: BLE001
                log.exception("Errore nel fermare un trigger")
        self.triggers.clear()
        self._hotkey = None

    def _restart_triggers(self) -> None:
        self._triggers_dirty = False
        self._stop_triggers()
        self._start_triggers()

    # --- feedback sul main thread -------------------------------------------

    def _apply_feedback_switches(self) -> None:
        fb = self.config.feedback
        self.sounds.enabled = fb.sounds
        self.notifier.enabled = fb.notifications

    @Slot(object, object)
    def _on_state(self, state: AppState, mode: Mode | None) -> None:
        fb = self.config.feedback
        if state is AppState.IDLE and self._triggers_dirty and not self._quitting:
            # Riavvio rimandato: fermare un listener mentre il pulsante è premuto perderebbe il rilascio.
            self._restart_triggers()
        if fb.tray:
            self.tray.set_state(state, mode)
        if fb.overlay:
            self.overlay.show_state(state, mode)
        name = SOUND_FOR_STATE.get(state)
        if name:
            try:
                self.sounds.play(name)
            except Exception:  # noqa: BLE001
                log.exception("Suono non riprodotto")

    @Slot(object)
    def _on_outcome(self, outcome: Outcome) -> None:
        if self.config.feedback.overlay:
            self.overlay.show_outcome(outcome)
        try:
            self.notifier.notify(outcome)
        except Exception:  # noqa: BLE001
            log.exception("Notifica non mostrata")

    def _notify(self, title: str, text: str, error: bool = False) -> None:
        # Gli avvisi di sistema (permessi, configurazione) si mostrano anche con le notifiche spente.
        enabled = self.notifier.enabled
        try:
            self.notifier.enabled = True
            self.notifier.show(title, text, error)
        except Exception:  # noqa: BLE001
            log.exception("Notifica non mostrata")
        finally:
            self.notifier.enabled = enabled

    # --- menu --------------------------------------------------------------

    @Slot()
    def open_config(self) -> None:
        try:
            open_in_editor(self.config_path)
        except Exception as e:  # noqa: BLE001
            log.exception("Impossibile aprire la configurazione")
            self._notify("Impossibile aprire la configurazione", str(e), True)

    def _add_open_log_action(self) -> QAction | None:
        """Aggiunge "Apri log" al menu del tray, subito dopo "Ricarica configurazione"."""
        menu = getattr(self.tray, "menu", None)
        if menu is None:
            return None
        action = QAction("Apri log", menu)
        action.triggered.connect(self.open_log)
        reload_action = getattr(self.tray, "reload_config_action", None)
        actions = menu.actions()
        if reload_action in actions and actions.index(reload_action) + 1 < len(actions):
            menu.insertAction(actions[actions.index(reload_action) + 1], action)
        else:
            menu.addAction(action)
        return action

    @Slot()
    def open_log(self) -> None:
        if not self.log_file.exists():
            self._notify("Log non disponibile", f"Il file {self.log_file} non esiste ancora.", True)
            return
        try:
            open_in_editor(self.log_file)  # su macOS si apre in Console
        except Exception as e:  # noqa: BLE001
            log.exception("Impossibile aprire il log")
            self._notify("Impossibile aprire il log", str(e), True)

    @Slot()
    def reload_config(self) -> None:
        """Voce di menu "Ricarica": rilegge il file anche se non è cambiato."""
        self._last_text = self._read_text()
        self._apply_file()

    def _apply_file(self) -> bool:
        """Applica il file se valido; altrimenti notifica e mantiene la configurazione in uso."""
        try:
            new = load_config(self.config_path)
        except ConfigError as e:
            log.error("%s", e)
            self._notify("Configurazione non valida", f"{e}\n\nResta in uso la configurazione precedente.", True)
            return False
        old, self.config = self.config, new
        self._apply_feedback_switches()
        if self.controller is not None:
            self.controller.reload(new)
            if trigger_maps(old) != trigger_maps(new):
                if self.controller.state is AppState.IDLE:
                    self._restart_triggers()
                else:
                    self._triggers_dirty = True
        text = "Le modifiche sono attive."
        later = restart_required(old, new)
        if later:
            text = f"Riavvia voicecmd per applicare: {', '.join(later)}."
        log.info("Configurazione ricaricata (%s)", text)
        self._notify("Configurazione ricaricata", text, bool(later))
        return True

    # --- osservazione del file -------------------------------------------------

    def _read_text(self) -> str | None:
        try:
            return self.config_path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _watch(self) -> None:
        """(Ri)aggancia file e cartella: dopo un rename il file nuovo non è più osservato."""
        files = set(self.watcher.files())
        dirs = set(self.watcher.directories())
        if str(self.config_path) not in files and self.config_path.exists():
            self.watcher.addPath(str(self.config_path))
        parent = self.config_path.parent
        if str(parent) not in dirs and parent.is_dir():
            self.watcher.addPath(str(parent))

    @Slot(str)
    def _on_file_event(self, _path: str) -> None:
        if not self._quitting:
            self._reload_timer.start()  # riparte a ogni evento: anti-rimbalzo

    @Slot()
    def _on_file_settled(self) -> None:
        self._watch()
        text = self._read_text()
        # File assente (salvataggio a metà) o contenuto identico (altri file della cartella,
        # salvataggio senza modifiche): niente da fare.
        if text is None or text == self._last_text:
            return
        self._last_text = text
        self._apply_file()

    @Slot()
    def quit(self) -> None:
        """Ferma trigger, controller (worker) e recorder in quest'ordine, poi chiude Qt."""
        self.shutdown()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def shutdown(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._reload_timer.stop()
        paths = self.watcher.files() + self.watcher.directories()
        if paths:
            self.watcher.removePaths(paths)
        self._stop_triggers()
        if self.controller is not None:
            self.controller.shutdown(wait=True)
        self._close_recorder(self.recorder)
        self.recorder = None
        try:
            self.overlay.hide()
            self.tray.hide()
        except Exception:  # noqa: BLE001
            log.exception("Errore nel chiudere l'interfaccia")

    @staticmethod
    def _close_recorder(recorder: Any) -> None:
        close = getattr(recorder, "close", None)
        if close is not None:
            try:
                close()
            except Exception:  # noqa: BLE001
                log.exception("Errore nel chiudere il microfono")


def _install_sigint(qapp: QApplication) -> QTimer:
    """Ctrl+C nel terminale chiude l'app. Il timer fa tornare il controllo a Python ogni
    200 ms, altrimenti il segnale resterebbe in coda finché Qt non esce dal suo loop."""
    signal.signal(signal.SIGINT, lambda *_: qapp.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)
    return timer


def main(argv: list[str] | None = None) -> int:
    log_file = setup_logging()
    log.info("Log su %s", log_file)
    qapp = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName("voicecmd")
    _sigint_timer = _install_sigint(qapp)  # noqa: F841 - va tenuto vivo
    app = VoiceCmdApp(log_file=log_file)
    try:
        return qapp.exec()
    finally:
        app.shutdown()
