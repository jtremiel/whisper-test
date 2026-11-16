"""Trigger da tastiera: combinazioni globali push-to-talk via `pynput.keyboard`.

Il listener è in sola lettura: lo spike T04 ha verificato che `<ctrl>+<alt>+space`
tenuta premuta non scrive caratteri nell'app attiva, quindi non serve soppressione
(vedi `docs/spikes/T04-trigger.md`).

Formato delle hotkey (come `pynput`, più tollerante): parti separate da `+`.
Ogni parte è un carattere (`a`), il nome di un tasto `pynput` con o senza parentesi
angolari (`<space>`, `space`, `<f13>`), oppure un codice virtuale (`<65>`).
I modificatori generici (`ctrl`, `alt`, `shift`, `cmd`) valgono per entrambi i lati;
le varianti `ctrl_l`, `alt_r`, ecc. solo per quel lato. Su macOS Option è `alt`.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Hashable, Mapping

from pynput import keyboard

from voicecmd.events import Mode

log = logging.getLogger(__name__)

# Identità di un tasto: tuple come ("mod", "ctrl"), ("side", "ctrl_r"),
# ("key", "space"), ("char", "a"), ("vk", 49).
KeyId = tuple[str, Any]

_MODIFIERS = ("ctrl", "alt", "shift", "cmd")
# Nome del tasto riportato da pynput → (modificatore generico, lato specifico).
# Su macOS `Key.alt`/`Key.ctrl`/... sono alias del tasto sinistro; `alt_gr` è il destro.
_SIDES: dict[str, tuple[str, str]] = {}
for _m in _MODIFIERS:
    _SIDES[_m] = (_m, f"{_m}_l")
    _SIDES[f"{_m}_l"] = (_m, f"{_m}_l")
    _SIDES[f"{_m}_r"] = (_m, f"{_m}_r")
_SIDES["alt_gr"] = ("alt", "alt_r")


class HotkeyError(ValueError):
    """Stringa hotkey non valida."""


def _parse_part(part: str, hotkey: str) -> KeyId:
    """Converte una parte della hotkey nell'identità del tasto."""
    raw = part.strip()
    if not raw:
        raise HotkeyError(f"Hotkey '{hotkey}' non valida: c'è una parte vuota (controlla i '+').")
    bracketed = len(raw) > 2 and raw[0] == "<" and raw[-1] == ">"
    name = raw[1:-1].strip().lower() if bracketed else raw.lower()
    if len(name) == 1 and not bracketed:
        return ("char", name)
    if name in _SIDES:
        generic, side = _SIDES[name]
        return ("mod", generic) if name == generic else ("side", side)
    if name in keyboard.Key.__members__:
        return ("key", keyboard.Key[name].name)  # risolve gli alias dell'enum
    if bracketed and name.isdigit():
        return ("vk", int(name))
    raise HotkeyError(
        f"Hotkey '{hotkey}' non valida: tasto sconosciuto '{raw}'. "
        "Usa un carattere, un nome di tasto come <ctrl>, <alt>, <shift>, <cmd>, "
        "<space>, <f13>, oppure un codice <numero>."
    )


def parse_hotkey(hotkey: str) -> frozenset[KeyId]:
    """Analizza una stringa hotkey; solleva `HotkeyError` con un messaggio chiaro."""
    if not isinstance(hotkey, str) or not hotkey.strip():
        raise HotkeyError("Hotkey vuota: indica almeno un tasto, ad es. '<ctrl>+<alt>+space'.")
    text = hotkey.strip()
    # '+' finale come tasto letterale (es. '<ctrl>++'), come in pynput.
    parts = text[:-2].split("+") + ["+"] if text.endswith("++") else text.split("+")
    keys = [_parse_part(p, hotkey) if p != "+" else ("char", "+") for p in parts]
    if len(keys) != len(set(keys)):
        raise HotkeyError(f"Hotkey '{hotkey}' non valida: un tasto è ripetuto.")
    return frozenset(keys)


def _key_ids(key: Any) -> frozenset[KeyId]:
    """Tutte le identità con cui un tasto ricevuto da pynput può soddisfare una hotkey."""
    ids: set[KeyId] = set()
    if isinstance(key, keyboard.Key):
        name = key.name
        if name in _SIDES:
            generic, side = _SIDES[name]
            ids.add(("mod", generic))
            ids.add(("side", side))
        else:
            ids.add(("key", name))
        vk = getattr(key.value, "vk", None)
        if vk is not None:
            ids.add(("vk", vk))
    elif isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            ids.add(("char", key.char.lower()))
        if key.vk is not None:
            ids.add(("vk", key.vk))
    return frozenset(ids)


def _press_token(key: Any, ids: frozenset[KeyId]) -> Hashable:
    """Chiave stabile tra pressione e rilascio dello stesso tasto fisico."""
    if isinstance(key, keyboard.Key):
        return ("key", key.name)
    vk = getattr(key, "vk", None)
    if vk is not None:
        return ("vk", vk)
    return ids


class HotkeyTrigger:
    """Trigger da tastiera che rispetta il Protocol `Trigger` di `events.py`.

    Emette `on_event(mode, True)` quando la combinazione di `mode` diventa completa
    e `on_event(mode, False)` quando smette di esserlo (uno dei suoi tasti è lasciato).
    L'autorepeat (pressioni ripetute di un tasto già giù) è ignorato. Mentre una
    modalità è attiva le altre non si attivano. Gli eventi iniettati (es. il Cmd+V
    della dettatura) sono ignorati.
    """

    def __init__(
        self,
        hotkeys: Mapping[Mode, str],
        listener_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not hotkeys:
            raise HotkeyError("Nessuna hotkey configurata.")
        self._combos: dict[Mode, frozenset[KeyId]] = {}
        for mode, text in hotkeys.items():
            try:
                combo = parse_hotkey(text)
            except HotkeyError as exc:
                raise HotkeyError(f"Trigger '{mode.value}': {exc}") from None
            for other, other_combo in self._combos.items():
                if other_combo == combo:
                    raise HotkeyError(
                        f"I trigger '{other.value}' e '{mode.value}' usano la stessa hotkey '{text}'."
                    )
            self._combos[mode] = combo
        self._all_ids: frozenset[KeyId] = frozenset().union(*self._combos.values())
        self._listener_factory = listener_factory or keyboard.Listener
        self._listener: Any = None
        self._on_event: Callable[[Mode, bool], None] | None = None
        self._pressed: dict[Hashable, frozenset[KeyId]] = {}
        self._active: set[Mode] = set()
        self._lock = threading.Lock()

    # --- Protocol Trigger -------------------------------------------------

    def start(self, on_event: Callable[[Mode, bool], None]) -> None:
        """Avvia il listener globale di tastiera (thread di pynput)."""
        self.stop()
        self._on_event = on_event
        self._listener = self._listener_factory(
            on_press=self.handle_press, on_release=self.handle_release
        )
        self._listener.start()
        # Su macOS pynput non fallisce senza permessi: avvisa nel log e poi non riceve nulla.
        # Si aspetta che il listener sia pronto e si controlla il flag, per non dichiararlo attivo.
        wait = getattr(self._listener, "wait", None)
        if callable(wait):
            wait()
        if getattr(self._listener, "IS_TRUSTED", True) is False:
            self.stop()
            raise RuntimeError(
                "impossibile ascoltare la tastiera: mancano i permessi 'Monitoraggio input' e "
                "'Accessibilità' (Impostazioni di Sistema > Privacy e sicurezza) per l'app che "
                "esegue voicecmd"
            )

    def stop(self) -> None:
        """Ferma il listener e azzera lo stato dei tasti."""
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.stop()
        with self._lock:
            self._pressed.clear()
            self._active.clear()

    # --- per T13 ----------------------------------------------------------

    def keys_released(self) -> bool:
        """True se nessun tasto usato dalle hotkey configurate è ancora premuto."""
        with self._lock:
            return not any(ids & self._all_ids for ids in self._pressed.values())

    # --- gestori pynput (pubblici per i test) -----------------------------

    def handle_press(self, key: Any, injected: bool = False) -> None:
        """Gestore di pressione del listener."""
        if key is None or injected:
            return
        ids = _key_ids(key)
        token = _press_token(key, ids)
        fired: list[tuple[Mode, bool]] = []
        with self._lock:
            if token in self._pressed:
                return  # autorepeat
            self._pressed[token] = ids
            if self._active:
                return
            candidates = [
                m for m, combo in self._combos.items()
                if combo & ids and self._satisfied(combo)
            ]
            if candidates:
                # Se più combinazioni si completano insieme vince la più lunga.
                best = max(candidates, key=lambda m: len(self._combos[m]))
                self._active.add(best)
                fired.append((best, True))
        self._dispatch(fired)

    def handle_release(self, key: Any, injected: bool = False) -> None:
        """Gestore di rilascio del listener."""
        if key is None or injected:
            return
        ids = _key_ids(key)
        token = _press_token(key, ids)
        fired: list[tuple[Mode, bool]] = []
        with self._lock:
            if self._pressed.pop(token, None) is None:
                # Il carattere può cambiare tra pressione e rilascio: ripiego sulle identità.
                for t, pids in list(self._pressed.items()):
                    if pids & ids:
                        del self._pressed[t]
                        break
            for mode in list(self._active):
                if not self._satisfied(self._combos[mode]):
                    self._active.discard(mode)
                    fired.append((mode, False))
        self._dispatch(fired)

    # --- interni ----------------------------------------------------------

    def _satisfied(self, combo: frozenset[KeyId]) -> bool:
        return all(any(k in ids for ids in self._pressed.values()) for k in combo)

    def _dispatch(self, fired: list[tuple[Mode, bool]]) -> None:
        cb = self._on_event
        if cb is None:
            return
        for mode, pressed in fired:
            try:
                cb(mode, pressed)
            except Exception:  # noqa: BLE001 - un errore non deve fermare il listener
                log.exception("Errore nel gestore del trigger da tastiera")
