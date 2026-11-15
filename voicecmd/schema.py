"""Modelli pydantic della configurazione (struttura del PRD §6)."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    """Base: i campi sconosciuti vengono rifiutati."""
    model_config = ConfigDict(extra="forbid")


class SttConfig(_Strict):
    # Spike T05. "auto" viene risolto dal Transcriber (T09) in base al dispositivo:
    #   device auto  -> "mps" su macOS Apple Silicon, altrimenti "cpu"; se MPS non carica, ripiego su "cpu"
    #   model auto   -> "turbo" su mps, "small" su cpu
    #   compute auto -> "float16" su mps, "int8" su cpu
    device: Literal["auto", "cpu", "mps"] = "auto"
    model: str = "auto"
    compute_type: str = "auto"


class TriggerConfig(_Strict):
    """Un trigger: esattamente uno tra `hotkey` e `mouse_button`."""
    hotkey: str | None = None  # formato pynput, es. "<ctrl>+<alt>+space"
    mouse_button: Literal["middle", "x1", "x2"] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "TriggerConfig":
        if (self.hotkey is None) == (self.mouse_button is None):
            raise ValueError("indicare esattamente uno tra 'hotkey' e 'mouse_button'")
        if self.hotkey is not None and not self.hotkey.strip():
            raise ValueError("'hotkey' non può essere vuoto")
        return self


def _default_command_trigger() -> TriggerConfig:
    # Provvisorio: lo spike T04 fissa i binding di default.
    return TriggerConfig(hotkey="<ctrl>+<alt>+space")


def _default_dictation_trigger() -> TriggerConfig:
    # Provvisorio: lo spike T04 fissa i binding di default.
    return TriggerConfig(mouse_button="x2")


class TriggersConfig(_Strict):
    command: TriggerConfig = Field(default_factory=_default_command_trigger)
    dictation: TriggerConfig = Field(default_factory=_default_dictation_trigger)


class MatchingConfig(_Strict):
    threshold: float = Field(80, ge=0, le=100)  # punteggio minimo (0-100)
    margin: float = Field(5, ge=0, le=100)      # distacco minimo dal secondo comando


class FeedbackConfig(_Strict):
    tray: bool = True
    sounds: bool = True
    overlay: bool = True
    notifications: bool = True


class AudioConfig(_Strict):
    silence_rms: float = Field(0.005, ge=0)  # sotto questa soglia l'audio è scartato (come real.py)
    keep_stream_open: bool = True            # T06: microfono sempre aperto, non perde l'inizio della frase
    preroll_ms: int = Field(300, ge=0)       # usato solo con keep_stream_open


class OpenAction(_Strict):
    type: Literal["open"]
    target: str = Field(min_length=1)  # URL, file o app da aprire


class ShellAction(_Strict):
    type: Literal["shell"]
    command: str | None = None  # comando unico per entrambi i sistemi
    mac: str | None = None
    windows: str | None = None
    timeout: float = Field(30, gt=0)  # secondi

    @model_validator(mode="after")
    def _has_command(self) -> "ShellAction":
        if not any((self.command, self.mac, self.windows)):
            raise ValueError("indicare 'command' oppure 'mac' / 'windows'")
        return self


Action = Annotated[Union[OpenAction, ShellAction], Field(discriminator="type")]


class Command(_Strict):
    name: str = Field(min_length=1)
    phrases: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    action: Action


class Config(_Strict):
    language: str = "it"
    stt: SttConfig = Field(default_factory=SttConfig)
    triggers: TriggersConfig = Field(default_factory=TriggersConfig)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    commands: list[Command] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> "Config":
        seen: set[str] = set()
        for c in self.commands:
            if c.name in seen:
                raise ValueError(f"nome di comando duplicato: '{c.name}'")
            seen.add(c.name)
        return self
