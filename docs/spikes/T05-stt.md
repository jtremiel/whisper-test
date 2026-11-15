# T05 - Benchmark dei modelli faster-whisper

Stato: completato (2026-11-15). **I numeri valgono per questo Mac (Apple M5, 10 core, 24 GB, solo CPU), non per Windows**: su Windows vanno rimisurati in T26.

## Cosa è stato provato

Script `spikes/stt_bench.py` (`.venv/bin/python spikes/stt_bench.py --extra`). faster-whisper 1.2.1, `device="cpu"`, `compute_type="int8"`, `language="it"`.

- Audio: `testVoice.mp3` (10,4 s in totale). Spezzoni presi dal primo parlato: "3s" = 3,0 s; "15s" = 9,4 s (il file non arriva a 15 s, si usa tutto il parlato rimasto).
- Tempo di trascrizione: media su 5 giri, escluso il primo (warm-up), compresa la lettura del generatore dei segmenti.
- Decodifica: `faster_whisper.decode_audio` fallisce con PyAV 19 (`metadata_errors`); lo script decodifica direttamente con PyAV. Il modulo di trascrizione non ne è toccato (riceve già un array numpy dal Recorder).

## Verifiche sulla versione installata

- Nomi di modello accettati (`faster_whisper.utils.available_models()`): `tiny`, `base`, `small`, `medium`, `large-v1/v2/v3`, `large`, `distil-*`, **`large-v3-turbo` e `turbo`**. `turbo` è valido.
- `hotwords`: presente nella firma di `WhisperModel.transcribe` (stringa, parole separate da spazi).
- `no_speech_prob`: attributo di ogni `Segment` restituito (`seg.no_speech_prob`, 0-1). Sul parlato vale 0,00-0,04.
- `beam_size` di default in `transcribe` è 5.

## Tempi

Tempo di caricamento: il primo valore include probabilmente il download dalla cache HF, quindi è indicativo.

| Modello | Caricamento | Trascrizione 3 s | Trascrizione 9,4 s |
|---|---|---|---|
| turbo | 1,39 s | 4,95 s | 5,44 s |
| small | 10,56 s (download incluso; 0,53 s a modello in cache) | **1,23 s** | 1,77 s |
| base | 4,75 s | 0,39 s | 0,64 s |

Varianti sul clip da 3 s:

| Modello | beam 1 | beam 5 | beam 1 + VAD | beam 5 + VAD | beam 1 + hotwords |
|---|---|---|---|---|---|
| turbo | 5,16 s | 5,39 s | 5,29 s | 5,50 s | 5,44 s |
| small | 1,11 s | 1,32 s | 1,12 s | 1,35 s | 1,16 s |
| base | 0,35 s | 0,42 s | 0,35 s | 0,43 s | 0,35 s |

## Qualità (a occhio)

Testo di riferimento: "Registrazione di test, prova, questa è la mia voce, testo da trascrivere, parlo normalmente. Apri Windows, chiudi Mac."

- **turbo**: perfetto, punteggiatura inclusa.
- **small**: quasi perfetto; "questa e" senza accento sul 3 s, "chiudi Mac" diventa "QD Mac" sul clip lungo. Con `hotwords="Chrome Spotify"` peggiora ("voce" diventa "vola").
- **base**: errori evidenti ("In gestrazione", "queste"); i comandi corti ("Apri Windows, chiudi Mac") però escono giusti.

## Decisione

- **Default `stt.model: small`, `compute_type: int8`**. Su 3 s di audio impiega 1,1-1,2 s, dentro l'obiettivo di 1,5 s del PRD §4, con qualità buona. `turbo` su CPU impiega circa 5 s ed è fuori obiettivo; `base` è veloce ma sbaglia troppo per la dettatura.
- **`beam_size=1`** nel Transcriber: circa 0,1-0,2 s in meno, nessuna differenza di testo in queste prove.
- **`vad_filter` disattivato** per i comandi: con trigger premi-e-parla non porta vantaggi e non cambia il testo. Il silenzio si scarta già nel Recorder (`silence_rms`) e con `no_speech_prob`.
- **`hotwords`**: il Transcriber lo accetta (il contratto lo prevede), ma il Controller per ora **non** lo passa: in questa prova ha peggiorato il testo. Da rivalutare in T24 con frasi di comando vere.
- `no_speech_prob`: il Transcriber può scartare i segmenti con valore alto (per esempio > 0,6) come "nessun parlato"; la soglia va tarata in T24, qui il parlato non supera 0,04.
- `turbo` resta selezionabile da YAML per chi accetta più latenza in cambio di qualità.
- Default `stt.model` portato a `small` in `voicecmd/schema.py` e `default_config.yaml` (su richiesta dell'utente, 2026-11-15). Il test `PRD_EXAMPLE` resta su `turbo`, che è un valore valido.

## Aggiunta: backend MPS (GPU Apple, sperimentale)

L'utente ha chiesto di provarlo (2026-11-15), in deroga a HANDOFF §3 "su Mac solo CPU". Script `spikes/stt_bench_mps.py`, stesso audio e stessa media su 5 giri. ctranslate2 4.9.0; `int8_float16` su MPS viene convertito da ctranslate2 in `float16` (stessi tempi). Il caricamento qui è a modello già in cache.

| Modello | Dispositivo | Caricamento | 3 s beam 1 | 3 s beam 5 | 9,4 s beam 1 | 9,4 s beam 5 |
|---|---|---|---|---|---|---|
| turbo | mps float16 | 1,35 s | **1,07 s** | 1,15 s | 1,16 s | 1,30 s |
| small | mps float16 | 0,40 s | 0,31 s | 0,41 s | 0,43 s | 0,62 s |
| turbo | cpu int8 | 1,28 s | 5,54 s | 5,68 s | 5,81 s | 6,41 s |
| small | cpu int8 | 0,53 s | 1,25 s | 1,47 s | 1,46 s | 2,02 s |

- Qualità: turbo su MPS dà lo stesso testo perfetto della CPU. small su MPS con beam 1 sbaglia "voce" in "vola" sul 3 s; con beam 5 è corretto.
- Lettura: su MPS turbo è circa 5 volte più veloce che su CPU e sta dentro l'obiettivo di 1,5 s con la qualità migliore. small su MPS è circa 4 volte più veloce.
- Rischi: backend dichiarato sperimentale da ctranslate2; esiste solo su Apple Silicon; su Windows resta la CPU (o CUDA, non in ambito). Il caricamento su MPS va protetto con un ripiego automatico su CPU.
- **Decisione dell'utente (2026-11-15)**: nuovo campo `stt.device` (`auto` | `cpu` | `mps`, default `auto`). `auto` = MPS su macOS Apple Silicon, CPU altrove; se il caricamento su MPS fallisce, ripiego su CPU. `model` e `compute_type` hanno default `auto`: `turbo`/`float16` su MPS, `small`/`int8` su CPU. `beam_size`: 5 su MPS (corregge small, costa ~0,1 s), 1 su CPU. Sostituisce il default "small ovunque" scritto sopra, che resta valido per la CPU.
