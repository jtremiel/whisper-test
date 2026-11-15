"""Azione `shell`: esegue un comando del sistema e ne riporta l'esito."""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys

from voicecmd.events import ActionResult
from voicecmd.schema import ShellAction

log = logging.getLogger(__name__)

TAIL_LINES = 5  # righe finali di stderr/stdout riportate nel feedback


def select_command(spec: ShellAction, platform: str | None = None) -> str | None:
    """Sceglie il comando per il sistema: prima la variante `mac`/`windows`, poi `command`."""
    platform = sys.platform if platform is None else platform
    if platform == "darwin" and spec.mac:
        return spec.mac
    if platform == "win32" and spec.windows:
        return spec.windows
    return spec.command or None


def _tail(text: str | None, n: int = TAIL_LINES) -> str:
    """Ultime `n` righe non vuote di `text`."""
    if not text:
        return ""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def _kill_tree(proc: subprocess.Popen) -> None:
    """Termina il processo e i suoi figli (la shell può aver lanciato altri processi)."""
    try:
        if sys.platform == "win32":
            # /T termina anche i figli; ripiego su kill() se taskkill non riesce
            r = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if r.returncode != 0:
                proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass


class ShellActionRunner:
    """Esegue lo `ShellAction` di un comando. Rispetta il Protocol `Action`; non solleva."""

    def __init__(self, platform: str | None = None) -> None:
        self._platform = sys.platform if platform is None else platform

    def run(self, spec: ShellAction) -> ActionResult:
        cmd = select_command(spec, self._platform)
        if not cmd:
            return ActionResult(False, "Nessun comando definito per questo sistema")

        log.info("Eseguo il comando shell: %s", cmd)
        popen_kwargs: dict = {}
        if sys.platform != "win32":
            # gruppo di processi separato, così al timeout si termina anche ciò che la shell ha lanciato
            popen_kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                **popen_kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — un'azione non deve mai far cadere l'app
            log.exception("Avvio del comando shell fallito")
            return ActionResult(False, f"Impossibile avviare il comando: {exc}")

        try:
            stdout, stderr = proc.communicate(timeout=spec.timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                stdout, stderr = "", ""
            log.warning("Comando shell scaduto dopo %s s: %s", spec.timeout, cmd)
            msg = f"Tempo scaduto dopo {spec.timeout:g} s"
            tail = _tail(stderr)
            return ActionResult(False, f"{msg}\n{tail}" if tail else msg)
        except Exception as exc:  # noqa: BLE001
            _kill_tree(proc)
            log.exception("Errore durante l'esecuzione del comando shell")
            return ActionResult(False, f"Errore durante l'esecuzione: {exc}")

        code = proc.returncode
        if code != 0:
            tail = _tail(stderr) or _tail(stdout)
            log.warning("Comando shell uscito con codice %s: %s", code, cmd)
            msg = f"Codice di uscita {code}"
            return ActionResult(False, f"{msg}\n{tail}" if tail else msg)

        out = _tail(stdout, 1)
        return ActionResult(True, f"Comando eseguito: {out}" if out else "Comando eseguito")
