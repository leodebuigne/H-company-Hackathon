"""Site d'achat choisi par la personne, et texte de recherche à taper d'un coup dans la barre du site.

Pilote n'est pas un comparateur : la personne a fait sa recherche ailleurs (un assistant, un ami, une
publicité) et demande d'acheter sur le site de son choix, n'importe lequel. Elle peut le donner :
- par un lien vers le produit ou le site (tapé dans le champ de texte) : on l'ouvre tel quel ;
- par son adresse (« sur maisonsdumonde.com ») ;
- par son nom (« chez Ikea », « sur Vinted ») : adresse connue si c'est une boutique courante, sinon
  l'agent part d'une recherche Bing et ouvre le site officiel ;
- pas du tout : Pilote demande « Sur quel site ? » (session), sauf pour les trains et les repas.

Recherche rapide : l'objet (nom exact ou référence si la personne le connaît) et ses critères en une
saisie, puis le budget avec le filtre de prix du site. Le budget n'est jamais tapé.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse

from orchestrator.contracts import Intent

# Boutiques courantes : adresse directe, sans recherche du site officiel.
KNOWN_SHOPS = {
    "amazon": "https://www.amazon.fr",
    "fnac": "https://www.fnac.com",
    "darty": "https://www.darty.com",
    "boulanger": "https://www.boulanger.com",
    "cdiscount": "https://www.cdiscount.com",
    "leroy merlin": "https://www.leroymerlin.fr",
    "ikea": "https://www.ikea.com/fr/fr/",
    "decathlon": "https://www.decathlon.fr",
    "castorama": "https://www.castorama.fr",
    "maisons du monde": "https://www.maisonsdumonde.com/FR/fr",
    "conforama": "https://www.conforama.fr",
    "la redoute": "https://www.laredoute.fr",
    "zalando": "https://www.zalando.fr",
    "vinted": "https://www.vinted.fr",
    "leboncoin": "https://www.leboncoin.fr",
    "carrefour": "https://www.carrefour.fr",
    "sephora": "https://www.sephora.fr",
    "uber eats": "https://www.ubereats.com/fr",
    "sncf": "https://www.sncf-connect.com",
}

# Noms à dire quand le nom de la boutique ne suffit pas tel quel.
DISPLAY = {
    "sncf": "SNCF Connect",
    "uber eats": "Uber Eats",
    "maisons du monde": "Maisons du Monde",
    "leroy merlin": "Leroy Merlin",
    "la redoute": "La Redoute",
}


def _display(name: str) -> str:
    return DISPLAY.get(name, name.title())


_URL = re.compile(r"https?://[^\s«»\"'<>]+", re.IGNORECASE)
_DOMAIN = re.compile(
    r"\b((?:[a-z0-9-]+\.)+(?:fr|com|net|org|eu|be|ch|io|co|shop|store|it|es|de|uk))\b", re.IGNORECASE
)
# « sur Vinted », « chez Bricomarché », « sur le site de Poltronesofà » ; pas « sur internet ».
_NAMED = re.compile(r"\b(?:sur|chez)\s+(?:le\s+site\s+(?:de\s+|d'|du\s+)?)?(.+)", re.IGNORECASE)
_NOT_A_SHOP = re.compile(
    r"^(internet|le web|le net|un site|leur site|leur appli\w*|mon (?:compte|téléphone)|la table)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SiteChoice:
    url: str  # page d'arrivée de l'agent
    name: str  # nom à dire et à afficher
    lookup: bool = False  # True : recherche Bing du site officiel, à ouvrir par l'agent
    product_link: bool = False  # True : lien direct vers le produit


def _said(intent: Intent) -> list[str]:
    site = intent.details.get("site") if intent.details else None
    return [x for x in (site, *intent.constraints, intent.text) if x]


def _clean_name(raw: str) -> str | None:
    name = re.split(r"[,.;!?]|\s+(?:pour|avec|à|a|en|de moins|moins|qui|pas)\s+", raw.strip(), maxsplit=1)[0]
    name = " ".join(name.split()[:4]).strip(" '\"«»")
    if not name or _NOT_A_SHOP.match(name) or len(name) < 2:
        return None
    return name


def resolve_site(intent: Intent) -> SiteChoice | None:
    """Site d'achat donné par la personne, ou None si elle n'en a pas donné."""
    texts = _said(intent)
    for text in texts:  # 1. un lien : produit ou site
        match = _URL.search(text)
        if match:
            url = match.group(0).rstrip(".,;)")
            path = urlparse(url).path.strip("/")
            return SiteChoice(url=url, name=site_name(url), product_link=len(path) > 2)
    for text in texts:  # 2. une adresse
        match = _DOMAIN.search(text)
        if match:
            domain = match.group(1).lower()
            return SiteChoice(url=f"https://{domain}", name=site_name(domain))
    for text in texts:  # 3. une boutique courante
        plain = text.lower().replace("-", " ")
        for name, url in KNOWN_SHOPS.items():
            if re.search(rf"\b{name}\b", plain):
                return SiteChoice(url=url, name=_display(name))
    for text in (intent.details.get("site") if intent.details else None, *intent.constraints, intent.text):
        if not text:  # 4. n'importe quel autre nom : on cherche son site officiel
            continue
        match = _NAMED.search(text)
        raw = match.group(1) if match else (text if text is intent.details.get("site") else None)
        name = _clean_name(raw) if raw else None
        if name:
            query = quote_plus(f"{name} site officiel achat en ligne")
            return SiteChoice(url=f"https://www.bing.com/search?q={query}", name=name, lookup=True)
    return None


def site_name(url_or_domain: str) -> str:
    """Nom lisible d'un site : « www.maisonsdumonde.com/FR/fr » -> « maisonsdumonde.com »."""
    host = urlparse(url_or_domain).hostname if "://" in url_or_domain else url_or_domain.split("/")[0]
    host = (host or url_or_domain).lower().removeprefix("www.")
    for name, url in KNOWN_SHOPS.items():
        if (urlparse(url).hostname or "").removeprefix("www.") == host:
            return _display(name)
    return host


def mentions_site(text: str) -> bool:
    """Le texte nomme-t-il un site (lien, adresse, boutique, « sur … ») ? À ne pas taper en recherche."""
    plain = text.lower().replace("-", " ")
    return bool(
        _URL.search(text)
        or _DOMAIN.search(text)
        or any(re.search(rf"\b{name}\b", plain) for name in KNOWN_SHOPS)
        or re.match(r"^\s*(sur|chez)\b", plain)
    )


def search_query(intent: Intent) -> str:
    """Texte à taper d'un coup dans la barre de recherche du site : l'objet et ses critères, sans le budget
    ni le site : une barre de recherche ne comprend pas « 3000 € max », on passe par le filtre de prix."""
    if intent.category == "train":
        d = intent.details
        when = intent.when
        parts = [d.get("origin", ""), d.get("destination", "")]
        if when.date:
            parts.append(f"{when.date.day} {MONTHS_FR[when.date.month - 1]}")
        if when.after or when.before:
            parts.append((when.after or when.before or "").replace(":00", "h").replace(":", "h"))
        return " ".join(p for p in parts if p)
    words = [] if not intent.object or mentions_site(intent.object) else [intent.object]
    for constraint in intent.constraints:
        if mentions_site(constraint) or re.search(r"\d+\s*(€|euros?)\b|\bmoins de\b|\bmax", constraint, re.I):
            continue  # « sur Vinted », « moins de 200 € » : pas dans la recherche
        words.append(constraint)
    return " ".join(w for w in words if w).strip()


MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]  # fmt: skip
