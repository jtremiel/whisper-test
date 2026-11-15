"""Spike T06: ritardo di apertura del microfono.

Modalità:
  cold  apre lo stream alla pressione di Invio (come farebbe un Recorder "a richiesta").
  warm  tiene lo stream sempre aperto con un buffer circolare (pre-roll) e, alla
        pressione di Invio, antepone il pre-roll alla registrazione.

Uso:
  .venv/bin/python spikes/mic_latency.py --mode cold --runs 5
  .venv/bin/python spikes/mic_latency.py --mode warm --runs 5 --preroll-ms 300
  .venv/bin/python spikes/mic_latency.py --mode cold --runs 3 --auto   # senza Invio, senza parlare
  .venv/bin/python spikes/mic_latency.py --mode cold --runs 5 --key    # trigger = Shift (richiede Monitoraggio input)
"""
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SR = 16000


def default_out() -> Path:
    # Fuori dal repo: i wav contengono la voce dell'utente.
    return Path(tempfile.gettempdir()) / "voicecmd-spikes" / "mic"


def save_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


class Capture:
    """Callback che raccoglie blocchi con il loro istante di arrivo."""

    def __init__(self, rms_threshold: float):
        self.lock = threading.Lock()
        self.thr = rms_threshold
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.blocks: list[np.ndarray] = []
            self.t0 = None
            self.t_first = None
            self.t_loud = None
            self.recording = False

    def arm(self, t0: float) -> None:
        with self.lock:
            self.blocks, self.t_first, self.t_loud = [], None, None
            self.t0 = t0
            self.recording = True

    def disarm(self) -> None:
        with self.lock:
            self.recording = False

    def callback(self, indata, frames, time_info, status) -> None:
        now = time.perf_counter()
        if status:
            print(f"  [avviso stream] {status}", file=sys.stderr)
        block = indata[:, 0].copy()
        with self.lock:
            if not self.recording:
                return
            if self.t_first is None:
                self.t_first = now
            if self.t_loud is None and float(np.sqrt(np.mean(block**2))) > self.thr:
                self.t_loud = now
            self.blocks.append(block)


def wait_shift(label: str) -> None:
    """Attende una pressione di Shift (qualunque finestra) via pynput."""
    from pynput import keyboard

    ev = threading.Event()

    def on_press(key):
        if key in (keyboard.Key.shift, keyboard.Key.shift_r):
            ev.set()
            return False

    print(f"\n{label} - premi Shift e parla subito", flush=True)
    with keyboard.Listener(on_press=on_press):
        ev.wait()


def wait_trigger(auto: bool, label: str, key: bool = False) -> None:
    if auto:
        time.sleep(0.8)
    elif key:
        wait_shift(label)
    else:
        input(f"\n{label} - premi Invio e parla subito: ")


def ms(t0, t1):
    return None if t0 is None or t1 is None else (t1 - t0) * 1000


def open_stream(cap: Capture, blocksize: int, device):
    try:
        s = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                           blocksize=blocksize, device=device, callback=cap.callback)
        return s
    except sd.PortAudioError as e:
        sys.exit(f"Impossibile aprire il microfono: {e}\n"
                 "Su macOS controlla Impostazioni di Sistema > Privacy e sicurezza > Microfono "
                 "e abilita l'app da cui lanci lo script (Terminale, iTerm, VS Code...).")


def run(args) -> None:
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    cap = Capture(args.rms_threshold)
    pre_n = int(SR * args.preroll_ms / 1000)
    results = []
    warm_stream = None
    ring = np.zeros(0, dtype=np.float32)
    ring_lock = threading.Lock()

    if args.mode == "warm":
        # In warm il callback alimenta anche il buffer circolare.
        base_cb = cap.callback

        def warm_cb(indata, frames, ti, status):
            nonlocal ring
            with ring_lock:
                ring = np.concatenate([ring, indata[:, 0]])[-pre_n:] if pre_n else ring
            base_cb(indata, frames, ti, status)

        warm_stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                     blocksize=args.blocksize, device=args.device, callback=warm_cb)
        try:
            warm_stream.start()
        except sd.PortAudioError as e:
            sys.exit(f"Impossibile aprire il microfono: {e}\n"
                     "Controlla il permesso Microfono in Impostazioni di Sistema.")
        time.sleep(1.0)  # lascia riempire il pre-roll
        print(f"Stream aperto (warm), pre-roll {args.preroll_ms} ms.")

    for i in range(1, args.runs + 1):
        wait_trigger(args.auto, f"Prova {i}/{args.runs} [{args.mode}]", args.key)
        if args.mode == "cold":
            cap.reset()
            t0 = time.perf_counter()
            cap.arm(t0)
            stream = open_stream(cap, args.blocksize, args.device)
            stream.start()
            t_started = time.perf_counter()
            time.sleep(args.duration)
            cap.disarm()
            stream.stop(); stream.close()
            audio = np.concatenate(cap.blocks) if cap.blocks else np.zeros(0, np.float32)
            preroll = 0
            open_ms = ms(t0, t_started)
        else:
            t0 = time.perf_counter()
            with ring_lock:
                pre = ring.copy()
            cap.arm(t0)
            time.sleep(args.duration)
            cap.disarm()
            body = np.concatenate(cap.blocks) if cap.blocks else np.zeros(0, np.float32)
            audio = np.concatenate([pre, body])
            preroll = len(pre)
            open_ms = 0.0

        first = ms(t0, cap.t_first)
        loud = ms(t0, cap.t_loud)
        wav = out / f"{args.mode}_{i:02d}.wav"
        save_wav(wav, audio)
        rms = float(np.sqrt(np.mean(audio**2))) if len(audio) else 0.0
        if len(audio) and not np.any(audio):
            print("  ATTENZIONE: audio tutto a zero. Probabile permesso Microfono negato "
                  "per questa app (Impostazioni di Sistema > Privacy e sicurezza > Microfono).")
        results.append((open_ms, first, loud))
        fmt = lambda v: "n/d" if v is None else f"{v:.0f} ms"
        print(f"  apertura stream: {fmt(open_ms)} | primo blocco: {fmt(first)} | "
              f"primo blocco sopra soglia: {fmt(loud)} | pre-roll: {preroll * 1000 // SR} ms | "
              f"durata: {len(audio) / SR:.2f} s | RMS: {rms:.4f}\n  -> {wav}")

    if warm_stream:
        warm_stream.stop(); warm_stream.close()

    print(f"\n=== Riepilogo [{args.mode}], {args.runs} prove ===")
    for name, idx in (("apertura stream", 0), ("richiesta -> primo blocco", 1),
                      ("richiesta -> primo blocco sopra soglia", 2)):
        vals = [r[idx] for r in results if r[idx] is not None]
        if vals:
            print(f"{name:42s} media {statistics.mean(vals):6.0f}  min {min(vals):6.0f}  max {max(vals):6.0f} ms")
        else:
            print(f"{name:42s} n/d (nessun blocco sopra soglia)")
    print(f"\nWav salvati in: {out}\nRiascoltali (es. `afplay {out}/{args.mode}_01.wav`): la prima sillaba c'e'?")


def main() -> None:
    p = argparse.ArgumentParser(description="Misura il ritardo di apertura del microfono (T06).")
    p.add_argument("--mode", choices=["cold", "warm"], required=True)
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--duration", type=float, default=3.0, help="secondi di registrazione")
    p.add_argument("--preroll-ms", type=int, default=300)
    p.add_argument("--blocksize", type=int, default=512, help="campioni per blocco (0 = automatico)")
    p.add_argument("--rms-threshold", type=float, default=0.01, help="soglia RMS per 'sopra soglia'")
    p.add_argument("--device", default=None, help="indice o nome del dispositivo di input")
    p.add_argument("--out", default=str(default_out()), help="cartella dei wav (fuori dal repo)")
    p.add_argument("--key", action="store_true", help="trigger = pressione di Shift in qualunque finestra (pynput)")
    p.add_argument("--auto", action="store_true", help="simula Invio, senza input (non serve parlare)")
    args = p.parse_args()
    if isinstance(args.device, str) and args.device.isdigit():
        args.device = int(args.device)
    run(args)


if __name__ == "__main__":
    main()
