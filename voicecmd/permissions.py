"""Controllo dei permessi macOS: Microfono, Accessibilità, Monitoraggio input.

Nessuna funzione di questo modulo apre il microfono o fa comparire richieste di
permesso: si usano solo le API di sola lettura (preflight / authorizationStatus).
Su Windows e Linux `check_permissions()` restituisce sempre una lista vuota.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

# Stati di un permesso mancante
DENIED = "denied"      # il sistema dice esplicitamente che manca
UNKNOWN = "unknown"    # il controllo è fallito: non sappiamo se c'è

MICROPHONE = "Microfono"
ACCESSIBILITY = "Accessibilità"
INPUT_MONITORING = "Monitoraggio input"

_PRIVACY = "Impostazioni di Sistema > Privacy e sicurezza > "

# nome -> (spiegazione, percorso nelle Impostazioni, URL che apre il pannello)
_INFO: dict[str, tuple[str, str, str]] = {
    MICROPHONE: (
        "Serve per registrare la voce mentre tieni premuto il trigger.",
        _PRIVACY + "Microfono",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    ),
    ACCESSIBILITY: (
        "Serve per incollare il testo dettato e per bloccare il pulsante del mouse "
        "usato come trigger (così non fa \"indietro\" nel browser).",
        _PRIVACY + "Accessibilità",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    ),
    INPUT_MONITORING: (
        "Serve per accorgersi della pressione dei tasti e dei pulsanti del mouse "
        "usati come trigger.",
        _PRIVACY + "Monitoraggio input",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
    ),
}

# Un controllo restituisce True se il permesso c'è, False se manca.
# Se solleva un'eccezione il permesso diventa "stato sconosciuto".
Check = Callable[[], bool]


@dataclass(frozen=True)
class MissingPermission:
    """Un permesso macOS mancante (o non verificabile)."""
    name: str            # es. "Microfono"
    explanation: str     # a cosa serve, in italiano
    settings_path: str   # es. "Impostazioni di Sistema > Privacy e sicurezza > Microfono"
    settings_url: str    # URL x-apple.systempreferences che apre il pannello giusto
    executable: str      # app o eseguibile da autorizzare nel pannello
    status: str          # DENIED oppure UNKNOWN

    @property
    def message(self) -> str:
        """Testo completo da mostrare all'utente."""
        if self.status == UNKNOWN:
            head = f"Impossibile verificare il permesso '{self.name}'."
        else:
            head = f"Manca il permesso '{self.name}'."
        return (
            f"{head} {self.explanation} Apri {self.settings_path} e abilita "
            f"\"{self.executable}\", poi riavvia {self.executable} e voicecmd."
        )


# ---------------------------------------------------------------------------
# Controlli reali (solo macOS; gli import stanno dentro le funzioni)

def _check_microphone() -> bool:
    import AVFoundation

    status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
        AVFoundation.AVMediaTypeAudio
    )
    # NotDetermined: l'app non l'ha ancora chiesto; macOS mostrerà da solo la
    # richiesta alla prima registrazione, quindi non lo segnaliamo come mancante.
    return status in (
        AVFoundation.AVAuthorizationStatusAuthorized,
        AVFoundation.AVAuthorizationStatusNotDetermined,
    )


def _check_accessibility() -> bool:
    from ApplicationServices import AXIsProcessTrusted

    return bool(AXIsProcessTrusted())


def _check_input_monitoring() -> bool:
    import Quartz

    return bool(Quartz.CGPreflightListenEventAccess())


def default_checks() -> dict[str, Check]:
    """Controlli reali, nell'ordine in cui vengono mostrati."""
    return {
        MICROPHONE: _check_microphone,
        ACCESSIBILITY: _check_accessibility,
        INPUT_MONITORING: _check_input_monitoring,
    }


# ---------------------------------------------------------------------------
# Quale eseguibile autorizzare

def _libproc():
    import ctypes

    return ctypes.CDLL("/usr/lib/libproc.dylib")


def _proc_path(pid: int) -> str | None:
    """Percorso dell'eseguibile del processo `pid` (proc_pidpath di libproc)."""
    import ctypes

    buf = ctypes.create_string_buffer(4096)  # PROC_PIDPATHINFO_MAXSIZE
    n = _libproc().proc_pidpath(ctypes.c_int(pid), buf, ctypes.c_uint32(len(buf)))
    return buf.value.decode("utf-8", "replace") if n > 0 else None


def _parent_pid(pid: int) -> int | None:
    """PID del padre (proc_pidinfo con PROC_PIDTBSDINFO; pbi_ppid è all'offset 16)."""
    import ctypes

    buf = ctypes.create_string_buffer(136)  # sizeof(struct proc_bsdinfo)
    n = _libproc().proc_pidinfo(ctypes.c_int(pid), ctypes.c_int(3), ctypes.c_uint64(0),
                                buf, ctypes.c_int(len(buf)))
    if n != len(buf):
        return None
    return int.from_bytes(buf.raw[16:20], sys.byteorder)


def _responsible_pid(pid: int) -> int | None:
    """Processo "responsabile" per i permessi (quello che macOS usa nel pannello).

    API privata di libsystem: se manca o fallisce si ripiega sulla catena dei padri.
    """
    import ctypes

    fn = getattr(ctypes.CDLL(None), "responsibility_get_pid_responsible_for_pid", None)
    if fn is None:
        return None
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_int]
    r = fn(pid)
    return r if r > 0 else None


def app_bundle(path: str) -> str | None:
    """Il bundle .app più esterno che contiene `path`, oppure None.

    '/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper.app/...'
    -> '/Applications/Visual Studio Code.app'
    """
    idx = path.find(".app/")
    if idx < 0:
        return path if path.endswith(".app") else None
    return path[: idx + len(".app")]


def _display(bundle: str) -> str:
    """'/Applications/Visual Studio Code.app' -> 'Visual Studio Code'."""
    return os.path.basename(bundle)[: -len(".app")]


def _is_python(path: str) -> bool:
    return "Python.framework" in path or os.path.basename(path).lower().startswith("python")


def find_executable_to_authorize(
    pid: int | None = None,
    proc_path: Callable[[int], str | None] = _proc_path,
    parent_pid: Callable[[int], int | None] = _parent_pid,
    responsible_pid: Callable[[int], int | None] = _responsible_pid,
) -> str:
    """Nome dell'app (o percorso dell'eseguibile) da autorizzare nelle Impostazioni.

    macOS attribuisce i permessi all'app "responsabile": il terminale, VS Code o
    un altro IDE da cui è partito l'interprete. Si prova prima l'API del processo
    responsabile, poi si risale la catena dei padri fino all'ultimo bundle .app
    (escluso l'interprete Python stesso). Se non si trova un'app si indica
    l'interprete Python.
    """
    if pid is None:
        pid = os.getpid()
    fallback = os.path.realpath(sys.executable) if sys.executable else "python"

    try:
        rpid = responsible_pid(pid)
        if rpid is not None and rpid != pid:
            path = proc_path(rpid)
            bundle = app_bundle(path) if path else None
            if bundle and not _is_python(bundle):
                return _display(bundle)
            if path and not _is_python(path):
                return path
    except Exception as exc:  # noqa: BLE001
        log.debug("processo responsabile non determinabile: %r", exc)

    try:
        found: str | None = None
        seen: set[int] = set()
        cur = parent_pid(pid)
        # risale fino a launchd (pid 1): l'ultima app trovata è quella più in alto
        while cur is not None and cur > 1 and cur not in seen:
            seen.add(cur)
            path = proc_path(cur)
            bundle = app_bundle(path) if path else None
            if bundle and not _is_python(bundle):
                found = bundle
            cur = parent_pid(cur)
        if found:
            return _display(found)
    except Exception as exc:  # noqa: BLE001
        log.debug("catena dei processi padre non leggibile: %r", exc)

    return fallback


# ---------------------------------------------------------------------------

def check_permissions(
    platform: str | None = None,
    checks: dict[str, Check] | None = None,
    executable: str | Callable[[], str] | None = None,
) -> list[MissingPermission]:
    """Elenca i permessi macOS mancanti; lista vuota se tutto è a posto o non su Mac.

    `checks` ed `executable` servono ai test per sostituire i controlli reali.
    Un controllo che solleva un'eccezione produce un permesso con stato UNKNOWN.
    """
    if (platform or sys.platform) != "darwin":
        return []
    if checks is None:
        checks = default_checks()

    results: list[tuple[str, str]] = []
    for name, check in checks.items():
        try:
            ok = bool(check())
        except Exception as exc:  # noqa: BLE001
            log.warning("Controllo del permesso '%s' fallito: %r", name, exc)
            results.append((name, UNKNOWN))
            continue
        if not ok:
            results.append((name, DENIED))
    if not results:
        return []

    if executable is None:
        executable = find_executable_to_authorize
    try:
        exe = executable() if callable(executable) else executable
    except Exception as exc:  # noqa: BLE001
        log.warning("Eseguibile da autorizzare non determinabile: %r", exc)
        exe = os.path.realpath(sys.executable) if sys.executable else "python"

    missing: list[MissingPermission] = []
    for name, status in results:
        explanation, path, url = _INFO.get(name, ("", _PRIVACY + name, ""))
        missing.append(MissingPermission(name, explanation, path, url, exe, status))
    return missing
