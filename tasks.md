# tasks.md — backlog di voicecmd

Prima di iniziare leggi [HANDOFF.md](HANDOFF.md). Requisiti in [PRD.md](PRD.md).

## Convenzioni

- `- [ ]` da fare · `- [x]` fatto. Chi chiude un task spunta la checkbox e aggiunge sotto una riga `Nota:`.
- **`[P]`** parallelizzabile: si può eseguire insieme agli altri `[P]` della stessa ondata, un sub-agent per task. Nessun file in comune tra loro.
- **Senza `[P]`** sequenziale: uno alla volta, nell'ordine scritto.
- **`[U]`** richiede l'utente (input fisico, microfono, Windows). L'agente prepara, l'utente esegue e conferma.
- **File**: gli unici file che il task può creare o modificare.
- **Dipende da**: task che devono essere già spuntati.
- **Fatto quando**: criterio verificabile di chiusura.
- Un'ondata parte solo quando la precedente è tutta spuntata. Per riprendere: primo task non spuntato.

## Avanzamento

| Ondata | Tipo | Task | Stato |
|---|---|---|---|
| 0 Fondamenta | sequenziale | T01-T03 | ☑ |
| 1 Spike | parallela | T04-T06 | ☑ |
| 2 Moduli | parallela | T07-T19 | ☑ |
| 3 Integrazione | sequenziale | T20-T23 | ☐ |
| 4 Verifica | parallela | T24-T27 | ☐ |
| 5 Fase 2 | backlog | T28-T30 | ☐ |

---

## Ondata 0 — Fondamenta (sequenziale)

Crea lo scheletro e i contratti. Tutto ciò che viene dopo dipende da qui.

- [x] **T01 Scheletro del progetto**
  - **File**: `pyproject.toml`, `voicecmd/__init__.py`, `voicecmd/actions/__init__.py`, `voicecmd/triggers/__init__.py`, `voicecmd/ui/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`, `.gitignore`
  - **Dipende da**: —
  - **Cosa**: `pyproject.toml` con il package `voicecmd` e le dipendenze: `numpy`, `sounddevice`, `faster-whisper`, `rapidfuzz`, `pydantic`, `PyYAML`, `platformdirs`, `pynput`, `PySide6`, `pyperclip`; solo su macOS (marker `sys_platform == "darwin"`) i pacchetti `pyobjc-framework-*` necessari; extra `dev` con `pytest` e `pytest-qt`. Configurazione pytest: `testpaths = ["tests"]` (nella root c'è `test_file.py` che non è un test) e marker `slow` escluso di default. Installa nel venv esistente. I file `__init__.py` restano vuoti.
  - **Fatto quando**: `.venv/bin/pip install -e ".[dev]"` riesce su Python 3.14; `tests/test_smoke.py` importa ogni dipendenza e `.venv/bin/pytest` è verde. Se una dipendenza non ha wheel per 3.14, fermati e segnalalo (HANDOFF §7.5).
  - Nota: creati `pyproject.toml` (setuptools, extra `dev`, marker pytest `slow` escluso di default via `addopts`, `testpaths=["tests"]`), i `__init__.py` vuoti e `tests/test_smoke.py` (16 import, incluso ctranslate2 e i moduli pyobjc). Dipendenze pyobjc su darwin: Quartz, Cocoa, AVFoundation, ApplicationServices. Tutte le dipendenze hanno wheel per Python 3.14.6, nessun problema aperto. `.gitignore`: aggiunti `*.egg-info/` e `.pytest_cache/`, righe dell'utente conservate. Nota: `package-data` include `default_config.yaml` e `ui/assets/*` (non ancora esistenti).

- [x] **T02 Contratti: `events.py`**
  - **File**: `voicecmd/events.py`, `tests/test_events.py`
  - **Dipende da**: T01
  - **Cosa**: solo tipi, nessuna logica e nessun import pesante.
    - `AppState`: `IDLE`, `LISTENING`, `PROCESSING`, `DONE`, `ERROR`
    - `Mode`: `COMMAND`, `DICTATION`
    - `ActionResult(ok: bool, message: str)`
    - `MatchResult(command, score, heard, closest, closest_score)` con `command = None` se non c'è corrispondenza
    - `Outcome(mode, ok, heard, title, detail)`: ciò che il feedback mostra a fine ciclo
    - Protocol `Trigger`: `start(on_event: Callable[[Mode, bool], None])`, `stop()`; il booleano è premuto/rilasciato
    - Protocol `Recorder`: `start()`, `stop() -> np.ndarray` (float32, mono, 16 kHz; array vuoto se silenzio)
    - Protocol `Transcriber`: `transcribe(audio, hotwords: list[str] | None = None) -> str`
    - Protocol `Action`: `run(spec) -> ActionResult`
    - Protocol `Feedback`: `on_state(state, mode)`, `on_outcome(outcome)`
    - costanti: `SAMPLE_RATE = 16000`, `MIN_PRESS_S = 0.3`, `MAX_COMMAND_S = 30`, `MAX_DICTATION_S = 120`
  - **Fatto quando**: il modulo si importa senza Qt, pynput né faster-whisper; un test costruisce ogni dataclass e verifica che una classe finta soddisfi ciascun Protocol (`runtime_checkable`).
  - Nota: creati `voicecmd/events.py` (dataclass frozen, Enum, 5 Protocol `runtime_checkable`, costanti) e `tests/test_events.py`. `numpy` solo sotto `TYPE_CHECKING`. Scelta di tipo: `MatchResult.command` e lo `spec` di `Action.run` sono `Any` perché `schema.py` (T03) non esiste ancora; si possono restringere al tipo pydantic dopo T03 (modifica del contratto a cura del coordinatore). `closest` è il nome del comando più vicino (str), `closest_score` 0-100. Nessuna deviazione.

- [x] **T03 Contratti: schema della configurazione**
  - **File**: `voicecmd/schema.py`, `voicecmd/default_config.yaml`, `tests/test_schema.py`
  - **Dipende da**: T02
  - **Cosa**: modelli pydantic per la struttura del PRD §6: `language`, `stt` (`model`, `compute_type`), `triggers.command` e `triggers.dictation` (esattamente uno tra `hotkey` e `mouse_button`; `mouse_button` ∈ `middle`, `x1`, `x2`), `matching` (`threshold`, `margin`), `feedback` (quattro booleani), `audio` (`silence_rms`, `keep_stream_open`, `preroll_ms`), `commands` (`name`, `phrases` non vuota, `action`). `action` è un'unione discriminata su `type`: `open` (`target`) e `shell` (`command` oppure `mac`/`windows`, più `timeout`). Campi sconosciuti rifiutati. Nomi di comando duplicati rifiutati. `default_config.yaml` commentato in italiano, con tre o quattro comandi d'esempio validi su entrambi i sistemi.
  - **Fatto quando**: i test coprono: `default_config.yaml` valido; l'esempio del PRD valido; rifiuto di trigger con entrambi o nessun binding, frasi vuote, tipo di azione ignoto, shell senza comando per alcun sistema, nomi duplicati.
  - Nota: creati `voicecmd/schema.py`, `voicecmd/default_config.yaml` (4 comandi d'esempio, commentato in italiano) e `tests/test_schema.py` (13 test, pytest completo: 34 passed). Modelli: `Config`, `SttConfig`, `TriggersConfig`, `TriggerConfig`, `MatchingConfig`, `FeedbackConfig`, `AudioConfig`, `Command`, `OpenAction`, `ShellAction`, alias `Action` (unione discriminata su `type`). Tutti con `extra="forbid"`. Default: language `it`; stt `turbo`/`int8` (provvisori, T05); trigger command `hotkey "<ctrl>+<alt>+space"`, dictation `mouse_button x2` (provvisori, T04); matching threshold 80, margin 5; feedback tutto true; audio silence_rms 0.005, keep_stream_open false, preroll_ms 300 (provvisori, T06); shell timeout 30; commands lista vuota. Il PRD §6 non contiene la sezione `audio`: l'ho resa opzionale con default. Nessuna deviazione; `default_config.yaml` e' gia' in package-data.

---

## Ondata 1 — Spike (parallela)

Chiudono i rischi di HANDOFF §7 prima di scrivere i moduli. Ogni spike lascia uno script riutilizzabile e una nota con: cosa è stato provato, risultato, **decisione**.

- [x] **T04 [P] [U] Trigger: pulsanti del mouse, soppressione, default**
  - **File**: `spikes/trigger_probe.py`, `docs/spikes/T04-trigger.md`
  - **Dipende da**: T01
  - **Cosa**: script che stampa ogni evento di tastiera e mouse visto da `pynput` (tasto/pulsante, premuto/rilasciato). Con l'utente verificare su Mac: (1) i pulsanti laterali sono distinti dal centrale? Se no, provare un event tap Quartz che legge il numero del pulsante; (2) si può sopprimere solo l'evento del trigger senza bloccare il resto? (3) una combinazione tenuta premuta scrive caratteri nell'app attiva? Proporre i binding di default per `command` e `dictation`.
  - **Fatto quando**: la nota indica: API da usare per il mouse su Mac, se la soppressione è possibile e come, binding di default scelti. Le parti Windows sono segnate "da verificare in T26".
  - Nota: `docs/spikes/T04-trigger.md`. Prove con l'utente (Logitech MX, senza Logi Options+). pynput riporta i laterali come `Button.middle`; il tap Quartz li distingue (centrale 2, x1 3, x2 4) e sopprime solo il pulsante del trigger (confermato: il browser non torna indietro). Ctrl+Option+Spazio tenuto premuto non scrive caratteri, quindi niente soppressione da tastiera. Default invariati: command `<ctrl>+<alt>+space`, dictation `x2`. Il tasto gesture del poggiapollice non manda eventi. Attenzione alla scorciatoia di sistema Ctrl+Option+Spazio (sorgenti di input), da citare in T27. Windows da verificare in T26.

- [x] **T05 [P] Benchmark dei modelli faster-whisper**
  - **File**: `spikes/stt_bench.py`, `docs/spikes/T05-stt.md`
  - **Dipende da**: T01
  - **Cosa**: da `testVoice.mp3` ricavare spezzoni di circa 3 s e 15 s; misurare tempo di caricamento e di trascrizione (media su 5 giri, escluso il primo) per `turbo`, `small`, `base` con `compute_type=int8`, `language="it"`. Verificare i nomi dei modelli accettati dalla versione installata, se il parametro `hotwords` è disponibile e come si legge `no_speech_prob` dai segmenti. Confrontare a occhio la qualità del testo.
  - **Fatto quando**: la nota ha la tabella dei tempi e indica il modello e i parametri di default, rispetto all'obiettivo di 1,5 s del PRD §4. Dice in modo esplicito che i numeri valgono per questo Mac e non per Windows.
  - Nota: `docs/spikes/T05-stt.md`. Su M5 CPU int8, clip 3 s: turbo 4,95 s, small 1,23 s, base 0,39 s. Decisione: default `small`/`int8`, `beam_size=1`, niente VAD, `hotwords` non passato per ora (peggiorava il testo). `turbo` valido ma fuori obiettivo su CPU. Da fare dal coordinatore: default `stt.model` da `turbo` a `small` in schema e YAML. Poi, su richiesta dell'utente: default portato a `small` e provato MPS (turbo 1,07 s su 3 s, testo perfetto). L'utente ha scelto `stt.device: auto` (MPS su Apple Silicon con ripiego su CPU; model/compute_type `auto`): aggiornati `schema.py`, `default_config.yaml`, `tests/test_schema.py`, HANDOFF §3 e il task T09.

- [x] **T06 [P] [U] Ritardo di apertura del microfono**
  - **File**: `spikes/mic_latency.py`, `docs/spikes/T06-mic.md`
  - **Dipende da**: T01
  - **Cosa**: script che alla pressione di Invio apre un `sd.InputStream` a 16 kHz, registra 3 s e salva un wav; misura il tempo tra la richiesta e il primo blocco audio. L'utente parla subito dopo Invio e riascolta: la prima sillaba c'è? Ripetere con stream già aperto e buffer circolare di 300 ms.
  - **Fatto quando**: la nota riporta il ritardo misurato e decide il default di `audio.keep_stream_open`.
  - Nota: `docs/spikes/T06-mic.md`. Script esteso con `--key` (trigger = Shift via pynput). Cold: richiesta -> primo blocco 103-521 ms (media 272), prima apertura dopo l'avvio ~3,3 s. Warm: voce catturata 20-40 ms dopo il trigger. "Abri" per "Apri" anche in warm, quindi non è un taglio. Decisione dell'utente: `keep_stream_open: true`, `preroll_ms: 300`; aggiornati `schema.py` e `default_config.yaml`. Whisper allucina su audio muto ("Grazie a tutti."): lo scarto del silenzio in T08/T09 è obbligatorio.

---

## Ondata 2 — Moduli (parallela)

Tredici moduli indipendenti. Ciascuno rispetta i Protocol di `events.py`, tocca solo i propri file e ha i propri test con dipendenze finte.

- [x] **T07 [P] Caricamento della configurazione**
  - **File**: `voicecmd/config.py`, `tests/test_config.py`
  - **Dipende da**: T03
  - **Cosa**: `config_path()` con `platformdirs.user_config_dir("voicecmd", appauthor=False)`; `ensure_config()` copia `default_config.yaml` se il file non esiste; `load_config(path) -> Config` solleva `ConfigError` con un messaggio in italiano che indica campo e problema (da errori YAML e da errori pydantic); `open_in_editor(path)` apre il file con l'app predefinita del sistema.
  - **Fatto quando**: test su cartella temporanea: creazione al primo avvio, caricamento valido, YAML malformato e schema violato producono `ConfigError` leggibile.
  - Nota: creati `voicecmd/config.py` e `tests/test_config.py` (17 test verdi). `config_path()` (platformdirs); `ensure_config(path=None) -> Path` copia `default_config.yaml` (via `importlib.resources`) solo se manca, creando le cartelle; `load_config(path=None) -> Config`; `open_in_editor(path=None)` non bloccante (`open` su Mac, `os.startfile` su Windows, `xdg-open` altrove). `ConfigError` elenca tutti gli errori, uno per riga, come `'commands[0].phrases': deve contenere almeno un elemento`; messaggi pydantic comuni tradotti in italiano, quelli dei validatori di `schema.py` lasciati invariati; errori YAML con riga e colonna. Scelte: file vuoto → `Config()` di default; file mancante o radice non dizionario → `ConfigError`. Il percorso include il tag dell'unione discriminata (es. `commands[0].action.shell`). Non verificati: apertura reale dell'editor, ramo Windows, caricamento del default da installazione non editable.

- [x] **T08 [P] Cattura audio**
  - **File**: `voicecmd/audio.py`, `tests/test_audio.py`
  - **Dipende da**: T02, T06
  - **Cosa**: `SoundDeviceRecorder` che rispetta `Recorder`. Callback → buffer protetto da lock (schema di `real.py:119-129`). `stop()` restituisce l'audio concatenato, oppure un array vuoto se l'RMS è sotto `silence_rms`. Modalità `keep_stream_open` con pre-roll secondo la decisione di T06. La creazione dello stream è iniettabile per i test.
  - **Fatto quando**: test con uno stream finto: i blocchi passati al callback tornano concatenati; il silenzio dà un array vuoto; il pre-roll antepone il numero giusto di campioni; `stop()` senza `start()` non solleva.
  - Nota: creati `voicecmd/audio.py` (`SoundDeviceRecorder(cfg: AudioConfig | None = None, *, stream_factory=None, samplerate=16000, blocksize=512)`, più `rms()` e `close()`) e `tests/test_audio.py` (15 test con stream finto). Callback → buffer con lock (real.py:119-129); `stop()` concatena e dà un array float32 vuoto se l'RMS è sotto `silence_rms`, senza registrazione o se ripetuto. Warm (T06): stream aperto nel costruttore, buffer circolare tagliato esattamente a `preroll_ms` (300 ms = 4800 campioni), anteposto a `start()`; se a `start()` lo stream non è `active` viene riaperto con un warning nel log. Cold: il costruttore apre e chiude lo stream una volta per scaldare CoreAudio, poi `start()` apre e `stop()` chiude. Microfono non disponibile all'avvio → log, nessuna eccezione, nuovo tentativo a `start()`, che invece solleva se fallisce (lo gestisce T20). Factory `(callback, samplerate, blocksize) -> stream`, default `sd.InputStream` mono float32 con import pigro. Tetti di durata 30/120 s lasciati al Controller. Il costruttore blocca (riscaldamento/apertura): T21 ne deve tenere conto. Non verificati: microfono reale, se `active` diventa davvero False quando lo stream cade (altrimenti serve `finished_callback`), efficacia del riscaldamento, Windows.

- [x] **T09 [P] Trascrizione**
  - **File**: `voicecmd/stt.py`, `tests/test_stt.py`
  - **Dipende da**: T02, T05
  - **Cosa**: `FasterWhisperTranscriber` che rispetta `Transcriber`. Carica il modello nel costruttore con i parametri decisi in T05 (leggere `docs/spikes/T05-stt.md`): funzione pura `resolve_stt(cfg, platform, machine) -> (device, model, compute_type)` per i valori `auto` (vedi commento in `SttConfig`); se il caricamento su `mps` fallisce, riprova su `cpu` con `small`/`int8` e lo registra nel log; `beam_size=1` su cpu, `beam_size=5` su mps (small su MPS con beam 1 sbagliava). `transcribe()` passa lingua e `hotwords`, scarta i segmenti con `no_speech_prob` alto, unisce il testo dei segmenti. Audio vuoto → stringa vuota senza chiamare il modello.
  - **Fatto quando**: test unitari con un modello finto (unione dei segmenti, scarto dei muti, audio vuoto, risoluzione di `auto` per Mac arm64 / Mac x86 / Windows, ripiego da mps a cpu); un test `slow` trascrive uno spezzone di `testVoice.mp3` e ottiene testo non vuoto.
  - Nota: creati `voicecmd/stt.py` e `tests/test_stt.py` (20 unitari + 3 slow verdi). `resolve_stt(cfg, platform, machine)` risolve `auto` come da `SttConfig` (mps solo con darwin+arm64). Modello creato da una factory iniettabile, import di faster_whisper ritardato. Caricamento su mps fallito → riprova su cpu/`int8` con warning nel log; il modello diventa `small` se era `auto`, altrimenti resta quello scelto dall'utente. `beam_size` 1 su cpu, 5 su mps. `transcribe()`: audio vuoto → "" senza chiamare il modello; `hotwords` uniti da spazi solo se la lista non è vuota; segmenti con `no_speech_prob > 0.6` scartati (parametro `no_speech_threshold`); testi uniti da spazi. **Problema aperto**: con turbo su mps `no_speech_prob` vale 0,0 anche sul silenzio (rumore sopra `silence_rms` → "Grazie a tutti."), mentre small lo scarta. Con `vad_filter=True` (nuovo parametro del costruttore, default `False` per la decisione T05) il rumore dà "" e il parlato costa +0,04 s. Decisione dell'utente: nuovo campo `stt.vad_filter`, default `true`; il costruttore lo legge da `cfg` se il parametro è `None` (aggiornati `schema.py`, `default_config.yaml`, `stt.py`, i test e la nota T05). Non verificati: fallimento MPS reale, errori MPS durante `transcribe()` (non intercettati), Windows, soglia 0,6 (da tarare in T24), `hotwords` col modello vero.

- [x] **T10 [P] Testo e matching**
  - **File**: `voicecmd/textutil.py`, `voicecmd/matcher.py`, `tests/test_textutil.py`, `tests/test_matcher.py`
  - **Dipende da**: T03
  - **Cosa**: `textutil`: `intelligent_concatenate` copiata da `real.py:37`; `normalize()` da `_norm` (`real.py:55`) estesa a frasi intere, con rimozione di accenti e punteggiatura e spazi compattati. `matcher.match(text, commands, threshold, margin) -> MatchResult`: punteggio `rapidfuzz` di ogni frase, migliore per comando; corrispondenza solo se il primo supera la soglia e stacca il secondo comando di `margin`. `closest` è sempre valorizzato se esiste almeno un comando.
  - **Fatto quando**: test: frase esatta; frase con errori tipici di trascrizione ("apri il brauser"); maiuscole, accenti e punto finale ignorati; frase estranea → nessuna corrispondenza ma `closest` presente; due comandi quasi pari → nessuna corrispondenza; testo vuoto; lista comandi vuota.
  - Nota: creati `voicecmd/textutil.py` (`intelligent_concatenate` da real.py:37; `normalize()`: minuscolo, accenti tolti con NFKD, ogni carattere non alfanumerico → spazio, spazi compattati), `voicecmd/matcher.py` (`match(text, commands, threshold=80, margin=5)`) e i test (23 verdi). Scorer `rapidfuzz.fuzz.ratio` sul testo normalizzato (WRatio/token_set/partial scartati: danno 90-100 a frasi parziali come "apri" contro "apri safari"). Aggiunta: il punteggio di una frase è il migliore fra confronto pieno e confronto senza articoli italiani, perché Whisper aggiunge articoli ("abre il safari" 80,0 → 81,8). Varianti degli spike con i default 80/5: "Abri Safari" 90,9 ✓, "Abre il safari" ✓, "abrisi a fare" 66,7 ✗ (serve una frase alternativa). Soglia e margine inclusivi; con un solo comando il secondo vale 0; a pari punteggio vince il primo della config; `heard` = testo originale; `closest` sempre valorizzato se c'è almeno un comando. Non provato su trascrizioni reali; due comandi che differiscono solo per l'articolo potrebbero non risultare ambigui.

- [x] **T11 [P] Azione `open`**
  - **File**: `voicecmd/actions/open.py`, `tests/test_action_open.py`
  - **Dipende da**: T03
  - **Cosa**: classe che rispetta `Action`. URL → `webbrowser`. Su Mac: `open <percorso>`, e `open -a <nome>` quando il target non è un percorso esistente. Su Windows: `os.startfile`. Espansione di `~` e delle variabili d'ambiente. Target inesistente → `ActionResult(ok=False, ...)` con messaggio chiaro, senza eccezioni.
  - **Fatto quando**: test con `subprocess`, `webbrowser` e `os.startfile` sostituiti: per ogni tipo di target viene scelta la chiamata giusta su entrambe le piattaforme (`sys.platform` simulato); gli errori diventano `ok=False`.
  - Nota: creati `voicecmd/actions/open.py` (`OpenActionRunner`, nome scelto per non scontrarsi con `schema.OpenAction`; helper `is_url`, `expand`, `looks_like_path`) e `tests/test_action_open.py` (26 test, chiamate di sistema sostituite). URL http/https/ftp/file/mailto → `webbrowser.open` (False → `ok=False`); `C:\...` non è preso per uno schema. Espansione di `~` e variabili d'ambiente. Target che sembra un percorso ma non esiste → `ok=False` "Il percorso ... non esiste", senza chiamate. Mac: `open <percorso>` se esiste, altrimenti `open -a <nome>`, timeout 10 s, codice ≠ 0 → `ok=False` con l'ultima riga di stderr. Windows: `os.startfile` per percorsi e nomi di app; `OSError` → `ok=False`. Ogni altra eccezione → `ok=False`. Extra: ripiego `xdg-open` su Linux. Non verificati: aperture reali su Mac (messaggi di `open -a` per app inesistente) e tutto Windows (incluso `%VAR%`).

- [x] **T12 [P] Azione `shell`**
  - **File**: `voicecmd/actions/shell.py`, `tests/test_action_shell.py`
  - **Dipende da**: T03
  - **Cosa**: classe che rispetta `Action`. Sceglie `mac`/`windows`/`command` in base al sistema; esegue con `subprocess.run(shell=True)`, timeout dallo spec, output catturato. Codice di uscita diverso da zero o timeout → `ok=False` con le ultime righe di stderr. Nessun comando per il sistema corrente → `ok=False`.
  - **Fatto quando**: test reali con comandi innocui: successo, codice di uscita ≠ 0, timeout (comando che dorme, timeout breve), variante mancante per il sistema.
  - Nota: creati `voicecmd/actions/shell.py` (`ShellActionRunner.run(spec) -> ActionResult`; il nome evita confusione con `schema.ShellAction`; non solleva mai; `select_command(spec, platform)`: variante `mac`/`windows` del sistema, ripiego su `command`, altrimenti `ok=False`) e `tests/test_action_shell.py` (14 test reali con echo/exit/sleep). Deviazione: `Popen` + `communicate(timeout)` al posto di `subprocess.run`, perché `run` al timeout resta bloccato se un figlio tiene aperte le pipe; su POSIX sessione separata e `killpg` al timeout, su Windows `taskkill /F /T`. Errori: "Codice di uscita N" + ultime 5 righe di stderr (o stdout); timeout "Tempo scaduto dopo X s". Cartella di lavoro ereditata dall'app. Ramo Windows non verificato.

- [x] **T13 [P] Azione dettatura**
  - **File**: `voicecmd/actions/dictation.py`, `tests/test_action_dictation.py`
  - **Dipende da**: T02
  - **Cosa**: `paste_text(text) -> ActionResult`: salva la clipboard, copia il testo, invia Cmd+V su Mac o Ctrl+V su Windows con `pynput`, attende un attimo e ripristina la clipboard. Prima di incollare attende che una funzione iniettata `keys_released()` restituisca vero, con un tetto di attesa (HANDOFF §7.6). Testo vuoto → nessuna azione, `ok=False`.
  - **Fatto quando**: test con clipboard e tastiera finte: sequenza salva → copia → incolla → ripristina; scorciatoia corretta per piattaforma; attesa del rilascio rispettata; clipboard ripristinata anche se l'incolla solleva.
  - Nota: creati `voicecmd/actions/dictation.py` e `tests/test_action_dictation.py` (12 test con clipboard, tastiera e orologio finti). `paste_text(text, *, clipboard, keyboard, keys_released, platform, release_timeout=1.0, restore_delay=0.25, sleep, clock) -> ActionResult`, non solleva mai; default `pyperclip` e `PynputKeyboard` (import pigri). Cmd+V su darwin, Ctrl+V altrove. Testo vuoto o di soli spazi → `ok=False` senza toccare nulla. Controlla `keys_released()` ogni 10 ms; se dopo 1 s i tasti sono ancora giù annulla con `ok=False` lasciando intatta la clipboard (HANDOFF §7.6). Pause di 50 ms tra copia e incolla e di 250 ms prima del ripristino, che sta in `finally`. Clipboard illeggibile → incolla senza ripristino. Limite: pyperclip gestisce solo testo (immagini/file in clipboard non ripristinati). Con trigger di dettatura sul mouse il Controller può passare `keys_released=None`. Da verificare in T25/T26: incolla reale con accenti, tempi, pyperclip su Windows, permesso Accessibilità per inviare tasti.

- [x] **T14 [P] Trigger da tastiera**
  - **File**: `voicecmd/triggers/hotkey.py`, `tests/test_trigger_hotkey.py`
  - **Dipende da**: T02, T04
  - **Cosa**: classe che rispetta `Trigger`, costruita con una mappa `Mode → stringa hotkey` (formato `pynput`, ad es. `<ctrl>+<alt>+space`, anche tasto singolo o solo modificatore). Tiene l'insieme dei tasti premuti: emette "premuto" quando la combinazione è completa, "rilasciato" quando uno dei suoi tasti viene lasciato. Ignora l'autorepeat. Espone `keys_released()` per T13. Applica la soppressione solo se T04 l'ha dichiarata possibile.
  - **Fatto quando**: test che alimentano direttamente i gestori di pressione e rilascio: combinazione completa → un solo "premuto"; autorepeat → nessun evento in più; rilascio di un tasto → "rilasciato"; due modalità con combinazioni diverse non si confondono; stringa hotkey non valida → errore chiaro.
  - Nota: creati `voicecmd/triggers/hotkey.py` e `tests/test_trigger_hotkey.py` (41 test con listener finto). `HotkeyTrigger(hotkeys: Mapping[Mode, str], listener_factory=None)` rispetta `Trigger`, `pynput.keyboard.Listener` in sola lettura (T04), espone `keys_released()` per T13. Parser proprio, perché `HotKey.parse` di pynput rifiuta `space` senza `<>` (cioè il default): accetta carattere, nome di tasto con o senza `<>`, codice `<n>`. Errori `HotkeyError(ValueError)` in italiano con trigger e tasto; rifiutate due modalità con la stessa hotkey e la mappa vuota. Modificatori generici validi per entrambi i lati, `<ctrl_r>` ecc. solo per quel lato. "Premuto" quando la combinazione si completa, "rilasciato" quando non è più completa; autorepeat ignorato; con una modalità attiva le altre non scattano; a pari completamento vince la combinazione più lunga; eventi iniettati (il Cmd+V della dettatura) e tasti `None` ignorati; eccezioni del callback nel log; `stop()` azzera lo stato. Non verificati: tastiera fisica; su Mac le combinazioni con lettera e Option/Ctrl potrebbero non scattare (il default no); su Windows `ctrl` generico trattato come sinistro; un rilascio perso lascia `keys_released()` falso (T13 ha il tetto di attesa).

- [x] **T15 [P] Trigger da mouse**
  - **File**: `voicecmd/triggers/mouse.py`, `tests/test_trigger_mouse.py`
  - **Dipende da**: T02, T04
  - **Cosa**: classe che rispetta `Trigger`, costruita con una mappa `Mode → pulsante` (`middle`, `x1`, `x2`). Su Windows `pynput.mouse.Listener`; su Mac event tap Quartz con soppressione dei soli pulsanti configurati (vedi `docs/spikes/T04-trigger.md`; codice di partenza in `spikes/trigger_probe.py`, `run_quartz_mouse`). Gli altri pulsanti e i movimenti non producono eventi.
  - **Fatto quando**: test che alimentano il gestore dei clic: il pulsante configurato emette premuto/rilasciato per la modalità giusta; gli altri vengono ignorati. Il ramo Windows è segnato nella nota come non verificato su macchina reale.
  - Nota: creati `voicecmd/triggers/mouse.py` (`MouseTrigger(buttons: Mapping[Mode, str])`, rispetta `Trigger`) e `tests/test_trigger_mouse.py` (14 test; callback Quartz provato con eventi creati in memoria, mai inviati). Logica comune `handle_click(button, pressed) -> bool` (True = pulsante del trigger, da sopprimere); inoltra solo le transizioni (pressione ripetuta soppressa ma non riemessa, rilascio senza pressione vista lasciato passare); eccezioni del gestore nel log. macOS: event tap Quartz come da T04 (session tap, head insert, opzione Default, maschera `OtherMouseDown`/`Up`, 2/3/4 = middle/x1/x2), CFRunLoop in thread daemon, riattivazione su timeout/user input, None solo per i pulsanti configurati. Windows: `pynput.mouse.Listener` con `win32_event_filter` (WM_MBUTTON, WM_XBUTTON) e `suppress_event()`; tutta la gestione sta nel filtro perché `suppress_event` blocca anche `on_click`. Pulsante non valido o assegnato a due modalità → `ValueError`; `start()` → `RuntimeError` in italiano se il tap non si crea (permessi), da intercettare in T21; `stop()` idempotente. Linux: warning e nessun evento. Da verificare: tap reale con il mouse (T25), tutto il ramo Windows (T26).

- [x] **T16 [P] Icona tray e menu**
  - **File**: `voicecmd/ui/tray.py`, `tests/test_tray.py`
  - **Dipende da**: T02
  - **Cosa**: `Tray` su `QSystemTrayIcon`. `set_state(state, mode)` cambia icona e tooltip; le icone sono disegnate via codice con `QPainter` (un colore per stato), senza file immagine. Menu: stato corrente (voce disabilitata), "Apri configurazione", "Ricarica configurazione", "Esci", esposti come segnali Qt. Espone l'oggetto `QSystemTrayIcon` per le notifiche.
  - **Fatto quando**: test con `pytest-qt`: ogni stato produce un'icona distinta; le voci di menu emettono i segnali corrispondenti.
  - Nota: creati `voicecmd/ui/tray.py` e `tests/test_tray.py` (10 test pytest-qt, offscreen). `Tray(QObject)` su `QSystemTrayIcon`; icone disegnate una volta con `QPainter` (cerchio pieno, bordo scuro): IDLE grigio, LISTENING arancione, PROCESSING blu, DONE verde, ERROR rosso. `set_state(state, mode)` aggiorna icona, tooltip (`voicecmd: <stato>`) e voce di stato del menu (es. "In ascolto (dettatura)"; in IDLE senza modalità). Segnali `open_config_requested`, `reload_config_requested`, `quit_requested`. Espone anche `tray_icon` (per il `Notifier`), `menu` (per "Apri log" in T23), `set_status_text(text)` (per "Caricamento del modello…" in T21), `show()`/`hide()`. Il colore distingue lo stato, non la modalità; niente icona template su macOS perché è richiesto il colore. Resa reale nella menu bar (chiara/scura) e clic reali da verificare in T25/T26.

- [x] **T17 [P] Overlay a schermo**
  - **File**: `voicecmd/ui/overlay.py`, `tests/test_overlay.py`
  - **Dipende da**: T02
  - **Cosa**: finestra senza bordi, sempre in primo piano, che non prende il focus e lascia passare i clic (flag Qt `Tool`, `FramelessWindowHint`, `WindowStaysOnTopHint`, `WindowDoesNotAcceptFocus`, attributo `WA_ShowWithoutActivating`). `show_state(state, mode)` mostra "In ascolto…", "Elaborazione…"; `show_outcome(outcome)` mostra esito e testo sentito e si nasconde da sola dopo circa 2 s (4 s per gli errori). Posizione: in basso al centro dello schermo in cui si trova il cursore.
  - **Fatto quando**: test con `pytest-qt`: i flag della finestra sono quelli richiesti; testi corretti per stato ed esito; scomparsa automatica con timer simulato. La nota ricorda che "non ruba il focus" va confermato a mano in T25/T26.
  - Nota: creati `voicecmd/ui/overlay.py` (`Overlay(QWidget)`, `show_state(state, mode)` / `show_outcome(outcome)`) e `tests/test_overlay.py` (15 test pytest-qt, offscreen). Flag: `Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus | WindowTransparentForInput`; attributi `WA_ShowWithoutActivating`, `WA_TransparentForMouseEvents`, `WA_TranslucentBackground`, `WA_MacAlwaysShowToolWindow` (senza, su macOS una finestra Tool sparisce quando l'app non è attiva); focus `NoFocus`. Testi: "In ascolto…" / "Elaborazione…" con sotto la modalità; IDLE nasconde; l'esito "Eseguito: <title>" / "Errore: <title>" con `detail` e il testo sentito tra «», scompare dopo 2000/4000 ms (parametri `done_ms`, `error_ms`; timer pubblico `hide_timer`); un nuovo stato annulla il timer. Posizione: in basso al centro dello schermo del cursore, 80 px dal bordo. Solo main thread. **Da confermare a mano in T25/T26**: niente focus rubato, clic che passano, visibilità sopra app a schermo intero / altri Spaces (niente `NSWindowCollectionBehavior` per ora), aspetto grafico.

- [x] **T18 [P] Suoni e notifiche**
  - **File**: `voicecmd/ui/sounds.py`, `voicecmd/ui/notify.py`, `voicecmd/ui/assets/sounds/*.wav`, `spikes/make_sounds.py`, `tests/test_sounds_notify.py`
  - **Dipende da**: T02
  - **Cosa**: tre suoni brevi (inizio ascolto, eseguito, errore) generati da `spikes/make_sounds.py` come toni sintetici e salvati nei wav. `Sounds.play(nome)` con `QSoundEffect`. `Notifier(tray_icon).notify(outcome)` usa `QSystemTrayIcon.showMessage`. Entrambi hanno un interruttore `enabled`.
  - **Fatto quando**: i tre wav esistono e durano meno di 300 ms; test: nome ignoto → errore chiaro; con `enabled=False` non parte niente; la notifica riceve titolo e testo presi dall'`Outcome`.
  - Nota: creati `voicecmd/ui/sounds.py`, `voicecmd/ui/notify.py`, `spikes/make_sounds.py` (solo libreria standard), i wav `start` 90 ms / `done` 160 ms / `error` 210 ms (sinusoidi 16 bit mono 44,1 kHz, rampa di 8 ms) e `tests/test_sounds_notify.py` (14 test con effetti e tray finti). `Sounds(enabled, effect_factory, sounds_dir)`: un `QSoundEffect` per suono creato al primo `play(nome)` e riusato; nome ignoto → `ValueError` con i nomi validi, anche con `enabled=False`. `Notifier(tray_icon, enabled)`: `notify(outcome)` → `showMessage(outcome.title, "Ho sentito: «heard»" + detail)`, icona Warning se `ok=False`, 4 s; in più `show(title, text, error=False)` per notifiche libere (T22). `enabled` modificabile a caldo; Qt importato dentro le funzioni. Il coordinatore ha corretto `package-data` in `ui/assets/**/*` (prima le sottocartelle restavano fuori). Da verificare in T25/T26: ascolto dei suoni, notifica reale, Windows.

- [x] **T19 [P] Permessi macOS**
  - **File**: `voicecmd/permissions.py`, `tests/test_permissions.py`
  - **Dipende da**: T01
  - **Cosa**: `check_permissions() -> list[MissingPermission]` con nome del permesso, spiegazione e percorso nelle Impostazioni di Sistema. Su Mac controlla Microfono, Accessibilità e Monitoraggio input (tramite `pyobjc` o `ctypes`; le API esatte vanno verificate sulla documentazione, non date per note). Indica quale eseguibile autorizzare (il terminale o l'interprete Python). Su Windows restituisce una lista vuota. Un controllo che fallisce diventa "stato sconosciuto", non un'eccezione.
  - **Fatto quando**: test con i controlli sostituiti: permessi mancanti elencati con il testo giusto; su piattaforma Windows simulata lista vuota; eccezione in un controllo gestita. La nota dice quali controlli sono stati provati davvero su questo Mac.
  - Nota: creati `voicecmd/permissions.py` e `tests/test_permissions.py` (14 test verdi). `check_permissions(platform=None, checks=None, executable=None) -> list[MissingPermission]`; `MissingPermission` (frozen): `name`, `explanation`, `settings_path`, `settings_url` (`x-apple.systempreferences:...Privacy_Microphone/Privacy_Accessibility/Privacy_ListenEvent`), `executable`, `status` (`denied`/`unknown`) e la proprietà `message` in italiano. API solo in lettura, senza dialoghi: `AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)`, `AXIsProcessTrusted()`, `Quartz.CGPreflightListenEventAccess()`. Microfono NotDetermined non segnalato (macOS chiede da solo alla prima registrazione), solo Denied/Restricted. Controllo che solleva → `status="unknown"`. Eseguibile da autorizzare: API privata `responsibility_get_pid_responsible_for_pid` (ctypes), in ripiego risalita dei padri con libproc fino al bundle .app più alto escluso Python.app, altrimenti `realpath(sys.executable)`. Provato davvero su questo Mac (in VS Code, permessi concessi): tre controlli True, `check_permissions()` → `[]`, eseguibile "Visual Studio Code" con entrambi i metodi. Non provati: permessi negati, avvio da Terminal.app/iTerm, Windows (restituisce `[]`).

---

## Ondata 3 — Integrazione (sequenziale)

- [x] **T20 Controller: macchina a stati**
  - **File**: `voicecmd/controller.py`, `tests/test_controller.py`
  - **Dipende da**: tutta l'ondata 2
  - **Cosa**: `Controller(config, recorder, transcriber, actions, feedback, paste)` senza import di Qt. `on_trigger(mode, pressed)`: premuto in IDLE → LISTENING e avvio registrazione; rilasciato → se durata < `MIN_PRESS_S` annulla, altrimenti PROCESSING su un worker thread. Timer per i tetti di durata. In PROCESSING: trascrive (con `hotwords` in modalità comando); comando → `matcher` → azione; dettatura → incolla. Produce sempre un `Outcome` e torna a IDLE. Trigger ricevuti fuori da IDLE (o rilasci senza pressione) ignorati. Ogni eccezione viene catturata e diventa un `Outcome` di errore. `reload(config)` sostituisce la configurazione solo in IDLE, altrimenti la applica al ritorno in IDLE.
  - **Fatto quando**: test con dipendenze finte e orologio controllabile: comando riconosciuto → azione chiamata una volta, sequenza di stati corretta; nessuna corrispondenza → nessuna azione, `Outcome` con testo sentito e comando più vicino; silenzio; pressione troppo breve; tetto di durata; dettatura; trigger durante PROCESSING ignorato; eccezione nel transcriber e nell'azione → errore e ritorno a IDLE.
  - Nota: creati `voicecmd/controller.py` e `tests/test_controller.py` (27 test con dipendenze finte, orologio e timer controllabili, worker sincrono, più un test con il worker vero). `Controller(config, recorder, transcriber, actions, feedback, paste, *, clock, submit, timer_factory, use_hotwords=False)`: `actions` è una mappa `type` → `Action` (`{"open": OpenActionRunner(), "shell": ShellActionRunner()}`), `paste(text) -> ActionResult` (in T21: `paste_text` con `keys_released` del trigger da tastiera). Worker di default: `ThreadPoolExecutor` a un thread (`voicecmd-worker`); `on_trigger` torna subito. Tetto di durata con `threading.Timer` (30/120 s): allo scadere chiude come un rilascio, e il rilascio vero successivo è ignorato. Pressione < `MIN_PRESS_S`: audio fermato e scartato, nessun `Outcome`, solo LISTENING → IDLE. Sequenza normale LISTENING → PROCESSING → DONE/ERROR → IDLE, con `on_outcome` fra DONE/ERROR e IDLE; IDLE viene notificato prima di accettare nuove pressioni, così la UI non riceve stati fuori ordine. Esiti: "Non ho sentito niente" (audio vuoto o testo vuoto, senza trascrivere nel primo caso), "Nessun comando riconosciuto" con "Il più vicino: X (N/100)", nome del comando + messaggio dell'azione, "Testo incollato" / "Dettatura non riuscita", "Microfono non disponibile" se `recorder.start()` solleva, "Errore" per ogni eccezione. Errori del feedback registrati nel log, mai fatali. `reload()` subito in IDLE, altrimenti al ritorno in IDLE (il ciclo in corso usa la config vecchia). `shutdown()` annulla il timer, ferma il worker e ignora nuovi trigger; il recorder lo chiude `app.py`. **`hotwords`**: spenti di default (`use_hotwords=False`) perché in T05 peggioravano il testo, anche se il PRD RF3 li prevede; da rivalutare in T24 con l'opzione già pronta (solo in modalità comando, parole distinte delle frasi).

- [x] **T21 Avvio e collegamento Qt**
  - **File**: `voicecmd/app.py`, `voicecmd/__main__.py`, `tests/test_app.py`
  - **Dipende da**: T20
  - **Cosa**: `app.py` crea `QApplication` (senza finestra principale, non termina alla chiusura dell'ultima finestra), carica la configurazione, controlla i permessi e li mostra se mancano, carica il modello mostrando lo stato "caricamento", costruisce i moduli reali e il `Controller`. Un `QObject` ponte implementa `Feedback` ed emette segnali verso tray, overlay, suoni e notifiche, rispettando gli interruttori di `feedback`. Avvia i trigger definiti in configurazione. "Esci" ferma trigger, recorder e worker in ordine. `__main__.py` chiama `app.main()`.
  - **Fatto quando**: test con `pytest-qt` e moduli finti: un ciclo completo premuto → rilasciato fa arrivare gli aggiornamenti alla UI sul main thread; "Esci" ferma tutto senza thread appesi. `.venv/bin/python -m voicecmd` parte su questo Mac e mostra l'icona (verifica visiva dell'utente in T25).
  - Nota: creati `voicecmd/app.py`, `voicecmd/__main__.py` e `tests/test_app.py` (12 test pytest-qt con moduli finti, compreso un ciclo che parte da un thread "listener" e arriva alla UI sul main thread, e l'uscita senza thread appesi). `VoiceCmdApp(config_path=None, factories=None, background_load=True)`: `ensure_config` + `load_config` (config non valida all'avvio → valori predefiniti + notifica), tray subito visibile con "Caricamento del modello…", controllo dei permessi con notifica, modello e microfono caricati su un thread `voicecmd-loader` con risultato riconsegnato al main thread via segnale; poi `Controller` e trigger (`trigger_maps` divide hotkey e pulsanti; `keys_released` del trigger da tastiera passato a `paste_text`). Errori di hotkey, di avvio dell'event tap o di caricamento del modello → notifica e icona in ERROR, mai crash. `FeedbackBridge(QObject)` implementa `Feedback` con segnali in coda; `_on_state`/`_on_outcome` rispettano `feedback.tray/overlay/sounds/notifications` (suoni: start su LISTENING, done/error a fine ciclo); gli avvisi di sistema (permessi, config) si mostrano anche con le notifiche spente. `Factories` raccoglie la costruzione dei moduli reali (sostituibile nei test). Menu: "Apri configurazione" → `open_in_editor`; "Ricarica" → versione base (T22 la estende); "Esci" ferma trigger → controller/worker → recorder, poi chiude Qt. Correzioni del coordinatore emerse dall'avvio reale: `stt._default_factory` prova prima `local_files_only=True` (prima ogni avvio contattava Hugging Face, contro la privacy del PRD §4); Ctrl+C nel terminale chiude l'app (handler SIGINT + QTimer). Avvio reale su questo Mac (`.venv/bin/python -m voicecmd`): turbo su mps, event tap del mouse attivo, "voicecmd pronto (2 trigger attivi)", nessuna richiesta di rete, uscita pulita con Ctrl+C. L'icona nella menu bar va confermata a vista in T25.

- [x] **T22 Ricarica della configurazione**
  - **File**: `voicecmd/app.py`, `tests/test_reload.py`
  - **Dipende da**: T21
  - **Cosa**: `QFileSystemWatcher` sul file (gestendo gli editor che lo sostituiscono invece di riscriverlo: ri-agganciare il percorso) con un breve ritardo anti-rimbalzo. File valido → `controller.reload()`, trigger riavviati se i binding sono cambiati, notifica "Configurazione ricaricata"; se cambiano `stt.model` o `compute_type`, avviso che serve il riavvio. File non valido → notifica con il messaggio di `ConfigError`, configurazione precedente mantenuta. Voce di menu "Ricarica" collegata allo stesso percorso.
  - **Fatto quando**: test: modifica valida applicata; modifica non valida rifiutata con messaggio e configurazione invariata; file sostituito (rename) ancora osservato; cambio di binding riavvia i trigger.
  - Nota: esteso `voicecmd/app.py`, creato `tests/test_reload.py` (11 test con `QFileSystemWatcher` vero su file temporanei; `tests/test_app.py` aggiornato, 13 test). Il watcher osserva il file **e la cartella**: dopo un salvataggio con rename (vim, VS Code, `os.replace`) il file viene ri-agganciato in `_watch()`. Anti-rimbalzo con `QTimer` a colpo singolo (`reload_debounce_ms`, default 300 ms) che riparte a ogni evento; poi si rilegge il testo e si ricarica solo se è cambiato rispetto all'ultimo visto (file assente a metà salvataggio, altri file della cartella o salvataggio identico → niente). File valido → `controller.reload()`, interruttori del feedback, notifica "Configurazione ricaricata"; file non valido → notifica con il messaggio di `ConfigError` + "Resta in uso la configurazione precedente". Binding cambiati (`trigger_maps` diverso) → trigger fermati e ricreati; se è in corso un ciclo il riavvio aspetta il ritorno in IDLE (fermare il listener a pulsante premuto perderebbe il rilascio). `keys_released` passato all'incolla ora delega al trigger da tastiera in uso (che cambia col riavvio). `restart_required(old, new)` segnala `language`, ogni campo di `stt` (anche `device`, `beam_size`, `vad_filter`) e di `audio`: la notifica dice "Riavvia voicecmd per applicare: …". "Ricarica" del menu usa lo stesso percorso anche senza modifiche. `shutdown()` ferma timer e watcher. Correzioni dall'avvio reale, prima di T22: `HotkeyTrigger.start()` attende il listener e solleva se `IS_TRUSTED` è falso (su macOS pynput senza permessi non falliva); `_real_paste` crea `PynputKeyboard` sul main thread (il suo `__init__` chiama `TSMGetInputSourceProperty`, che sul worker faceva terminare il processo con SIGTRAP). Da verificare a mano: salvataggio dal vero editor di sistema.

- [x] **T23 Log ed errori**
  - **File**: `voicecmd/logging_setup.py`, `voicecmd/app.py`, `voicecmd/controller.py`, `tests/test_logging.py`
  - **Dipende da**: T22
  - **Cosa**: log su file a rotazione in `platformdirs.user_log_dir("voicecmd", appauthor=False)` e su stderr. Ogni ciclo registra: modalità, durata dell'audio, tempo di trascrizione, testo sentito, comando e punteggio, esito. `sys.excepthook` e `threading.excepthook` scrivono nel log invece di chiudere l'app. Voce di menu "Apri log" (aggiunta in `app.py`).
  - **Fatto quando**: test: un ciclo scrive la riga attesa; un'eccezione in un thread finisce nel log. L'intera suite è verde.
  - Nota: creati `voicecmd/logging_setup.py` e `tests/test_logging.py` (12 test: file nella cartella indicata, percorso predefinito, rotazione reale a 4 file, nessun gestore duplicato, ripiego su stderr se la cartella non è scrivibile, riga di ciclo per comando / nessuna corrispondenza / dettatura / audio vuoto, eccezioni nel thread e nel main thread nel log, voce di menu). `setup_logging(directory=None, level, stderr=True, install_hooks=True) -> Path`: `RotatingFileHandler` 1 MB × 3 backup in `user_log_dir("voicecmd", appauthor=False)` (su questo Mac `~/Library/Logs/voicecmd/voicecmd.log`) più stderr, formato con nome del thread; richiamabile più volte. `sys.excepthook` / `threading.excepthook` scrivono a livello CRITICAL e non chiudono l'app (PySide6 passa da `sys.excepthook` anche per gli slot). Controller: `cycle_summary()` e una riga INFO per ciclo, es. `Ciclo comando, audio 1.50 s, trascrizione 0.42 s, testo 'apri chrome', comando Chrome (100/100), esito ok: Chrome - aperto`; senza corrispondenza `comando nessuno (più vicino X N/100)`; la dettatura riporta il messaggio dell'incolla. Il tempo di trascrizione usa `perf_clock` (iniettabile, default `time.perf_counter`). `app.py`: `main()` usa `setup_logging()`; `VoiceCmdApp(log_file=...)`; "Apri log" inserito nel menu dopo "Ricarica configurazione" (con `open_in_editor`, su macOS si apre in Console; file assente → notifica). Il log contiene i testi trascritti e resta sul computer.

---

## Ondata 4 — Verifica (parallela)

- [x] **T24 [P] Test end-to-end con audio da file**
  - **File**: `tests/test_e2e.py`, `tests/data/`
  - **Dipende da**: T23
  - **Cosa**: test `slow` con `Controller` reale, `FasterWhisperTranscriber` reale, matcher reale, recorder finto che restituisce uno spezzone di `testVoice.mp3`, azione finta. Prima trascrivere lo spezzone per sapere cosa dice, poi costruire una configurazione di prova in cui un comando ha quella frase e un altro una frase estranea.
  - **Fatto quando**: il test verifica che venga scelto il comando giusto, che con una configurazione senza quella frase l'esito sia "nessuna corrispondenza", e stampa i tempi di trascrizione.
  - Nota: creati `tests/test_e2e.py` (9 test `slow`, verdi due volte di fila; `pytest -m slow -s tests/test_e2e.py` stampa i tempi) e `tests/data/` (5 wav 16 kHz mono, 168 KB, con le frasi dei comandi predefiniti generate in locale con `say -v Alice`). Controller, `FasterWhisperTranscriber` (auto: turbo su mps), matcher veri; recorder e azioni finti; worker sincrono. Spezzone `testVoice.mp3` 0-3 s: "Registrazione di test, prova." → con il comando "registrazione di test prova" sceglie quello (azione chiamata una volta); senza quella frase "Nessun comando riconosciuto", "Il più vicino: Luce (37/100)". Comandi predefiniti da voce sintetica con 300 ms di rumore attorno: "apri chrome", "apri il browser", "blocca lo schermo", "che giorno è oggi" → comando giusto; dettatura (0-5 s) incollata; solo rumore → "Non ho sentito niente". Tempi del ciclo completo su questo Mac: 1,06-1,12 s (comando), 1,21 s (dettatura di 5 s), dentro 1,5 s del PRD. **Hotwords** (rivalutazione richiesta da T05/T20): 5 frasi × 6 varianti di rumore e volume. Turbo/mps: comandi giusti 23/30 senza, 24/30 con, punteggi più alti ("Apricrom" 84 → "apri chrome" 100); small/cpu: 24/30 → 29/30; **nessun comando sbagliato** in entrambi i casi. In dettatura gli hotwords tolgono punteggiatura e maiuscole: lì vanno tenuti spenti (il Controller già li usa solo in modalità comando). "apri github" con la voce sintetica resta irriconoscibile su turbo ("aprivi tab", 67-76/100), riconosciuto su cpu con hotwords: escluso dai test, da riprovare con la voce reale in T25. Soglia `no_speech` 0,6: non tarata, con `vad_filter` attivo il rumore dà già "" (il segmento non arriva al controllo). Limite: voce sintetica, non quella dell'utente. Decisione dell'utente dopo T24: nuovo campo `stt.hotwords` (default `true`) in `schema.py` e `default_config.yaml`; il Controller lo legge a ogni ciclo (`use_hotwords=None`), quindi cambiarlo non richiede il riavvio (escluso da `restart_required`); HANDOFF §3 aggiornato.

- [ ] **T25 [P] [U] Verifica manuale su macOS**
  - **File**: `docs/checklists/macos.md`
  - **Dipende da**: T23
  - **Cosa**: checklist che ripercorre i criteri di accettazione del PRD §7 più: concessione dei tre permessi da zero; pulsante del mouse come trigger; l'overlay non toglie il focus (scrivere in un editor mentre compare); dettatura con accenti; clipboard ripristinata; latenza percepita. L'utente la esegue e segna l'esito di ogni voce.
  - **Fatto quando**: l'utente ha compilato la checklist. Ogni voce fallita diventa un nuovo task in fondo a questa ondata.

- [ ] **T26 [P] [U] Verifica manuale su Windows**
  - **File**: `docs/checklists/windows.md`
  - **Dipende da**: T23
  - **Cosa**: istruzioni di installazione su Windows (Python, venv, `pip install -e .`), poi la stessa checklist di T25 più i punti lasciati "da verificare" in T04 e T15 (pulsanti `x1`/`x2`, soppressione), `os.startfile`, i comandi shell `windows:`, e la latenza con il modello di default su quella macchina.
  - **Fatto quando**: l'utente ha compilato la checklist su una macchina Windows reale. Ogni voce fallita diventa un nuovo task.

- [ ] **T27 [P] Guida utente**
  - **File**: `docs/GUIDA.md`
  - **Dipende da**: T23
  - **Cosa**: installazione su Mac e Windows, permessi macOS passo per passo, avvio, dove sta il file di configurazione, riferimento completo dello YAML con esempi per ogni tipo di azione, come scegliere frasi che si riconoscono bene, risoluzione dei problemi (trigger che non scatta, comando non riconosciuto, lentezza), dove sta il log. `README.md` non va modificato.
  - **Fatto quando**: ogni campo di `schema.py` è documentato e ogni comando citato nella guida è stato eseguito almeno una volta.

---

## Ondata 5 — Fase 2 (backlog, da dettagliare)

Non iniziare senza una richiesta esplicita dell'utente. Ogni voce va prima scomposta in task come quelli sopra.

- [ ] **T28 Gesture del mouse con stop su silenzio** — riconoscere un movimento disegnato tenendo premuto un pulsante; l'ascolto parte alla gesture e si chiude dopo circa 1 s di silenzio (serve un VAD). Nuovo trigger in `voicecmd/triggers/gesture.py`, nuova modalità di chiusura nel `Controller`, nuovi campi nello schema.
- [ ] **T29 Avvio automatico al login** — LaunchAgent su Mac, collegamento in Esecuzione automatica su Windows; voce di menu per attivarlo e disattivarlo.
- [ ] **T30 Eseguibile standalone** — `.app` e `.exe` con PyInstaller, modello scaricato al primo avvio; valutare firma e notarizzazione su Mac.

---

## Copertura dei requisiti

| Requisito (PRD) | Task |
|---|---|
| RF1 Trigger | T04, T14, T15, T20 |
| RF2 Cattura audio | T06, T08 |
| RF3 Trascrizione | T05, T09 |
| RF4 Matching | T10 |
| RF5 Azioni | T11, T12 |
| RF6 Dettatura | T13, T20 |
| RF7 Configurazione | T03, T07, T22 |
| RF8 Feedback | T16, T17, T18, T21 |
| RF9 Permessi | T19, T21 |
| Latenza | T05, T24, T25, T26 |
| Robustezza e log | T20, T23 |
| Criteri di accettazione | T24, T25, T26 |
