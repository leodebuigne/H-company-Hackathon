"""Mémoire des sites : une fiche par domaine, stockée dans Redis (Upstash REST).

Sans UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN, les fiches sont gardées dans un fichier
local (data/site-cards.json, ou PILOTE_SITE_MEMORY_PATH) : un site appris le reste.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import ValidationError

from orchestrator.contracts import SiteCard

from .models import SiteNotes

MAX_LINES = 12
# Tout ce qui ressemble à une donnée personnelle : email, numéro long, adresse avec numéro de rue.
_PERSONAL = re.compile(r"@|\d{4,}|\b\d{1,4}\s*(rue|avenue|bd|boulevard|chemin|place|allée)\b", re.IGNORECASE)


def sanitize(lines: list[str], keep: str = "first") -> list[str]:
    """Garde seulement des lignes génériques sur l'usage du site, sans donnée personnelle.

    MAX_LINES au plus : les premières (keep="first") ou les plus récentes, en fin de liste (keep="last").
    """
    clean = []
    for line in lines:
        text = " ".join(str(line).split())[:200]
        if text and not _PERSONAL.search(text) and text not in clean:
            clean.append(text)
    return clean[-MAX_LINES:] if keep == "last" else clean[:MAX_LINES]


def domain_of(site: str) -> str:
    """Clé de la fiche (Redis `site:{domaine}`), telle que dans docs/sites.md : www.sncf-connect.com."""
    return re.sub(r"^https?://", "", site.strip().lower()).split("/")[0]


def _mean(old_mean: float | None, old_count: int, value: float | None) -> float | None:
    if value is None:
        return old_mean
    return round(((old_mean or 0.0) * old_count + value) / (old_count + 1), 1)


def merge_card(
    old: SiteCard | None,
    domain: str,
    notes: SiteNotes | None,
    seconds: float,
    steps: int | None = None,
    now: dt.datetime | None = None,
    *,
    success: bool = True,
    blocked: str | None = None,
) -> SiteCard:
    """Ajoute une commande à la fiche du site (contrat SiteCard), achetée ou non.

    Une commande qui n'aboutit pas apprend aussi : ses pièges, ses boutons, et la raison du blocage,
    pour que la suivante l'évite. Seul un achat réussi compte dans successful_runs. On garde les
    lignes les plus récentes.
    """
    runs = old.runs if old else 0
    buttons = sanitize(
        (old.useful_buttons if old else []) + (notes.useful_buttons if notes else []), keep="last"
    )
    learned = (notes.pitfalls if notes else []) + (
        [f"Blocage d'une commande précédente : {blocked}"] if blocked else []
    )
    return SiteCard(
        domain=domain,
        steps=sanitize((notes.steps if notes else []) or (old.steps if old else [])),
        useful_buttons=[button[:80] for button in buttons],
        pitfalls=sanitize((old.pitfalls if old else []) + learned, keep="last"),
        runs=runs + 1,
        successful_runs=(old.successful_runs if old else 0) + (1 if success else 0),
        avg_duration_s=_mean(old.avg_duration_s if old else None, runs, seconds),
        avg_steps=_mean(old.avg_steps if old else None, runs, steps),
        updated_at=now or dt.datetime.now(dt.UTC),
    )


# Fiches de départ, écrites à la main après observation du site (2026-11-18), utilisées tant que la
# mémoire n'a rien appris sur le domaine. Sans elles, l'agent tournait en rond sur SNCF Connect.
STARTER_CARDS: dict[str, dict[str, list[str]]] = {
    "www.sncf-connect.com": {
        "steps": [
            "Part de la page d'accueil https://www.sncf-connect.com, attends qu'elle soit chargée.",
            "Clique sur l'onglet « Trains », dans la barre d'onglets sous le grand titre (à droite de "
            "« Tout rechercher »). Le formulaire Départ / Arrivée / Aller / Voyageurs apparaît.",
            "Clique sur « Départ », tape la ville, choisis la gare dans la liste de suggestions.",
            "Fais de même pour « Arrivée ».",
            "Clique sur « Aller » pour choisir la date et l'heure de départ, puis valide.",
            "Clique sur la loupe ronde à droite du formulaire pour lancer la recherche.",
        ],
        "useful_buttons": ["Trains", "Départ", "Arrivée", "Aller", "Loupe (rechercher)"],
        "pitfalls": [
            "Le grand bandeau « Ouverture des ventes » sous le formulaire est une publicité : ne clique "
            "jamais dessus. S'il t'emmène sur une page /bons-plans/, retourne sur https://www.sncf-connect.com.",
            "Les adresses /trains et /train/france ne sont pas des pages de recherche : repars de l'accueil.",
            "Ne tape pas le trajet dans le champ « Tout rechercher » : utilise l'onglet « Trains ».",
            "Sur le panier, « Valider et payer » est le bouton final, même pour un billet à 0 € : ne clique "
            "dessus qu'à l'étape « achat » ou « paiement », après approbation.",
        ],
    },
}


# Variante « recherche rapide » : tout le trajet tapé d'un coup dans « Tout rechercher »
# (5 actions au lieu de 12 à 17 : 47 s au lieu de 88 s, mesuré le 2026-11-18). Le 2026-11-19, Entrée ne
# lance plus rien et les suggestions sont des adresses : il faut cliquer « Rechercher ». Par défaut ;
# PILOTE_SNCF_QUICK_SEARCH=0 revient au formulaire Trains.
QUICK_SEARCH_SNCF: dict[str, list[str]] = {
    "steps": [
        "Part de la page d'accueil https://www.sncf-connect.com, attends qu'elle soit chargée.",
        "Reste sur l'onglet « Tout rechercher ». Clique dans le champ « Entrez une destination, un trajet… » et "
        "tape d'un coup le trajet, la date et l'heure, par exemple « Paris Nantes 19 novembre 8h ».",
        "Ne choisis aucune suggestion (ce sont des adresses) et n'appuie pas sur Entrée (ça ne fait rien).",
        "Clique tout de suite sur le bouton bleu « Rechercher » à droite du champ, puis attends le chargement "
        "(une dizaine de secondes) : la page des trains s'ouvre.",
        "Sur les résultats, lis directement les trains : ne refais pas la recherche et ne reconfirme pas "
        "Départ, Arrivée ni la date.",
        "Ne corrige que si la gare ou la date affichée en haut des résultats est fausse.",
    ],
    "useful_buttons": ["Tout rechercher", "Rechercher", "Choisir ce tarif", "Passer l'étape"],
    "pitfalls": [
        "Le grand bandeau « Ouverture des ventes » sous le champ est une publicité : ne clique jamais dessus. "
        "S'il t'emmène sur une page /bons-plans/, retourne sur https://www.sncf-connect.com.",
        "Seulement si la page des trains ne s'ouvre pas après le clic sur « Rechercher », utilise l'onglet "
        "« Trains » et son formulaire.",
        "Sur le panier, « Valider et payer » est le bouton final, même pour un billet à 0 € : ne clique dessus "
        "qu'à l'étape « achat » ou « paiement », après approbation.",
    ],
}


def starter_card(domain: str) -> SiteCard | None:
    seed = STARTER_CARDS.get(domain)
    if domain == "www.sncf-connect.com" and os.getenv("PILOTE_SNCF_QUICK_SEARCH", "").strip() != "0":
        seed = QUICK_SEARCH_SNCF
    if seed is None:
        return None
    return SiteCard(
        domain=domain,
        steps=seed["steps"],
        useful_buttons=seed["useful_buttons"],
        pitfalls=seed["pitfalls"],
        runs=0,
        successful_runs=0,
        avg_duration_s=None,
        avg_steps=None,
        updated_at=dt.datetime(2026, 11, 18, tzinfo=dt.UTC),
    )


def card_for_order(learned: SiteCard | None, starter: SiteCard | None) -> SiteCard | None:
    """Fiche donnée à l'agent : les étapes de départ écrites à la main (le speedrun SNCF) passent
    toujours en premier, et la mémoire ajoute ce qu'elle a appris (pièges, boutons, statistiques).
    Sans fiche de départ, la mémoire seule ; sans mémoire, la fiche de départ seule."""
    if learned is None or starter is None:
        return learned or starter
    return learned.model_copy(
        update={
            "steps": starter.steps,
            "pitfalls": sanitize(starter.pitfalls + learned.pitfalls),
            "useful_buttons": sanitize(starter.useful_buttons + learned.useful_buttons),
        }
    )


class SiteMemory(Protocol):
    async def get(self, domain: str) -> SiteCard | None: ...
    async def put(self, card: SiteCard) -> None: ...


class InMemorySiteMemory:
    def __init__(self) -> None:
        self._cards: dict[str, SiteCard] = {}

    async def get(self, domain: str) -> SiteCard | None:
        return self._cards.get(domain)

    async def put(self, card: SiteCard) -> None:
        self._cards[card.domain] = card


class UpstashSiteMemory:
    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _cmd(self, *args: str) -> str | None:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(self._url, headers=self._headers, json=list(args))
            resp.raise_for_status()
            return resp.json().get("result")

    async def get(self, domain: str) -> SiteCard | None:
        raw = await self._cmd("GET", f"site:{domain}")
        if not raw:
            return None
        try:
            return SiteCard.model_validate_json(raw)
        except ValidationError:  # fiche écrite dans un ancien format : on repart de zéro
            return None

    async def put(self, card: SiteCard) -> None:
        await self._cmd("SET", f"site:{card.domain}", card.model_dump_json())


class FileSiteMemory:
    """Fiches gardées dans un fichier JSON sur cet ordinateur : chaque site appris le reste après un
    redémarrage. Utilisée par défaut quand Redis (Upstash) n'est pas configuré."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)

    def _read(self) -> dict[str, dict]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    async def get(self, domain: str) -> SiteCard | None:
        raw = self._read().get(domain)
        if raw is None:
            return None
        try:
            return SiteCard.model_validate(raw)
        except ValidationError:  # fiche d'un ancien format : on repart de zéro
            return None

    async def put(self, card: SiteCard) -> None:
        data = self._read()
        data[card.domain] = card.model_dump(mode="json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)  # écriture atomique : jamais de fichier à moitié écrit


DEFAULT_MEMORY_PATH = "data/site-cards.json"


def site_memory_from_env() -> SiteMemory:
    """Redis (Upstash) s'il est configuré, sinon un fichier local (PILOTE_SITE_MEMORY_PATH)."""
    url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        return UpstashSiteMemory(url, token)
    return FileSiteMemory(os.getenv("PILOTE_SITE_MEMORY_PATH") or DEFAULT_MEMORY_PATH)
