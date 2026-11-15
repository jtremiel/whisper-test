import pytest

from voicecmd.matcher import match
from voicecmd.schema import Command, MatchingConfig


def _cmd(name: str, *phrases: str) -> Command:
    return Command(name=name, phrases=list(phrases), action={"type": "open", "target": "x"})


COMMANDS = [
    _cmd("Apri browser", "apri il browser", "apri chrome"),
    _cmd("Apri Safari", "apri safari"),
    _cmd("Blocca schermo", "blocca lo schermo"),
]

DEFAULTS = MatchingConfig()


def _match(text, commands=COMMANDS):
    return match(text, commands, DEFAULTS.threshold, DEFAULTS.margin)


def test_exact_phrase():
    r = _match("apri il browser")
    assert r.command is COMMANDS[0]
    assert r.score == 100
    assert r.closest == "Apri browser"
    assert r.closest_score == 100
    assert r.heard == "apri il browser"


def test_second_phrase_of_command():
    assert _match("apri chrome").command is COMMANDS[0]


def test_transcription_typo():
    r = _match("apri il brauser")
    assert r.command is COMMANDS[0]
    assert r.score >= 80


def test_case_accents_and_final_dot_ignored():
    r = _match("  BLÒCCA lo Schermo.")
    assert r.command is COMMANDS[2]
    assert r.score == 100
    assert r.heard == "  BLÒCCA lo Schermo."  # testo originale, non normalizzato


@pytest.mark.parametrize("heard", ["Abri Safari", "Abre il safari", "abri safari.", "Apri il Safari"])
def test_whisper_variants_of_apri(heard):
    # varianti reali viste negli spike (docs/spikes/T06-mic.md), soglia 80 e margin 5 di default
    r = _match(heard)
    assert r.command is COMMANDS[1], (heard, r)


def test_unrelated_phrase_no_match_but_closest():
    r = _match("che tempo fa oggi")
    assert r.command is None
    assert r.score == 0.0
    assert r.closest in {c.name for c in COMMANDS}
    assert 0 < r.closest_score < 80


def test_two_commands_almost_tied_no_match():
    cmds = [_cmd("Apri note", "apri note"), _cmd("Apri nota", "apri nota")]
    r = _match("apri not", cmds)  # ~94 per entrambi
    assert r.command is None
    assert r.closest in {"Apri note", "Apri nota"}
    assert r.closest_score >= 80


def test_margin_respected_exactly():
    cmds = [_cmd("A", "apri safari"), _cmd("B", "apri safara")]
    # "apri safari" = 100 per A, ~90.9 per B: distacco > 5 -> corrispondenza
    assert match("apri safari", cmds, 80, 5).command is cmds[0]
    # con margine più alto del distacco -> nessuna corrispondenza
    assert match("apri safari", cmds, 80, 20).command is None


def test_threshold_respected():
    r = match("apri il brauser", COMMANDS, threshold=95, margin=5)
    assert r.command is None
    assert r.closest == "Apri browser"


def test_single_command_no_second():
    cmds = [_cmd("Solo", "apri safari")]
    assert _match("apri safari", cmds).command is cmds[0]


@pytest.mark.parametrize("text", ["", "   ", "?!."])
def test_empty_text(text):
    r = _match(text)
    assert r.command is None
    assert r.score == 0.0
    assert r.closest is not None
    assert r.closest_score == 0.0


def test_empty_command_list():
    r = _match("apri il browser", [])
    assert r.command is None
    assert r.closest is None
    assert r.score == 0.0 and r.closest_score == 0.0
