# Verifica manuale su Windows (T26)

Installazione su una macchina Windows reale, poi la stessa verifica di
[`macos.md`](macos.md) adattata a Windows, più i punti rimasti "da verificare" in T04, T11,
T12, T13 e T15. Nessuna parte Windows è stata ancora provata su una macchina vera: aspettati
qualche `KO`.

**Come compilarla.** Per ogni voce: segui i passi, confronta con **Atteso**, poi metti `[x]`
se va bene oppure scrivi `KO` dopo **Esito** con una nota (cosa è successo, riga del log se
utile). Le voci non applicabili si segnano `n/a`. Ogni `KO` diventerà un nuovo task.

- Data: ______  Windows (Win+R → `winver`): ______  CPU: ______  RAM: ______  GPU: ______
- Layout tastiera: ______  Mouse: ______  Python: ______
- Commit provato (`git log --oneline -1`): ______

## 0. Installazione

Comandi da **PowerShell** (non serve l'amministratore).

1. **Python.** Installa Python 3.12 o 3.13 a 64 bit da python.org, spuntando "Add python.exe
   to PATH". Il Mac usa 3.14, ma su Windows alcune librerie (ctranslate2, PySide6) potrebbero
   non avere ancora i pacchetti per 3.14: se l'installazione al punto 4 fallisce con 3.14,
   annota l'errore e usa 3.13.
2. **Git.** Installa Git for Windows (git-scm.com) se manca.
3. **Codice.** Il ramo `applicazione` deve essere stato pubblicato su GitHub dal Mac
   (`git push -u origin applicazione`). Poi:
   ```powershell
   git clone https://github.com/jtremiel/whisper-test.git
   cd whisper-test
   git checkout applicazione
   ```
4. **Ambiente e dipendenze.**
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -e ".[dev]"
   ```
   Se PowerShell blocca `Activate.ps1`: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
5. **Test automatici.** `pytest -q` (poi `pytest -m slow -s` per quelli col modello vero).
6. **Primo avvio.** `python -m voicecmd`. Il primo avvio scarica il modello Whisper da
   Hugging Face (unica connessione prevista, PRD §4); i successivi usano la copia locale.
7. **Percorsi.** Configurazione e log (dovrebbero essere
   `%LOCALAPPDATA%\voicecmd\config.yaml` e `%LOCALAPPDATA%\voicecmd\Logs\voicecmd.log`):
   ```powershell
   python -c "from voicecmd.config import config_path; from voicecmd.logging_setup import log_path; print(config_path()); print(log_path())"
   ```
   Per seguire il log in una seconda finestra:
   `Get-Content "$env:LOCALAPPDATA\voicecmd\Logs\voicecmd.log" -Wait -Tail 20`

- [ ] **I1** `pip install -e ".[dev]"` termina senza errori. Versione di Python usata: ____
  **Esito:**
- [ ] **I2** `pytest -q` verde. Se no, incolla i nomi dei test falliti.
  **Esito:**
- [ ] **I3** `pytest -m slow -s` verde; annota i tempi `[e2e] … ciclo X s`.
  **Esito:**
- [ ] **I4** I percorsi stampati al punto 7 sono quelli attesi.
  **Esito:**

> Trigger predefiniti: comandi = **Ctrl+Alt+Spazio**, dettatura = pulsante laterale
> **avanti** del mouse (`x2`). Su Windows non servono permessi di Accessibilità, ma il
> microfono deve essere abilitato per le app desktop.

## 1. Microfono e avvio

- [ ] **P1** Impostazioni > Privacy e sicurezza > Microfono: "Consenti alle app desktop di accedere al microfono" attivo. Avvia voicecmd.
  **Atteso:** nessun avviso di permessi; log "Modello STT 'small' caricato su cpu (int8)" e "voicecmd pronto (2 trigger attivi)".
  **Esito:**
- [ ] **P2** Disattiva quell'interruttore, riavvia voicecmd, premi il trigger comandi.
  **Atteso:** esito "Microfono non disponibile" o "Non ho sentito niente", mai un crash; annota il messaggio. Poi riattiva.
  **Esito:**
- [ ] **A1** Icona nell'area di notifica (accanto all'orologio; può finire tra le icone nascoste, freccia ^).
  **Atteso:** cerchio grigio ben visibile con tema chiaro e scuro; clic destro mostra il menu con Apri configurazione, Ricarica configurazione, Apri log, Esci.
  **Esito:**
- [ ] **A2** Nessuna connessione di rete dopo il primo avvio: con voicecmd avviato, in PowerShell
  `Get-NetTCPConnection -OwningProcess (Get-Process python | Select-Object -ExpandProperty Id)`.
  **Atteso:** nessuna connessione (errore "nessun oggetto trovato" va bene).
  **Esito:**
- [ ] **A3** Menu > Esci, poi riavvia e chiudi con Ctrl+C nella finestra di PowerShell.
  **Atteso:** l'app si chiude entro 1-2 s in entrambi i casi, nessuna finestra di errore.
  **Esito:**

## 2. Criteri di accettazione del PRD §7

- [ ] **C1** Tieni premuto il trigger comandi, di' "apri il browser", rilascia.
  **Atteso:** si apre il browser predefinito su google.com; overlay e notifica mostrano "Apri browser"; riga `Ciclo comando, … esito ok` nel log.
  **Esito:**
- [ ] **C2** Trigger comandi, di' "prepara il caffè".
  **Atteso:** nessuna azione; "Nessun comando riconosciuto" con testo sentito e "Il più vicino: …".
  **Esito:**
- [ ] **C3** Copia una parola (Ctrl+C). Apri Blocco note, tieni premuto il trigger dettatura, di' "perché è già così, però funziona", rilascia. Poi premi Ctrl+V in un punto vuoto.
  **Atteso:** compare il testo dettato con gli accenti giusti; il Ctrl+V finale incolla la parola copiata prima (clipboard ripristinata).
  **Esito:**
- [ ] **C4** Menu > Apri configurazione. Aggiungi:
  ```yaml
    - name: Apri calcolatrice
      phrases: ["apri la calcolatrice"]
      action: {type: open, target: calc}
  ```
  Salva e pronuncia "apri la calcolatrice".
  **Atteso:** "Configurazione ricaricata" al salvataggio; si apre la Calcolatrice senza riavviare (`os.startfile` con un nome di programma).
  **Esito:**
- [ ] **C5** Scrivi `threshold: 500` sotto `matching`, salva, poi ripeti C1.
  **Atteso:** "Configurazione non valida" con `matching.threshold`; C1 funziona ancora. Rimetti `80`.
  **Esito:**
- [ ] **C6** Comando `{name: Fallisce, phrases: ["comando che fallisce"], action: {type: shell, windows: "exit /b 3"}}`.
  **Atteso:** errore "Codice di uscita 3"; l'app resta attiva.
  **Esito:**

## 3. Trigger (da T04 e T15)

- [ ] **T1** Pulsante laterale **avanti** (`x2`) tenuto premuto in un browser con cronologia.
  **Atteso:** parte la dettatura; il browser **non** va avanti. Il pulsante **indietro** (`x1`) continua a fare "indietro".
  **Esito:**
- [ ] **T2** Metti `mouse_button: x1` nel trigger dettatura e salva; ripeti con il pulsante indietro.
  **Atteso:** ora scatta `x1` e il browser non torna indietro; `x2` torna a fare "avanti". Rimetti `x2`.
  **Esito:**
- [ ] **T3** Prova `mouse_button: middle`.
  **Atteso:** il centrale fa partire il trigger e non apre link in nuove schede né lo scorrimento automatico. Rimetti `x2`.
  **Esito:**
- [ ] **T4** Ctrl+Alt+Spazio tenuto premuto in Blocco note e in un campo del browser.
  **Atteso:** nessun carattere scritto, nessun cambio di lingua/IME, nessun menu di sistema. Con layout italiano annota se Ctrl+Alt si comporta come AltGr.
  **Esito:**
- [ ] **T5** Pressione < 0,3 s; seconda pressione durante l'elaborazione; pressione oltre 30 s.
  **Atteso:** rispettivamente ignorata ("Pressione troppo breve" nel log), ignorata, chiusa da sola a 30 s.
  **Esito:**
- [ ] **T6** Scambia i trigger nel file (comandi ↔ dettatura) e salva.
  **Atteso:** "Configurazione ricaricata"; i trigger funzionano subito con i nuovi ruoli. Rimetti com'erano.
  **Esito:**

## 4. Overlay, dettatura e feedback

- [ ] **O1** Scrivi di continuo in Blocco note mentre esegui "che giorno è oggi".
  **Atteso:** l'overlay compare ma il cursore resta in Blocco note; nessuna icona nuova sulla barra delle applicazioni.
  **Esito:**
- [ ] **O2** Clic su un punto sotto l'overlay visibile; prova anche con un'app a schermo intero (F11 nel browser).
  **Atteso:** il clic passa alla finestra sotto; l'overlay è visibile sopra l'app a schermo intero.
  **Esito:**
- [ ] **D1** Dettatura nella barra degli indirizzi del browser, in un campo web e in PowerShell.
  **Atteso:** testo incollato con Ctrl+V in tutti e tre.
  **Esito:**
- [ ] **D2** Dettatura in un'app avviata come amministratore (es. Blocco note → "Esegui come amministratore").
  **Atteso:** probabilmente **non** funziona (Windows impedisce a un'app normale di inviare tasti a una elevata). Annota cosa succede: è un limite da documentare in T27, non un errore.
  **Esito:**
- [ ] **D3** Con il trigger dettatura sulla tastiera (scambia come in T6), rilascia i tasti lentamente uno alla volta.
  **Atteso:** testo incollato una volta sola, nessuna scorciatoia strana.
  **Esito:**
- [ ] **F1** Suoni di inizio, riuscita ed errore.
  **Atteso:** tre suoni brevi e distinti.
  **Esito:**
- [ ] **F2** Notifiche dopo un comando riuscito e uno fallito.
  **Atteso:** notifica di Windows con titolo ed "Ho sentito: «…»" (se non compaiono, controlla Impostazioni > Sistema > Notifiche e "Non disturbare").
  **Esito:**
- [ ] **F3** `feedback: {tray: false, sounds: false, overlay: false, notifications: false}`, salva, esegui un comando.
  **Atteso:** il comando funziona senza feedback. Rimetti tutto a `true`.
  **Esito:**

## 5. Azioni su Windows (da T11 e T12)

- [ ] **W1** `open` con percorso e variabile d'ambiente: `target: "%USERPROFILE%\\Documents"`.
  **Atteso:** si apre Esplora file sulla cartella Documenti.
  **Esito:**
- [ ] **W2** `open` con un file: `target: "~\\Desktop\\prova.txt"` (crea prima il file).
  **Atteso:** il file si apre con il programma predefinito.
  **Esito:**
- [ ] **W3** `open` con un percorso inesistente, es. `target: "C:\\non\\esiste"`.
  **Atteso:** errore "Il percorso … non esiste", nessun crash.
  **Esito:**
- [ ] **W4** Comando predefinito "che giorno è oggi" (`command: "echo oggi"`).
  **Atteso:** esito ok.
  **Esito:**
- [ ] **W5** `shell` con variante `windows:`: `{type: shell, mac: "false", windows: "start notepad"}`.
  **Atteso:** si apre Blocco note (viene usata la variante Windows).
  **Esito:**
- [ ] **W6** Timeout: `{type: shell, windows: "ping -n 60 127.0.0.1", timeout: 3}`.
  **Atteso:** dopo circa 3 s "Tempo scaduto dopo 3 s"; in Gestione attività non resta nessun `ping.exe`.
  **Esito:**
- [ ] **W7** "blocca lo schermo" (`rundll32.exe user32.dll,LockWorkStation`). Attenzione: blocca davvero.
  **Atteso:** lo schermo si blocca; dopo lo sblocco voicecmd è ancora attivo.
  **Esito:**

## 6. Latenza (PRD §4: su Windows va misurata)

- [ ] **L1** Esegui 5 volte "apri il browser" (frase di 2-3 s). Leggi nel log `trascrizione X s`.
  **Atteso:** tempi: ____ ____ ____ ____ ____. Obiettivo del Mac ≤ 1,5 s; su Windows annota se è accettabile.
  **Esito:**
- [ ] **L2** Se L1 è lento (> 2 s), prova `stt: {model: base}` (serve il riavvio) e ripeti.
  **Atteso:** tempi: ____ ____ ____; qualità del riconoscimento: ____. Serve per scegliere il modello predefinito su Windows.
  **Esito:**
- [ ] **L3** Primo comando subito dopo l'avvio e inizio frase senza pausa.
  **Atteso:** primo comando non molto più lento; la prima parola non viene tagliata.
  **Esito:**
- [ ] **L4** Riconoscimento con la tua voce: 3 volte ciascuno "apri github", "apri chrome", "che giorno è oggi".
  **Atteso:** riconosciuti; annota quelli sbagliati con il testo sentito.
  **Esito:**
- [ ] **L5** 2 s di silenzio col trigger premuto.
  **Atteso:** "Non ho sentito niente", nessuna frase inventata.
  **Esito:**

## 7. Configurazione, log e robustezza

- [ ] **R1** Menu > Apri log e Apri configurazione.
  **Atteso:** i file si aprono con il programma associato (Blocco note o altro).
  **Esito:**
- [ ] **R2** `stt: {model: small}` → `base`, salva.
  **Atteso:** "Riavvia voicecmd per applicare: stt.model".
  **Esito:**
- [ ] **R3** Salva il file da VS Code o Notepad++ due volte di fila.
  **Atteso:** entrambe le modifiche ricaricate.
  **Esito:**
- [ ] **R4** Collega/scollega un microfono o cuffie USB/Bluetooth con voicecmd avviato, poi un comando.
  **Atteso:** nessun crash; messaggio comprensibile se fallisce; il tentativo successivo funziona.
  **Esito:**

## Note libere

-
