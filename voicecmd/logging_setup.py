"""Log di voicecmd: file a rotazione nella cartella dei log dell'utente, più stderr.

Le eccezioni non gestite (main thread, slot Qt e thread secondari) finiscono nel log
invece di chiudere l'app. Il log resta sul computer: contiene i testi trascritti.
"""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from platformdirs import user_log_dir

LOG_FILE_NAME = "voicecmd.log"
MAX_BYTES = 1_000_000  # circa 1 MB per file
BACKUP_COUNT = 3       # voicecmd.log.1 … .3
FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"

log = logging.getLogger("voicecmd")

# Gestori installati da setup_logging, rimossi alla chiamata successiva (test, riconfigurazione).
_installed: list[logging.Handler] = []


def log_dir() -> Path:
    return Path(user_log_dir("voicecmd", appauthor=False))


def log_path(directory: Path | None = None) -> Path:
    return (directory if directory is not None else log_dir()) / LOG_FILE_NAME


def setup_logging(
    directory: Path | None = None,
    level: int = logging.INFO,
    stderr: bool = True,
    install_hooks: bool = True,
) -> Path:
    """Configura il logger radice e restituisce il percorso del file di log.

    Se la cartella non è scrivibile si continua solo su stderr (mai un errore fatale).
    """
    root = logging.getLogger()
    for h in _installed:
        root.removeHandler(h)
        h.close()
    _installed.clear()

    fmt = logging.Formatter(FORMAT)
    path = log_path(directory)
    file_error: OSError | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    except OSError as e:
        file_error = e
    else:
        fh.setFormatter(fmt)
        _installed.append(fh)
    if stderr:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        _installed.append(sh)
    for h in _installed:
        root.addHandler(h)
    root.setLevel(level)
    if file_error is not None:
        log.warning("Log su file non disponibile (%s): solo stderr", file_error)
    if install_hooks:
        install_exception_hooks()
    return path


def _excepthook(exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    log.critical("Eccezione non gestita", exc_info=(exc_type, exc, tb))


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread is not None else "?"
    log.critical("Eccezione non gestita nel thread %s", name,
                 exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def install_exception_hooks() -> None:
    """Le eccezioni non gestite vanno nel log. PySide6 passa da sys.excepthook anche per
    gli errori negli slot, e dopo il log il loop di Qt continua."""
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
