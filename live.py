import threading
import time

import numpy as np
import sounddevice as sd
import whisper

SAMPLE_RATE = 16000     # Whisper vuole 16 kHz
PROCESSING_TIME = 2     # x: ogni quanti secondi trascrivere
CAPTURE_TIME = 10       # y: secondi di audio nella finestra (x < y, max 30)
MODEL_NAME = "turbo"
LANGUAGE = "it"         # None = rilevamento automatico
SILENCE_RMS = 0.005     # sotto questa soglia si salta la trascrizione


class LiveTranscriber:
    def __init__(self):
        print(f"Carico il modello '{MODEL_NAME}'...")
        self.model = whisper.load_model(MODEL_NAME)
        self.buffer = np.zeros(0, dtype=np.float32)
        self.lock = threading.Lock()
        self._thread = None
        self._ticker = time.time()

    def _callback(self, indata, frames, time_info, status):
        """Chiamata da sounddevice a ogni blocchetto di audio (capture)."""
        if status:
            print(status)
        with self.lock:
            self.buffer = np.concatenate([self.buffer, indata[:, 0]])
            # tieni solo gli ultimi CAPTURE_TIME secondi
            self.buffer = self.buffer[-CAPTURE_TIME * SAMPLE_RATE:]

    def transcribe(self, audio: np.ndarray):
        result = self.model.transcribe(
            audio,
            language=LANGUAGE,
            fp16=False,
            condition_on_previous_text=False,
        )
        text = result["text"].strip()
        if text:
            self.on_text(text)
        self._thread = None

    def on_text(self, text: str):
        # PERSONALIZZA QUI: è il punto dove arriva il testo
        print(f"> {text}")

    def process(self):
        """Decide quando lanciare la trascrizione (finestra scorrevole)."""
        if time.time() - self._ticker < PROCESSING_TIME:
            return
        if self._thread is not None:
            print("(trascrizione ancora in corso, salto questo giro)")
            self._ticker = time.time()
            return

        with self.lock:
            audio = self.buffer.copy()

        if len(audio) < SAMPLE_RATE or np.sqrt(np.mean(audio**2)) < SILENCE_RMS:
            self._ticker = time.time()
            return

        self._ticker = time.time()
        self._thread = threading.Thread(target=self.transcribe, args=(audio,))
        self._thread.start()

    def run(self):
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", callback=self._callback):
            print("Ascolto... (Ctrl+C per uscire)")
            try:
                while True:
                    self.process()
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nFine.")


if __name__ == "__main__":
    LiveTranscriber().run()
