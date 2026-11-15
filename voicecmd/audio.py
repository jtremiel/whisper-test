"""Cattura audio dal microfono: Recorder push-to-talk su sounddevice.

Schema di cattura ripreso da real.py (righe 119-129): il callback di PortAudio
accoda i blocchi in un buffer protetto da lock; `stop()` li concatena.

Decisioni dello spike T06 (docs/spikes/T06-mic.md):
- `keep_stream_open: true` (default): stream sempre aperto, i blocchi che arrivano
  fuori registrazione finiscono in un buffer circolare di `preroll_ms` che viene
  anteposto alla registrazione. Se lo stream cade, viene riaperto con un log.
- `keep_stream_open: false`: lo stream si apre a `start()` e si chiude a `stop()`;
  all'avvio viene aperto e chiuso una volta per assorbire la lenta prima apertura
  di CoreAudio (~3,3 s).
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Callable, Protocol

import numpy as np

from voicecmd.events import SAMPLE_RATE
from voicecmd.schema import AudioConfig

log = logging.getLogger(__name__)

BLOCKSIZE = 512  # campioni per blocco (32 ms a 16 kHz), come nello spike T06

AudioCallback = Callable[[np.ndarray, int, Any, Any], None]


class InputStreamLike(Protocol):
    """Parte di `sounddevice.InputStream` usata dal Recorder."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


# stream_factory(callback, samplerate, blocksize) -> stream non ancora avviato
StreamFactory = Callable[[AudioCallback, int, int], InputStreamLike]


def sounddevice_stream(callback: AudioCallback, samplerate: int, blocksize: int) -> InputStreamLike:
    """Crea uno `sd.InputStream` mono float32 (import pigro: i test non toccano PortAudio)."""
    import sounddevice as sd

    return sd.InputStream(
        samplerate=samplerate,
        channels=1,
        dtype="float32",
        blocksize=blocksize,
        callback=callback,
    )


def rms(audio: np.ndarray) -> float:
    """Valore efficace dell'audio; 0.0 per un array vuoto."""
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


class SoundDeviceRecorder:
    """Recorder (vedi `events.Recorder`) su microfono, 16 kHz mono float32."""

    def __init__(
        self,
        cfg: AudioConfig | None = None,
        *,
        stream_factory: StreamFactory | None = None,
        samplerate: int = SAMPLE_RATE,
        blocksize: int = BLOCKSIZE,
    ) -> None:
        self.cfg = cfg if cfg is not None else AudioConfig()
        self._factory: StreamFactory = stream_factory or sounddevice_stream
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._preroll_samples = (
            int(self.cfg.preroll_ms * samplerate / 1000) if self.cfg.keep_stream_open else 0
        )

        self._lock = threading.Lock()         # protegge _chunks, _preroll, _recording
        self._chunks: list[np.ndarray] = []   # blocchi della registrazione in corso
        self._preroll: deque[np.ndarray] = deque()  # buffer circolare (solo warm)
        self._preroll_len = 0                 # campioni presenti in _preroll
        self._recording = False
        self._stream: InputStreamLike | None = None

        self._prepare()

    # --- ciclo di vita dello stream ---

    def _prepare(self) -> None:
        """All'avvio: in warm apre lo stream; in cold lo apre e chiude una volta per scaldarlo."""
        try:
            if self.cfg.keep_stream_open:
                self._open_stream()
            else:
                stream = self._factory(self._callback, self.samplerate, self.blocksize)
                try:
                    stream.start()
                    stream.stop()
                finally:
                    stream.close()
        except Exception:
            # Non blocca l'avvio dell'app: si riprova a start()
            log.exception("Impossibile aprire il microfono all'avvio; nuovo tentativo alla registrazione")
            self._stream = None

    def _open_stream(self) -> None:
        stream = self._factory(self._callback, self.samplerate, self.blocksize)
        try:
            stream.start()
        except Exception:
            _safe_close(stream)
            raise
        self._stream = stream

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            _safe_close(stream, stop=True)

    def _stream_alive(self) -> bool:
        if self._stream is None:
            return False
        # sd.InputStream espone `active`; gli stream finti possono non averlo
        return bool(getattr(self._stream, "active", True))

    def close(self) -> None:
        """Chiude definitivamente lo stream (all'uscita dell'app)."""
        with self._lock:
            self._recording = False
            self._chunks = []
            self._clear_preroll()
        self._close_stream()

    # --- callback di PortAudio (thread audio) ---

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            log.warning("Stato dello stream audio: %s", status)
        samples = np.array(indata[:, 0] if indata.ndim > 1 else indata, dtype=np.float32, copy=True)
        with self._lock:
            if self._recording:
                self._chunks.append(samples)
            elif self._preroll_samples > 0:
                self._preroll.append(samples)
                self._preroll_len += len(samples)
                # tiene solo gli ultimi `_preroll_samples` campioni
                while self._preroll and self._preroll_len - len(self._preroll[0]) >= self._preroll_samples:
                    self._preroll_len -= len(self._preroll.popleft())

    def _clear_preroll(self) -> None:
        self._preroll.clear()
        self._preroll_len = 0

    # --- Recorder ---

    def start(self) -> None:
        """Inizia a registrare. Solleva se il microfono non si può aprire."""
        if self.cfg.keep_stream_open:
            if not self._stream_alive():
                if self._stream is not None:
                    log.warning("Lo stream del microfono è caduto: lo riapro")
                self._close_stream()
                with self._lock:
                    self._clear_preroll()
                self._open_stream()
            with self._lock:
                pre = list(self._preroll)
                excess = self._preroll_len - self._preroll_samples
                if excess > 0 and pre:
                    pre[0] = pre[0][excess:]
                self._chunks = pre
                self._clear_preroll()
                self._recording = True
        else:
            with self._lock:
                self._chunks = []
                self._recording = True
            try:
                self._close_stream()
                self._open_stream()
            except Exception:
                with self._lock:
                    self._recording = False
                raise

    def stop(self) -> np.ndarray:
        """Termina e restituisce l'audio; array vuoto se silenzio o se non si stava registrando."""
        with self._lock:
            was_recording = self._recording
            self._recording = False
            chunks, self._chunks = self._chunks, []
        if not self.cfg.keep_stream_open:
            self._close_stream()
        if not was_recording or not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunks).astype(np.float32, copy=False)
        level = rms(audio)
        if level < self.cfg.silence_rms:
            log.info("Audio scartato: RMS %.4f sotto la soglia %.4f", level, self.cfg.silence_rms)
            return np.zeros(0, dtype=np.float32)
        return audio


def _safe_close(stream: InputStreamLike, stop: bool = False) -> None:
    """Ferma e chiude lo stream ignorando gli errori (lo stream può essere già morto)."""
    if stop:
        try:
            stream.stop()
        except Exception:
            log.debug("Errore fermando lo stream audio", exc_info=True)
    try:
        stream.close()
    except Exception:
        log.debug("Errore chiudendo lo stream audio", exc_info=True)
