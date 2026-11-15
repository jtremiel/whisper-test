"""Test di voicecmd.stt con un modello finto; un test slow usa il modello vero."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from voicecmd.events import SAMPLE_RATE, Transcriber
from voicecmd.schema import SttConfig
from voicecmd.stt import FasterWhisperTranscriber, resolve_stt


@dataclass
class FakeSegment:
    text: str
    no_speech_prob: float = 0.01


class FakeModel:
    def __init__(self, segments: list[FakeSegment]) -> None:
        self.segments = segments
        self.calls: list[dict] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append({"audio": audio, **kwargs})
        return iter(self.segments), object()


class FakeFactory:
    """Registra i caricamenti; `fail_on` elenca i device su cui il caricamento solleva."""

    def __init__(self, model: FakeModel, fail_on: tuple[str, ...] = ()) -> None:
        self.model = model
        self.fail_on = fail_on
        self.loads: list[tuple[str, str, str]] = []

    def __call__(self, name: str, device: str, compute_type: str) -> FakeModel:
        self.loads.append((name, device, compute_type))
        if device in self.fail_on:
            raise RuntimeError("backend non disponibile")
        return self.model


def make(segments=(), cfg=None, platform="linux", machine="x86_64", **kw):
    model = FakeModel(list(segments))
    factory = FakeFactory(model, kw.pop("fail_on", ()))
    t = FasterWhisperTranscriber(
        cfg or SttConfig(), model_factory=factory, platform=platform, machine=machine, **kw
    )
    return t, model, factory


AUDIO = np.zeros(SAMPLE_RATE, dtype=np.float32)


# --- resolve_stt -------------------------------------------------------------

def test_resolve_auto_mac_arm64():
    assert resolve_stt(SttConfig(), "darwin", "arm64") == ("mps", "turbo", "float16")


def test_resolve_auto_mac_x86():
    assert resolve_stt(SttConfig(), "darwin", "x86_64") == ("cpu", "small", "int8")


def test_resolve_auto_windows():
    assert resolve_stt(SttConfig(), "win32", "AMD64") == ("cpu", "small", "int8")


def test_resolve_explicit_values_kept():
    cfg = SttConfig(device="cpu", model="turbo", compute_type="float32")
    assert resolve_stt(cfg, "darwin", "arm64") == ("cpu", "turbo", "float32")


def test_resolve_partial_auto():
    cfg = SttConfig(device="mps", model="small")
    assert resolve_stt(cfg, "darwin", "arm64") == ("mps", "small", "float16")
    cfg = SttConfig(device="auto", compute_type="int8_float16")
    assert resolve_stt(cfg, "darwin", "arm64") == ("mps", "turbo", "int8_float16")


# --- caricamento e ripiego ---------------------------------------------------

def test_satisfies_protocol():
    t, _, _ = make()
    assert isinstance(t, Transcriber)


def test_load_cpu_beam1():
    t, _, factory = make(platform="win32", machine="AMD64")
    assert factory.loads == [("small", "cpu", "int8")]
    assert (t.device, t.model_name, t.compute_type, t.beam_size) == ("cpu", "small", "int8", 1)


def test_load_mps_beam5():
    t, _, factory = make(platform="darwin", machine="arm64")
    assert factory.loads == [("turbo", "mps", "float16")]
    assert (t.device, t.beam_size) == ("mps", 5)


def test_mps_failure_falls_back_to_cpu(caplog):
    with caplog.at_level(logging.WARNING, logger="voicecmd.stt"):
        t, _, factory = make(platform="darwin", machine="arm64", fail_on=("mps",))
    assert factory.loads == [("turbo", "mps", "float16"), ("small", "cpu", "int8")]
    assert (t.device, t.model_name, t.compute_type, t.beam_size) == ("cpu", "small", "int8", 1)
    assert any("ripiego" in r.getMessage() for r in caplog.records)


def test_mps_failure_keeps_explicit_model():
    cfg = SttConfig(device="mps", model="base")
    t, _, factory = make(cfg=cfg, platform="darwin", machine="arm64", fail_on=("mps",))
    assert factory.loads[-1] == ("base", "cpu", "int8")


def test_cpu_failure_is_raised():
    with pytest.raises(RuntimeError):
        make(fail_on=("cpu",))


# --- transcribe --------------------------------------------------------------

def test_joins_segments():
    t, model, _ = make([FakeSegment(" Apri il"), FakeSegment(" browser. ")])
    assert t.transcribe(AUDIO) == "Apri il browser."
    call = model.calls[0]
    assert call["language"] == "it"
    assert call["beam_size"] == 1
    assert call["audio"].dtype == np.float32
    assert "hotwords" not in call
    assert call["vad_filter"] is True  # default di SttConfig


def test_vad_filter_passed():
    t, model, _ = make([FakeSegment("x")], vad_filter=True)
    t.transcribe(AUDIO)
    assert model.calls[0]["vad_filter"] is True


def test_vad_filter_from_config_and_override():
    t, model, _ = make([FakeSegment("x")], cfg=SttConfig(vad_filter=False))
    t.transcribe(AUDIO)
    assert model.calls[0]["vad_filter"] is False
    t, model, _ = make([FakeSegment("x")], cfg=SttConfig(vad_filter=False), vad_filter=True)
    t.transcribe(AUDIO)
    assert model.calls[0]["vad_filter"] is True


def test_language_passed():
    t, model, _ = make([FakeSegment("hello")], language="en")
    t.transcribe(AUDIO)
    assert model.calls[0]["language"] == "en"


def test_drops_no_speech_segments():
    segs = [FakeSegment("Apri il browser", 0.02), FakeSegment("Grazie a tutti.", 0.9)]
    t, _, _ = make(segs)
    assert t.transcribe(AUDIO) == "Apri il browser"


def test_only_silence_gives_empty_string():
    t, _, _ = make([FakeSegment("Grazie a tutti.", 0.8)])
    assert t.transcribe(AUDIO) == ""


def test_threshold_is_configurable():
    segs = [FakeSegment("ciao", 0.3)]
    t, _, _ = make(segs, no_speech_threshold=0.2)
    assert t.transcribe(AUDIO) == ""
    t, _, _ = make(segs, no_speech_threshold=0.5)
    assert t.transcribe(AUDIO) == "ciao"


def test_empty_audio_skips_model():
    t, model, _ = make([FakeSegment("non deve uscire")])
    assert t.transcribe(np.zeros(0, dtype=np.float32)) == ""
    assert model.calls == []


def test_hotwords_joined_with_spaces():
    t, model, _ = make([FakeSegment("apri chrome")])
    t.transcribe(AUDIO, hotwords=["apri il browser", "apri chrome"])
    assert model.calls[0]["hotwords"] == "apri il browser apri chrome"


def test_empty_hotwords_not_passed():
    t, model, _ = make([FakeSegment("x")])
    t.transcribe(AUDIO, hotwords=[])
    assert "hotwords" not in model.calls[0]


# --- modello vero ------------------------------------------------------------

TEST_VOICE = Path(__file__).resolve().parent.parent / "testVoice.mp3"


def _load_audio(path: Path) -> np.ndarray:
    # faster_whisper.decode_audio con PyAV 19 fallisce: decodifica diretta (da spikes/stt_bench.py).
    import av

    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks = []
    with av.open(str(path)) as c:
        for frame in c.decode(audio=0):
            for f in resampler.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
        for f in resampler.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
    return np.concatenate(chunks).astype(np.float32) / 32768.0


NOISE = (np.random.default_rng(0).standard_normal(3 * SAMPLE_RATE) * 0.01).astype(np.float32)


@pytest.mark.slow
def test_real_model_transcribes_test_voice():
    t = FasterWhisperTranscriber(SttConfig())  # auto: turbo su mps qui
    clip = _load_audio(TEST_VOICE)[: 5 * SAMPLE_RATE]
    assert t.transcribe(clip).strip()


@pytest.mark.slow
def test_real_small_cpu_silence_dropped_by_no_speech_prob():
    # T06: su audio muto Whisper allucina; con small no_speech_prob è alto e il segmento si scarta.
    t = FasterWhisperTranscriber(SttConfig(device="cpu"))
    assert t.transcribe(NOISE) == ""


@pytest.mark.slow
def test_real_auto_silence_dropped_with_vad():
    # Con turbo no_speech_prob vale 0 sul silenzio: serve il VAD.
    t = FasterWhisperTranscriber(SttConfig(), vad_filter=True)
    assert t.transcribe(NOISE) == ""
