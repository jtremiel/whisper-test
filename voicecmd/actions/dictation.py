"""Azione dettatura: incolla il testo nel campo attivo tramite la clipboard.

Sequenza: attende il rilascio dei tasti del trigger → salva la clipboard → copia il
testo → Cmd+V (Mac) / Ctrl+V (Windows) → breve attesa → ripristina la clipboard.

`pyperclip` e `pynput` vengono importati solo quando servono davvero, così il
modulo si importa senza effetti (e nei test si iniettano clipboard e tastiera finte).
"""
from __future__ import annotations

import logging
import sys
import time
from typing import Any, Callable, Protocol

from voicecmd.events import ActionResult

log = logging.getLogger(__name__)

RELEASE_TIMEOUT_S = 1.0   # tetto di attesa per il rilascio dei tasti del trigger
RELEASE_POLL_S = 0.01     # intervallo tra un controllo e l'altro di keys_released()
COPY_SETTLE_S = 0.05      # pausa tra la copia nella clipboard e l'incolla
RESTORE_DELAY_S = 0.25    # pausa tra l'incolla e il ripristino: l'app di destinazione legge la clipboard in modo asincrono


class Clipboard(Protocol):
    """Clipboard di testo (stessa interfaccia del modulo `pyperclip`)."""

    def paste(self) -> str: ...

    def copy(self, text: str) -> None: ...


class Keyboard(Protocol):
    """Invia una scorciatoia: `modifier` è "cmd" o "ctrl", `key` un carattere."""

    def send_shortcut(self, modifier: str, key: str) -> None: ...


class PynputKeyboard:
    """`Keyboard` reale basata su `pynput.keyboard.Controller`."""

    def __init__(self, controller: Any = None, key_cls: Any = None) -> None:
        if controller is None or key_cls is None:
            from pynput import keyboard as _kb  # import pigro

            controller = controller if controller is not None else _kb.Controller()
            key_cls = key_cls if key_cls is not None else _kb.Key
        self._controller = controller
        self._key_cls = key_cls

    def send_shortcut(self, modifier: str, key: str) -> None:
        mod = getattr(self._key_cls, modifier)
        # `pressed` garantisce il rilascio del modificatore anche se `tap` solleva
        with self._controller.pressed(mod):
            self._controller.tap(key)


def _default_clipboard() -> Clipboard:
    import pyperclip  # import pigro

    return pyperclip  # type: ignore[return-value]


def paste_modifier(platform: str | None = None) -> str:
    """Modificatore della scorciatoia di incolla: "cmd" su macOS, "ctrl" altrove."""
    platform = sys.platform if platform is None else platform
    return "cmd" if platform == "darwin" else "ctrl"


def _wait_keys_released(
    keys_released: Callable[[], bool],
    timeout: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> bool:
    """Attende che `keys_released()` diventi vero; False se scade il tetto (HANDOFF §7.6)."""
    deadline = clock() + timeout
    while True:
        if keys_released():
            return True
        if clock() >= deadline:
            return False
        sleep(RELEASE_POLL_S)


def paste_text(
    text: str,
    *,
    clipboard: Clipboard | None = None,
    keyboard: Keyboard | None = None,
    keys_released: Callable[[], bool] | None = None,
    platform: str | None = None,
    release_timeout: float = RELEASE_TIMEOUT_S,
    restore_delay: float = RESTORE_DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> ActionResult:
    """Incolla `text` nel campo attivo e ripristina la clipboard precedente. Non solleva."""
    if not text or not text.strip():
        return ActionResult(False, "Nessun testo da incollare")

    try:
        # 1. Attesa del rilascio dei tasti del trigger, prima di toccare la clipboard
        if keys_released is not None and not _wait_keys_released(
            keys_released, release_timeout, sleep, clock
        ):
            log.warning("Tasti del trigger ancora premuti dopo %.1f s: incolla annullato", release_timeout)
            return ActionResult(False, "Tasti del trigger ancora premuti: testo non incollato")

        clip = clipboard if clipboard is not None else _default_clipboard()
        kb = keyboard if keyboard is not None else PynputKeyboard()
    except Exception as exc:  # noqa: BLE001 - l'azione non deve mai far cadere l'app
        log.exception("Dettatura: preparazione fallita")
        return ActionResult(False, f"Dettatura non disponibile: {exc}")

    # 2. Salvataggio della clipboard (solo testo: pyperclip non gestisce immagini o file)
    try:
        previous: str | None = clip.paste()
    except Exception:  # noqa: BLE001
        log.warning("Dettatura: impossibile leggere la clipboard, non verrà ripristinata", exc_info=True)
        previous = None

    result: ActionResult
    try:
        # 3. Copia e incolla
        clip.copy(text)
        sleep(COPY_SETTLE_S)
        kb.send_shortcut(paste_modifier(platform), "v")
        sleep(restore_delay)
        result = ActionResult(True, "Testo incollato")
    except Exception as exc:  # noqa: BLE001
        log.exception("Dettatura: incolla fallito")
        result = ActionResult(False, f"Incolla non riuscito: {exc}")
    finally:
        # 4. Ripristino, anche se l'incolla ha sollevato
        if previous is not None:
            try:
                clip.copy(previous)
            except Exception:  # noqa: BLE001
                log.warning("Dettatura: ripristino della clipboard fallito", exc_info=True)
    return result
