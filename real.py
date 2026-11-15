"""Trascrizione realtime con costruzione delle frasi (Parte 3 dell'articolo).

Uso:
    python real.py              # dal microfono
    python real.py audio.mp3    # da file, per provare la pipeline senza parlare
"""

import queue
import sys
import threading
import time

import numpy as np
import sounddevice as sd
import whisper

SAMPLE_RATE = 16000     # Whisper vuole 16 kHz
PROCESSING_TIME = 4     # passo: di quanti secondi avanza la finestra
CAPTURE_TIME = 8        # finestra: secondi di audio trascritti a ogni giro (max 30)
MODEL_NAME = "turbo"
LANGUAGE = "it"         # None = rilevamento automatico
SILENCE_RMS = 0.005     # sotto questa soglia la finestra viene saltata
NO_SPEECH_PROB = 0.6    # sopra questa probabilità Whisper considera la finestra muta
USE_PREFIX = False      # True = passa a Whisper il testo precedente, come nell'articolo
                        # (non può più correggere le parole troncate a fine finestra)
PREFIX_WORDS = 12       # quante parole finali del testo precedente usare come prefix
REFRESH_TIME = 2        # ogni quanti secondi ridisegnare il trascritto
MAX_BACKLOG = 30        # secondi massimi di audio in attesa (oltre, si scarta il più vecchio)

PUNCTUATION = ".,;:!?"
MERGE_LOOKBACK = 60     # parole finali del trascritto in cui cercare sovrapposizioni
MERGE_SKIP = 2          # parole iniziali del nuovo testo che possono essere "sporche"


# --- costruzione delle frasi -------------------------------------------------

def intelligent_concatenate(first: str, second: str) -> str:
    """Unisce due pezzi di testo sistemando punteggiatura e maiuscole."""
    first, second = first.strip(), second.strip()
    if not second:
        return first
    if not first:
        return second
    if second[0] in PUNCTUATION:
        if first[-1] in PUNCTUATION:
            first = first[:-1]
        return first + second
    if second[0].islower() and first[-1] == ".":
        return first[:-1] + " " + second
    if second[0].isupper() and first[-1] not in PUNCTUATION:
        return first + ". " + second
    return first + " " + second


def _norm(word: str) -> str:
    return "".join(c for c in word.lower() if c.isalnum())


def merge_text(confirmed: str, new: str) -> str:
    """Fonde `new` in `confirmed` senza ripetere la parte già trascritta.

    Finestre consecutive si sovrappongono, quindi l'inizio di `new` ripete la
    fine di `confirmed`. Cerca nella coda di `confirmed` le prime parole di
    `new` (l'ancora), tollerando qualche parola iniziale tagliata dal bordo
    della finestra. Da lì in poi vince `new`: le ultime parole di una finestra
    sono spesso troncate, mentre nella finestra successiva cadono al centro.
    """
    conf_words = confirmed.split()
    new_words = new.split()
    if not new_words:
        return confirmed
    base = max(0, len(conf_words) - MERGE_LOOKBACK)
    tail = [_norm(w) for w in conf_words[base:]]
    head = [_norm(w) for w in new_words]

    for skip in range(MERGE_SKIP + 1):
        for size in (3, 2):
            anchor = head[skip:skip + size]
            if len(anchor) < size or not all(anchor):
                continue
            for pos in range(len(tail) - size, -1, -1):   # ultima occorrenza
                if tail[pos:pos + size] == anchor:
                    kept = conf_words[:base + pos + size]
                    return " ".join(kept + new_words[skip + size:])

    # sovrapposizione di una sola parola, proprio sulla giunzione
    if tail and head[0] and head[0] == tail[-1]:
        return intelligent_concatenate(confirmed, " ".join(new_words[1:]))
    if (len(head) > 1 and len(tail) > 1 and head[0] and head[1] == tail[-1]
            and tail[-2].endswith(head[0])):   # prima parola tagliata a metà
        return intelligent_concatenate(confirmed, " ".join(new_words[2:]))
    return intelligent_concatenate(confirmed, new)


# --- pipeline ----------------------------------------------------------------

class RealtimeSTT:
    def __init__(self):
        print(f"Carico il modello '{MODEL_NAME}'...")
        self.model = whisper.load_model(MODEL_NAME)
        self.window = CAPTURE_TIME * SAMPLE_RATE
        self.step = PROCESSING_TIME * SAMPLE_RATE

        self.buffer = np.zeros(0, dtype=np.float32)
        self.lock = threading.Lock()              # protegge buffer
        self.transcribed = queue.Queue()          # process -> builder
        self.confirmed_text = ""
        self.lock_transcript = threading.Lock()   # protegge confirmed_text
        self.last_text = ""                       # ultimo testo, usato come prefix

        self.running = False
        self.finished = threading.Event()         # in modalità file: audio esaurito
        self._eof = False
        self._processed_any = False
        self._stream = None
        self._threads = []

    # 1. capture: accoda l'audio in arrivo
    def _callback(self, indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        self.feed(indata[:, 0])

    def feed(self, samples: np.ndarray):
        with self.lock:
            self.buffer = np.concatenate([self.buffer, samples])
            if not self._eof and len(self.buffer) > MAX_BACKLOG * SAMPLE_RATE:
                # la trascrizione non tiene il passo: scarta l'audio più vecchio
                self.buffer = self.buffer[-MAX_BACKLOG * SAMPLE_RATE:]

    # 2. process: estrae le finestre e le trascrive
    def _next_window(self):
        with self.lock:
            if len(self.buffer) >= self.window:
                audio = self.buffer[:self.window].copy()
                self.buffer = self.buffer[self.step:]
                return audio
            if self._eof:
                # coda del file: trascrivi quel che resta, se contiene audio nuovo
                overlap = self.window - self.step
                if len(self.buffer) > overlap or not self._processed_any:
                    audio = self.buffer.copy()
                    self.buffer = np.zeros(0, dtype=np.float32)
                    if len(audio):
                        return audio
                self.finished.set()
        return None

    def _process(self):
        while self.running:
            audio = self._next_window()
            if audio is None:
                time.sleep(0.05)
                continue
            self._processed_any = True
            if np.sqrt(np.mean(audio**2)) < SILENCE_RMS:
                continue
            text = self.transcribe(audio)
            if text:
                self.transcribed.put(text)

    def transcribe(self, audio: np.ndarray) -> str:
        mel = whisper.log_mel_spectrogram(
            whisper.pad_or_trim(audio), n_mels=self.model.dims.n_mels
        ).to(self.model.device)
        prefix = " ".join(self.last_text.split()[-PREFIX_WORDS:]) if USE_PREFIX else ""
        options = whisper.DecodingOptions(
            language=LANGUAGE,
            fp16=False,
            without_timestamps=True,
            prefix=prefix or None,
        )
        result = whisper.decode(self.model, mel, options)
        if result.no_speech_prob > NO_SPEECH_PROB:
            return ""
        text = result.text.strip()
        if text:
            self.last_text = intelligent_concatenate(prefix, text)
        return text

    # 3. builder: unisce i pezzi in un unico trascritto
    def _build_transcript(self):
        while self.running or not self.transcribed.empty():
            try:
                text = self.transcribed.get(timeout=0.1)
            except queue.Empty:
                continue
            with self.lock_transcript:
                self.confirmed_text = merge_text(self.confirmed_text, text)
                current = self.confirmed_text
            self.on_text(current)

    def on_text(self, text: str):
        # PERSONALIZZA QUI: riceve il trascritto completo a ogni aggiornamento
        # (le ultime parole possono ancora cambiare al giro successivo)
        pass

    def get_text(self) -> str:
        with self.lock_transcript:
            return self.confirmed_text

    def start(self, use_microphone=True):
        self.running = True
        self._threads = [
            threading.Thread(target=self._process, daemon=True),
            threading.Thread(target=self._build_transcript, daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        if use_microphone:
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                          dtype="float32", callback=self._callback)
            self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.running = False
        for thread in self._threads:
            thread.join()

    def feed_file(self, path: str):
        """Usa un file audio al posto del microfono."""
        self.feed(whisper.load_audio(path, sr=SAMPLE_RATE))
        with self.lock:
            self._eof = True


def run_microphone():
    stt = RealtimeSTT()
    stt.start()
    try:
        while True:
            time.sleep(REFRESH_TIME)
            print("\033[2J\033[H", end="")   # pulisce lo schermo
            print("Ascolto... (Ctrl+C per uscire)\n")
            print(stt.get_text())
    except KeyboardInterrupt:
        print("\nChiudo...")
    finally:
        stt.stop()
    print("\nTrascritto finale:")
    print(stt.get_text())


def run_file(path: str):
    stt = RealtimeSTT()
    stt.on_text = lambda text: print(f"> {text}")
    stt.feed_file(path)
    stt.start(use_microphone=False)
    try:
        stt.finished.wait()
    except KeyboardInterrupt:
        pass
    stt.stop()
    print("\nTrascritto finale:")
    print(stt.get_text())


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_file(sys.argv[1])
    else:
        run_microphone()
