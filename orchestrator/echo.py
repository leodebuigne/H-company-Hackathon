"""Écho : reconnaître, dans ce que le micro a compris, la propre voix de Pilote.

Le micro capte parfois ce que Pilote dit (haut-parleurs). Sans filtre, Pilote répond à sa propre question,
la répète, ou pire : un « oui » dit par sa propre phrase (« dites oui pour confirmer ») serait pris pour
un accord. Deux gardes, sans horloge (l'heure d'arrivée d'un enregistrement ne dit rien sur le moment où
il a été fait) :

- une transcription qui reprend une longue suite de mots d'une phrase récente de Pilote est de l'écho ;
- un enregistrement que l'interface déclare chevauché par la voix de Pilote ne peut pas valoir « oui »,
  « non » ni code : ces mots-là peuvent venir de Pilote.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

# Part des mots de la transcription qui se retrouvent, d'affilée, dans une phrase récente de Pilote.
ECHO_SHARE = 0.8
# En dessous de ce nombre de mots, une ressemblance ne prouve rien (« la deuxième » est dans la phrase
# qui propose les options, mais c'est aussi la vraie réponse).
ECHO_MIN_WORDS = 4

_DIGIT_WORDS = {"zero", "un", "une", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf"}
_BARE_ANSWERS = {
    "oui", "ouais", "ok", "okay", "non", "nan", "d", "accord", "daccord", "c", "est", "bon", "confirme",
    "vas", "y", "allez", "valide", "paie", "payez", "achete", "exactement", "stop",
}  # fmt: skip


def words(text: str) -> list[str]:
    """Mots en minuscules sans accents ni ponctuation, comparables d'une phrase à l'autre."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("'", " ").replace("’", " "))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", plain).split()


def echo_share(text: str, sentences: list[str]) -> float:
    """Part (0 à 1) des mots de `text` qui forment une suite continue d'une des `sentences`."""
    heard = words(text)
    if not heard:
        return 0.0
    best = 0
    for sentence in sentences:
        said = words(sentence)
        if not said:
            continue
        match = difflib.SequenceMatcher(None, heard, said, autojunk=False).find_longest_match(
            0, len(heard), 0, len(said)
        )
        best = max(best, match.size)
    return best / len(heard)


def is_echo(text: str, sentences: list[str]) -> bool:
    """La transcription reprend de longues suites d'une phrase récente de Pilote."""
    return len(words(text)) >= ECHO_MIN_WORDS and echo_share(text, sentences) >= ECHO_SHARE


def is_bare_answer(text: str) -> bool:
    """Seulement « oui », « non », « d'accord »… ou des chiffres (un code) : des mots que Pilote dit aussi."""
    tokens = words(text)
    if not tokens:
        return False
    return all(t in _BARE_ANSWERS or t in _DIGIT_WORDS or t.isdigit() for t in tokens)


def should_drop(text: str, sentences: list[str], overlapped: bool) -> bool:
    """Faut-il ignorer cette transcription comme venant de la voix de Pilote ?"""
    if is_echo(text, sentences):
        return True
    return overlapped and (is_bare_answer(text) or echo_share(text, sentences) >= ECHO_SHARE)
