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


# --- comparaison entre boutiques (aucune boutique nommée) -----------------------------

# Boutiques par type de produit, les plus spécialisées d'abord. Adresses vérifiées le 2026-11-18.
MAISONS_DU_MONDE = ("Maisons du Monde", "https://www.maisonsdumonde.com/FR/fr")
IKEA = ("Ikea", "https://www.ikea.com/fr/fr/")
CONFORAMA = ("Conforama", "https://www.conforama.fr")
LA_REDOUTE = ("La Redoute", "https://www.laredoute.fr")
FNAC = ("Fnac", "https://www.fnac.com")
DARTY = ("Darty", "https://www.darty.com")
BOULANGER = ("Boulanger", "https://www.boulanger.com")
CDISCOUNT = ("Cdiscount", "https://www.cdiscount.com")
DECATHLON = ("Decathlon", "https://www.decathlon.fr")
INTERSPORT = ("Intersport", "https://www.intersport.fr")
LEROY_MERLIN = ("Leroy Merlin", "https://www.leroymerlin.fr")
CASTORAMA = ("Castorama", "https://www.castorama.fr")
MANOMANO = ("ManoMano", "https://www.manomano.fr")
ZALANDO = ("Zalando", "https://www.zalando.fr")
GALERIES_LAFAYETTE = ("Galeries Lafayette", "https://www.galerieslafayette.com")
CULTURA = ("Cultura", "https://www.cultura.com")
KING_JOUET = ("King Jouet", "https://www.king-jouet.com")
SEPHORA = ("Sephora", "https://www.sephora.fr")
NOCIBE = ("Nocibé", "https://www.nocibe.fr")

CATALOG: list[tuple[str, list[tuple[str, str]]]] = [
    # Poltronesofà n'est pas proposé : site vitrine sans prix ni vente en ligne (vu le 2026-11-18).
    (r"canap|sofa|fauteuil|m[ée]ridienne|pouf", [MAISONS_DU_MONDE, CONFORAMA, IKEA]),
    (r"\blit\b|matelas|sommier|armoire|commode|table|chaise|buffet|meuble|[ée]tag[èe]re|bureau|dressing",
     [MAISONS_DU_MONDE, IKEA, CONFORAMA]),
    (r"lampe|abat|luminaire|suspension|lampadaire|miroir|tapis|rideau|coussin|d[ée]co|vase|plaid",
     [MAISONS_DU_MONDE, IKEA, LA_REDOUTE]),
    (r"frigo|r[ée]frig[ée]rateur|lave|four|micro.?onde|aspirateur|cafeti[èe]re|machine [àa] caf[ée]|"
     r"bouilloire|grille.?pain|plaque", [DARTY, BOULANGER, CDISCOUNT]),
    (r"casque|[ée]couteur|t[ée]l[ée]|tv|ordinateur|\bpc\b|portable|smartphone|t[ée]l[ée]phone|tablette|"
     r"console|enceinte|appareil photo|montre connect", [FNAC, DARTY, BOULANGER]),
    (r"v[ée]lo|running|course|tente|ballon|raquette|sport|randonn|\bski\b|fitness|yoga|natation",
     [DECATHLON, INTERSPORT, CDISCOUNT]),
    (r"perceuse|visseuse|outil|peinture|parquet|carrelage|tondeuse|barbecue|jardin|robinet|[ée]chelle",
     [LEROY_MERLIN, CASTORAMA, MANOMANO]),
    (r"chaussure|basket|veste|manteau|robe|pantalon|jean|t.?shirt|pull|chemise|sac\b|v[êe]tement",
     [ZALANDO, LA_REDOUTE, GALERIES_LAFAYETTE]),
    (r"parfum|maquillage|cr[èe]me|soin|shampo|rouge [àa] l[èe]vres", [SEPHORA, NOCIBE]),
    (r"livre|roman|\bbd\b|manga|jeu vid[ée]o", [FNAC, CULTURA]),
    (r"jouet|lego|puzzle|poup[ée]e|peluche|jeu de soci[ée]t[ée]", [KING_JOUET, FNAC, CULTURA]),
]  # fmt: skip
GENERALISTS = [CDISCOUNT, LA_REDOUTE, FNAC]
MAX_COMPARED = 3  # sessions H en même temps : 3 au plus avec l'offre gratuite


def compare_sites(intent: Intent) -> list[tuple[str, str]]:
    """Boutiques à comparer pour cet objet (nom, adresse), les plus adaptées d'abord."""
    said = f"{intent.object or ''} {intent.text or ''}".lower()
    for pattern, shops in CATALOG:
        if re.search(pattern, said):
            return shops[:MAX_COMPARED]
    return GENERALISTS[:MAX_COMPARED]


def shop_name(url: str) -> str:
    """Nom lisible d'une boutique à partir de son adresse."""
    known = {u: n for _, shops in CATALOG for n, u in shops} | {u: n for n, u in GENERALISTS}
    if url in known:
        return known[url]
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return host
