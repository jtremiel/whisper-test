"""Trascrizione con faster-whisper (decisioni dello spike T05, docs/spikes/T05-stt.md)."""
from __future__ import annotations

import logging
import platform as _platform
import sys
from typing import Any, Callable

import numpy as np

from voicecmd.schema import SttConfig

log = logging.getLogger(__name__)

# Sopra questa probabilità un segmento è considerato senza parlato (come real.py).
# Sul parlato vero vale 0,00-0,10 (T05/T09); da tarare in T24.
# Funziona con small (silenzio 0,85+ su mps); con turbo vale 0,0 anche sul silenzio.
DEFAULT_NO_SPEECH_THRESHOLD = 0.6

# Ripiego quando il caricamento su MPS fallisce.
FALLBACK_DEVICE = "cpu"
FALLBACK_MODEL = "small"
FALLBACK_COMPUTE = "int8"

# beam 1 su CPU (più veloce, stesso testo); beam 5 su MPS (small con beam 1 sbagliava).
_BEAM_SIZE = {"cpu": 1, "mps": 5}

ModelFactory = Callable[..., Any]


def resolve_stt(cfg: SttConfig, platform: str, machine: str) -> tuple[str, str, str]:
    """Risolve i valori `auto` di `SttConfig` in (device, model, compute_type).

    `platform` è come `sys.platform`, `machine` come `platform.machine()`.
    """
    device = cfg.device
    if device == "auto":
        device = "mps" if platform == "darwin" and machine == "arm64" else "cpu"
    model = cfg.model
    if model == "auto":
        model = "turbo" if device == "mps" else "small"
    compute = cfg.compute_type
    if compute == "auto":
        compute = "float16" if device == "mps" else "int8"
    return device, model, compute


def _default_factory(model: str, device: str, compute_type: str) -> Any:
    # Import qui: il modulo si importa (e si testa) senza caricare ctranslate2.
    from faster_whisper import WhisperModel

    return WhisperModel(model, device=device, compute_type=compute_type)


class FasterWhisperTranscriber:
    """`Transcriber` su faster-whisper; il modello viene caricato nel costruttore e tenuto in memoria."""

    def __init__(
        self,
        cfg: SttConfig,
        language: str = "it",
        no_speech_threshold: float = DEFAULT_NO_SPEECH_THRESHOLD,
        model_factory: ModelFactory | None = None,
        platform: str | None = None,
        machine: str | None = None,
        vad_filter: bool | None = None,
    ) -> None:
        # vad_filter: None = valore di cfg.vad_filter (default acceso, decisione dell'utente dopo T09).
        # Con turbo no_speech_prob vale sempre 0, quindi senza VAD il rumore produce allucinazioni.
        self.language = language
        self.vad_filter = cfg.vad_filter if vad_filter is None else vad_filter
        self.no_speech_threshold = no_speech_threshold
        factory = model_factory or _default_factory
        device, model, compute = resolve_stt(
            cfg,
            platform if platform is not None else sys.platform,
            machine if machine is not None else _platform.machine(),
        )
        try:
            self._model = factory(model, device=device, compute_type=compute)
        except Exception:
            if device != "mps":
                raise
            # MPS è sperimentale in ctranslate2: si riprova su CPU.
            fb_model = model if cfg.model != "auto" else FALLBACK_MODEL
            log.warning(
                "Caricamento di '%s' su mps (%s) fallito, ripiego su %s con '%s'/%s",
                model, compute, FALLBACK_DEVICE, fb_model, FALLBACK_COMPUTE,
                exc_info=True,
            )
            device, model, compute = FALLBACK_DEVICE, fb_model, FALLBACK_COMPUTE
            self._model = factory(model, device=device, compute_type=compute)
        self.device, self.model_name, self.compute_type = device, model, compute
        self.beam_size = _BEAM_SIZE[device]
        log.info("Modello STT '%s' caricato su %s (%s), beam %d", model, device, compute, self.beam_size)

    def transcribe(self, audio: np.ndarray, hotwords: list[str] | None = None) -> str:
        """Trascrive `audio` (float32 mono 16 kHz). Stringa vuota se non c'è parlato."""
        if audio is None or audio.size == 0:
            return ""
        kwargs: dict[str, Any] = {
            "language": self.language,
            "beam_size": self.beam_size,
            "vad_filter": self.vad_filter,
        }
        if hotwords:
            kwargs["hotwords"] = " ".join(hotwords)
        segments, _info = self._model.transcribe(np.asarray(audio, dtype=np.float32), **kwargs)
        parts: list[str] = []
        for seg in segments:  # generatore pigro: la trascrizione avviene qui
            if seg.no_speech_prob > self.no_speech_threshold:
                log.debug("Segmento scartato (no_speech_prob %.2f): %r", seg.no_speech_prob, seg.text)
                continue
            text = seg.text.strip()
            if text:
                parts.append(text)
        return " ".join(parts)
