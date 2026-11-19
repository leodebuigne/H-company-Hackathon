"""Recherche par adresse directe : le navigateur s'ouvre déjà sur la page de résultats du site.

La plupart des sites mettent la recherche dans l'adresse (amazon.fr/s?k=casque). Ouvrir cette adresse
évite à l'agent de trouver la barre de recherche, cliquer, taper et valider : plusieurs actions de
moins, chacune coûtant plusieurs secondes de modèle. Si la page ne montre pas de résultats, l'agent
reprend la barre de recherche du site (consigne de prompts.SEARCH_METHOD).

Deux sources d'adresses : celles connues d'avance (BUILTIN), et celles apprises par la mémoire des sites
(une ligne « Recherche directe : … » dans la fiche, déduite de la page de résultats rapportée par l'agent).
PILOTE_SEARCH_SHORTCUTS=0 coupe tout (mesure avant / après).
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote_plus, unquote_plus, urlsplit

from orchestrator.contracts import Intent, SiteCard

# Adresses de recherche connues, {q} = la recherche (mots séparés par +).
BUILTIN: dict[str, str] = {
    "www.amazon.fr": "https://www.amazon.fr/s?k={q}",
    "www.fnac.com": "https://www.fnac.com/SearchResult/ResultList.aspx?Search={q}",
    "www.darty.com": "https://www.darty.com/nav/recherche?text={q}",
    "www.google.com": "https://www.google.com/maps/search/{q}",
    "www.ubereats.com": "https://www.ubereats.com/fr/search?q={q}",
    "www.booking.com": "https://www.booking.com/searchresults.fr.html?ss={q}",
    "duckduckgo.com": "https://duckduckgo.com/?q={q}",
}

LEARNED_PREFIX = "Recherche directe : "

_RESTAURANT = re.compile(r"restau|table|d[iî]ner|d[ée]jeuner|brunch", re.IGNORECASE)
_HOTEL = re.compile(r"h[ôo]tel|chambre|nuit|logement", re.IGNORECASE)


@dataclass(frozen=True)
class Shortcut:
    domain: str  # clé de la fiche du site (www.amazon.fr)
    url: str  # page de résultats à ouvrir
    query: str  # la recherche tapée, en clair


def enabled() -> bool:
    return os.getenv("PILOTE_SEARCH_SHORTCUTS", "").strip() != "0"


def _words(*parts: str | None) -> str:
    return " ".join(" ".join(p.split()) for p in parts if p and p.strip())


def query_for(intent: Intent) -> str:
    """Ce qu'une personne taperait dans la barre de recherche du site, d'après la demande."""
    d = intent.details
    if intent.category == "train":
        return ""  # SNCF Connect : recherche rapide décrite dans sa fiche
    if intent.category == "reservation":
        kind = _words(intent.object, d.get("kind"))
        if _RESTAURANT.search(kind) or d.get("cuisine"):
            return _words("restaurant", d.get("cuisine"), d.get("place"))
        return _words(intent.object if not _HOTEL.search(kind) else "", d.get("place")) or _words(kind)
    if intent.category == "repas":
        return _words(intent.object or d.get("cuisine"), d.get("restaurant"))
    obj = intent.object or ""
    extra = [v for k in ("brand", "color") if (v := d.get(k)) and v.lower() not in obj.lower()]
    return _words(obj, *extra)


def default_domain(intent: Intent) -> str | None:
    """Site choisi d'office quand aucun site n'est configuré (le plus connu en France pour la tâche)."""
    if intent.category == "boutique":
        return "www.amazon.fr"
    if intent.category == "reservation":
        kind = _words(intent.object, intent.details.get("kind"))
        if _RESTAURANT.search(kind) or intent.details.get("cuisine"):
            return "www.google.com"  # Google Maps : presque tous les restaurants, avec note et adresse
        if _HOTEL.search(kind):
            return "www.booking.com"
        return "duckduckgo.com"  # rendez-vous, spectacle : le moteur trouve le site officiel
    return None


def learned_template(card: SiteCard | None) -> str | None:
    for line in card.steps if card else []:
        if line.startswith(LEARNED_PREFIX) and "{q}" in line:
            return line[len(LEARNED_PREFIX) :].strip()
    return None


def plan(intent: Intent, site_domain: str, card: SiteCard | None) -> Shortcut | None:
    """Adresse directe pour cette demande, ou None (l'agent part de l'accueil du site)."""
    if not enabled():
        return None
    query = query_for(intent)
    domain = site_domain or default_domain(intent) or ""
    template = learned_template(card) or BUILTIN.get(domain)
    if not query or not template:
        return None
    return Shortcut(domain=domain, url=template.replace("{q}", quote_plus(query)), query=query)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", unquote_plus(text)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def template_from(results_url: str, query: str) -> str | None:
    """Adresse type d'une page de résultats, la recherche remplacée par {q} :
    « https://www.x.fr/recherche?q=casque+sony&page=1 » + « casque sony »
    → « https://www.x.fr/recherche?q={q} ».

    Ne garde que le paramètre (ou le morceau de chemin) qui contient la recherche : aucun identifiant de
    session ni donnée de compte n'entre dans la fiche.
    """
    words = _norm(query).split()
    if not words or not results_url.startswith(("http://", "https://")):
        return None
    parts = urlsplit(results_url)
    base = f"{parts.scheme}://{parts.netloc}"
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        if words[0] in _norm(value).split():
            return f"{base}{parts.path}?{key}={{q}}"
    segments = parts.path.split("/")
    for i, segment in enumerate(segments):
        if words[0] in _norm(segment).split():
            return base + "/".join(segments[:i] + ["{q}"])
    return None
