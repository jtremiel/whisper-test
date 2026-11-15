"""Verifica che le dipendenze dell'app siano importabili."""
import importlib
import sys

import pytest

MODULES = [
    "numpy", "sounddevice", "faster_whisper", "ctranslate2", "rapidfuzz",
    "pydantic", "yaml", "platformdirs", "pynput", "PySide6.QtWidgets",
    "pyperclip", "voicecmd",
]
if sys.platform == "darwin":
    MODULES += ["Quartz", "Cocoa", "AVFoundation", "ApplicationServices"]


@pytest.mark.parametrize("name", MODULES)
def test_import(name: str) -> None:
    importlib.import_module(name)
