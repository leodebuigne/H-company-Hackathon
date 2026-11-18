"""Phrases dites à l'utilisateur : résumé des options et confirmation de commande.

Écrites à la main plutôt que générées par un modèle : un prix ou un article inventé au moment de
la confirmation serait grave. Elles sont aussi plus rapides, et identiques dans FakeAI et HFAI.
"""

from __future__ import annotations

import re

from orchestrator.contracts import Option, OrderSummary

MAX_SPOKEN_OPTIONS = 3


def euros(cents: int) -> str:
    """1450 -> « 14 euros 50 », 1400 -> « 14 euros »."""
    whole, rest = divmod(cents, 100)
    return f"{whole} euros" if rest == 0 else f"{whole} euros {rest:02d}"


def _rating(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def options_summary(options: list[Option]) -> str:
    """3 options au maximum : numéro, nom, prix, note. Se termine en proposant les détails."""
    if not options:
        return "Je n'ai rien trouvé. Voulez-vous que je cherche autrement ?"
    parts = []
    for number, option in enumerate(options[:MAX_SPOKEN_OPTIONS], start=1):
        note = f", noté {_rating(option.rating)} sur 5" if option.rating is not None else ""
        parts.append(f"{number}, {option.title}, {euros(option.price_cents)}{note}")
    return "J'ai trouvé : " + ". ".join(parts) + ". Voulez-vous des détails sur l'une d'elles ?"


def order_statement(summary: OrderSummary) -> str:
    """Confirmation sous forme d'affirmation, jamais de question : le oui est demandé à part."""
    articles = []
    for item in summary.items:
        label = f"{item.quantity} {item.name}"
        if item.options:
            label += " (" + ", ".join(item.options) + ")"
        articles.append(label)
    sentence = f"J'ai mis dans le panier {', '.join(articles)}, total {euros(summary.total_cents)}"
    fees = sum(fee.amount_cents for fee in summary.fees)
    if fees:
        sentence += f" dont {euros(fees)} de frais"
    if summary.when_label:
        sentence += f", {summary.when_label}"
    sentence += "."
    if summary.conditions:
        sentence += f" {summary.conditions.rstrip('.')}."
    return sentence


_ORDINAL_OPTIONS = [
    "Première",
    "Deuxième",
    "Troisième",
    "Quatrième",
    "Cinquième",
    "Sixième",
    "Septième",
    "Huitième",
]

_SPOKEN_REPLACEMENTS = [
    # « 1, TGV… » est mal lu (« Zon ») : on dit « Première option : TGV… »
    (
        re.compile(r"(^|[:.]\s*)([1-8]),\s+"),
        lambda m: f"{m.group(1)}{_ORDINAL_OPTIONS[int(m.group(2)) - 1]} option : ",
    ),
    (re.compile(r"\binoui\b", re.IGNORECASE), "Inoui"),
    (re.compile(r"\s*(→|->|⟶)\s*"), " vers "),
    (re.compile(r"\s+[·•|—–]\s+"), ", "),
    (re.compile(r"\b1(?:re|ère)\b"), "première"),
    (re.compile(r"\b2(?:de|nde)\b"), "seconde"),
    (re.compile(r"\b(\d+)(?:e|ème)\b"), r"\1ième"),
    # « h » seul est épelé par Kokoro (« 14, H44 ») : on écrit « heures » en toutes lettres.
    (re.compile(r"\b(\d{1,2})\s*[:h]\s*(\d{2})\b"), lambda m: _hours(m.group(1), m.group(2))),
    (re.compile(r"\b(\d{1,2})\s*h\b"), lambda m: _hours(m.group(1), "00")),
    (re.compile(r"(\d+),00\s*(?:€|EUR\b)"), r"\1 euros"),
    (re.compile(r"(\d+),(\d{2})\s*(?:€|EUR\b)"), r"\1 euros \2"),
    (re.compile(r"(\d+)\s*(?:€|EUR\b)"), r"\1 euros"),
    (re.compile(r"\b(\d+)\s*min\b"), r"\1 minutes"),
    (re.compile(r"\s{2,}"), " "),
]


def _hours(hours: str, minutes: str) -> str:
    unit = "heure" if int(hours) <= 1 else "heures"
    return f"{int(hours)} {unit}" if minutes == "00" else f"{int(hours)} {unit} {minutes}"


def for_speech(text: str) -> str:
    """Réécrit un texte affiché pour qu'il sonne juste à l'oral (heures, flèches, prix, abréviations).

    « 14:44 → 15:48, 2de classe » -> « 14 heures 44 vers 15 heures 48, seconde classe ».
    Ne change que la prononciation : le texte affiché à l'écran reste celui du site.
    """
    for pattern, replacement in _SPOKEN_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text.strip()
