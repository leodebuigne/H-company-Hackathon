"""Boutiques reconnues et texte de recherche : ce que l'agent tape d'un coup dans la barre du site.

Recherche rapide (généralisée à tous les sites, sur le modèle de « Tout rechercher » de SNCF Connect) :
l'objet et ses critères en une seule saisie, puis le budget avec le filtre de prix ou le tri du site.
Le budget n'est jamais tapé : une barre de recherche prend « 3000 » pour un mot du produit.
"""

from __future__ import annotations

import re

from orchestrator.contracts import Intent

# Boutiques reconnues quand la personne les nomme (« sur Amazon », « chez Fnac »…), toutes catégories.
NAMED_SHOPS = {
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
    "la redoute": "https://www.laredoute.fr",
    "uber eats": "https://www.ubereats.com/fr",
    "sncf": "https://www.sncf-connect.com",
}


def named_shop(intent: Intent) -> str | None:
    """Boutique nommée dans la demande (« un casque sur Amazon »), sinon None."""
    said = " ".join([intent.text or "", *intent.constraints]).lower().replace("-", " ")
    return next((url for name, url in NAMED_SHOPS.items() if re.search(rf"\b{name}\b", said)), None)


def search_query(intent: Intent) -> str:
    """Texte à taper d'un coup dans la barre de recherche du site : l'objet et ses critères, sans le budget
    ni la boutique : une barre de recherche ne comprend pas « 3000 € max », on passe par le filtre de prix."""
    if intent.category == "train":
        d = intent.details
        when = intent.when
        parts = [d.get("origin", ""), d.get("destination", "")]
        if when.date:
            parts.append(f"{when.date.day} {MONTHS_FR[when.date.month - 1]}")
        if when.after or when.before:
            parts.append((when.after or when.before or "").replace(":00", "h").replace(":", "h"))
        return " ".join(p for p in parts if p)
    words = [intent.object or ""]
    for constraint in intent.constraints:
        if named_shop_text(constraint) or re.search(r"\d", constraint):
            continue  # « sur Amazon », « moins de 200 € » : pas dans la recherche
        words.append(constraint)
    return " ".join(w for w in words if w).strip()


def named_shop_text(text: str) -> bool:
    plain = text.lower().replace("-", " ")
    return any(re.search(rf"\b{name}\b", plain) for name in NAMED_SHOPS)


MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]  # fmt: skip
