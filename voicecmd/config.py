"""Configurazione: percorso del file, primo avvio, caricamento e validazione."""
from __future__ import annotations

import os
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_dir
from pydantic import ValidationError

from .schema import Config

CONFIG_FILENAME = "config.yaml"

# Traduzione dei messaggi pydantic più comuni (per tipo di errore).
_PYDANTIC_MESSAGES: dict[str, str] = {
    "missing": "campo obbligatorio mancante",
    "extra_forbidden": "campo sconosciuto",
    "string_type": "deve essere un testo",
    "string_too_short": "non può essere vuoto",
    "too_short": "deve contenere almeno un elemento",
    "list_type": "deve essere una lista",
    "bool_type": "deve essere true o false",
    "bool_parsing": "deve essere true o false",
    "int_type": "deve essere un numero intero",
    "int_parsing": "deve essere un numero intero",
    "int_from_float": "deve essere un numero intero",
    "float_type": "deve essere un numero",
    "float_parsing": "deve essere un numero",
    "greater_than": "valore troppo basso",
    "greater_than_equal": "valore troppo basso",
    "less_than": "valore troppo alto",
    "less_than_equal": "valore troppo alto",
    "model_type": "deve essere una sezione (chiave: valore)",
    "model_attributes_type": "deve essere una sezione (chiave: valore)",
    "dict_type": "deve essere una sezione (chiave: valore)",
    "literal_error": "valore non ammesso",
    "union_tag_invalid": "tipo di azione sconosciuto",
    "union_tag_not_found": "manca il campo 'type' dell'azione",
}


class ConfigError(Exception):
    """Configurazione non leggibile o non valida; il messaggio è per l'utente."""


def config_path() -> Path:
    """Percorso del file di configurazione dell'utente."""
    return Path(user_config_dir("voicecmd", appauthor=False)) / CONFIG_FILENAME


def default_config_text() -> str:
    """Contenuto del modello `default_config.yaml` incluso nel package."""
    return resources.files("voicecmd").joinpath("default_config.yaml").read_text(encoding="utf-8")


def ensure_config(path: Path | None = None) -> Path:
    """Crea il file dal modello se non esiste ancora; restituisce il percorso."""
    path = Path(path) if path is not None else config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default_config_text(), encoding="utf-8")
    return path


def _format_loc(loc: tuple[Any, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = _format_loc(tuple(err.get("loc", ())))
        typ = err.get("type", "")
        if typ == "value_error":
            # Messaggi dei validatori di schema.py, già in italiano.
            msg = str(err.get("ctx", {}).get("error", err.get("msg", "")))
        else:
            msg = _PYDANTIC_MESSAGES.get(typ, err.get("msg", ""))
            if typ == "literal_error" and "ctx" in err:
                msg += f" (ammessi: {err['ctx'].get('expected')})"
            elif typ in ("greater_than", "greater_than_equal", "less_than", "less_than_equal") and "ctx" in err:
                limit = next(iter(err["ctx"].values()), None)
                msg += f" (limite: {limit})"
            elif typ == "union_tag_invalid" and "ctx" in err:
                msg += f" '{err['ctx'].get('tag')}' (ammessi: {err['ctx'].get('expected_tags')})"
        where = f"'{loc}'" if loc else "radice del file"
        lines.append(f"- {where}: {msg}")
    return "\n".join(lines)


def load_config(path: Path | None = None) -> Config:
    """Legge e valida il file. Solleva `ConfigError` con un messaggio leggibile."""
    path = Path(path) if path is not None else config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"File di configurazione non trovato: {path}") from None
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"Impossibile leggere {path}: {e}") from None

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (riga {mark.line + 1}, colonna {mark.column + 1})" if mark is not None else ""
        problem = getattr(e, "problem", None) or str(e)
        raise ConfigError(f"Errore di sintassi YAML in {path}{where}: {problem}") from None

    if data is None:
        data = {}  # file vuoto: tutti i valori predefiniti
    if not isinstance(data, dict):
        raise ConfigError(f"Configurazione non valida in {path}: il file deve contenere sezioni 'chiave: valore'")

    try:
        return Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"Configurazione non valida in {path}:\n{_format_validation_error(e)}") from None


def open_in_editor(path: Path | None = None) -> None:
    """Apre il file con l'applicazione predefinita del sistema."""
    path = Path(path) if path is not None else config_path()
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
