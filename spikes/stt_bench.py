"""T05 - benchmark dei modelli faster-whisper su CPU (int8).

Uso: .venv/bin/python spikes/stt_bench.py [file_audio] [--extra]
Gli spezzoni restano in memoria: nessun file audio viene scritto.
"""
import statistics
import sys
import time

import av
import numpy as np
from faster_whisper import WhisperModel

SR = 16000
MODELS = ["turbo", "small", "base"]
ROUNDS = 5  # media su 5 giri, escluso il primo (warm-up)


def load_audio(path: str) -> np.ndarray:
    # faster_whisper.decode_audio con av 19 fallisce (metadata_errors): decodifica diretta con PyAV.
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SR)
    chunks = []
    with av.open(path) as c:
        for frame in c.decode(audio=0):
            for f in resampler.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
        for f in resampler.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def pick_clip(audio: np.ndarray, seconds: float) -> np.ndarray:
    """Spezzone di `seconds` che parte dal primo parlato (RMS a finestre di 100 ms)."""
    win = SR // 10
    n = len(audio) // win
    rms = np.sqrt((audio[: n * win].reshape(n, win) ** 2).mean(axis=1))
    idx = np.flatnonzero(rms > 0.02)
    start = int(idx[0]) * win if len(idx) else 0
    return audio[start : start + int(seconds * SR)]


def run(model, clip, **kw):
    segs, _ = model.transcribe(clip, language="it", **kw)
    segs = list(segs)  # il generatore e' pigro: la trascrizione avviene qui
    text = " ".join(s.text.strip() for s in segs)
    nsp = [round(s.no_speech_prob, 3) for s in segs]
    return text, nsp


def bench(model, clip, **kw):
    times, text, nsp = [], "", []
    for i in range(ROUNDS + 1):
        t = time.perf_counter()
        text, nsp = run(model, clip, **kw)
        dt = time.perf_counter() - t
        if i > 0:
            times.append(dt)
    return statistics.mean(times), text, nsp


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    extra = "--extra" in sys.argv
    audio = load_audio(args[0] if args else "testVoice.mp3")
    print(f"audio totale: {len(audio) / SR:.1f} s")
    clips = {"3s": pick_clip(audio, 3), "15s": pick_clip(audio, 15)}
    for name, c in clips.items():
        print(f"clip {name}: {len(c) / SR:.1f} s")
    for m in MODELS:
        t = time.perf_counter()
        model = WhisperModel(m, device="cpu", compute_type="int8")
        load = time.perf_counter() - t
        print(f"\n== {m}  caricamento {load:.2f} s")
        for name, c in clips.items():
            avg, text, nsp = bench(model, c)
            print(f"[{m} {name}] {avg:.2f} s  no_speech_prob={nsp}\n   {text}")
        if extra:
            c = clips["3s"]
            for label, kw in [
                ("beam1", dict(beam_size=1)),
                ("beam5", dict(beam_size=5)),
                ("beam1+vad", dict(beam_size=1, vad_filter=True)),
                ("beam5+vad", dict(beam_size=5, vad_filter=True)),
                ("beam1+hotwords", dict(beam_size=1, hotwords="Chrome Spotify")),
            ]:
                avg, text, _ = bench(model, c, **kw)
                print(f"[{m} 3s {label}] {avg:.2f} s | {text}")


if __name__ == "__main__":
    main()
