"""Contratti tra i moduli di voicecmd: solo tipi, nessuna logica."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np

    from voicecmd.schema import Command, OpenAction, ShellAction

SAMPLE_RATE = 16000   # Hz, frequenza dell'audio registrato e passato a Whisper
MIN_PRESS_S = 0.3     # pressioni più brevi di così vengono ignorate
MAX_COMMAND_S = 30    # durata massima di una registrazione in modalità comando
MAX_DICTATION_S = 120  # durata massima di una registrazione in modalità dettatura


class AppState(Enum):
    """Stato del ciclo dell'app."""
    IDLE = "idle"              # in attesa del trigger
    LISTENING = "listening"    # trigger premuto, si registra
    PROCESSING = "processing"  # trascrizione e azione in corso
    DONE = "done"              # ciclo concluso con successo
    ERROR = "error"            # ciclo concluso con un errore


class Mode(Enum):
    """Quale trigger ha avviato il ciclo."""
    COMMAND = "command"      # esegue il comando più simile alla frase
    DICTATION = "dictation"  # incolla il testo dettato


@dataclass(frozen=True)
class ActionResult:
    """Esito di un'azione."""
    ok: bool       # True se l'azione è riuscita
    message: str   # dettaglio leggibile dall'utente (errore o conferma)


@dataclass(frozen=True)
class MatchResult:
    """Esito del matching tra la frase sentita e i comandi configurati."""
    command: Command | None  # comando scelto (voce di `commands` della config); None se nessuna corrispondenza
    score: float         # punteggio 0-100 del comando scelto; 0.0 se command è None
    heard: str           # testo trascritto, così come arriva dal matcher
    closest: str | None  # nome del comando più vicino anche se sotto soglia o ambiguo; None se non ci sono comandi
    closest_score: float  # punteggio 0-100 di `closest`; 0.0 se closest è None


@dataclass(frozen=True)
class Outcome:
    """Ciò che il feedback mostra a fine ciclo."""
    mode: Mode    # modalità del ciclo concluso
    ok: bool      # True se il ciclo è riuscito
    heard: str    # testo trascritto (può essere vuoto)
    title: str    # riga breve, es. nome del comando eseguito o motivo del fallimento
    detail: str   # spiegazione più lunga; può essere vuota


@runtime_checkable
class Trigger(Protocol):
    """Sorgente di pressione/rilascio (tastiera o mouse)."""

    def start(self, on_event: Callable[[Mode, bool], None]) -> None:
        """Avvia l'ascolto; `on_event(mode, pressed)` con pressed=True alla pressione, False al rilascio."""
        ...

    def stop(self) -> None:
        """Ferma l'ascolto."""
        ...


@runtime_checkable
class Recorder(Protocol):
    """Cattura audio dal microfono."""

    def start(self) -> None:
        """Inizia a registrare."""
        ...

    def stop(self) -> np.ndarray:
        """Termina e restituisce l'audio float32 mono a 16 kHz; array vuoto se silenzio."""
        ...


@runtime_checkable
class Transcriber(Protocol):
    """Trascrive audio in testo."""

    def transcribe(self, audio: np.ndarray, hotwords: list[str] | None = None) -> str:
        """Restituisce il testo; `hotwords` suggerisce parole da favorire. Stringa vuota se non c'è parlato."""
        ...


@runtime_checkable
class Action(Protocol):
    """Azione eseguibile associata a un comando."""

    def run(self, spec: OpenAction | ShellAction) -> ActionResult:
        """Esegue l'azione; `spec` è il modello `action` del comando nella config (open, shell). Non solleva."""
        ...


@runtime_checkable
class Feedback(Protocol):
    """Destinazione del feedback verso l'utente (overlay, suoni, notifiche)."""

    def on_state(self, state: AppState, mode: Mode | None) -> None:
        """Il ciclo è passato a `state`; `mode` è None in IDLE."""
        ...

    def on_outcome(self, outcome: Outcome) -> None:
        """Il ciclo è concluso con questo esito."""
        ...
