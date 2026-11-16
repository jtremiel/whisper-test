"""Macchina a stati di voicecmd: trigger -> registrazione -> trascrizione -> azione -> esito.

Nessun import di Qt: le dipendenze arrivano come oggetti che rispettano i Protocol di
`events.py`. `on_trigger` viene chiamato dai thread dei listener (pynput, event tap
Quartz) e deve tornare subito: trascrizione e azioni girano su un solo worker thread.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Protocol

from voicecmd.events import (
    MAX_COMMAND_S,
    MAX_DICTATION_S,
    MIN_PRESS_S,
    SAMPLE_RATE,
    ActionResult,
    Action,
    AppState,
    Feedback,
    Mode,
    Outcome,
    Recorder,
    Transcriber,
)
from voicecmd.matcher import match
from voicecmd.schema import Config

log = logging.getLogger(__name__)

PasteFn = Callable[[str], ActionResult]
# Esegue una funzione sul worker thread. Default: ThreadPoolExecutor a un solo thread.
SubmitFn = Callable[[Callable[[], None]], Any]

MAX_DURATION_S = {Mode.COMMAND: MAX_COMMAND_S, Mode.DICTATION: MAX_DICTATION_S}
MODE_LABEL = {Mode.COMMAND: "comando", Mode.DICTATION: "dettatura"}


def cycle_summary(mode: Mode, info: Mapping[str, Any], outcome: Outcome) -> str:
    """Una riga per ciclo: modalità, durata audio, tempo di trascrizione, testo, comando, esito."""
    parts = [f"Ciclo {MODE_LABEL[mode]}"]
    audio_s = info.get("audio_s")
    parts.append(f"audio {audio_s:.2f} s" if audio_s is not None else "audio -")
    stt_s = info.get("stt_s")
    parts.append(f"trascrizione {stt_s:.2f} s" if stt_s is not None else "trascrizione -")
    parts.append(f"testo {info['text']!r}" if "text" in info else "testo -")
    if mode is Mode.COMMAND:
        if info.get("command"):
            parts.append(f"comando {info['command']} ({info['score']:.0f}/100)")
        elif info.get("closest"):
            parts.append(f"comando nessuno (più vicino {info['closest']} {info['closest_score']:.0f}/100)")
        else:
            parts.append("comando nessuno")
    result = "ok" if outcome.ok else "errore"
    detail = f" - {outcome.detail}" if outcome.detail else ""
    parts.append(f"esito {result}: {outcome.title}{detail}")
    return ", ".join(parts)


class Timer(Protocol):
    def start(self) -> None: ...
    def cancel(self) -> None: ...


TimerFactory = Callable[[float, Callable[[], None]], Timer]


def _thread_timer(delay: float, fn: Callable[[], None]) -> Timer:
    t = threading.Timer(delay, fn)
    t.daemon = True
    return t


def hotwords_for(config: Config) -> list[str]:
    """Parole distinte delle frasi dei comandi, nell'ordine in cui compaiono."""
    seen: dict[str, None] = {}
    for cmd in config.commands:
        for phrase in cmd.phrases:
            for w in phrase.split():
                seen.setdefault(w, None)
    return list(seen)


class Controller:
    """Coordina un ciclo alla volta. Thread-safe rispetto a `on_trigger` e `reload`."""

    def __init__(
        self,
        config: Config,
        recorder: Recorder,
        transcriber: Transcriber,
        actions: Mapping[str, Action],
        feedback: Feedback,
        paste: PasteFn,
        *,
        clock: Callable[[], float] = time.monotonic,
        submit: SubmitFn | None = None,
        timer_factory: TimerFactory = _thread_timer,
        use_hotwords: bool | None = None,
        perf_clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        # use_hotwords: None = segue `stt.hotwords` della config in uso (cambiabile a caldo);
        # True/False lo forza (test). Solo in modalità comando: vedi `SttConfig.hotwords`.
        self._config = config
        self._pending_config: Config | None = None
        self._recorder = recorder
        self._transcriber = transcriber
        self._actions = dict(actions)  # chiave = `type` dell'azione ("open", "shell")
        self._feedback = feedback
        self._paste = paste
        self._clock = clock
        self._perf_clock = perf_clock  # solo per misurare la trascrizione nel log
        self._timer_factory = timer_factory
        self._use_hotwords = use_hotwords
        self._executor: ThreadPoolExecutor | None = None
        if submit is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voicecmd-worker")
            submit = self._executor.submit
        self._submit = submit

        self._lock = threading.Lock()
        self._state = AppState.IDLE
        self._mode: Mode | None = None
        self._t_start = 0.0
        self._timer: Timer | None = None
        self._closed = False

    # --- stato ------------------------------------------------------------

    @property
    def state(self) -> AppState:
        return self._state

    @property
    def config(self) -> Config:
        return self._config

    # --- ingressi ---------------------------------------------------------

    def on_trigger(self, mode: Mode, pressed: bool) -> None:
        """Pressione o rilascio di un trigger (chiamato dai thread dei listener)."""
        if pressed:
            self._on_press(mode)
        else:
            self._on_release(mode, capped=False)

    def reload(self, config: Config) -> None:
        """Sostituisce la configurazione; se un ciclo è in corso la applica al ritorno in IDLE."""
        with self._lock:
            if self._state is AppState.IDLE:
                self._config = config
                self._pending_config = None
            else:
                self._pending_config = config

    def shutdown(self, wait: bool = True) -> None:
        """Annulla il timer e ferma il worker. Il recorder lo chiude chi lo ha creato."""
        with self._lock:
            self._closed = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if self._executor is not None:
            self._executor.shutdown(wait=wait, cancel_futures=True)

    # --- transizioni ------------------------------------------------------

    def _on_press(self, mode: Mode) -> None:
        with self._lock:
            if self._closed or self._state is not AppState.IDLE:
                return  # trigger durante ascolto/elaborazione: ignorato (RF1)
            try:
                self._recorder.start()
            except Exception as e:  # noqa: BLE001
                log.exception("Impossibile avviare la registrazione")
                failed = Outcome(mode, False, "", "Microfono non disponibile", str(e))
            else:
                failed = None
                self._state = AppState.LISTENING
                self._mode = mode
                self._t_start = self._clock()
                self._timer = self._timer_factory(
                    MAX_DURATION_S[mode], lambda: self._on_release(mode, capped=True)
                )
                self._timer.start()
        if failed is not None:
            self._emit_outcome(failed)
            self._emit_state(AppState.IDLE, None)
            return
        self._emit_state(AppState.LISTENING, mode)

    def _on_release(self, mode: Mode, capped: bool) -> None:
        with self._lock:
            if self._state is not AppState.LISTENING or self._mode is not mode:
                return  # rilascio senza pressione vista, o di un'altra modalità
            if self._timer is not None and not capped:
                self._timer.cancel()
            self._timer = None
            duration = self._clock() - self._t_start
            short = duration < MIN_PRESS_S
            # Anche per la pressione breve si resta fuori da IDLE finché non è notificato.
            self._state = AppState.PROCESSING
            config = self._config
        if short:
            try:
                self._recorder.stop()  # audio scartato
            except Exception:  # noqa: BLE001
                log.exception("Errore nel fermare la registrazione")
            log.info("Pressione troppo breve (%.2f s): ignorata", duration)
            self._go_idle()
            return
        if capped:
            log.info("Tetto di durata raggiunto (%s s): chiudo l'ascolto", MAX_DURATION_S[mode])
        self._emit_state(AppState.PROCESSING, mode)
        try:
            self._submit(lambda: self._process(mode, config))
        except Exception as e:  # noqa: BLE001 - executor chiuso
            log.exception("Impossibile avviare l'elaborazione")
            self._finish(Outcome(mode, False, "", "Errore", str(e)))

    # --- elaborazione (worker thread) -------------------------------------

    def _process(self, mode: Mode, config: Config) -> None:
        info: dict[str, Any] = {}
        try:
            outcome = self._run_cycle(mode, config, info)
        except Exception as e:  # noqa: BLE001
            log.exception("Errore durante l'elaborazione")
            outcome = Outcome(mode, False, info.get("text", ""), "Errore", f"{type(e).__name__}: {e}")
        try:
            log.info("%s", cycle_summary(mode, info, outcome))
        except Exception:  # noqa: BLE001 - il log non deve fermare il ciclo
            log.exception("Riepilogo del ciclo non scritto")
        self._finish(outcome)

    def _run_cycle(self, mode: Mode, config: Config, info: dict[str, Any]) -> Outcome:
        audio = self._recorder.stop()
        if audio is None or len(audio) == 0:
            info["audio_s"] = 0.0
            return Outcome(mode, False, "", "Non ho sentito niente", "")
        info["audio_s"] = len(audio) / SAMPLE_RATE
        hotwords = None
        use = config.stt.hotwords if self._use_hotwords is None else self._use_hotwords
        if mode is Mode.COMMAND and use:
            hotwords = hotwords_for(config) or None
        t0 = self._perf_clock()
        text = self._transcriber.transcribe(audio, hotwords=hotwords).strip()
        info["stt_s"] = self._perf_clock() - t0
        info["text"] = text
        if not text:
            return Outcome(mode, False, "", "Non ho sentito niente", "")
        if mode is Mode.DICTATION:
            res = self._paste(text)
            title = "Testo incollato" if res.ok else "Dettatura non riuscita"
            return Outcome(mode, res.ok, text, title, res.message)
        m = match(text, config.commands, config.matching.threshold, config.matching.margin)
        info.update(command=m.command.name if m.command else None, score=m.score,
                    closest=m.closest, closest_score=m.closest_score)
        if m.command is None:
            detail = (
                f"Il più vicino: {m.closest} ({m.closest_score:.0f}/100)"
                if m.closest is not None else "Nessun comando configurato"
            )
            return Outcome(mode, False, text, "Nessun comando riconosciuto", detail)
        action = self._actions.get(m.command.action.type)
        if action is None:
            return Outcome(mode, False, text, m.command.name,
                           f"Azione '{m.command.action.type}' non disponibile")
        res = action.run(m.command.action)
        return Outcome(mode, res.ok, text, m.command.name, res.message)

    def _finish(self, outcome: Outcome) -> None:
        final = AppState.DONE if outcome.ok else AppState.ERROR
        self._emit_state(final, outcome.mode)
        self._emit_outcome(outcome)
        self._go_idle()

    def _go_idle(self) -> None:
        """Notifica IDLE e solo dopo accetta nuove pressioni, così la UI non riceve stati fuori ordine."""
        self._emit_state(AppState.IDLE, None)
        with self._lock:
            if self._pending_config is not None:
                self._config = self._pending_config
                self._pending_config = None
            self._state = AppState.IDLE
            self._mode = None

    # --- feedback (mai fatale) --------------------------------------------

    def _emit_state(self, state: AppState, mode: Mode | None) -> None:
        try:
            self._feedback.on_state(state, mode)
        except Exception:  # noqa: BLE001
            log.exception("Errore nel feedback (stato %s)", state)

    def _emit_outcome(self, outcome: Outcome) -> None:
        try:
            self._feedback.on_outcome(outcome)
        except Exception:  # noqa: BLE001
            log.exception("Errore nel feedback (esito)")
