"""Icona nella menu bar / system tray con il menu dell'app."""
from __future__ import annotations

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from voicecmd.events import AppState, Mode

ICON_SIZE = 64  # lato in pixel del disegno; Qt lo ridimensiona per la menu bar

# Un colore per stato (riempimento del cerchio)
STATE_COLORS: dict[AppState, str] = {
    AppState.IDLE: "#8e8e93",        # grigio
    AppState.LISTENING: "#ff9500",   # arancione
    AppState.PROCESSING: "#007aff",  # blu
    AppState.DONE: "#34c759",        # verde
    AppState.ERROR: "#ff3b30",       # rosso
}

STATE_LABELS: dict[AppState, str] = {
    AppState.IDLE: "Inattivo",
    AppState.LISTENING: "In ascolto",
    AppState.PROCESSING: "Elaborazione",
    AppState.DONE: "Eseguito",
    AppState.ERROR: "Errore",
}

MODE_LABELS: dict[Mode, str] = {
    Mode.COMMAND: "comando",
    Mode.DICTATION: "dettatura",
}

APP_NAME = "voicecmd"


def state_text(state: AppState, mode: Mode | None) -> str:
    """Testo dello stato mostrato nel tooltip e nel menu, es. "In ascolto (dettatura)"."""
    label = STATE_LABELS[state]
    if mode is not None and state is not AppState.IDLE:
        label = f"{label} ({MODE_LABELS[mode]})"
    return label


def make_state_pixmap(state: AppState, size: int = ICON_SIZE) -> QPixmap:
    """Disegna l'icona di uno stato: cerchio pieno del colore dello stato con bordo scuro."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen_width = max(2.0, size / 16)
        painter.setPen(QPen(QColor("#1c1c1e"), pen_width))
        painter.setBrush(QColor(STATE_COLORS[state]))
        margin = pen_width
        painter.drawEllipse(QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    finally:
        painter.end()
    return pixmap


class Tray(QObject):
    """Icona tray a stati con menu: stato, Apri configurazione, Ricarica configurazione, Esci.

    Va creata e usata solo sul main thread di Qt (serve una QApplication già esistente).
    """

    open_config_requested = Signal()
    reload_config_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Icone disegnate una volta sola
        self._icons: dict[AppState, QIcon] = {s: QIcon(make_state_pixmap(s)) for s in AppState}

        self._menu = QMenu()
        self._status_action = QAction("", self._menu)
        self._status_action.setEnabled(False)
        self._menu.addAction(self._status_action)
        self._menu.addSeparator()

        self.open_config_action = QAction("Apri configurazione", self._menu)
        self.open_config_action.triggered.connect(self.open_config_requested)
        self._menu.addAction(self.open_config_action)

        self.reload_config_action = QAction("Ricarica configurazione", self._menu)
        self.reload_config_action.triggered.connect(self.reload_config_requested)
        self._menu.addAction(self.reload_config_action)

        self._menu.addSeparator()
        self.quit_action = QAction("Esci", self._menu)
        self.quit_action.triggered.connect(self.quit_requested)
        self._menu.addAction(self.quit_action)

        self._icon = QSystemTrayIcon(self)
        self._icon.setContextMenu(self._menu)

        self._state = AppState.IDLE
        self._mode: Mode | None = None
        self.set_state(AppState.IDLE, None)

    @property
    def tray_icon(self) -> QSystemTrayIcon:
        """L'oggetto `QSystemTrayIcon`, da passare al `Notifier` per le notifiche."""
        return self._icon

    @property
    def menu(self) -> QMenu:
        """Il menu contestuale; chi integra può aggiungere voci (es. "Apri log")."""
        return self._menu

    @property
    def state(self) -> AppState:
        return self._state

    @property
    def mode(self) -> Mode | None:
        return self._mode

    def icon_for(self, state: AppState) -> QIcon:
        """Icona usata per `state`."""
        return self._icons[state]

    def status_text(self) -> str:
        """Testo attuale della voce di stato nel menu."""
        return self._status_action.text()

    def set_state(self, state: AppState, mode: Mode | None) -> None:
        """Aggiorna icona, tooltip e voce di stato del menu."""
        self._state = state
        self._mode = mode
        self._icon.setIcon(self._icons[state])
        self._set_text(state_text(state, mode))

    def set_status_text(self, text: str) -> None:
        """Mostra un testo di stato libero (es. "Caricamento del modello…") senza cambiare icona."""
        self._set_text(text)

    def _set_text(self, text: str) -> None:
        self._status_action.setText(text)
        self._icon.setToolTip(f"{APP_NAME}: {text}")

    def show(self) -> None:
        """Mostra l'icona nella menu bar / tray."""
        self._icon.show()

    def hide(self) -> None:
        """Nasconde l'icona (da chiamare prima di uscire)."""
        self._icon.hide()
