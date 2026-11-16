# Verifica manuale su macOS (T25)

Checklist da eseguire sul Mac con il microfono e il mouse veri. Ripercorre i criteri di
accettazione del PRD §7 e i punti che i test automatici non possono coprire.

**Come compilarla.** Per ogni voce: segui i passi, confronta con **Atteso**, poi metti `[x]`
se va bene oppure scrivi `KO` dopo **Esito** con una nota (cosa è successo, riga del log se
utile). Le voci non applicabili si segnano `n/a`. Ogni `KO` diventerà un nuovo task.

- Data: ______  macOS: ______  Mac: ______  Mouse: ______
- Commit provato (`git log --oneline -1`): ______
- Terminale da cui lanci voicecmd (iTerm, Terminal, VS Code): ______

> I trigger qui sono chiamati **trigger comandi** e **trigger dettatura**. Con la tua
> configurazione attuale: comandi = pulsante **avanti** del mouse (`x2`), dettatura =
> **Ctrl+Option+Spazio**. Con quella predefinita sono invertiti.

## 0. Preparazione

1. Chiudi ogni voicecmd già aperto (Ctrl+C nel terminale oppure menu > Esci).
2. In un secondo terminale segui il log durante tutta la prova:
   `tail -f ~/Library/Logs/voicecmd/voicecmd.log`
3. Avvia: `cd ~/whisper-test && .venv/bin/python -m voicecmd`

## 1. Permessi da zero

Si azzerano i tre permessi del terminale e si concedono di nuovo. Usa l'identificativo del
tuo terminale: iTerm `com.googlecode.iterm2`, Terminal `com.apple.Terminal`,
VS Code `com.microsoft.VSCode`.

- [ ] **P1** Chiudi voicecmd. Esegui `tccutil reset Accessibility <id>`, `tccutil reset ListenEvent <id>`, `tccutil reset Microphone <id>`. Chiudi del tutto il terminale (Cmd+Q), riaprilo, avvia voicecmd.
  **Atteso:** notifica "Permessi mancanti" che nomina Accessibilità e Monitoraggio input e il tuo terminale (non "Python"); nel log anche "Trigger non attivi" e "voicecmd pronto (0 trigger attivi)". L'app resta aperta, icona nella menu bar.
  **Esito:**
- [ ] **P2** Concedi Monitoraggio input e Accessibilità al terminale come indicato dal messaggio. Cmd+Q sul terminale, riaprilo, riavvia voicecmd.
  **Atteso:** nessun avviso di permessi; log "voicecmd pronto (2 trigger attivi)".
  **Esito:**
- [ ] **P3** Primo uso del microfono: premi il trigger comandi e parla.
  **Atteso:** macOS chiede l'accesso al microfono per il terminale; dopo il consenso il ciclo successivo funziona. (Con `keep_stream_open: true` la richiesta può comparire già all'avvio.)
  **Esito:**
- [ ] **P4** Nega il microfono (Impostazioni > Privacy > Microfono, spegni il terminale), riavvia voicecmd.
  **Atteso:** avviso che manca il permesso Microfono; premendo il trigger, esito "Microfono non disponibile" o "Non ho sentito niente", mai un crash. Poi riattiva il permesso.
  **Esito:**

## 2. Avvio e uscita

- [ ] **A1** All'avvio guarda la menu bar.
  **Atteso:** icona grigia; nel menu la voce di stato dice "Caricamento del modello…" e poi lo stato inattivo. Voci: Apri configurazione, Ricarica configurazione, Apri log, Esci.
  **Esito:**
- [ ] **A2** Icona con menu bar chiara e scura (Impostazioni > Aspetto).
  **Atteso:** il cerchio si vede bene in entrambi i casi.
  **Esito:**
- [ ] **A3** Nessuna connessione di rete: con voicecmd avviato esegui `lsof -i -a -p $(pgrep -f "python -m voicecmd")`.
  **Atteso:** nessuna riga (o solo intestazione).
  **Esito:**
- [ ] **A4** Menu > Esci.
  **Atteso:** l'app si chiude entro 1-2 s, il terminale torna al prompt, pallino arancione del microfono spento, nessun dialogo "Python si è chiuso".
  **Esito:**
- [ ] **A5** Riavvia e chiudi con Ctrl+C nel terminale.
  **Atteso:** come A4.
  **Esito:**

## 3. Criteri di accettazione del PRD §7

- [ ] **C1** Tieni premuto il trigger comandi, di' "apri il browser", rilascia.
  **Atteso:** si apre il browser su google.com; overlay e notifica mostrano il comando "Apri browser"; icona verde poi grigia; nel log una riga `Ciclo comando, … esito ok: Apri browser`.
  **Esito:**
- [ ] **C2** Trigger comandi, di' "prepara il caffè", rilascia.
  **Atteso:** nessuna azione; esito "Nessun comando riconosciuto" con il testo sentito e "Il più vicino: … (N/100)"; icona rossa poi grigia.
  **Esito:**
- [ ] **C3** Apri TextEdit (o Note), clicca nel testo, tieni premuto il trigger dettatura, di' "perché è già così, però funziona", rilascia.
  **Atteso:** il testo compare nel documento con gli accenti giusti (è, già, così, però).
  **Esito:**
- [ ] **C3b** Prima di C3 copia una parola qualsiasi (Cmd+C). Dopo la dettatura premi Cmd+V in un punto vuoto.
  **Atteso:** viene incollata la parola copiata prima, non il testo dettato (clipboard ripristinata).
  **Esito:**
- [ ] **C4** Menu > Apri configurazione. Aggiungi in fondo a `commands`:
  ```yaml
    - name: Apri calcolatrice
      phrases: ["apri la calcolatrice"]
      action: {type: open, target: Calculator}
  ```
  Salva, poi di' "apri la calcolatrice" col trigger comandi.
  **Atteso:** notifica "Configurazione ricaricata" al salvataggio; la Calcolatrice si apre senza riavviare voicecmd.
  **Esito:**
- [ ] **C5** Nel file scrivi `threshold: 500` (sotto `matching`) e salva. Poi ripeti C1.
  **Atteso:** notifica "Configurazione non valida" che nomina `matching.threshold`; C1 funziona ancora. Rimetti `80` e salva: "Configurazione ricaricata".
  **Esito:**
- [ ] **C6** Aggiungi un comando `{name: Fallisce, phrases: ["comando che fallisce"], action: {type: shell, command: "exit 3"}}`, salva, pronuncialo.
  **Atteso:** esito di errore con "Codice di uscita 3"; l'app resta attiva e il ciclo successivo funziona.
  **Esito:**

## 4. Trigger

- [ ] **T1** Pulsante del mouse come trigger: tienilo premuto su una pagina web con cronologia (fai prima qualche "indietro").
  **Atteso:** ascolto avviato; la pagina **non** va avanti/indietro. Gli altri pulsanti (sinistro, destro, l'altro laterale, centrale) funzionano come sempre.
  **Esito:**
- [ ] **T2** Hotkey Ctrl+Option+Spazio tenuta premuta in un campo di testo.
  **Atteso:** nessun carattere scritto; nessun cambio di sorgente di input (se macOS cambia la lingua della tastiera, annota: va citato in T27).
  **Esito:**
- [ ] **T3** Pressione brevissima (un clic, < 0,3 s) del trigger comandi.
  **Atteso:** nessun esito, nessuna notifica; nel log "Pressione troppo breve".
  **Esito:**
- [ ] **T4** Durante l'elaborazione di un comando premi di nuovo un trigger.
  **Atteso:** la seconda pressione è ignorata; il primo comando finisce normalmente.
  **Esito:**
- [ ] **T5** Tieni premuto il trigger comandi senza rilasciare per più di 30 s.
  **Atteso:** a 30 s l'ascolto si chiude da solo ed elabora; il rilascio successivo non fa nulla.
  **Esito:**
- [ ] **T6** Scambia i trigger nel file (comandi ↔ dettatura) e salva, senza riavviare.
  **Atteso:** "Configurazione ricaricata"; i trigger funzionano subito con i nuovi ruoli. Poi rimetti com'erano.
  **Esito:**

## 5. Overlay e focus

- [ ] **O1** In TextEdit scrivi di continuo mentre premi e rilasci il trigger comandi (con un comando innocuo, es. "che giorno è oggi").
  **Atteso:** l'overlay compare e sparisce, ma il cursore resta in TextEdit e i tasti continuano a scrivere lì.
  **Esito:**
- [ ] **O2** Con l'overlay visibile, clicca su un punto sotto di esso.
  **Atteso:** il clic arriva alla finestra sotto (l'overlay non blocca i clic).
  **Esito:**
- [ ] **O3** Ripeti con un'app a tutto schermo (es. Safari in full screen) e su un'altra Scrivania (Space).
  **Atteso:** l'overlay è visibile sopra l'app; nessun salto di Space.
  **Esito:**
- [ ] **O4** Testi lunghi: dettatura di una frase di 15-20 parole.
  **Atteso:** l'overlay resta leggibile (testo tagliato o a capo, non fuori dallo schermo).
  **Esito:**

## 6. Dettatura

- [ ] **D1** Dettatura nella barra degli indirizzi di Chrome (problema visto il 2026-11-16).
  **Atteso:** il testo compare nella barra. Se no, copia qui la riga `Ciclo dettatura, …` del log.
  **Esito:**
- [ ] **D2** Dettatura in un campo web (es. ricerca di google.com), in Note e nel terminale.
  **Atteso:** testo incollato in tutti e tre.
  **Esito:**
- [ ] **D3** Dettatura di 60 s circa.
  **Atteso:** testo completo incollato; tempo di attesa dopo il rilascio annotato: ____ s.
  **Esito:**
- [ ] **D4** Con il trigger dettatura sulla tastiera: rilascia i tasti uno alla volta, lentamente.
  **Atteso:** il testo viene incollato una volta sola e non parte nessuna scorciatoia strana (es. Option+V che scrive "◊").
  **Esito:**

## 7. Feedback

- [ ] **F1** Suoni: inizio ascolto, comando riuscito, errore.
  **Atteso:** tre suoni brevi e distinti, volume ragionevole.
  **Esito:**
- [ ] **F2** Notifiche: dopo un comando riuscito e uno fallito.
  **Atteso:** notifica di macOS con titolo ed "Ho sentito: «…»". (Se non compaiono, controlla Impostazioni > Notifiche per il terminale/Python.)
  **Esito:**
- [ ] **F3** Nel file metti `feedback: {tray: false, sounds: false, overlay: false, notifications: false}` e salva; esegui un comando.
  **Atteso:** il comando funziona senza suoni, overlay né notifiche, e l'icona non cambia colore. Rimetti tutto a `true`.
  **Esito:**

## 8. Latenza e riconoscimento con la tua voce

- [ ] **L1** Esegui 5 volte "apri il browser". Per ognuna leggi nel log `trascrizione X s`.
  **Atteso:** sensazione di risposta immediata; trascrizione ≤ 1,5 s. Tempi: ____ ____ ____ ____ ____
  **Esito:**
- [ ] **L2** Primo comando subito dopo l'avvio ("pronto" nel log).
  **Atteso:** non molto più lento dei successivi. Tempo: ____ s
  **Esito:**
- [ ] **L3** Di' 3 volte ciascuno: "apri github", "apri chrome", "blocca lo schermo" (attenzione: blocca davvero), "che giorno è oggi".
  **Atteso:** riconosciuti. Annota quelli sbagliati con il testo sentito (riga `Ciclo comando` del log). In T24 "apri github" con voce sintetica non veniva riconosciuto.
  **Esito:**
- [ ] **L4** Inizio frase: premi e parla subito, senza pausa.
  **Atteso:** la prima parola non viene tagliata ("apri" non diventa "pri").
  **Esito:**
- [ ] **L5** Silenzio: tieni premuto 2 s senza parlare, in una stanza con rumore normale.
  **Atteso:** "Non ho sentito niente", nessuna frase inventata ("Grazie a tutti.").
  **Esito:**

## 9. Configurazione, log e robustezza

- [ ] **R1** Menu > Apri log.
  **Atteso:** si apre `voicecmd.log` in Console con le righe `Ciclo …`.
  **Esito:**
- [ ] **R2** Nel file cambia `stt: {model: small}` e salva.
  **Atteso:** notifica "Riavvia voicecmd per applicare: stt.model". Rimetti `auto`.
  **Esito:**
- [ ] **R3** Salva il file con un editor che sostituisce il file (es. `vim`) due volte di fila.
  **Atteso:** entrambe le modifiche vengono ricaricate.
  **Esito:**
- [ ] **R4** Con voicecmd avviato scollega/cambia il microfono (es. collega le AirPods), poi esegui un comando.
  **Atteso:** l'app non si chiude; se il comando fallisce, il messaggio è comprensibile e un tentativo successivo funziona (annota cosa succede).
  **Esito:**
- [ ] **R5** Comando con `{type: shell, command: "sleep 60", timeout: 3}`.
  **Atteso:** dopo circa 3 s errore "Tempo scaduto dopo 3 s"; l'app resta attiva.
  **Esito:**

## Note libere

-
