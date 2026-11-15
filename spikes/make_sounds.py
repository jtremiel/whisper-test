"""Genera i tre suoni di feedback di voicecmd come toni sintetici.

Uso: .venv/bin/python spikes/make_sounds.py
Scrive voicecmd/ui/assets/sounds/{start,done,error}.wav (16 bit, mono, 44,1 kHz).
Solo libreria standard: si può rilanciare per rigenerare i file.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

RATE = 44100
VOLUME = 0.35
FADE_S = 0.008  # rampa di attacco/rilascio per evitare click
OUT_DIR = Path(__file__).resolve().parent.parent / "voicecmd" / "ui" / "assets" / "sounds"

# Ogni suono è una sequenza di note (frequenza Hz, durata s).
SOUNDS: dict[str, list[tuple[float, float]]] = {
    "start": [(880.0, 0.09)],                     # bip singolo acuto: inizio ascolto
    "done": [(660.0, 0.07), (990.0, 0.09)],       # due note ascendenti: eseguito
    "error": [(330.0, 0.09), (220.0, 0.12)],      # due note discendenti gravi: errore
}


def _tone(freq: float, dur: float) -> list[int]:
    n = int(RATE * dur)
    fade = int(RATE * FADE_S)
    samples = []
    for i in range(n):
        env = min(1.0, i / fade, (n - 1 - i) / fade) if fade else 1.0
        value = VOLUME * env * math.sin(2 * math.pi * freq * i / RATE)
        samples.append(int(value * 32767))
    return samples


def render(notes: list[tuple[float, float]]) -> bytes:
    samples: list[int] = []
    for freq, dur in notes:
        samples.extend(_tone(freq, dur))
    return struct.pack(f"<{len(samples)}h", *samples)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, notes in SOUNDS.items():
        path = OUT_DIR / f"{name}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(render(notes))
        dur_ms = sum(d for _, d in notes) * 1000
        print(f"scritto {path} ({dur_ms:.0f} ms)")


if __name__ == "__main__":
    main()
