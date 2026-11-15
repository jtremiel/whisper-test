"""Suoni brevi di feedback riprodotti con QSoundEffect."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

SOUNDS_DIR = Path(__file__).resolve().parent / "assets" / "sounds"

# Nomi dei suoni disponibili → file wav in assets/sounds/
SOUND_FILES: dict[str, str] = {
    "start": "start.wav",  # inizio ascolto
    "done": "done.wav",    # azione eseguita
    "error": "error.wav",  # errore o nessuna corrispondenza
}


def _qt_effect(path: Path) -> Any:
    """Crea un QSoundEffect per il file indicato (import di Qt solo qui)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QSoundEffect

    effect = QSoundEffect()
    effect.setSource(QUrl.fromLocalFile(str(path)))
    effect.setVolume(0.6)
    return effect


class Sounds:
    """Riproduce i suoni di feedback. Va usato dal main thread di Qt.

    `effect_factory(path)` crea l'oggetto con metodo `play()`; di default un
    `QSoundEffect`. Gli effetti si creano alla prima riproduzione e si riusano.
    """

    def __init__(
        self,
        enabled: bool = True,
        effect_factory: Callable[[Path], Any] | None = None,
        sounds_dir: Path = SOUNDS_DIR,
    ) -> None:
        self.enabled = enabled
        self._factory = effect_factory or _qt_effect
        self._dir = sounds_dir
        self._effects: dict[str, Any] = {}

    @staticmethod
    def names() -> list[str]:
        """Nomi dei suoni disponibili."""
        return list(SOUND_FILES)

    def play(self, name: str) -> None:
        """Riproduce il suono `name`; ValueError se il nome non esiste."""
        if name not in SOUND_FILES:
            raise ValueError(
                f"Suono sconosciuto: {name!r}. Suoni disponibili: {', '.join(SOUND_FILES)}"
            )
        if not self.enabled:
            return
        effect = self._effects.get(name)
        if effect is None:
            effect = self._factory(self._dir / SOUND_FILES[name])
            self._effects[name] = effect
        effect.play()
