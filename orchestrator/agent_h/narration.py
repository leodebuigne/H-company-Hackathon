"""Commentaire en direct : ce que l'agent H s'apprête à faire, en une phrase courte à dire à l'oral.

Règles fixes (pas de modèle) : instantané, gratuit, et jamais de texte inventé. Une action sans phrase
connue renvoie None et ne dit rien. Aucune donnée personnelle : on ne répète que des villes ou des mots
courts tapés par l'agent, jamais une adresse e-mail ni un numéro.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_PERSONAL = re.compile(r"@|\d{4,}")


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Sites connus : nom dit à voix haute quand l'agent les ouvre
_SITES: list[tuple[str, str]] = [
    ("sncf", "SNCF Connect"),
    ("ubereats", "Uber Eats"),
    ("google.com/maps", "Google Maps"),
    ("amazon", "Amazon"),
    ("fnac", "la Fnac"),
    ("darty", "Darty"),
    ("doctolib", "Doctolib"),
    ("booking.com", "Booking"),
    ("thefork", "TheFork"),
    ("duckduckgo", "le moteur de recherche"),
    ("google.", "Google"),
]

# (mots à trouver dans la description de l'élément cliqué, phrase) — le premier qui correspond gagne
_CLICKS: list[tuple[tuple[str, ...], str]] = [
    (("valider et payer", "payer", "commander", "confirmer la commande"), "Je valide l'achat."),
    (
        ("choisir ce tarif", "tarif", "2de classe", "1re classe", "seconde classe", "premiere classe"),
        "Je choisis le tarif.",
    ),
    (("passer l'etape", "continuer", "suivant"), "J'avance dans la réservation."),
    (("panier",), "J'ouvre le panier."),
    (("lancer la recherche", "rechercher", "loupe"), "Je lance la recherche."),
    (("trains",), "J'ouvre la recherche de trains."),
    (("calendrier", "date", "aller", "jour "), "Je choisis la date."),
    (("depart",), "J'indique la gare de départ."),
    (("arrivee",), "J'indique la gare d'arrivée."),
    (("reserver une table", "reserver"), "J'ouvre la réservation."),
    (("se connecter", "connexion", "mon compte"), "J'ouvre la page de connexion."),
    (("cookies", "accepter", "refuser"), "Je ferme le bandeau des cookies."),
]


def describe_action(tool_name: str, args: dict[str, Any] | None) -> str | None:
    """Phrase courte pour une action de l'agent H, ou None s'il n'y a rien d'utile à dire."""
    args = args or {}
    if tool_name == "go_to_web":
        url = str(args.get("url", ""))
        for part, name in _SITES:
            if part in url:
                return f"J'ouvre {name}."
        return None
    if tool_name == "write":
        text = " ".join(str(args.get("text", "")).split())
        if not text or len(text) > 40 or _PERSONAL.search(text):
            return None
        return f"J'écris {text}."
    if tool_name == "scroll_web":
        return "Je parcours les résultats."
    if tool_name == "click_web":
        element = _plain(str(args.get("element", "")))
        for words, sentence in _CLICKS:
            if any(word in element for word in words):
                return sentence
        return None
    if tool_name == "request_payment_approval":
        return "Je vérifie le prix avant d'acheter."
    return None


def actions_in(event: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Actions annoncées par un événement du flux H (policy_event : ce que l'agent va faire)."""
    data = event.get("data") or {}
    if data.get("kind") != "policy_event":
        return []
    return [
        (str(req.get("tool_name", "")), req.get("args") or {})
        for req in data.get("tool_reqs") or []
        if isinstance(req, dict)
    ]
