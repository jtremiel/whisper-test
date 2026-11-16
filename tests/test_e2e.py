"""Test end-to-end (slow): Controller, FasterWhisperTranscriber e matcher veri, audio da file.

Solo il recorder (restituisce lo spezzone) e le azioni sono finti. Si lanciano con
`pytest -m slow -s tests/test_e2e.py` (con -s si vedono i tempi di trascrizione).

Audio usato:
- `testVoice.mp3` 0-3 s: "Registrazione di test, prova." (voce reale, trascritta da turbo su mps).
- `tests/data/cmd_*.wav`: frasi dei comandi predefiniti sintetizzate in locale con
  `say -v Alice -o FILE --data-format=LEI16@16000 "FRASE"` (voce italiana di macOS).
"""
from __future__ import annotations

import time
import wave
from importlib.resources import files
from pathlib import Path

import numpy as np
import pytest
import yaml

from voicecmd.controller import Controller
from voicecmd.events import SAMPLE_RATE, ActionResult, AppState, Mode
from voicecmd.schema import Config, SttConfig

from tests.test_stt import TEST_VOICE, _load_audio

pytestmark = pytest.mark.slow

DATA = Path(__file__).resolve().parent / "data"

TEST_CONFIG = {
    "commands": [
        {"name": "Prova", "phrases": ["registrazione di test prova"],
         "action": {"type": "open", "target": "https://example.org"}},
        {"name": "Luce", "phrases": ["spegni la luce della cucina"],
         "action": {"type": "shell", "command": "true"}},
    ],
}


# --- dipendenze finte -------------------------------------------------------------

class ClipRecorder:
    def __init__(self, audio):
        self.audio = audio

    def start(self):
        pass

    def stop(self):
        return self.audio


class RecordingAction:
    def __init__(self):
        self.specs = []

    def run(self, spec):
        self.specs.append(spec)
        return ActionResult(True, "eseguito")


class Feedback:
    def __init__(self):
        self.outcomes, self.states = [], []

    def on_state(self, state, mode):
        self.states.append(state)

    def on_outcome(self, outcome):
        self.outcomes.append(outcome)


class NoTimer:
    def start(self):
        pass

    def cancel(self):
        pass


# --- supporto ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def transcriber():
    from voicecmd.stt import FasterWhisperTranscriber
    t = FasterWhisperTranscriber(SttConfig(), language="it")  # auto: turbo su mps su questo Mac
    t.transcribe(_load_wav(DATA / "cmd_apri_chrome.wav"))  # riscaldamento, escluso dai tempi
    return t


def _load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert w.getframerate() == SAMPLE_RATE and w.getnchannels() == 1
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def _as_from_mic(audio: np.ndarray) -> np.ndarray:
    """Aggiunge 300 ms di rumore leggero prima e dopo, come preroll e coda del microfono."""
    rng = np.random.default_rng(0)
    pad = (rng.standard_normal(int(0.3 * SAMPLE_RATE)) * 0.003).astype(np.float32)
    return np.concatenate([pad, audio, pad])


def default_config() -> Config:
    return Config.model_validate(yaml.safe_load((files("voicecmd") / "default_config.yaml").read_text("utf-8")))


def run(transcriber, config, audio, mode=Mode.COMMAND, use_hotwords=True, label=""):
    actions = {"open": RecordingAction(), "shell": RecordingAction()}
    pasted = []
    fb = Feedback()
    clock = [0.0]

    def paste(text):
        pasted.append(text)
        return ActionResult(True, "")

    c = Controller(config, ClipRecorder(audio), transcriber, actions, fb, paste,
                   clock=lambda: clock[0], submit=lambda fn: fn(),
                   timer_factory=lambda d, fn: NoTimer(), use_hotwords=use_hotwords)
    t0 = time.perf_counter()
    c.on_trigger(mode, True)
    clock[0] = len(audio) / SAMPLE_RATE
    c.on_trigger(mode, False)
    elapsed = time.perf_counter() - t0
    assert c.state is AppState.IDLE and len(fb.outcomes) == 1
    out = fb.outcomes[0]
    print(f"\n[e2e] {label or mode.value}: audio {len(audio) / SAMPLE_RATE:.2f} s, "
          f"ciclo {elapsed:.2f} s, sentito {out.heard!r}, esito {out.title!r} {out.detail!r}")
    return out, actions, pasted


# --- test -------------------------------------------------------------------------

def test_test_voice_picks_right_command(transcriber):
    clip = _load_audio(TEST_VOICE)[: 3 * SAMPLE_RATE]
    out, actions, _ = run(transcriber, Config.model_validate(TEST_CONFIG), clip, label="testVoice")
    assert out.ok and out.title == "Prova"
    assert [s.target for s in actions["open"].specs] == ["https://example.org"]
    assert actions["shell"].specs == []


def test_test_voice_without_phrase_is_no_match(transcriber):
    cfg = Config.model_validate({"commands": TEST_CONFIG["commands"][1:]})
    clip = _load_audio(TEST_VOICE)[: 3 * SAMPLE_RATE]
    out, actions, _ = run(transcriber, cfg, clip, label="testVoice senza frase")
    assert not out.ok and out.title == "Nessun comando riconosciuto"
    assert out.detail.startswith("Il più vicino: Luce")
    assert actions["open"].specs == [] and actions["shell"].specs == []


# Frasi dei comandi predefiniti → comando atteso. "apri github" manca: la voce sintetica
# lo pronuncia all'italiana e turbo sente "apri vita ab" (70/100), anche con gli hotwords.
DEFAULT_CLIPS = [
    ("cmd_apri_chrome.wav", "Apri browser"),
    ("cmd_apri_il_browser.wav", "Apri browser"),
    ("cmd_blocca_lo_schermo.wav", "Blocca schermo"),
    ("cmd_che_giorno_e_oggi.wav", "Data di oggi"),
]


@pytest.mark.parametrize("clip,expected", DEFAULT_CLIPS)
def test_default_commands_from_speech(transcriber, clip, expected):
    out, actions, _ = run(transcriber, default_config(), _as_from_mic(_load_wav(DATA / clip)), label=clip)
    assert out.ok and out.title == expected
    assert sum(len(a.specs) for a in actions.values()) == 1


def test_hotwords_separate_glued_words(transcriber):
    # Senza hotwords turbo unisce le parole ("Apricrom", 84/100: passa per poco); con gli
    # hotwords "apri" resta una parola a sé ("apri chrome" o "apri crom", 90-100/100).
    audio = _as_from_mic(_load_wav(DATA / "cmd_apri_chrome.wav"))
    without, _, _ = run(transcriber, default_config(), audio, use_hotwords=False, label="senza hotwords")
    with_hw, _, _ = run(transcriber, default_config(), audio, use_hotwords=True, label="con hotwords")
    assert with_hw.ok and with_hw.title == "Apri browser"
    assert with_hw.heard.lower().split()[0] == "apri"
    print(f"[e2e] senza hotwords {without.heard!r}, con {with_hw.heard!r}")


def test_dictation_pastes_transcript(transcriber):
    clip = _load_audio(TEST_VOICE)[: 5 * SAMPLE_RATE]
    out, actions, pasted = run(transcriber, default_config(), clip, mode=Mode.DICTATION,
                               label="dettatura")
    assert out.ok and out.title == "Testo incollato"
    assert len(pasted) == 1 and "mia voce" in pasted[0].lower()
    assert all(a.specs == [] for a in actions.values())


def test_noise_only_is_nothing_heard(transcriber):
    noise = (np.random.default_rng(0).standard_normal(2 * SAMPLE_RATE) * 0.01).astype(np.float32)
    out, actions, _ = run(transcriber, default_config(), noise, label="solo rumore")
    assert not out.ok and out.title == "Non ho sentito niente"
    assert all(a.specs == [] for a in actions.values())
