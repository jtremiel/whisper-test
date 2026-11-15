# PRD — voicecmd: comandi vocali push-to-talk per Mac e Windows

Stato: **accettato** il 2026-11-15. Documenti collegati: [HANDOFF.md](HANDOFF.md) (per chi scrive il codice), [tasks.md](tasks.md) (backlog).

## 1. Obiettivo

Un'app che gira in background (menu bar su Mac, system tray su Windows). L'utente tiene premuto un tasto o un pulsante del mouse, parla, rilascia. L'app trascrive in locale e:

- **modalità comando**: esegue l'azione salvata la cui frase è più simile a quanto detto;
- **modalità dettatura**: incolla il testo nel campo attivo.

Punto di partenza è `real.py`, una demo di trascrizione continua con Whisper. L'app ne riusa alcune parti ma non la sostituisce.

## 2. Decisioni

| Tema | Scelta MVP |
|---|---|
| Piattaforme | macOS e Windows, stesso codice Python |
| Trigger | Hotkey globale da tastiera e pulsante extra del mouse, entrambi configurabili |
| Ascolto | Push-to-talk: premi, parli, rilasci; una sola trascrizione dell'intero audio |
| Azioni | Apri app/file/cartella/URL · comando shell/script · dettatura libera |
| Dettatura | Trigger dedicato, separato da quello dei comandi; testo incollato al rilascio |
| Matching | Fuzzy su frasi fisse (una o più per comando), soglia configurabile |
| Nessuna corrispondenza | Suono di errore, overlay e notifica con il testo sentito e il comando più vicino; niente viene eseguito |
| Configurazione | File YAML + menu tray (Apri configurazione, Ricarica, Esci); ricarica automatica al salvataggio |
| Feedback | Icona tray a stati, suoni, overlay a schermo, notifica di sistema; ognuno disattivabile da YAML |
| Motore STT | faster-whisper (al posto di openai-whisper usato in `real.py`) |
| Lingua | Italiano (`language: it`), modificabile da YAML |
| Shell | Comandi eseguiti senza conferma: il file di configurazione è dell'utente |
| Distribuzione | Script Python in un venv, avviato da terminale |

## 3. Requisiti funzionali

**RF1 — Trigger.** Due binding indipendenti, `command` e `dictation`. Ciascuno è una combinazione di tasti, un tasto singolo (anche un solo modificatore) o un pulsante del mouse. Pressione = inizio ascolto, rilascio = fine. Pressioni più brevi di 300 ms vengono ignorate. Durata massima: 30 s per i comandi, 120 s per la dettatura; al tetto l'ascolto si chiude come a un rilascio. Un trigger premuto mentre l'app sta già ascoltando o elaborando viene ignorato.

**RF2 — Cattura audio.** Microfono a 16 kHz mono. L'audio sotto la soglia di silenzio (RMS) viene scartato senza trascrivere e segnalato come "non ho sentito niente".

**RF3 — Trascrizione.** faster-whisper, modello caricato all'avvio e tenuto in memoria. Modello e `compute_type` configurabili. In modalità comando le frasi dei comandi vengono passate al modello come suggerimento (`hotwords`) per orientare il riconoscimento.

**RF4 — Matching.** Testo e frasi vengono normalizzati (minuscole, senza punteggiatura né accenti) e confrontati con `rapidfuzz`. Vince il comando col punteggio più alto se supera la soglia (default 80) e stacca il secondo comando di un margine minimo (default 5); altrimenti è "nessuna corrispondenza".

**RF5 — Azioni.**
- `open`: apre un'app, un file, una cartella o un URL con il meccanismo del sistema operativo.
- `shell`: esegue un comando; può essere unico o distinto per sistema (`mac:` / `windows:`). Timeout configurabile (default 30 s). Codice di uscita ed errore vengono riportati nel feedback.

**RF6 — Dettatura.** Il testo trascritto viene incollato nel campo attivo tramite clipboard e Cmd+V / Ctrl+V; la clipboard precedente viene ripristinata subito dopo.

**RF7 — Configurazione.** File YAML nella cartella di configurazione dell'utente, creato da un modello con comandi d'esempio al primo avvio. Alla modifica viene ricaricato da solo. Un file non valido produce un messaggio che indica campo ed errore e **non** sostituisce la configurazione in uso.

**RF8 — Feedback.** Stati visibili: inattivo → in ascolto → elaborazione → eseguito oppure errore. L'overlay mostra stato e testo sentito e non deve togliere il focus all'app in primo piano.

**RF9 — Permessi.** All'avvio su macOS l'app verifica Microfono, Accessibilità e Monitoraggio input; se ne manca uno spiega quale attivare e per quale eseguibile.

## 4. Requisiti non funzionali

- **Latenza.** Dal rilascio all'azione: obiettivo ≤ 1,5 s per un comando di 2-3 s su Apple Silicon. Su Windows senza GPU va misurata e il modello di default scelto di conseguenza.
- **Privacy.** Tutto in locale; nessuna connessione dopo il download del modello.
- **Robustezza.** Un errore nella trascrizione, in un'azione o nella configurazione non deve mai chiudere l'app. Gli errori finiscono in un file di log.

## 5. Fuori scope dell'MVP

Gesture del mouse e del trackpad · stop automatico su silenzio · comandi con parametri (`apri {app}`) · interpretazione tramite LLM · simulazione di scorciatoie da tastiera come azione · editor grafico dei comandi · dettatura in streaming · eseguibile standalone · avvio automatico al login.

Previsti in fase 2: gesture del mouse (con stop su silenzio), avvio automatico al login, eseguibile standalone.

## 6. Esempio di configurazione

```yaml
language: it
stt:
  model: turbo
  compute_type: int8
triggers:
  command:
    hotkey: "<ctrl>+<alt>+space"
  dictation:
    mouse_button: x2
matching:
  threshold: 80
  margin: 5
feedback:
  tray: true
  sounds: true
  overlay: true
  notifications: true
commands:
  - name: Apri browser
    phrases: ["apri il browser", "apri chrome"]
    action:
      type: open
      target: "https://www.google.com"
  - name: Blocca schermo
    phrases: ["blocca lo schermo"]
    action:
      type: shell
      mac: "pmset displaysleepnow"
      windows: "rundll32.exe user32.dll,LockWorkStation"
```

## 7. Criteri di accettazione

1. Tenendo premuto il trigger dei comandi e dicendo "apri il browser", al rilascio si apre il browser e il feedback mostra "eseguito".
2. Una frase senza corrispondenza produce errore con il testo sentito e il comando più vicino; non parte nessuna azione.
3. Tenendo premuto il trigger di dettatura in un editor di testo, al rilascio compare il testo dettato, accenti compresi, e la clipboard torna quella di prima.
4. Aggiungendo un comando al YAML e salvando, il comando funziona senza riavviare l'app.
5. Salvando un YAML non valido, l'app segnala l'errore e continua a funzionare con la configurazione precedente.
6. Un comando shell che fallisce mostra l'errore e l'app resta attiva.
7. I punti 1-6 valgono sia su macOS sia su Windows.
