# T04 - Trigger: pulsanti del mouse, soppressione, default

Stato: prove su Mac fatte con l'utente il 2026-11-15. Le parti Windows sono **da verificare in T26**.

## Cosa è stato provato

Script `spikes/trigger_probe.py` (vedi docstring per l'uso). macOS, Apple Silicon, mouse **Logitech MX** (tasto gesture sul poggiapollice + due tasti laterali sotto la rotella del pollice), nessun software del produttore installato (niente Logi Options+). Permessi Accessibilità e Monitoraggio input concessi a Visual Studio Code, l'app da cui gira il terminale, e applicati dopo il riavvio dell'app.

1. `pynput` (tastiera + mouse): centrale, laterale indietro, laterale avanti, poi Ctrl+Option+Spazio tenuto premuto in un campo di testo.
2. `--quartz`: event tap Quartz sul mouse, che legge `kCGMouseEventButtonNumber`.
3. `--quartz --suppress x1`: tap attivo (`kCGEventTapOptionDefault`) che restituisce `None` solo per il pulsante 3; laterale indietro e avanti premuti nel browser.

## Risultati

| Prova | Risultato |
|---|---|
| pynput, mouse | **I laterali arrivano come `Button.middle`**, indistinguibili dal centrale (rischio HANDOFF §7.1 confermato). |
| Quartz, mouse | Numeri distinti: centrale = 2, laterale indietro = 3 (`x1`), laterale avanti = 4 (`x2`). Sinistro = 0. |
| Quartz + soppressione x1 | Log: `pulsante=3 ... (soppresso: ritorno None)` sia alla pressione sia al rilascio; `pulsante=4` e i clic sinistri passano. Il resto del mouse continua a funzionare. L'utente conferma che nel browser la pagina non è tornata indietro. |
| Ctrl+Option+Spazio tenuto premuto | pynput vede `Key.ctrl`, `Key.alt`, `Key.space` (premuti e rilasciati). L'utente conferma che **nel campo di testo non compare alcun carattere**. |

Tasto gesture del poggiapollice (Logitech MX), senza Logi Options+: **nessun evento** né in pynput né nel tap Quartz sul mouse. Non è utilizzabile come trigger senza il software Logitech.

Nota di metodo: due prove sono andate a vuoto per questioni di tempi (pulsanti premuti fuori dalla finestra di ascolto, o sinistro/destro scambiati per i laterali); sono state ripetute. Ctrl+Cmd+Spazio, premuto per errore in una prova, apre il pannello emoji di macOS: da evitare come trigger.

## Decisione

- **Mouse su Mac: event tap Quartz via `pyobjc`**, non `pynput.mouse`. Mappa: `middle` = 2, `x1` = 3, `x2` = 4. Il tap va creato su `kCGSessionEventTap`, `kCGHeadInsertEventTap`, con maschera `OtherMouseDown` | `OtherMouseUp`, e fatto girare con un proprio `CFRunLoop` in un thread dedicato. Su `kCGEventTapDisabledByTimeout` / `ByUserInput` va riattivato con `CGEventTapEnable`. Il callback deve restare velocissimo: si limita a inoltrare l'evento al Controller.
- **Soppressione: possibile e selettiva su Mac** per i pulsanti del mouse. Il tap restituisce `None` per pressione e rilascio del solo pulsante del trigger; tutti gli altri eventi tornano invariati. Così il laterale non fa più "indietro" nel browser.
- **Tastiera: nessuna soppressione necessaria** per `<ctrl>+<alt>+space`: tenuta premuta non scrive caratteri. Il trigger da tastiera resta su `pynput.keyboard` in sola lettura.
- **Binding di default (confermati, invariati rispetto allo schema)**:
  - `command`: `hotkey: "<ctrl>+<alt>+space"` (Ctrl+Option+Spazio su Mac).
  - `dictation`: `mouse_button: x2` (laterale avanti), soppresso. Essendo un pulsante del mouse, al momento di incollare non ci sono modificatori tenuti giù (HANDOFF §7.6).
- **Attenzione per T14 / T25**: macOS ha una scorciatoia di sistema Ctrl+Option+Spazio ("Seleziona la sorgente successiva nel menu Inserimento") che agisce solo se sono attive più sorgenti di input. Sul Mac dell'utente non ha avuto effetto. Va citata nella guida (T27) con l'indicazione di disattivarla o cambiare hotkey.

## Windows (da verificare in T26)

- `pynput.mouse` su Windows dovrebbe distinguere `Button.x1` / `Button.x2`: da verificare.
- Soppressione: `pynput` offre `win32_event_filter` con `suppress_event()`; va provato che sopprima solo il pulsante del trigger.
- Se Ctrl+Alt+Spazio tenuto premuto scrive caratteri o va in conflitto con le scorciatoie dell'IME.
