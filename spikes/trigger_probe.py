"""Spike T04: sonda per tastiera e mouse (pynput / event tap Quartz).

Uso (dalla root del repo):
  .venv/bin/python spikes/trigger_probe.py                    # pynput, tastiera + mouse
  .venv/bin/python spikes/trigger_probe.py --quartz           # mouse via Quartz (numero pulsante)
  .venv/bin/python spikes/trigger_probe.py --suppress x1      # prova a sopprimere solo x1
  .venv/bin/python spikes/trigger_probe.py --quartz --suppress x1
  .venv/bin/python spikes/trigger_probe.py --suppress f13     # sopprime un tasto
  .venv/bin/python spikes/trigger_probe.py --seconds 10       # termina da solo
Ctrl+C per uscire.

--suppress accetta: middle, x1, x2 (pulsanti mouse) oppure un tasto pynput
(f13, space, ctrl_r, alt_r, cmd_r, a, ...). Gli altri eventi passano normalmente.
Numeri pulsante Quartz: 0 sinistro, 1 destro, 2 centrale, 3 laterale "indietro"
(x1), 4 laterale "avanti" (x2).
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

T0 = time.monotonic()
MOUSE_NAMES = {"middle": 2, "x1": 3, "x2": 4}


def log(msg: str) -> None:
    print(f"[{time.monotonic() - T0:8.3f}] {msg}", flush=True)


def check_permissions() -> None:
    """Avvisa (in italiano) se mancano i permessi macOS."""
    if sys.platform != "darwin":
        return
    try:
        import Quartz
        from ApplicationServices import AXIsProcessTrusted

        trusted = bool(AXIsProcessTrusted())
        listen = bool(Quartz.CGPreflightListenEventAccess())
    except Exception as exc:  # noqa: BLE001
        log(f"Impossibile verificare i permessi ({exc!r}).")
        return
    if not listen:
        log("ATTENZIONE: manca il permesso 'Monitoraggio input'. Apri Impostazioni di "
            "Sistema > Privacy e sicurezza > Monitoraggio input e abilita il terminale "
            "che esegue lo script, poi riavvialo.")
    if not trusted:
        log("ATTENZIONE: manca il permesso 'Accessibilita'' (serve per sopprimere eventi). "
            "Impostazioni di Sistema > Privacy e sicurezza > Accessibilita': abilita il "
            "terminale, poi riavvialo.")
    if listen and trusted:
        log("Permessi macOS: Monitoraggio input e Accessibilita' presenti.")


def parse_suppress(value: str | None):
    """Ritorna ('mouse', numero_quartz, nome) | ('key', Key|KeyCode, nome) | None."""
    if not value:
        return None
    from pynput import keyboard

    v = value.strip().lower()
    if v in MOUSE_NAMES:
        return ("mouse", MOUSE_NAMES[v], v)
    if hasattr(keyboard.Key, v):
        return ("key", getattr(keyboard.Key, v), v)
    if len(value) == 1:
        return ("key", keyboard.KeyCode.from_char(value), value)
    raise SystemExit(f"--suppress: '{value}' non e' un pulsante (middle/x1/x2) ne' un tasto noto.")


def run_keyboard(sup, deadline) -> object:
    """Listener tastiera pynput; con sup di tipo 'key' passa darwin_intercept."""
    from pynput import keyboard

    holder: dict = {}
    kwargs = {}
    if sys.platform == "darwin" and sup and sup[0] == "key":
        import Quartz

        def intercept(event_type, event):
            # _event_to_key e' API privata di pynput 1.8.2: va bene per uno spike.
            try:
                key = holder["l"]._event_to_key(event)
            except Exception:  # noqa: BLE001
                return event
            if key == sup[1]:
                log(f"   (soppresso evento tastiera tipo={event_type} tasto={sup[2]})")
                return None
            return event

        kwargs["darwin_intercept"] = intercept

    def on_press(key):
        log(f"TASTO     premuto   {key}")

    def on_release(key):
        log(f"TASTO     rilasciato {key}")

    listener = keyboard.Listener(on_press=on_press, on_release=on_release, **kwargs)
    holder["l"] = listener
    listener.start()
    return listener


def run_mouse_pynput(sup):
    from pynput import mouse

    kwargs = {}
    if sys.platform == "darwin" and sup and sup[0] == "mouse":
        import Quartz

        def intercept(event_type, event):
            if event_type in (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp):
                num = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventButtonNumber)
                if num == sup[1]:
                    log(f"   (soppresso evento mouse tipo={event_type} pulsante={num})")
                    return None
            return event

        kwargs["darwin_intercept"] = intercept

    def on_click(x, y, button, pressed):
        log(f"MOUSE     {'premuto  ' if pressed else 'rilasciato'} {button} @({x:.0f},{y:.0f})")

    # Nota: i movimenti e lo scroll non vengono stampati per non inondare l'output.
    listener = mouse.Listener(on_click=on_click, **kwargs)
    listener.start()
    return listener


def run_quartz_mouse(sup, deadline) -> None:
    """Event tap Quartz sul mouse; gira nel thread chiamante finche' non scade."""
    import Quartz as Q

    names = {Q.kCGEventLeftMouseDown: ("sinistro", True), Q.kCGEventLeftMouseUp: ("sinistro", False),
             Q.kCGEventRightMouseDown: ("destro", True), Q.kCGEventRightMouseUp: ("destro", False),
             Q.kCGEventOtherMouseDown: ("altro", True), Q.kCGEventOtherMouseUp: ("altro", False)}
    mask = 0
    for t in names:
        mask |= Q.CGEventMaskBit(t)
    suppress_num = sup[1] if sup and sup[0] == "mouse" else None
    state = {"tap": None}

    def callback(proxy, etype, event, refcon):
        if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            log("ATTENZIONE: event tap disabilitato dal sistema, lo riattivo.")
            Q.CGEventTapEnable(state["tap"], True)
            return event
        if etype not in names:
            return event
        kind, pressed = names[etype]
        num = Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventButtonNumber)
        label = {v: k for k, v in MOUSE_NAMES.items()}.get(num, "")
        log(f"QUARTZ    {'premuto  ' if pressed else 'rilasciato'} pulsante={num} ({kind}) {label}")
        if etype in (Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp) and num == suppress_num:
            log("   (soppresso: ritorno None)")
            return None
        return event

    options = (Q.kCGEventTapOptionDefault if suppress_num is not None
               else Q.kCGEventTapOptionListenOnly)
    tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, options, mask,
                             callback, None)
    if tap is None:
        log("ERRORE: impossibile creare l'event tap Quartz. Mancano i permessi "
            "(Monitoraggio input / Accessibilita'): abilita il terminale in Impostazioni "
            "di Sistema > Privacy e sicurezza e riavvialo.")
        return
    state["tap"] = tap
    src = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
    Q.CFRunLoopAddSource(Q.CFRunLoopGetCurrent(), src, Q.kCFRunLoopCommonModes)
    Q.CGEventTapEnable(tap, True)
    log("Event tap Quartz attivo (mouse).")
    while deadline is None or time.monotonic() < deadline:
        Q.CFRunLoopRunInMode(Q.kCFRunLoopDefaultMode, 0.2, False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quartz", action="store_true", help="mouse via event tap Quartz (solo macOS)")
    ap.add_argument("--suppress", metavar="TRIGGER", help="pulsante (middle/x1/x2) o tasto da sopprimere")
    ap.add_argument("--seconds", type=float, help="termina da solo dopo N secondi")
    args = ap.parse_args()

    if args.quartz and sys.platform != "darwin":
        raise SystemExit("--quartz esiste solo su macOS.")
    sup = parse_suppress(args.suppress)
    deadline = time.monotonic() + args.seconds if args.seconds else None

    log(f"Avvio: piattaforma={sys.platform} quartz={args.quartz} suppress={args.suppress}")
    check_permissions()
    log("Premi tasti / pulsanti del mouse. Ctrl+C per uscire.")

    listeners = []
    try:
        listeners.append(run_keyboard(sup, deadline))
        if args.quartz:
            run_quartz_mouse(sup, deadline)
        else:
            listeners.append(run_mouse_pynput(sup))
            while deadline is None or time.monotonic() < deadline:
                time.sleep(0.1)
    except KeyboardInterrupt:
        log("Interrotto dall'utente (Ctrl+C).")
    finally:
        for l in listeners:
            l.stop()
    log("Fine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
