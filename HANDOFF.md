# HANDOFF — istruzioni per l'LLM che scrive il codice

Leggi questo file per primo, per intero. Vale sia per l'agente che coordina sia per ogni sub-agent che esegue un singolo task. Non hai visto la conversazione in cui sono stati decisi i requisiti: tutto quello che ti serve è qui, in [PRD.md](PRD.md) e in [tasks.md](tasks.md).

## 1. Il progetto

`voicecmd` è un'app desktop per macOS e Windows che sta nella menu bar / system tray. L'utente tiene premuto un tasto o un pulsante del mouse, parla e rilascia: l'app trascrive in locale con Whisper e poi esegue il comando salvato più simile alla frase (aprire un'app, lanciare uno script) oppure, con un secondo trigger, incolla il testo dettato nel campo attivo.

Oggi il repo contiene solo demo di trascrizione: `real.py` (trascrizione continua, la base di partenza), `live.py`, `test_file.py`. Il package `voicecmd/` va creato da zero seguendo `tasks.md`.

## 2. Ordine di lettura

1. `HANDOFF.md` (questo file)
2. `PRD.md` — cosa deve fare l'app e cosa è escluso
3. `tasks.md` — le convenzioni in testa, poi il tuo task
4. `voicecmd/events.py` — i contratti tra moduli (esiste dopo il task T02)
5. `real.py` — solo le parti da riusare, elencate al punto 5

## 3. Decisioni già prese

Non riaprirle. Se una si rivela impraticabile, fermati, scrivi il motivo nella nota del task e segnalalo: non scegliere un'alternativa da solo.

| Decisione | Motivo |
|---|---|
| **PySide6 (Qt)** per tray, overlay, suoni, notifiche e controllo del file di config | Un solo event loop su entrambi i sistemi. `pystray` + `tkinter` su macOS si contendono il main thread. |
| **faster-whisper** al posto di openai-whisper | Molto più veloce su CPU, non richiede PyTorch. Su Mac Apple Silicon usa il backend MPS di ctranslate2 (sperimentale) con ripiego su CPU: `stt.device: auto`, decisione dell'utente dopo lo spike T05. |
| **Una trascrizione unica al rilascio** | I comandi durano 2-3 s: le finestre scorrevoli di `real.py` (8 s / 4 s) aggiungerebbero solo latenza. |
| **pynput** per hotkey e pulsanti del mouse | Stessa API su Mac e Windows. Limiti noti al punto 7. |
| **rapidfuzz** per il matching | Locale, veloce, tollera gli errori di trascrizione. |
| **Incolla via clipboard** per la dettatura | Digitare carattere per carattere sbaglia accenti e layout di tastiera. |
| **pydantic + PyYAML** per la configurazione | Errori di validazione leggibili da mostrare all'utente. |
| **Push-to-talk**, lingua italiana, shell senza conferma | Scelte dell'utente, vedi PRD §2. |

## 4. Architettura

```
voicecmd/
  events.py          stati, eventi, Protocol delle interfacce      ← contratto, non cambiarlo
  schema.py          modelli pydantic della configurazione         ← contratto, non cambiarlo
  default_config.yaml  modello creato al primo avvio
  config.py          percorsi, caricamento, validazione, primo avvio
  audio.py           Recorder: start() / stop() -> np.ndarray
  stt.py             Transcriber su faster-whisper
  textutil.py        normalize(), intelligent_concatenate()
  matcher.py         match(text, commands) -> MatchResult
  actions/           open.py, shell.py, dictation.py
  triggers/          hotkey.py, mouse.py
  ui/                tray.py, overlay.py, sounds.py, notify.py, assets/
  permissions.py     controlli dei permessi macOS
  controller.py      macchina a stati; nessun import di Qt
  app.py             collegamento Qt: segnali, thread, watcher del file
  logging_setup.py
  __main__.py        python -m voicecmd
tests/
docs/spikes/         decisioni degli spike
docs/checklists/     verifiche manuali
```

**Flusso.** Trigger premuto → `controller` passa a LISTENING e avvia il `Recorder` → trigger rilasciato → PROCESSING: `Transcriber` → in modalità comando `matcher` e poi l'azione; in modalità dettatura l'azione `dictation` → DONE o ERROR → IDLE.

**Thread.** Qt occupa il main thread. I listener di `pynput` hanno i loro thread. Trascrizione e azioni girano su un solo worker thread. `controller.py` non importa Qt: riceve le dipendenze come oggetti che rispettano i Protocol di `events.py`, così si testa con dei finti. È `app.py` a trasformare le chiamate verso la UI in segnali Qt: nessun widget va toccato fuori dal main thread.

## 5. Cosa riusare da `real.py`

| Da `real.py` | Dove va | Uso |
|---|---|---|
| `intelligent_concatenate` (riga 37) | `textutil.py` | Unire i segmenti restituiti da faster-whisper |
| `_norm` (riga 55) | `textutil.py` | Base di `normalize()`; aggiungere la rimozione degli accenti |
| callback → buffer protetto da lock (righe 119-129) | `audio.py` | Stesso schema di cattura |
| filtro RMS `SILENCE_RMS` (riga 156) | `audio.py` | Scartare le registrazioni mute |
| controllo `no_speech_prob` (riga 174) | `stt.py` | Scartare i segmenti senza parlato |

`merge_text` e le finestre scorrevoli **non** servono nell'MVP. Copia le funzioni: `real.py` non va importato né modificato.

## 6. Regole di lavoro

- **Perimetro.** Modifica solo i file elencati nel campo *File* del tuo task. Mai `real.py`, `live.py`, `test_file.py`, `requirements.txt`, `README.md`, i file audio.
- **Contratti.** `events.py` e `schema.py` non si cambiano dentro un task `[P]`. Se ti serve una modifica, descrivila nella nota del task e fermati su quel punto: la applica chi coordina, tra un'ondata e l'altra.
- **Dipendenze.** Sono tutte dichiarate in `pyproject.toml` dal task T01. Se te ne serve una nuova, scrivilo nella nota: non modificare `pyproject.toml` in un task `[P]`.
- **Test.** Ogni modulo ha i suoi test in `tests/`. Microfono, tastiera, mouse, schermo e modello Whisper stanno dietro interfacce: nei test unitari si usano dei finti. I test che caricano il modello vero vanno marcati `@pytest.mark.slow`.
- **Scope.** Niente di ciò che il PRD §5 esclude, anche se sembra facile da aggiungere.
- **Stile.** Commenti e messaggi per l'utente in italiano, come in `real.py`; identificatori in inglese. Type hint sulle funzioni pubbliche.
- **Piattaforma.** Il codice specifico di un sistema sta dietro `sys.platform` e l'import avviene dentro il ramo, così il modulo si importa su entrambi.
- **Git.** Non fare commit né push se non ti viene chiesto.

## 7. Rischi aperti

Gli spike dell'ondata 1 servono a chiuderli. Le decisioni vanno scritte in `docs/spikes/` e chi implementa i moduli dipendenti le deve leggere.

1. **Pulsanti extra del mouse su macOS.** `pynput` su Mac potrebbe riportare i pulsanti 4 e 5 come "centrale" senza distinguerli. Ripiego previsto: un event tap Quartz tramite `pyobjc`, leggendo il numero del pulsante dall'evento.
2. **Eventi che arrivano anche all'app in primo piano.** Il tasto laterale del mouse fa "indietro" nel browser; una combinazione come Ctrl+Alt+Spazio tenuta premuta può inserire caratteri nel campo attivo. Va verificato se si può sopprimere solo l'evento del trigger e, se no, scelti default che non disturbano (per esempio un solo modificatore destro, o un tasto funzione alto).
3. **Latenza di faster-whisper.** Misurare `turbo` e `small` con `int8` su un audio di 3 s e fissare il default. Il nome del modello `turbo` va verificato sulla versione installata.
4. **Apertura del microfono.** Aprire lo stream alla pressione può tagliare la prima sillaba. Ripiego: stream sempre aperto con un pre-roll di circa 300 ms, attivabile da YAML.
5. **Python 3.14.** Il venv usa Python 3.14.6. Il task T01 verifica che PySide6, faster-whisper (ctranslate2), pynput e pyobjc abbiano wheel per questa versione. Se manca qualcosa, fermati e segnalalo: la scelta di cambiare versione di Python spetta all'utente.
6. **Modificatori ancora premuti all'incolla.** Se il trigger di dettatura è una combinazione, al momento di inviare Cmd/Ctrl+V qualche tasto potrebbe essere ancora giù e alterare la scorciatoia. Prima di incollare bisogna attendere che i tasti del trigger siano rilasciati.

## 8. Ambiente

- macOS su Apple Silicon (arm64); venv già presente in `.venv` con Python 3.14.6 e le dipendenze delle demo (openai-whisper, torch). Le dipendenze dell'app si aggiungono allo stesso venv.
- Installazione: `.venv/bin/pip install -e ".[dev]"` (dopo T01)
- Test: `.venv/bin/pytest` · test lenti compresi: `.venv/bin/pytest -m "slow or not slow"`
- Avvio: `.venv/bin/python -m voicecmd`
- `test_file.py` nella root **non** è un test pytest (carica Whisper all'import): `pyproject.toml` deve limitare la raccolta a `tests/`.
- File di configurazione dell'utente, tramite `platformdirs.user_config_dir("voicecmd", appauthor=False)`:
  - Mac: `~/Library/Application Support/voicecmd/config.yaml`
  - Windows: `%LOCALAPPDATA%\voicecmd\config.yaml`
- Audio di prova: `testVoice.mp3` (versionato), `testEmy.m4a` (solo locale).

## 9. Come si esegue il backlog

**Chi coordina**
1. Esegue le ondate nell'ordine di `tasks.md`. Un'ondata parte solo quando la precedente è tutta spuntata.
2. Nelle ondate parallele lancia un sub-agent per ogni task `[P]`, tutti insieme.
3. A fine ondata esegue l'intera suite di test, controlla che nessuno abbia toccato file fuori perimetro (`git status`), applica le eventuali modifiche ai contratti richieste nelle note, poi passa oltre.
4. I task `[U]` richiedono l'utente: prepara il materiale, poi chiedi a lui di eseguire la prova e riportare l'esito. Non spuntarli da solo.

**Prompt per un sub-agent** (da copiare, sostituendo l'ID):

> Leggi `HANDOFF.md` per intero, poi il task `<ID>` in `tasks.md`. Esegui solo quel task e modifica solo i file indicati nel campo *File*. Hai finito quando il criterio *Fatto quando* è soddisfatto: esegui i test, spunta la checkbox del task e aggiungi sotto una riga `Nota:` con cosa hai fatto e ogni deviazione o problema aperto. Riporta l'esito dei test così com'è.

**Ripresa dopo un'interruzione.** Parti dal primo task non spuntato. Prima leggi le note dei task già chiusi e i file in `docs/spikes/`.

## 10. Cosa non si può verificare da questa macchina

- **Windows.** Tutto il comportamento su Windows richiede una macchina Windows reale. Scrivi il codice seguendo la documentazione, ma non dichiararlo funzionante: lo conferma l'utente con la checklist T26.
- **Permessi macOS e input fisico.** Pressioni di tasti, pulsanti del mouse, microfono e finestre di sistema dei permessi richiedono una persona. I task `[U]` si chiudono solo con la sua conferma.

## 11. Quando un task è finito

- il criterio *Fatto quando* è soddisfatto e i test sono verdi;
- nessun file fuori dal perimetro è stato modificato;
- la checkbox è spuntata e c'è la riga `Nota:`;
- se qualcosa non funziona o non è stato verificato, la nota lo dice in modo esplicito.
