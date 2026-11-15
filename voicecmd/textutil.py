"""Utilità sul testo: unione dei segmenti di Whisper e normalizzazione per il matching."""
from __future__ import annotations

import unicodedata

PUNCTUATION = ".,;:!?"


def intelligent_concatenate(first: str, second: str) -> str:
    """Unisce due pezzi di testo sistemando punteggiatura e maiuscole (copiata da real.py)."""
    first, second = first.strip(), second.strip()
    if not second:
        return first
    if not first:
        return second
    if second[0] in PUNCTUATION:
        if first[-1] in PUNCTUATION:
            first = first[:-1]
        return first + second
    if second[0].islower() and first[-1] == ".":
        return first[:-1] + " " + second
    if second[0].isupper() and first[-1] not in PUNCTUATION:
        return first + ". " + second
    return first + " " + second


def _strip_accents(text: str) -> str:
    # NFKD separa la lettera dall'accento, poi si scartano i segni combinanti
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Minuscole, senza accenti né punteggiatura, spazi compattati.

    Come `_norm` di real.py ma su una frase intera: ogni carattere non
    alfanumerico (punteggiatura, apostrofi, trattini) diventa uno spazio,
    così "l'app" diventa "l app" e "Apri Safari." diventa "apri safari".
    """
    text = _strip_accents(text.lower())
    cleaned = "".join(c if c.isalnum() else " " for c in text)
    return " ".join(cleaned.split())
