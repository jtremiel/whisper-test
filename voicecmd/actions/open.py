"""Azione `open`: apre un'app, un file, una cartella o un URL col meccanismo del sistema."""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from voicecmd.events import ActionResult

if TYPE_CHECKING:
    from voicecmd.schema import OpenAction

# Schemi trattati come URL e passati al browser predefinito.
URL_SCHEMES = ("http", "https", "ftp", "file", "mailto")

# Tetto di attesa per `open` su macOS: il comando torna subito, serve solo a non bloccarsi.
MAC_OPEN_TIMEOUT_S = 10


def is_url(target: str) -> bool:
    """True se `target` è un URL con uno schema noto (non scambia `C:\\...` per uno schema)."""
    scheme = urlparse(target).scheme.lower()
    return scheme in URL_SCHEMES


def expand(target: str) -> str:
    """Espande `~` e le variabili d'ambiente (`$HOME`, `%USERPROFILE%`)."""
    return os.path.expanduser(os.path.expandvars(target.strip()))


def looks_like_path(target: str) -> bool:
    """True se `target` sembra un percorso (contiene un separatore o inizia con `~` / `.`)."""
    return (
        "/" in target
        or "\\" in target
        or target.startswith(("~", "."))
        or (len(target) >= 2 and target[1] == ":")  # C:...
    )


class OpenActionRunner:
    """Esegue le azioni `open`; rispetta il Protocol `Action` di events.py."""

    def run(self, spec: OpenAction) -> ActionResult:
        try:
            return self._run(spec.target)
        except Exception as exc:  # un'azione non deve mai far cadere l'app
            return ActionResult(ok=False, message=f"Impossibile aprire '{spec.target}': {exc}")

    def _run(self, raw: str) -> ActionResult:
        raw = raw.strip()
        if not raw:
            return ActionResult(ok=False, message="Nessun target da aprire.")

        if is_url(raw):
            if webbrowser.open(raw):
                return ActionResult(ok=True, message=f"Aperto {raw}")
            return ActionResult(ok=False, message=f"Impossibile aprire l'URL '{raw}' nel browser.")

        target = expand(raw)
        exists = os.path.exists(target)
        if not exists and looks_like_path(raw):
            return ActionResult(ok=False, message=f"Il percorso '{target}' non esiste.")

        if sys.platform == "darwin":
            return self._open_mac(target, is_app=not exists)
        if sys.platform == "win32":
            return self._open_windows(target)
        return self._open_other(target, exists)

    def _open_mac(self, target: str, is_app: bool) -> ActionResult:
        # Percorso esistente -> `open <percorso>`; altrimenti nome di un'app -> `open -a <nome>`
        args = ["open", "-a", target] if is_app else ["open", target]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=MAC_OPEN_TIMEOUT_S)
        if proc.returncode == 0:
            return ActionResult(ok=True, message=f"Aperto {target}")
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        reason = detail[-1] if detail else f"codice di uscita {proc.returncode}"
        what = "l'app" if is_app else "il percorso"
        return ActionResult(ok=False, message=f"Impossibile aprire {what} '{target}': {reason}")

    def _open_windows(self, target: str) -> ActionResult:
        # os.startfile apre file, cartelle e app registrate (es. "notepad"); esiste solo su Windows
        startfile = getattr(os, "startfile")
        try:
            startfile(target)
        except OSError as exc:
            return ActionResult(ok=False, message=f"Impossibile aprire '{target}': {exc.strerror or exc}")
        return ActionResult(ok=True, message=f"Aperto {target}")

    def _open_other(self, target: str, exists: bool) -> ActionResult:
        # Fuori dal perimetro dell'MVP (solo Mac e Windows): tentativo con xdg-open sui percorsi
        if not exists:
            return ActionResult(ok=False, message=f"'{target}' non trovato su questo sistema.")
        proc = subprocess.run(["xdg-open", target], capture_output=True, text=True, timeout=MAC_OPEN_TIMEOUT_S)
        if proc.returncode == 0:
            return ActionResult(ok=True, message=f"Aperto {target}")
        return ActionResult(ok=False, message=f"Impossibile aprire '{target}': codice di uscita {proc.returncode}")
