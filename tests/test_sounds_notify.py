"""Test di voicecmd.ui.sounds e voicecmd.ui.notify con oggetti finti (nessun suono né notifica reali)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import wave
from pathlib import Path

import pytest

from voicecmd.events import Mode, Outcome
from voicecmd.ui.notify import Notifier
from voicecmd.ui.sounds import SOUND_FILES, SOUNDS_DIR, Sounds


class FakeEffect:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.plays = 0

    def play(self) -> None:
        self.plays += 1


class FakeFactory:
    def __init__(self) -> None:
        self.created: list[FakeEffect] = []

    def __call__(self, path: Path) -> FakeEffect:
        effect = FakeEffect(path)
        self.created.append(effect)
        return effect


class FakeTray:
    def __init__(self) -> None:
        self.messages: list[tuple] = []

    def showMessage(self, title, text, icon, ms) -> None:  # noqa: N802 (API Qt)
        self.messages.append((title, text, icon, ms))


# --- wav -------------------------------------------------------------------

@pytest.mark.parametrize("name", ["start", "done", "error"])
def test_wav_exists_and_is_short(name: str) -> None:
    path = SOUNDS_DIR / SOUND_FILES[name]
    assert path.is_file()
    with wave.open(str(path), "rb") as w:
        duration = w.getnframes() / w.getframerate()
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
    assert 0 < duration < 0.3


# --- Sounds ----------------------------------------------------------------

def test_play_uses_right_file_and_reuses_effect() -> None:
    factory = FakeFactory()
    sounds = Sounds(effect_factory=factory)
    sounds.play("done")
    sounds.play("done")
    assert len(factory.created) == 1
    assert factory.created[0].path == SOUNDS_DIR / "done.wav"
    assert factory.created[0].plays == 2


def test_unknown_name_raises_clear_error() -> None:
    sounds = Sounds(effect_factory=FakeFactory())
    with pytest.raises(ValueError, match="Suono sconosciuto: 'boh'.*start, done, error"):
        sounds.play("boh")


def test_unknown_name_raises_even_when_disabled() -> None:
    sounds = Sounds(enabled=False, effect_factory=FakeFactory())
    with pytest.raises(ValueError):
        sounds.play("boh")


def test_disabled_plays_nothing() -> None:
    factory = FakeFactory()
    sounds = Sounds(enabled=False, effect_factory=factory)
    for name in Sounds.names():
        sounds.play(name)
    assert factory.created == []


def test_enabled_can_be_toggled() -> None:
    factory = FakeFactory()
    sounds = Sounds(effect_factory=factory)
    sounds.enabled = False
    sounds.play("start")
    assert factory.created == []
    sounds.enabled = True
    sounds.play("start")
    assert factory.created[0].plays == 1


def test_default_factory_builds_qsoundeffect(qapp) -> None:
    # Crea il QSoundEffect vero senza riprodurlo.
    from PySide6.QtMultimedia import QSoundEffect

    from voicecmd.ui.sounds import _qt_effect

    effect = _qt_effect(SOUNDS_DIR / "start.wav")
    assert isinstance(effect, QSoundEffect)
    assert effect.source().toLocalFile().endswith("start.wav")


# --- Notifier --------------------------------------------------------------

def _outcome(ok: bool = True, heard: str = "apri il browser", detail: str = "") -> Outcome:
    return Outcome(mode=Mode.COMMAND, ok=ok, heard=heard, title="Apri browser", detail=detail)


def test_notify_uses_title_and_text_from_outcome() -> None:
    from PySide6.QtWidgets import QSystemTrayIcon

    tray = FakeTray()
    Notifier(tray).notify(_outcome(detail="Aperto https://www.google.com"))
    assert len(tray.messages) == 1
    title, text, icon, ms = tray.messages[0]
    assert title == "Apri browser"
    assert "apri il browser" in text
    assert "Aperto https://www.google.com" in text
    assert icon == QSystemTrayIcon.MessageIcon.Information
    assert ms > 0


def test_notify_error_uses_warning_icon() -> None:
    from PySide6.QtWidgets import QSystemTrayIcon

    tray = FakeTray()
    Notifier(tray).notify(_outcome(ok=False, heard="", detail="Comando più vicino: Apri browser"))
    title, text, icon, _ = tray.messages[0]
    assert text == "Comando più vicino: Apri browser"
    assert icon == QSystemTrayIcon.MessageIcon.Warning


def test_notify_disabled_shows_nothing() -> None:
    tray = FakeTray()
    notifier = Notifier(tray, enabled=False)
    notifier.notify(_outcome())
    notifier.show("Configurazione ricaricata", "")
    assert tray.messages == []


def test_show_free_message() -> None:
    tray = FakeTray()
    Notifier(tray).show("Configurazione ricaricata", "3 comandi")
    assert tray.messages[0][:2] == ("Configurazione ricaricata", "3 comandi")


def test_notifier_with_real_tray_icon(qapp, monkeypatch) -> None:
    # QSystemTrayIcon vero, ma showMessage intercettato: nessuna notifica reale.
    from PySide6.QtWidgets import QSystemTrayIcon

    icon = QSystemTrayIcon()
    calls: list[tuple] = []
    monkeypatch.setattr(icon, "showMessage", lambda *a: calls.append(a))
    Notifier(icon).notify(_outcome())
    assert calls and calls[0][0] == "Apri browser"
