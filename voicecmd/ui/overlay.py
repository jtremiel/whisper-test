"""Overlay a schermo: piccolo riquadro in basso al centro con stato ed esito del ciclo.

La finestra non ha bordi, resta sopra le altre, non prende il focus e lascia passare
i clic. Va usata solo dal main thread di Qt: `app.py` ci arriva tramite segnali.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from voicecmd.events import AppState, Mode, Outcome

DONE_HIDE_MS = 2000    # l'esito positivo resta visibile circa 2 s
ERROR_HIDE_MS = 4000   # gli errori restano di più, per leggere il testo sentito
BOTTOM_MARGIN_PX = 80  # distanza dal bordo inferiore dell'area utile dello schermo

STATE_TEXT: dict[AppState, str] = {
    AppState.LISTENING: "In ascolto…",
    AppState.PROCESSING: "Elaborazione…",
}

MODE_TEXT: dict[Mode, str] = {
    Mode.COMMAND: "Comando",
    Mode.DICTATION: "Dettatura",
}

WINDOW_FLAGS = (
    Qt.WindowType.Tool
    | Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.WindowDoesNotAcceptFocus
    | Qt.WindowType.WindowTransparentForInput  # i clic passano alla finestra sotto
)

_STYLE = """
#overlay-box {
    background-color: rgba(30, 30, 30, 220);
    border-radius: 12px;
}
QLabel { color: white; }
#overlay-title { font-size: 16px; font-weight: bold; }
#overlay-box[status="ok"] #overlay-title { color: #7ee787; }
#overlay-box[status="error"] #overlay-title { color: #ff7b72; }
#overlay-sub { font-size: 12px; color: #c9d1d9; }
#overlay-heard { font-size: 13px; font-style: italic; }
"""


class Overlay(QWidget):
    """Riquadro di feedback che non ruba il focus all'app in primo piano."""

    def __init__(self, done_ms: int = DONE_HIDE_MS, error_ms: int = ERROR_HIDE_MS) -> None:
        super().__init__(None, WINDOW_FLAGS)
        self.done_ms = done_ms
        self.error_ms = error_ms

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Su macOS una finestra Tool si nasconde quando l'app non è attiva,
        # e un'app da menu bar non lo è quasi mai.
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._box = QWidget(self)
        self._box.setObjectName("overlay-box")
        self.title_label = QLabel(self._box)
        self.title_label.setObjectName("overlay-title")
        self.sub_label = QLabel(self._box)
        self.sub_label.setObjectName("overlay-sub")
        self.heard_label = QLabel(self._box)
        self.heard_label.setObjectName("overlay-heard")
        self.heard_label.setWordWrap(True)
        for label in (self.title_label, self.sub_label, self.heard_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        inner = QVBoxLayout(self._box)
        inner.setContentsMargins(20, 12, 20, 12)
        inner.setSpacing(4)
        inner.addWidget(self.title_label)
        inner.addWidget(self.sub_label)
        inner.addWidget(self.heard_label)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._box)
        self.setStyleSheet(_STYLE)
        self.setMinimumWidth(240)
        self.setMaximumWidth(520)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    # --- API pubblica -------------------------------------------------------

    def show_state(self, state: AppState, mode: Mode | None) -> None:
        """Mostra lo stato in corso; in IDLE nasconde. DONE ed ERROR arrivano da `show_outcome`."""
        if state == AppState.IDLE:
            self.hide_timer.stop()
            self.hide()
            return
        text = STATE_TEXT.get(state)
        if text is None:
            return
        self.hide_timer.stop()
        self._set_status("busy")
        self._set_texts(text, MODE_TEXT.get(mode, "") if mode else "", "")
        self._present()

    def show_outcome(self, outcome: Outcome) -> None:
        """Mostra l'esito e il testo sentito, poi si nasconde da sola."""
        prefix = "Eseguito" if outcome.ok else "Errore"
        title = f"{prefix}: {outcome.title}" if outcome.title else prefix
        heard = f"«{outcome.heard}»" if outcome.heard else ""
        self._set_status("ok" if outcome.ok else "error")
        self._set_texts(title, outcome.detail, heard)
        self._present()
        self.hide_timer.start(self.done_ms if outcome.ok else self.error_ms)

    # --- interni ------------------------------------------------------------

    def _set_texts(self, title: str, sub: str, heard: str) -> None:
        self.title_label.setText(title)
        self.sub_label.setText(sub)
        self.sub_label.setVisible(bool(sub))
        self.heard_label.setText(heard)
        self.heard_label.setVisible(bool(heard))

    def _set_status(self, status: str) -> None:
        self._box.setProperty("status", status)
        # Riapplica lo stile perché il selettore [status=...] venga rivalutato
        self._box.style().unpolish(self._box)
        self._box.style().polish(self._box)

    def _present(self) -> None:
        self.adjustSize()
        self.move(self._target_pos())
        if not self.isVisible():
            self.show()  # con WA_ShowWithoutActivating non attiva la finestra
        self.raise_()

    def _target_pos(self) -> QPoint:
        """In basso al centro dello schermo in cui si trova il cursore."""
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return QPoint(0, 0)
        area = screen.availableGeometry()
        x = area.x() + (area.width() - self.width()) // 2
        y = area.y() + area.height() - self.height() - BOTTOM_MARGIN_PX
        return QPoint(x, max(area.y(), y))
