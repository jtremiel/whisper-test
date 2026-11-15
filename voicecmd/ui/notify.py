"""Notifiche di sistema tramite QSystemTrayIcon.showMessage."""
from __future__ import annotations

from typing import Any

from voicecmd.events import Outcome

NOTIFY_MS = 4000  # durata della notifica (ms); il sistema può ignorarla


def outcome_text(outcome: Outcome) -> str:
    """Corpo della notifica: testo sentito e dettaglio, se presenti."""
    lines = []
    if outcome.heard:
        lines.append(f"Ho sentito: «{outcome.heard}»")
    if outcome.detail:
        lines.append(outcome.detail)
    return "\n".join(lines)


class Notifier:
    """Mostra l'esito di un ciclo come notifica del tray. Va usato dal main thread di Qt."""

    def __init__(self, tray_icon: Any, enabled: bool = True) -> None:
        self._tray = tray_icon  # QSystemTrayIcon (o un oggetto con showMessage)
        self.enabled = enabled

    def notify(self, outcome: Outcome) -> None:
        """Mostra titolo e testo presi da `outcome`; niente se disattivato."""
        if not self.enabled:
            return
        self.show(outcome.title, outcome_text(outcome), error=not outcome.ok)

    def show(self, title: str, text: str, error: bool = False) -> None:
        """Notifica libera (es. "Configurazione ricaricata"); niente se disattivato."""
        if not self.enabled:
            return
        from PySide6.QtWidgets import QSystemTrayIcon

        icon = (
            QSystemTrayIcon.MessageIcon.Warning
            if error
            else QSystemTrayIcon.MessageIcon.Information
        )
        self._tray.showMessage(title, text, icon, NOTIFY_MS)
