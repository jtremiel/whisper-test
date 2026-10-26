# whisper-test

Trascrizione vocale (speech-to-text) in locale con [OpenAI Whisper](https://github.com/openai/whisper): test su file audio e trascrizione **live** dal microfono, in italiano.

Il progetto segue la serie di articoli di pcb.it18 su Medium e può essere esteso con codice personale.

- [Parte 1: installazione e uso su file](https://medium.com/@pcb.it18/how-to-make-whisper-stt-live-transcription-part-1-79c628984fc6)
- [Parte 2: trascrizione live con finestra scorrevole](https://medium.com/@pcb.it18/how-to-make-whisper-stt-live-transcription-part-2-5daa1dfa3be8)
- [Parte 3: costruzione delle frasi e deduplicazione](https://medium.com/@pcb.it18/how-to-make-whisper-stt-real-time-transcription-part-3-10395d124c73)
- [Repo dell'autore](https://github.com/PCB-IT/Whisper-Live-STT)

## Dove è stato testato

| Elemento | Valore |
|---|---|
| Sistema | macOS su Apple Silicon (M5) |
| Gestore pacchetti | Homebrew |
| Python | 3.14 (venv) |
| Libreria | `openai-whisper` (inferenza su CPU) |
| Lingua | Italiano |

Il percorso Python (`openai-whisper`) è stato provato end to end. Il percorso `whisper.cpp` descritto più sotto **non è stato ancora testato**.

Su altri sistemi (Linux, Windows) il codice dovrebbe funzionare con piccoli adattamenti, ma non è stato verificato.

## Struttura

```
whisper-test/
├── test_file.py       # trascrive un file mp3
├── live.py            # trascrizione live dal microfono
├── requirements.txt
└── README.md
```

## Requisiti

- Python 3 (consigliato 3.12 se hai problemi con `numba`/`llvmlite` su versioni più recenti)
- [ffmpeg](https://ffmpeg.org/) (Whisper lo usa per leggere i file audio)
- Un microfono e il relativo permesso per il terminale

## Installazione

```bash
git clone https://github.com/jtremiel/whisper-test.git
cd whisper-test

brew install ffmpeg            # macOS; su Linux: apt install ffmpeg

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` contiene `openai-whisper`, `sounddevice` e `numpy`.

Verifica che l'ambiente funzioni:

```bash
python -c "import whisper, sounddevice, numpy; print('ok')"
```

> Su macOS con Python Homebrew un `pip install` fuori da un venv dà `error: externally-managed-environment`. Non usare `--break-system-packages`: usa sempre il venv.

Se l'installazione fallisce con errori su `numba` o `llvmlite`, ricrea il venv con Python 3.12:

```bash
brew install python@3.12
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Permesso microfono (macOS)

Alla prima esecuzione di `live.py` macOS chiede il permesso per l'app che usi (Terminale, iTerm, VS Code). Se la richiesta non compare, abilitalo a mano in Impostazioni di Sistema → Privacy e sicurezza → Microfono.

## 1. Test su file audio

I file audio **non sono inclusi nel repository** (`*.mp3` è nel `.gitignore`). Per provare il test devi aggiungerne uno tuo:

1. Registra o procurati un file `.mp3` di pochi secondi.
2. Mettilo nella cartella del progetto.
3. In `test_file.py` imposta il nome del tuo file (nello snippet sotto, `AUDIO_FILE`).

```python
import whisper

AUDIO_FILE = "testEmy.mp3"   # sostituisci con il nome del tuo mp3
MODEL_NAME = "small"         # prova anche "turbo" per più precisione

model = whisper.load_model(MODEL_NAME)
audio = whisper.pad_or_trim(whisper.load_audio(AUDIO_FILE))
mel = whisper.log_mel_spectrogram(audio, n_mels=model.dims.n_mels).to(model.device)

_, probs = model.detect_language(mel)
print("Lingua:", max(probs, key=probs.get))

result = whisper.decode(model, mel, whisper.DecodingOptions(fp16=False))
print(result.text)
```

Esegui:

```bash
python test_file.py
```

Deve stampare la lingua rilevata e il testo. Se compare `FileNotFoundError` su ffmpeg, installalo (vedi Requisiti).

Note:

- `fp16=False` serve perché su Mac Whisper gira su CPU.
- I modelli con suffisso `.en` sono solo per l'inglese: per l'italiano usa `small`, `medium` o `turbo`.
- La scelta del modello conta. Con una registrazione di test che diceva "...apri windows chiudi mac", il modello `small` ha trascritto male la parola finale, mentre `turbo` l'ha riconosciuta correttamente. Se la precisione di `small` non basta, passa a `turbo`.

## 2. Trascrizione live

```bash
python live.py
```

Parla nel microfono: compaiono righe `> testo`. Esci con `Ctrl+C`.

### Come funziona

Whisper non supporta lo streaming nativo: trascrive blocchi di audio completi. `live.py` usa una **finestra scorrevole**:

- ogni `PROCESSING_TIME` secondi (`x`) lancia una trascrizione;
- trascrive gli ultimi `CAPTURE_TIME` secondi (`y`) di audio;
- vincolo: `x < y` e `y <= 30`.

Il sorgente completo è in `live.py`. I parametri da regolare sono all'inizio del file:

```python
SAMPLE_RATE = 16000     # Whisper vuole 16 kHz
PROCESSING_TIME = 2     # x: ogni quanti secondi trascrivere
CAPTURE_TIME = 10       # y: secondi di audio nella finestra
MODEL_NAME = "small"
LANGUAGE = "it"         # None = rilevamento automatico
SILENCE_RMS = 0.005     # sotto questa soglia si salta la trascrizione
```

### Perché compaiono più output per la stessa frase

È il comportamento previsto, non un bug. Ogni secondo di audio resta nella finestra per più giri, quindi viene trascritto più volte, ogni volta con un contesto leggermente diverso (parole tagliate ai bordi, maiuscole e punteggiatura diverse, risultati parziali se parli mentre la trascrizione parte). Per ottenere frasi pulite serve una deduplicazione: è l'argomento della Parte 3 dell'articolo.

Per comandi vocali brevi puoi anche cambiare strategia: invece della finestra scorrevole, aspetta un breve silenzio che chiude la frase e trascrivi **una volta sola** (endpointing). Ottieni un solo output per frase, ma il testo compare dopo che hai finito di parlare.

### Regolazioni

- "trascrizione ancora in corso": usa un modello più piccolo (`base`) o aumenta `PROCESSING_TIME`.
- Allucinazioni sul silenzio: alza `SILENCE_RMS`.
- Testo ripetuto: normale (vedi sopra).

## Aggiungere codice tuo

Il punto di estensione è il metodo `on_text()` in `live.py`: riceve ogni testo trascritto e puoi salvarlo, mandarlo a un'API, interpretarlo come comando e così via.

```python
def on_text(self, text: str):
    print(f"> {text}")   # sostituisci con la tua logica
```

## Alternativa più veloce: whisper.cpp (non ancora testata qui)

[whisper.cpp](https://github.com/ggml-org/whisper.cpp) è una reimplementazione in C++ che su Apple Silicon sfrutta la GPU tramite Metal ed è molto più veloce di `openai-whisper` su CPU. Include `whisper-stream`, che implementa già la finestra scorrevole. Richiede SDL2 per leggere il microfono, quindi va compilato da sorgente.

```bash
brew install cmake sdl2
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build -DWHISPER_SDL2=ON
cmake --build build -j --config Release

# modello multilingua (senza ".en") per l'italiano
sh ./models/download-ggml-model.sh small

./build/bin/whisper-stream -m models/ggml-small.bin -l it -t 8 --step 500 --length 5000
```

`--step` e `--length` corrispondono a `x` e `y`, in **millisecondi**. I file `models/*.bin` sono pesanti: non committarli.

Per integrare l'output in Python puoi leggerlo riga per riga con `subprocess`:

```python
import subprocess

cmd = [
    "./build/bin/whisper-stream",
    "-m", "models/ggml-small.bin",
    "-l", "it", "-t", "8",
    "--step", "500", "--length", "5000",
]
with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as proc:
    for line in proc.stdout:
        line = line.strip()
        if line:
            print("TESTO:", line)
```

## Risoluzione dei problemi

| Sintomo | Causa probabile | Azione |
|---|---|---|
| `externally-managed-environment` | pip su Python Homebrew | usare un venv |
| `FileNotFoundError` su ffmpeg | ffmpeg mancante | installare ffmpeg |
| errore `numba` / `llvmlite` | Python troppo recente | usare Python 3.12 |
| `can't open file '.../live.py'` | comando lanciato dalla cartella sbagliata | `cd` nella cartella del progetto |
| nessun audio / testo vuoto | permesso microfono | abilitarlo in Privacy e sicurezza |
| "trascrizione ancora in corso" | modello troppo pesante | modello più piccolo o `x` più grande |
| testo ripetuto | finestra scorrevole | normale; deduplicare (Parte 3) |
| `whisper-stream` non esiste | build senza SDL2 | ricompilare con `-DWHISPER_SDL2=ON` |

## Note per i contributori

Non committare l'ambiente virtuale, i file audio né i modelli. Il `.gitignore` dovrebbe contenere almeno:

```
.venv/
venv/
__pycache__/
*.pyc
.DS_Store
*.mp3
*.wav
models/*.bin
```
