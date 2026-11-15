"""Test del trigger da mouse: si alimenta direttamente il gestore, senza tap né listener reali."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from voicecmd.events import Mode, Trigger
from voicecmd.triggers import mouse as m
from voicecmd.triggers.mouse import MouseTrigger


@pytest.fixture
def started(monkeypatch):
    """Crea un MouseTrigger avviato con il backend di piattaforma disattivato."""
    monkeypatch.setattr(MouseTrigger, "_start_backend", lambda self: None)
    monkeypatch.setattr(MouseTrigger, "_stop_backend", lambda self: None)

    def make(buttons):
        events: list[tuple[Mode, bool]] = []
        trig = MouseTrigger(buttons)
        trig.start(lambda mode, pressed: events.append((mode, pressed)))
        return trig, events

    return make


def test_rispetta_il_protocol():
    assert isinstance(MouseTrigger({Mode.DICTATION: "x2"}), Trigger)


def test_pulsante_configurato_emette_premuto_e_rilasciato(started):
    trig, events = started({Mode.DICTATION: "x2", Mode.COMMAND: "middle"})
    assert trig.handle_click("x2", True) is True
    assert trig.handle_click("x2", False) is True
    assert trig.handle_click("middle", True) is True
    assert trig.handle_click("middle", False) is True
    assert events == [(Mode.DICTATION, True), (Mode.DICTATION, False),
                      (Mode.COMMAND, True), (Mode.COMMAND, False)]


def test_altri_pulsanti_ignorati(started):
    trig, events = started({Mode.DICTATION: "x2"})
    assert trig.handle_click("x1", True) is False
    assert trig.handle_click("x1", False) is False
    assert trig.handle_click("middle", True) is False
    assert trig.handle_click(None, True) is False
    assert events == []


def test_pressione_ripetuta_assorbita_e_rilascio_orfano_passa(started):
    trig, events = started({Mode.COMMAND: "x1"})
    assert trig.handle_click("x1", False) is False  # rilascio senza pressione vista
    trig.handle_click("x1", True)
    assert trig.handle_click("x1", True) is True    # ripetuta: soppressa, non riemessa
    trig.handle_click("x1", False)
    assert events == [(Mode.COMMAND, True), (Mode.COMMAND, False)]


def test_niente_eventi_prima_di_start_e_dopo_stop(started):
    trig = MouseTrigger({Mode.COMMAND: "x1"})
    assert trig.handle_click("x1", True) is False
    trig2, events = started({Mode.COMMAND: "x1"})
    trig2.stop()
    assert trig2.handle_click("x1", True) is False
    assert events == []
    trig2.stop()  # idempotente


def test_errore_nel_gestore_non_propaga(started, monkeypatch):
    monkeypatch.setattr(MouseTrigger, "_start_backend", lambda self: None)
    trig = MouseTrigger({Mode.COMMAND: "x1"})

    def boom(mode, pressed):
        raise RuntimeError("guasto")

    trig.start(boom)
    assert trig.handle_click("x1", True) is True


def test_mappa_non_valida():
    with pytest.raises(ValueError, match="non valido"):
        MouseTrigger({Mode.COMMAND: "left"})
    with pytest.raises(ValueError, match="assegnato sia"):
        MouseTrigger({Mode.COMMAND: "x1", Mode.DICTATION: "x1"})


def test_mappa_vuota_non_avvia_backend(monkeypatch):
    def fail(self):
        raise AssertionError("backend avviato senza pulsanti")

    monkeypatch.setattr(MouseTrigger, "_start_backend", fail)
    MouseTrigger({}).start(lambda mode, pressed: None)


def test_errore_del_backend_lascia_il_trigger_fermo(monkeypatch):
    def fail(self):
        raise RuntimeError("permessi mancanti")

    monkeypatch.setattr(MouseTrigger, "_start_backend", fail)
    trig = MouseTrigger({Mode.COMMAND: "x1"})
    with pytest.raises(RuntimeError):
        trig.start(lambda mode, pressed: None)
    assert trig.handle_click("x1", True) is False


def test_numeri_quartz():
    assert [m.quartz_button_name(n) for n in range(6)] == [None, None, "middle", "x1", "x2", None]


def test_decodifica_win32():
    assert m.win32_button(m.WM_MBUTTONDOWN, 0) == ("middle", True)
    assert m.win32_button(m.WM_MBUTTONUP, 0) == ("middle", False)
    assert m.win32_button(m.WM_XBUTTONDOWN, m.XBUTTON1 << 16) == ("x1", True)
    assert m.win32_button(m.WM_XBUTTONUP, m.XBUTTON2 << 16) == ("x2", False)
    assert m.win32_button(m.WM_XBUTTONDOWN, 3 << 16) is None
    assert m.win32_button(0x0201, 0) is None  # sinistro
    assert m.win32_button(0x0200, 0) is None  # movimento


class _Suppressed(Exception):
    pass


def test_filtro_win32_sopprime_solo_il_trigger(started):
    trig, events = started({Mode.DICTATION: "x2"})

    def suppress_event():
        raise _Suppressed

    trig._listener = SimpleNamespace(suppress_event=suppress_event)
    with pytest.raises(_Suppressed):
        trig._win32_filter(m.WM_XBUTTONDOWN, SimpleNamespace(mouseData=m.XBUTTON2 << 16))
    assert trig._win32_filter(m.WM_XBUTTONDOWN, SimpleNamespace(mouseData=m.XBUTTON1 << 16)) is True
    assert trig._win32_filter(0x0200, SimpleNamespace(mouseData=0)) is True
    with pytest.raises(_Suppressed):
        trig._win32_filter(m.WM_XBUTTONUP, SimpleNamespace(mouseData=m.XBUTTON2 << 16))
    assert events == [(Mode.DICTATION, True), (Mode.DICTATION, False)]


@pytest.mark.skipif(sys.platform != "darwin", reason="solo macOS")
def test_callback_quartz_sopprime_solo_il_trigger(started):
    # Eventi CGEvent creati in memoria (non inviati al sistema), nessun event tap.
    import Quartz as Q

    trig, events = started({Mode.DICTATION: "x2"})

    def ev(etype, number):
        return Q.CGEventCreateMouseEvent(None, etype, (0, 0), number)

    down4 = ev(Q.kCGEventOtherMouseDown, 4)
    assert trig._quartz_callback(None, Q.kCGEventOtherMouseDown, down4, None) is None
    down3 = ev(Q.kCGEventOtherMouseDown, 3)
    assert trig._quartz_callback(None, Q.kCGEventOtherMouseDown, down3, None) is down3
    move = Q.CGEventCreateMouseEvent(None, Q.kCGEventMouseMoved, (5, 5), 0)
    assert trig._quartz_callback(None, Q.kCGEventMouseMoved, move, None) is move
    up4 = ev(Q.kCGEventOtherMouseUp, 4)
    assert trig._quartz_callback(None, Q.kCGEventOtherMouseUp, up4, None) is None
    assert events == [(Mode.DICTATION, True), (Mode.DICTATION, False)]


@pytest.mark.skipif(sys.platform != "darwin", reason="solo macOS")
def test_callback_quartz_riattiva_il_tap(started, monkeypatch):
    import Quartz as Q

    trig, _ = started({Mode.DICTATION: "x2"})
    calls = []
    monkeypatch.setattr(Q, "CGEventTapEnable", lambda tap, on: calls.append((tap, on)))
    trig._tap = "tap"
    sentinel = object()
    assert trig._quartz_callback(None, Q.kCGEventTapDisabledByTimeout, sentinel, None) is sentinel
    assert calls == [("tap", True)]
