"""Test dell'icona tray e del menu."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QSystemTrayIcon  # noqa: E402

from voicecmd.events import AppState, Mode  # noqa: E402
from voicecmd.ui.tray import Tray, make_state_pixmap, state_text  # noqa: E402


@pytest.fixture
def tray(qapp):
    t = Tray()
    yield t
    t.hide()
    t.deleteLater()


def _image(tray: Tray, state: AppState) -> QImage:
    return tray.icon_for(state).pixmap(32, 32).toImage().convertToFormat(QImage.Format.Format_ARGB32)


def test_ogni_stato_ha_icona_distinta(tray):
    images = [_image(tray, s) for s in AppState]
    for img in images:
        assert not img.isNull()
    for i in range(len(images)):
        for j in range(i + 1, len(images)):
            assert images[i] != images[j]


def test_pixmap_non_vuota(qapp):
    pm = make_state_pixmap(AppState.LISTENING, 32)
    img = pm.toImage()
    assert img.pixelColor(16, 16).alpha() == 255   # centro pieno
    assert img.pixelColor(0, 0).alpha() == 0       # angolo trasparente


def test_set_state_cambia_icona_e_tooltip(tray):
    assert tray.state is AppState.IDLE
    assert tray.status_text() == "Inattivo"

    tray.set_state(AppState.LISTENING, Mode.DICTATION)
    assert tray.state is AppState.LISTENING
    assert tray.mode is Mode.DICTATION
    assert tray.status_text() == "In ascolto (dettatura)"
    assert "In ascolto (dettatura)" in tray.tray_icon.toolTip()
    shown = tray.tray_icon.icon().pixmap(32, 32).toImage()
    assert shown == tray.icon_for(AppState.LISTENING).pixmap(32, 32).toImage()

    tray.set_state(AppState.ERROR, Mode.COMMAND)
    assert tray.status_text() == "Errore (comando)"


def test_state_text_idle_senza_modalita():
    assert state_text(AppState.IDLE, Mode.COMMAND) == "Inattivo"
    assert state_text(AppState.PROCESSING, None) == "Elaborazione"
    assert state_text(AppState.DONE, Mode.COMMAND) == "Eseguito (comando)"


def test_set_status_text_libero(tray):
    tray.set_status_text("Caricamento del modello…")
    assert tray.status_text() == "Caricamento del modello…"
    assert "Caricamento del modello…" in tray.tray_icon.toolTip()


def test_menu_voci_e_stato_disabilitato(tray):
    actions = [a for a in tray.menu.actions() if not a.isSeparator()]
    texts = [a.text() for a in actions]
    assert texts == ["Inattivo", "Apri configurazione", "Ricarica configurazione", "Esci"]
    assert not actions[0].isEnabled()
    assert all(a.isEnabled() for a in actions[1:])
    assert tray.tray_icon.contextMenu() is tray.menu


@pytest.mark.parametrize(
    "action_attr, signal_attr",
    [
        ("open_config_action", "open_config_requested"),
        ("reload_config_action", "reload_config_requested"),
        ("quit_action", "quit_requested"),
    ],
)
def test_voci_menu_emettono_segnali(qtbot, tray, action_attr, signal_attr):
    with qtbot.waitSignal(getattr(tray, signal_attr), timeout=1000):
        getattr(tray, action_attr).trigger()


def test_espone_qsystemtrayicon(tray):
    assert isinstance(tray.tray_icon, QSystemTrayIcon)
