# T06 - Ritardo di apertura del microfono

Stato: completato con l'utente il 2026-11-15.

## Cosa è stato provato

Script `spikes/mic_latency.py` (`sd.InputStream`, 16 kHz, mono, float32, blocchi da 512 campioni = 32 ms).

- `--mode cold`: alla pressione di Invio crea e avvia lo stream, registra 3 s. Misura: richiesta -> `start()` terminato, richiesta -> primo blocco audio, richiesta -> primo blocco con RMS sopra soglia (0,01, solo indicatore).
- `--mode warm`: stream sempre aperto con buffer circolare (`--preroll-ms`, default 300). Alla pressione di Invio il pre-roll viene anteposto alla registrazione.
- `--runs N`, riepilogo media/min/max, wav salvati in `--out` (default `$TMPDIR/voicecmd-spikes/mic`, fuori dal repo).
- `--auto` simula Invio (attesa 0,8 s) senza input e senza parlare.

## Ritardi misurati (prova automatica, 3 prove per modalità, nessuno parla)

Questo Mac (Apple Silicon), microfono integrato, permesso microfono disponibile (l'audio non è a zero).

| Modalità | Apertura stream | Richiesta -> primo blocco |
|---|---|---|
| cold | media 76 ms (64-88) | media 110 ms (98-122) |
| warm | 0 ms | media 32 ms (29-34), cioè un blocco |

Il "primo blocco sopra soglia" in `--auto` è rumore ambientale e non significa nulla: ignorarlo in questa tabella.

Lettura: in cold i primi ~100-120 ms dopo Invio/trigger non sono catturati. Una sillaba iniziale dura 100-200 ms, quindi il taglio è plausibile ma non certo: dipende da quanto l'utente parla subito dopo il trigger. Va giudicato all'ascolto.

## Procedura per l'utente

Dal repo, nel Terminale che ha il permesso Microfono:

```
.venv/bin/python spikes/mic_latency.py --mode cold --runs 5
.venv/bin/python spikes/mic_latency.py --mode warm --runs 5 --preroll-ms 300
```

Ad ogni prova: premi Invio e inizia SUBITO a parlare, senza pausa, con la frase "Apri Safari" (poi, in alcune prove, una parola corta come "Chrome"). Parla per circa 2 s, poi stai zitto fino alla fine dei 3 s.

Poi riascolta i wav (il percorso è stampato a fine script):

```
afplay /tmp/.../voicecmd-spikes/mic/cold_01.wav     # sostituisci col percorso stampato; ripeti per cold_02..05
afplay <cartella>/warm_01.wav                       # ripeti per warm_02..05
```

Cosa ascoltare: la prima sillaba ("A" di "Apri", "Chro" di "Chrome") c'è o è tagliata? In warm, c'è un clic o un suono strano all'inizio?

Se compare un errore o l'audio è silenzioso: Impostazioni di Sistema > Privacy e sicurezza > Microfono, abilita il Terminale (o l'app da cui lanci), riavvialo e riprova.

## Prova con l'utente, modalità cold (2026-11-15)

Script lanciato con `--key`: il trigger è la pressione di Shift, in qualunque finestra (via pynput). L'utente preme Shift e dice subito "Apri Safari" o "Chrome". I wav sono stati trascritti con turbo su MPS (beam 5), misurando l'inizio della voce (RMS a finestre di 20 ms, soglia 0,01).

| Prova | Apertura stream / primo blocco | Inizio voce nel wav | Trascrizione |
|---|---|---|---|
| 1 | (riepilogo: max 473 / 521 ms) | nessuna voce sopra soglia | "Grazie a tutti." (allucinazione su silenzio) |
| 2 | - | 180 ms | "Apri Safari!" |
| 3 | - | 1060 ms | "Abri Safari" |
| 4 | 89 / 123 ms | 200 ms | "abrisi a fare" |
| 5 | 189 / 216 ms | 360 ms | "Abre il safari." |

Riepilogo dello script: apertura stream media 234 ms (68-473), richiesta -> primo blocco media 272 ms (103-521).

- Il ritardo cold con l'utente è più alto e molto più variabile dei ~110 ms della prova automatica.
- **Prima apertura dopo l'avvio del processo: ~3,3 s** (prova `--auto` dopo il riavvio di VS Code; poi di nuovo ~86 ms). Il Recorder (T08) deve aprire e chiudere lo stream una volta all'avvio dell'app per scaldare CoreAudio, anche in modalità cold.
- "Apri" diventa spesso "Abri"/"Abre": può essere un taglio dell'attacco della "A" o semplicemente la pronuncia. Il confronto con la prova warm serve a distinguere i due casi.
- Prova 1 senza voce: Whisper produce "Grazie a tutti." Conferma che servono lo scarto per `silence_rms` e `no_speech_prob` (T08/T09).

## Prova con l'utente, modalità warm (2026-11-15)

Stesso metodo, `--preroll-ms 300`. Registrate solo 2 prove su 5: le pressioni di Shift arrivate durante la registrazione della prova precedente vanno perse, perché lo script ascolta Shift solo fra una prova e l'altra. È un limite dello script, non del microfono.

| Prova | Primo blocco | Inizio voce nel wav (pre-roll incluso) | Trascrizione |
|---|---|---|---|
| 1 | 23 ms | 320 ms, cioè ~20 ms dopo Shift | "Abri Safari" |
| 2 | 1 ms | 340 ms, cioè ~40 ms dopo Shift | "Abre il suo fare." |

- In warm la voce comincia **20-40 ms dopo il trigger**: chi parla subito lo fa ben prima dei 100-520 ms che la modalità cold perde.
- "Apri" diventa "Abri"/"Abre" anche in warm: è un limite del riconoscimento, non un taglio del microfono. Va migliorato nel matching (T10, fuzzy) e con frasi alternative nei comandi.
- Nessun clic o artefatto evidente nel pre-roll (RMS dei primi 100 ms: 0,0003-0,0025).

## Tabella di riepilogo

| Modalità | Prove con prima sillaba tagliata (su 5) | Ritardi stampati (media apertura / primo blocco) | Note |
|---|---|---|---|
| cold | non misurabile all'ascolto: il wav parte dopo il ritardo | 234 / 272 ms (max 473 / 521) | allucinazione su una prova senza voce |
| warm | 0 / 2 | 0 / ~12 ms | voce già catturata 20-40 ms dopo il trigger |

Altre osservazioni: in warm l'indicatore arancione del microfono di macOS resta acceso finché lo stream è aperto.

## Decisione (dell'utente, 2026-11-15)

- **`audio.keep_stream_open: true`** come default, con **`preroll_ms: 300`**. La modalità cold perde 100-520 ms dopo il trigger e la prima apertura dopo l'avvio ne richiede ~3,3 s; in warm la registrazione parte subito e include anche i 300 ms prima del trigger. Costo accettato dall'utente: l'indicatore arancione di macOS resta acceso mentre l'app è attiva. L'audio resta solo in memoria, in un buffer circolare.
- `keep_stream_open: false` resta disponibile da YAML. In quel caso il Recorder (T08) deve aprire e chiudere lo stream una volta all'avvio per assorbire i ~3,3 s della prima apertura.
- Recorder (T08): in warm, se lo stream cade (dispositivo cambiato, errore PortAudio), va riaperto e segnalato nel log.
- Lo scarto del silenzio (`silence_rms`, `no_speech_prob`) è obbligatorio: su una prova senza voce Whisper ha prodotto "Grazie a tutti."
- Numeri validi per questo Mac; su Windows (WASAPI/MME) il ritardo di apertura può essere diverso: da verificare in T26.
