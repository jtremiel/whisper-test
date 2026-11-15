"""T05 bis - faster-whisper su backend MPS (sperimentale) contro CPU.

Uso: .venv/bin/python spikes/stt_bench_mps.py [file_audio]
"""
import sys
import time

from faster_whisper import WhisperModel

sys.path.insert(0, "spikes")
from stt_bench import bench, load_audio, pick_clip, SR  # noqa: E402

CASES = [
    ("turbo", "mps", "float16"),
    ("turbo", "mps", "int8_float16"),
    ("small", "mps", "float16"),
    ("small", "mps", "int8_float16"),
    ("turbo", "cpu", "int8"),  # riferimento
    ("small", "cpu", "int8"),  # riferimento
]


def main() -> None:
    audio = load_audio(sys.argv[1] if len(sys.argv) > 1 else "testVoice.mp3")
    clips = {"3s": pick_clip(audio, 3), "15s": pick_clip(audio, 15)}
    for m, dev, ct in CASES:
        try:
            t = time.perf_counter()
            model = WhisperModel(m, device=dev, compute_type=ct)
            load = time.perf_counter() - t
        except Exception as e:  # noqa: BLE001
            print(f"\n== {m} {dev} {ct}: ERRORE caricamento: {e}")
            continue
        print(f"\n== {m} {dev} {ct}  caricamento {load:.2f} s")
        for name, c in clips.items():
            try:
                for beam in (1, 5):
                    avg, text, nsp = bench(model, c, beam_size=beam)
                    print(f"[{m} {dev} {ct} {name} beam{beam}] {avg:.2f} s nsp={nsp}\n   {text}")
            except Exception as e:  # noqa: BLE001
                print(f"[{m} {dev} {ct} {name}] ERRORE: {e}")
        del model


if __name__ == "__main__":
    main()
