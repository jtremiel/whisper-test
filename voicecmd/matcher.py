"""Matching fuzzy tra la frase trascritta e le frasi dei comandi (PRD RF4)."""
from __future__ import annotations

from typing import Sequence

from rapidfuzz import fuzz

from voicecmd.events import MatchResult
from voicecmd.schema import Command
from voicecmd.textutil import normalize

# Articoli italiani: Whisper li aggiunge o li toglie spesso ("abre il safari"
# per "apri safari"); il punteggio si calcola anche senza, e vale il migliore.
_ARTICLES = frozenset({"il", "lo", "la", "i", "gli", "le", "l", "un", "uno", "una"})


def _without_articles(text: str) -> str:
    return " ".join(w for w in text.split() if w not in _ARTICLES)


def _score(heard: str, phrase: str) -> float:
    """Punteggio 0-100 tra due testi già normalizzati."""
    if not heard or not phrase:
        return 0.0
    best = fuzz.ratio(heard, phrase)
    h, p = _without_articles(heard), _without_articles(phrase)
    if h and p and (h, p) != (heard, phrase):
        best = max(best, fuzz.ratio(h, p))
    return float(best)


def match(
    text: str,
    commands: Sequence[Command],
    threshold: float = 80,
    margin: float = 5,
) -> MatchResult:
    """Sceglie il comando la cui frase è più simile a `text`.

    Il punteggio di un comando è il migliore tra le sue frasi. C'è
    corrispondenza solo se il primo raggiunge `threshold` (soglia inclusa) e
    supera il secondo comando di almeno `margin`. `closest` è il nome del
    comando col punteggio più alto ed è valorizzato se c'è almeno un comando.
    """
    heard = normalize(text)
    scored: list[tuple[float, Command]] = []
    for cmd in commands:
        phrases = [normalize(p) for p in cmd.phrases]
        scored.append((max((_score(heard, p) for p in phrases), default=0.0), cmd))

    if not scored:
        return MatchResult(command=None, score=0.0, heard=text, closest=None, closest_score=0.0)

    # ordinamento stabile: a pari punteggio vince il primo comando della config
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_cmd = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if heard and best_score >= threshold and best_score - second_score >= margin:
        return MatchResult(
            command=best_cmd,
            score=best_score,
            heard=text,
            closest=best_cmd.name,
            closest_score=best_score,
        )
    return MatchResult(
        command=None,
        score=0.0,
        heard=text,
        closest=best_cmd.name,
        closest_score=best_score,
    )
