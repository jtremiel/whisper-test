"""Test dell'overlay a schermo (pytest-qt, piattaforma offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication

from voicecmd.events import AppState, Mode, Outcome
from voicecmd.ui import overlay as overlay_mod
from voicecmd.ui.overlay import Overlay


@pytest.fixture
def overlay(qtbot):
    w = Overlay(done_ms=50, error_ms=100)
    qtbot.addWidget(w)  # chiusa e distrutta a fine test
    yield w
    w.hide_timer.stop()
    w.hide()


def test_window_flags(overlay):
    flags = overlay.windowFlags()
    for f in (
        Qt.WindowType.Tool,
        Qt.WindowType.FramelessWindowHint,
        Qt.WindowType.WindowStaysOnTopHint,
        Qt.WindowType.WindowDoesNotAcceptFocus,
        Qt.WindowType.WindowTransparentForInput,
    ):
        assert flags & f == f, f
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
    assert overlay.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_default_hide_durations():
    assert overlay_mod.DONE_HIDE_MS == 2000
    assert overlay_mod.ERROR_HIDE_MS == 4000


@pytest.mark.parametrize(
    "state, text", [(AppState.LISTENING, "In ascolto…"), (AppState.PROCESSING, "Elaborazione…")]
)
@pytest.mark.parametrize("mode, mode_text", [(Mode.COMMAND, "Comando"), (Mode.DICTATION, "Dettatura")])
def test_state_texts(overlay, state, text, mode, mode_text):
    overlay.show_state(state, mode)
    assert overlay.isVisible()
    assert overlay.title_label.text() == text
    assert overlay.sub_label.text() == mode_text
    assert overlay.heard_label.text() == ""
    assert not overlay.hide_timer.isActive()


def test_idle_hides(overlay):
    overlay.show_state(AppState.LISTENING, Mode.COMMAND)
    overlay.show_state(AppState.IDLE, None)
    assert not overlay.isVisible()


def test_done_and_error_states_are_ignored(overlay):
    # l'esito arriva da show_outcome: on_state(DONE/ERROR) non deve cambiare nulla
    overlay.show_state(AppState.DONE, Mode.COMMAND)
    overlay.show_state(AppState.ERROR, Mode.COMMAND)
    assert not overlay.isVisible()


def test_outcome_ok_texts_and_timer(overlay, qtbot):
    overlay.show_outcome(Outcome(Mode.COMMAND, True, "apri il browser", "Apri browser", ""))
    assert overlay.isVisible()
    assert overlay.title_label.text() == "Eseguito: Apri browser"
    assert overlay.heard_label.text() == "«apri il browser»"
    assert overlay.sub_label.isHidden()
    assert overlay.hide_timer.isActive()
    assert overlay.hide_timer.interval() == 50
    qtbot.waitUntil(lambda: not overlay.isVisible(), timeout=1000)


def test_outcome_error_texts_and_timer(overlay):
    overlay.show_outcome(
        Outcome(Mode.COMMAND, False, "apri il bowser", "Nessuna corrispondenza",
                "Più vicino: Apri browser (72)")
    )
    assert overlay.title_label.text() == "Errore: Nessuna corrispondenza"
    assert overlay.sub_label.text() == "Più vicino: Apri browser (72)"
    assert overlay.heard_label.text() == "«apri il bowser»"
    assert overlay.hide_timer.interval() == 100
    # timer simulato: lo scatto nasconde l'overlay
    overlay.hide_timer.timeout.emit()
    assert not overlay.isVisible()


def test_outcome_without_title_or_heard(overlay):
    overlay.show_outcome(Outcome(Mode.DICTATION, False, "", "", ""))
    assert overlay.title_label.text() == "Errore"
    assert overlay.heard_label.isHidden()


def test_new_state_cancels_pending_hide(overlay):
    overlay.show_outcome(Outcome(Mode.COMMAND, True, "x", "X", ""))
    assert overlay.hide_timer.isActive()
    overlay.show_state(AppState.LISTENING, Mode.DICTATION)
    assert not overlay.hide_timer.isActive()
    assert overlay.isVisible()


def test_production_durations_used_by_default(qtbot):
    w = Overlay()
    qtbot.addWidget(w)
    w.show_outcome(Outcome(Mode.COMMAND, True, "", "ok", ""))
    assert w.hide_timer.interval() == 2000
    w.show_outcome(Outcome(Mode.COMMAND, False, "", "ko", ""))
    assert w.hide_timer.interval() == 4000
    w.hide_timer.stop()
    w.hide()


def test_position_bottom_center_of_cursor_screen(overlay, monkeypatch):
    screen = QGuiApplication.primaryScreen()
    area = screen.availableGeometry()
    monkeypatch.setattr(overlay_mod.QCursor, "pos", staticmethod(lambda: area.center()))
    overlay.show_state(AppState.LISTENING, Mode.COMMAND)
    pos = overlay.pos()
    assert abs((pos.x() + overlay.width() / 2) - (area.x() + area.width() / 2)) <= 1
    assert pos.y() + overlay.height() == area.y() + area.height() - overlay_mod.BOTTOM_MARGIN_PX


def test_position_falls_back_to_primary_screen(overlay, monkeypatch):
    monkeypatch.setattr(overlay_mod.QCursor, "pos", staticmethod(lambda: QPoint(-99999, -99999)))
    overlay.show_state(AppState.PROCESSING, Mode.COMMAND)
    area = QGuiApplication.primaryScreen().availableGeometry()
    assert area.contains(overlay.pos())
