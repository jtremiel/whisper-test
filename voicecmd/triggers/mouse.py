"""Trigger da pulsante del mouse (centrale, laterale x1, laterale x2).

Su macOS usa un event tap Quartz (decisione dello spike T04, docs/spikes/T04-trigger.md):
pynput riporta i laterali come `Button.middle`, il tap invece legge il numero del pulsante
(centrale 2, x1 3, x2 4) e sopprime solo i pulsanti configurati, così il laterale non fa
"indietro" nel browser.

Su Windows usa `pynput.mouse.Listener` con `win32_event_filter`: il filtro riconosce il
pulsante dal messaggio Windows e sopprime l'evento con `listener.suppress_event()`.
Il ramo Windows NON è verificato su una macchina reale (da confermare in T26).

La logica comune sta in `MouseTrigger.handle_click`, che i test chiamano direttamente.
"""
from __future__ import annotations

import logging
import sys
import threading
from typing import Any, Callable, Mapping

from voicecmd.events import Mode

log = logging.getLogger(__name__)

BUTTON_NAMES: tuple[str, ...] = ("middle", "x1", "x2")

# Numeri dei pulsanti nell'evento Quartz (kCGMouseEventButtonNumber), misurati in T04.
QUARTZ_BUTTONS: dict[int, str] = {2: "middle", 3: "x1", 4: "x2"}

# Messaggi Windows dei pulsanti (WinUser.h); la parola alta di mouseData dice quale X.
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
XBUTTON1 = 1
XBUTTON2 = 2


def quartz_button_name(number: int) -> str | None:
    """Nome del pulsante dal numero Quartz; None per sinistro, destro e altri."""
    return QUARTZ_BUTTONS.get(int(number))


def win32_button(msg: int, mouse_data: int) -> tuple[str, bool] | None:
    """(nome, premuto) da un messaggio Windows del mouse; None se non è centrale/x1/x2."""
    if msg in (WM_MBUTTONDOWN, WM_MBUTTONUP):
        return "middle", msg == WM_MBUTTONDOWN
    if msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
        which = (int(mouse_data) >> 16) & 0xFFFF
        name = {XBUTTON1: "x1", XBUTTON2: "x2"}.get(which)
        if name is None:
            return None
        return name, msg == WM_XBUTTONDOWN
    return None


class MouseTrigger:
    """Trigger che rispetta il Protocol `Trigger` di events.py per i pulsanti del mouse."""

    def __init__(self, buttons: Mapping[Mode, str]) -> None:
        """`buttons` associa a ogni modalità un pulsante tra `middle`, `x1`, `x2`."""
        by_button: dict[str, Mode] = {}
        for mode, button in buttons.items():
            if button not in BUTTON_NAMES:
                raise ValueError(
                    f"pulsante del mouse '{button}' non valido: usare uno tra {', '.join(BUTTON_NAMES)}"
                )
            if button in by_button:
                raise ValueError(
                    f"il pulsante '{button}' è assegnato sia a '{by_button[button].value}' "
                    f"sia a '{mode.value}'"
                )
            by_button[button] = mode
        self._by_button = by_button
        self._held: set[str] = set()
        self._lock = threading.Lock()
        self._on_event: Callable[[Mode, bool], None] | None = None
        # stato del backend di piattaforma
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._tap: Any = None
        self._runloop: Any = None
        self._listener: Any = None

    # ------------------------------------------------------------------ logica comune

    def handle_click(self, button: str | None, pressed: bool) -> bool:
        """Gestisce un clic già decodificato; True se è un pulsante del trigger (da sopprimere).

        Chiamata dal thread del backend: deve restare velocissima. Inoltra `on_event` solo
        sulle transizioni (premuto una volta, poi rilasciato); le pressioni ripetute
        senza rilascio vengono assorbite.
        """
        mode = self._by_button.get(button) if button is not None else None
        if mode is None:
            return False
        on_event = self._on_event
        if on_event is None:
            return False
        with self._lock:
            if pressed:
                if button in self._held:
                    return True
                self._held.add(button)
            else:
                if button not in self._held:
                    # rilascio di una pressione vista prima dell'avvio: lo lasciamo passare
                    return False
                self._held.discard(button)
        try:
            on_event(mode, pressed)
        except Exception:  # noqa: BLE001 - un errore a valle non deve fermare il trigger
            log.exception("Errore nel gestore del trigger da mouse")
        return True

    # ------------------------------------------------------------------ Protocol Trigger

    def start(self, on_event: Callable[[Mode, bool], None]) -> None:
        """Avvia l'ascolto dei pulsanti configurati. Solleva RuntimeError se il sistema lo rifiuta."""
        if self._on_event is not None:
            return
        self._on_event = on_event
        self._held.clear()
        if not self._by_button:
            return
        try:
            self._start_backend()
        except Exception:
            self._on_event = None
            raise

    def stop(self) -> None:
        """Ferma l'ascolto; si può chiamare più volte."""
        if self._on_event is None:
            return
        try:
            self._stop_backend()
        finally:
            self._on_event = None
            self._held.clear()

    # ------------------------------------------------------------------ backend

    def _start_backend(self) -> None:
        if sys.platform == "darwin":
            self._start_quartz()
        else:
            self._start_pynput()

    def _stop_backend(self) -> None:
        if sys.platform == "darwin":
            self._stop_quartz()
        else:
            self._stop_pynput()

    # --- macOS: event tap Quartz in un thread con il suo CFRunLoop

    def _quartz_callback(self, proxy: Any, etype: int, event: Any, refcon: Any) -> Any:
        import Quartz as Q

        try:
            if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                log.warning("Event tap del mouse disabilitato dal sistema: lo riattivo.")
                if self._tap is not None:
                    Q.CGEventTapEnable(self._tap, True)
                return event
            if etype not in (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp):
                return event
            number = Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventButtonNumber)
            if self.handle_click(quartz_button_name(number), etype == Q.kCGEventOtherMouseDown):
                return None  # soppresso: l'app in primo piano non lo riceve
        except Exception:  # noqa: BLE001 - mai propagare eccezioni dentro Quartz
            log.exception("Errore nel callback dell'event tap del mouse")
        return event

    def _start_quartz(self) -> None:
        ready = threading.Event()
        error: list[str] = []
        self._stopping.clear()

        def run() -> None:
            import Quartz as Q

            mask = Q.CGEventMaskBit(Q.kCGEventOtherMouseDown) | Q.CGEventMaskBit(Q.kCGEventOtherMouseUp)
            tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                     Q.kCGEventTapOptionDefault, mask, self._quartz_callback, None)
            if tap is None:
                error.append(
                    "impossibile creare l'event tap del mouse: mancano i permessi "
                    "'Monitoraggio input' e 'Accessibilità' (Impostazioni di Sistema > "
                    "Privacy e sicurezza) per l'app che esegue voicecmd"
                )
                ready.set()
                return
            self._tap = tap
            source = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
            self._runloop = Q.CFRunLoopGetCurrent()
            Q.CFRunLoopAddSource(self._runloop, source, Q.kCFRunLoopCommonModes)
            Q.CGEventTapEnable(tap, True)
            ready.set()
            log.info("Event tap Quartz del mouse attivo: %s", self._describe())
            while not self._stopping.is_set():
                Q.CFRunLoopRunInMode(Q.kCFRunLoopDefaultMode, 0.5, False)
            Q.CGEventTapEnable(tap, False)
            Q.CFRunLoopRemoveSource(self._runloop, source, Q.kCFRunLoopCommonModes)
            Q.CFMachPortInvalidate(tap)
            self._tap = None
            self._runloop = None

        self._thread = threading.Thread(target=run, name="voicecmd-mouse-tap", daemon=True)
        self._thread.start()
        if not ready.wait(5.0):
            log.warning("L'event tap del mouse non ha confermato l'avvio entro 5 s")
        if error:
            self._thread.join(1.0)
            self._thread = None
            raise RuntimeError(error[0])

    def _stop_quartz(self) -> None:
        import Quartz as Q

        self._stopping.set()
        if self._runloop is not None:
            Q.CFRunLoopStop(self._runloop)
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None

    # --- Windows: pynput con win32_event_filter (non verificato su macchina reale)

    def _win32_filter(self, msg: int, data: Any) -> bool:
        decoded = win32_button(msg, getattr(data, "mouseData", 0))
        if decoded is not None and self.handle_click(*decoded) and self._listener is not None:
            # solleva un'eccezione interna di pynput che blocca la propagazione dell'evento
            self._listener.suppress_event()
        return True

    def _start_pynput(self) -> None:
        from pynput import mouse

        if sys.platform != "win32":
            log.warning("Trigger da mouse supportato solo su macOS e Windows (piattaforma: %s)",
                        sys.platform)
        self._listener = mouse.Listener(win32_event_filter=self._win32_filter)
        self._listener.start()
        log.info("Listener pynput del mouse attivo: %s", self._describe())

    def _stop_pynput(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _describe(self) -> str:
        return ", ".join(f"{m.value}={b}" for b, m in self._by_button.items())
