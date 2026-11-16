# Guida di voicecmd

voicecmd vive nella menu bar del Mac (o nell'area di notifica di Windows). Tieni premuto un
tasto o un pulsante del mouse, parli, rilasci:

- in **modalità comando** esegue il comando della tua configurazione più simile a ciò che hai
  detto (aprire un sito o un'app, lanciare un comando);
- in **modalità dettatura** scrive quello che hai detto nel campo di testo in cui si trova il
  cursore.

La trascrizione avviene sul tuo computer con [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
Dopo il primo download del modello voicecmd non si collega più a internet.

---

## 1. Installazione

### macOS (Apple Silicon o Intel)

Serve Python 3.11 o più recente; è stato provato con Python 3.14 di Homebrew.

```bash
brew install python@3.14            # se non hai già Python
git clone https://github.com/jtremiel/whisper-test.git
cd whisper-test
git checkout applicazione
python3.14 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q                  # facoltativo: verifica che tutto sia a posto
```

### Windows 10/11

Serve Python 3.12 o 3.13 a 64 bit da [python.org](https://www.python.org/downloads/), con
"Add python.exe to PATH" spuntato, e [Git for Windows](https://git-scm.com/). In PowerShell:

```powershell
git clone https://github.com/jtremiel/whisper-test.git
cd whisper-test
git checkout applicazione
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Se PowerShell rifiuta `Activate.ps1`, esegui una volta
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

> La versione Windows non è ancora stata provata su una macchina reale (checklist in
> [`checklists/windows.md`](checklists/windows.md)).

## 2. Avvio

Dalla cartella del progetto:

| Sistema | Comando |
|---|---|
| macOS | `.venv/bin/python -m voicecmd` |
| Windows | `.\.venv\Scripts\python -m voicecmd` |

Al **primo avvio** voicecmd:

1. crea il file di configurazione con alcuni comandi d'esempio (vedi §4);
2. scarica il modello Whisper da Hugging Face (circa 500 MB per `small`, 1,6 GB per `turbo`). È l'unica connessione a internet; dagli avvii successivi usa la copia
   locale.

Nella menu bar compare un cerchio grigio. Quando il modello è caricato il terminale scrive
`voicecmd pronto (2 trigger attivi)`.

Per chiudere: menu dell'icona > **Esci**, oppure Ctrl+C nel terminale.

## 3. Permessi su macOS

macOS assegna i permessi **all'app da cui lanci voicecmd**, cioè il terminale: iTerm, Terminal
o Visual Studio Code. Non va aggiunto "Python". Se cambi terminale, devi concedere di nuovo i
permessi a quello nuovo.

| Permesso | A cosa serve |
|---|---|
| **Microfono** | registrare la voce |
| **Monitoraggio input** | accorgersi della pressione dei tasti e dei pulsanti del mouse usati come trigger |
| **Accessibilità** | incollare il testo dettato (inviare Cmd+V) e bloccare il pulsante del mouse del trigger, così non fa "indietro" nel browser |

All'avvio voicecmd controlla i permessi e, se ne manca qualcuno, mostra una notifica che dice
quale attivare e per quale app.

**Passo per passo:**

1. Apri **Impostazioni di Sistema > Privacy e sicurezza > Monitoraggio input**.
2. Se il tuo terminale è nell'elenco, attiva l'interruttore. Se non c'è, premi **+**, scegli
   l'app in Applicazioni (es. `iTerm`) e premi Apri.
3. Fai lo stesso in **Privacy e sicurezza > Accessibilità**.
4. **Chiudi del tutto il terminale** (Cmd+Q) e riaprilo: macOS applica i permessi solo a un
   processo nuovo.
5. Avvia voicecmd. La prima volta che registra, macOS chiede il permesso **Microfono**:
   rispondi Consenti.

Se il terminale è già nell'elenco e acceso ma non funziona (capita dopo un aggiornamento del
terminale), toglilo con **−**, aggiungilo di nuovo con **+** e ripeti dal punto 4.

Su Windows non servono questi permessi. Controlla solo che **Impostazioni > Privacy e
sicurezza > Microfono > Consenti alle app desktop di accedere al microfono** sia attivo.

## 4. Uso

### Trigger

Ci sono due trigger, uno per modalità. I valori iniziali sono:

| Modalità | Trigger iniziale |
|---|---|
| comando | **Ctrl+Option+Spazio** (Ctrl+Alt+Spazio su Windows) |
| dettatura | pulsante laterale **avanti** del mouse |

Si usano così: **tieni premuto**, parla, **rilascia**. La registrazione dura quanto la
pressione.

- Una pressione più breve di 0,3 s viene ignorata (un clic accidentale non fa nulla).
- Massimo 30 s per un comando e 120 s per una dettatura: al limite l'ascolto si chiude da solo.
- Mentre voicecmd sta ascoltando o elaborando, un'altra pressione viene ignorata.
- In dettatura il testo viene incollato dove si trova il cursore. Clicca prima nel campo giusto.

### Cosa vedi e senti

| Colore dell'icona | Stato |
|---|---|
| grigio | in attesa |
| arancione | in ascolto |
| blu | elaborazione |
| verde | fatto |
| rosso | errore |

Durante l'ascolto compare anche un piccolo riquadro (overlay) con lo stato e, alla fine, con
il testo sentito: resta circa 2 s se tutto è andato bene e 4 s in caso di errore. L'overlay
non prende il focus e non blocca i clic: puoi continuare a scrivere. Ci sono anche un suono
all'inizio dell'ascolto, uno alla riuscita e uno all'errore, e una notifica di sistema con
l'esito. Ognuno si può spegnere (vedi `feedback` in §5).

### Menu dell'icona

| Voce | Cosa fa |
|---|---|
| Apri configurazione | apre il file di configurazione con l'app predefinita |
| Ricarica configurazione | rilegge il file subito (di solito non serve: lo fa da sola al salvataggio) |
| Apri log | apre il file di log (su Mac in Console) |
| Esci | chiude voicecmd |

## 5. Il file di configurazione

### Dove sta

| Sistema | Percorso |
|---|---|
| macOS | `~/Library/Application Support/voicecmd/config.yaml` |
| Windows | `%LOCALAPPDATA%\voicecmd\config.yaml` |

Per stampare il percorso esatto:

```bash
.venv/bin/python -c "from voicecmd.config import config_path; print(config_path())"
```

### Modifiche e ricarica

Quando salvi il file, voicecmd lo rilegge da solo dopo circa 0,3 s e mostra la notifica
**"Configurazione ricaricata"**. Comandi, soglie, feedback e trigger valgono subito.

Le sezioni `stt`, `audio` e `language` vengono lette solo all'avvio (servono a preparare il
modello e il microfono): se le cambi, la notifica dice **"Riavvia voicecmd per applicare: …"**.
Fa eccezione `stt.hotwords`, che vale subito.

Se il file contiene un errore, voicecmd mostra **"Configurazione non valida"** con il campo e
il problema, ad esempio `'matching.threshold': valore troppo alto (limite: 100.0)`, e **continua a
usare la configurazione precedente**. Correggi e salva di nuovo.

Un campo scritto male è un errore, non viene ignorato: `treshold` invece di `threshold` dà
`'matching.treshold': campo sconosciuto`.

### Riferimento completo

Ogni sezione è facoltativa: quello che manca prende il valore predefinito.

#### `language`

| Campo | Valori | Predefinito | Significato |
|---|---|---|---|
| `language` | codice ISO di 2 lettere (`it`, `en`, …) | `it` | lingua parlata, passata a Whisper. Richiede il riavvio. |

#### `stt` — trascrizione (richiede il riavvio, tranne `hotwords`)

| Campo | Valori | Predefinito | Significato |
|---|---|---|---|
| `device` | `auto`, `cpu`, `mps` | `auto` | dove gira il modello. `auto` usa la GPU (`mps`) sui Mac Apple Silicon e la CPU altrove; se la GPU non parte, torna alla CPU da solo. |
| `model` | `auto`, `tiny`, `base`, `small`, `medium`, `large-v3`, `turbo` | `auto` | modello Whisper. `auto` = `turbo` su `mps`, `small` su `cpu`. Più grande = più preciso e più lento. |
| `compute_type` | `auto`, `int8`, `float16`, `float32`, `int8_float16` | `auto` | precisione dei calcoli. `auto` = `float16` su `mps`, `int8` su `cpu`. |
| `vad_filter` | `true`, `false` | `true` | scarta il rumore di fondo prima di trascrivere. Senza, il modello può inventare frasi ("Grazie a tutti.") quando non parli. Costa circa 0,04 s. |
| `hotwords` | `true`, `false` | `true` | in modalità comando suggerisce a Whisper le parole delle frasi dei comandi: separa meglio parole come "apri chrome" (invece di "apricrom"). Non vale per la dettatura. Cambiarlo non richiede il riavvio. |

Tempi misurati su un Mac M5 per una frase di 3 s: `turbo` su `mps` circa 1,1 s; `small` su
`cpu` circa 1,2 s; `turbo` su `cpu` circa 5 s (troppo lento).

#### `triggers` — come si avvia l'ascolto

Due voci, `command` e `dictation`. Ciascuna ha **esattamente uno** tra `hotkey` e
`mouse_button`:

```yaml
triggers:
  command:
    hotkey: "<ctrl>+<alt>+space"
  dictation:
    mouse_button: x2
```

| Campo | Valori | Significato |
|---|---|---|
| `hotkey` | combinazione di tasti (vedi sotto) | tieni premuti tutti i tasti della combinazione |
| `mouse_button` | `middle`, `x1`, `x2` | pulsante centrale, laterale indietro (`x1`) o laterale avanti (`x2`). Su Mac il pulsante del trigger viene bloccato: non arriva alle altre app. |

Le due modalità non possono usare la stessa combinazione. Per avere il pulsante del mouse sui
comandi basta scambiare:

```yaml
triggers:
  command:
    mouse_button: x2
  dictation:
    hotkey: "<ctrl>+<alt>+space"
```

**Formato di `hotkey`.** Parti separate da `+`, senza distinzione fra maiuscole e minuscole.
Ogni parte è una di queste:

- un carattere: `a`, `1`, `+` (per il `+` scrivi `<ctrl>++`);
- un modificatore: `<ctrl>`, `<alt>` (Option su Mac), `<shift>`, `<cmd>` (Cmd su Mac, tasto
  Windows su Windows). Valgono sia il tasto sinistro sia il destro; per uno solo dei due usa
  `<ctrl_l>`, `<ctrl_r>`, `<alt_l>`, `<alt_r>`, `<shift_l>`, `<shift_r>`, `<cmd_l>`, `<cmd_r>`;
- un tasto con nome: `<space>`, `<enter>`, `<tab>`, `<esc>`, `<backspace>`, `<delete>`,
  `<up>`, `<down>`, `<left>`, `<right>`, `<home>`, `<end>`, `<page_up>`, `<page_down>`,
  `<f1>` … `<f20>`. Le parentesi angolari sono facoltative (`space` = `<space>`);
- un codice di tasto numerico: `<65>`.

Esempi: `"<ctrl>+<alt>+space"`, `"<f13>"`, `"<alt_r>"` (solo Option destro), `"<cmd>+<shift>+d"`.

Su Mac le combinazioni con una lettera e Option/Ctrl potrebbero non funzionare: preferisci
`space`, un tasto funzione o un modificatore singolo.

#### `matching` — quanto deve somigliare la frase

| Campo | Valori | Predefinito | Significato |
|---|---|---|---|
| `threshold` | 0-100 | `80` | punteggio minimo perché un comando venga eseguito. Più alto = meno errori ma più frasi non riconosciute. |
| `margin` | 0-100 | `5` | distacco minimo dal secondo comando più simile. Se due comandi sono quasi pari non viene eseguito nessuno dei due. |

Il confronto ignora maiuscole, accenti, punteggiatura e articoli italiani ("apri **il**
browser" ≈ "apri browser").

#### `feedback` — segnali durante l'uso

| Campo | Predefinito | Significato |
|---|---|---|
| `tray` | `true` | l'icona cambia colore con lo stato |
| `sounds` | `true` | suoni di inizio, riuscita ed errore |
| `overlay` | `true` | riquadro con stato e testo sentito |
| `notifications` | `true` | notifica di sistema con l'esito |

Gli avvisi importanti (permessi mancanti, configurazione non valida) compaiono sempre, anche
con `notifications: false`.

#### `audio` — microfono (richiede il riavvio)

| Campo | Valori | Predefinito | Significato |
|---|---|---|---|
| `silence_rms` | numero ≥ 0 | `0.005` | sotto questo volume medio l'audio è considerato silenzio e non viene trascritto ("Non ho sentito niente"). Alzalo se rumori di fondo vengono trascritti, abbassalo se la tua voce non viene sentita. |
| `keep_stream_open` | `true`, `false` | `true` | `true`: microfono sempre aperto (su Mac il pallino arancione resta acceso), l'audio resta solo in memoria e non si perde l'inizio della frase. `false`: il microfono si apre alla pressione, ma i primi 100-500 ms vanno persi. |
| `preroll_ms` | millisecondi ≥ 0 | `300` | quanto audio *prima* della pressione viene incluso. Solo con `keep_stream_open: true`. |

#### `commands` — i comandi vocali

Una lista; ogni comando ha:

| Campo | Obbligatorio | Significato |
|---|---|---|
| `name` | sì | nome mostrato nell'esito; deve essere unico |
| `phrases` | sì, almeno una | frasi che attivano il comando |
| `action` | sì | cosa fare: `type: open` oppure `type: shell` |

**Azione `open`** — apre un sito, un'app, un file o una cartella.

| Campo | Significato |
|---|---|
| `type` | `open` |
| `target` | URL (`https://…`, `mailto:…`), percorso di file o cartella, oppure nome di un'app. `~` e le variabili d'ambiente (`$HOME`, `%USERPROFILE%`) vengono espanse. |

```yaml
commands:
  - name: Apri GitHub
    phrases: ["apri github"]
    action: {type: open, target: "https://github.com"}

  - name: Calcolatrice
    phrases: ["apri la calcolatrice"]
    action: {type: open, target: Calculator}       # su Windows: calc

  - name: Download
    phrases: ["apri i download", "cartella download"]
    action: {type: open, target: "~/Downloads"}

  - name: Lista della spesa
    phrases: ["lista della spesa"]
    action: {type: open, target: "~/Documents/spesa.txt"}
```

Su Mac il nome di un'app è quello del file in Applicazioni senza `.app` (`Safari`,
`Calculator`, `"Visual Studio Code"`). Su Windows è un programma noto al sistema (`calc`,
`notepad`) o il percorso di un `.exe`.

**Azione `shell`** — esegue un comando nella shell del sistema (`/bin/sh` su Mac,
`cmd.exe` su Windows), **senza chiedere conferma**.

| Campo | Significato |
|---|---|
| `type` | `shell` |
| `command` | comando unico per entrambi i sistemi |
| `mac`, `windows` | comando specifico per sistema; ha la precedenza su `command` |
| `timeout` | secondi prima di interromperlo (predefinito `30`) |

Serve almeno uno fra `command`, `mac` e `windows`. Se il comando finisce con un codice
diverso da 0, l'esito è un errore con "Codice di uscita N" e le ultime righe dell'output; se
supera il timeout viene fermato con "Tempo scaduto dopo N s".

```yaml
  - name: Blocca schermo
    phrases: ["blocca lo schermo"]
    action:
      type: shell
      mac: "pmset displaysleepnow"
      windows: "rundll32.exe user32.dll,LockWorkStation"

  - name: Progetto
    phrases: ["apri il progetto"]
    action: {type: shell, mac: "open -a 'Visual Studio Code' ~/whisper-test"}

  - name: Backup
    phrases: ["fai il backup"]
    action: {type: shell, command: "~/bin/backup.sh", timeout: 300}
```

## 6. Frasi che si riconoscono bene

- **Due o tre parole**, con un verbo e un oggetto: "apri github", "blocca lo schermo".
- **Parole diverse fra un comando e l'altro.** "apri mail" e "apri mappe" si somigliano
  troppo: con `margin` 5 a volte nessuno dei due parte.
- **Più frasi per lo stesso comando**, comprese le varianti che Whisper sente davvero. Se il
  log dice `testo 'abri safari'` quando dici "apri safari", aggiungi `"abri safari"` alle
  `phrases`.
- **Nomi stranieri o di marca** (GitHub, Chrome) sono i più difficili: aggiungi la versione
  italianizzata ("apri chrom") o un sinonimo italiano ("apri il browser").
- **Parla subito dopo aver premuto** e rilascia dopo l'ultima parola: il microfono è già
  aperto e non perde l'inizio.
- Controlla nel log il testo sentito e il punteggio (§7) per capire perché un comando non
  parte.

## 7. Il log

voicecmd scrive tutto quello che fa in un file, oltre che nel terminale:

| Sistema | Percorso |
|---|---|
| macOS | `~/Library/Logs/voicecmd/voicecmd.log` |
| Windows | `%LOCALAPPDATA%\voicecmd\Logs\voicecmd.log` |

Si apre dal menu > **Apri log**, oppure si segue dal vivo:

```bash
tail -f ~/Library/Logs/voicecmd/voicecmd.log                                   # macOS
```
```powershell
Get-Content "$env:LOCALAPPDATA\voicecmd\Logs\voicecmd.log" -Wait -Tail 20      # Windows
```

Ogni comando o dettatura produce una riga come questa:

```
Ciclo comando, audio 1.50 s, trascrizione 0.42 s, testo 'apri chrome', comando Apri browser (100/100), esito ok: Apri browser - aperto
```

Se nessun comando supera la soglia la riga dice `comando nessuno (più vicino Apri GitHub
70/100)`. Il file si rinnova da solo (al massimo 4 file da circa 1 MB).

Il log contiene i testi che hai detto e dettato. Resta sul computer, ma tienine conto se lo
condividi.

## 8. Risoluzione dei problemi

### Il trigger non scatta

- **Su Mac controlla i permessi** (§3). Se nel terminale vedi `voicecmd pronto (0 trigger
  attivi)` oppure la notifica "Trigger non attivi", mancano Monitoraggio input o Accessibilità
  per il terminale da cui lanci voicecmd. Dopo averli concessi chiudi il terminale con Cmd+Q.
- **Hai cambiato terminale?** I permessi valgono per un'app sola: iTerm, Terminal e VS Code
  vanno autorizzati separatamente.
- **Ctrl+Option+Spazio cambia la lingua della tastiera?** macOS usa la stessa combinazione per
  passare alla sorgente di input successiva. Disattivala in Impostazioni di Sistema > Tastiera >
  Abbreviazioni da tastiera > Sorgenti di input, oppure scegli un'altra `hotkey`.
- **Pulsante del mouse:** il tasto "gesture" sotto il pollice dei Logitech MX non manda eventi.
  Usa `x1` o `x2`. Il software Logi Options+ può rimappare i pulsanti laterali: se lo usi,
  lasciali con la funzione predefinita.
- **Notifica "Configurazione non valida" con `hotkey`:** il messaggio indica il tasto che non è
  stato riconosciuto. Vedi il formato in §5.

### Il comando non viene riconosciuto

- Leggi nel log (§7) il **testo sentito** e il **comando più vicino** con il punteggio.
- Se il testo è giusto ma il punteggio è sotto 80, aggiungi quella frase alle `phrases`
  oppure abbassa `matching.threshold` (es. 75).
- Se due comandi sono vicini, rendi le frasi più diverse (§6).
- Se il testo è molto diverso da quello che hai detto, parla più vicino al microfono e
  controlla che `stt.hotwords` sia `true`.

### "Non ho sentito niente"

- Hai parlato prima di premere o rilasciato troppo presto: tieni premuto fino alla fine.
- Il volume è sotto `audio.silence_rms`: abbassa il valore (es. `0.002`) e riavvia.
- Su Mac controlla il permesso Microfono e il microfono scelto in Impostazioni di Sistema >
  Suono > Ingresso.

### È lento

- Guarda nel log `trascrizione X s`.
- Il primo comando dopo l'avvio è un po' più lento: il modello si sta ancora scaldando.
- Su Mac Apple Silicon verifica nel log `Modello STT 'turbo' caricato su mps`. Se dice `cpu`
  con `turbo`, imposta `stt.device: auto` e `stt.model: auto`.
- Su computer senza GPU prova `stt.model: base` (più veloce, meno preciso) e riavvia.

### La dettatura non incolla

- Clicca nel campo di testo **prima** di premere il trigger.
- Su Mac serve il permesso Accessibilità per il terminale.
- Se il trigger di dettatura è una combinazione di tasti, rilasciali tutti: voicecmd aspetta
  fino a 1 s che siano rilasciati, poi rinuncia ("Tasti del trigger ancora premuti").
- Su Windows la dettatura non può scrivere nelle app avviate come amministratore.
- La clipboard viene ripristinata dopo l'incolla, ma solo se conteneva testo (immagini e file
  copiati vanno persi).

### L'app si chiude o non parte

- Leggi le ultime righe del log: gli errori imprevisti vengono scritti lì con il dettaglio.
- "Impossibile avviare voicecmd" con un errore sul modello: al primo avvio serve internet
  per scaricarlo.
- Se l'avviso dice che manca un permesso ma l'hai concesso, chiudi il terminale con Cmd+Q e
  riaprilo.

## 9. Privacy

- Audio e trascrizione restano sul computer; l'audio non viene salvato su disco.
- L'unica connessione è il download del modello al primo avvio.
- Con `keep_stream_open: true` il microfono resta aperto per non perdere l'inizio delle
  frasi, ma l'audio viene tenuto in memoria solo per 0,3 s e usato soltanto mentre tieni
  premuto il trigger.
- Il log contiene i testi riconosciuti (§7).
