"""Mémoire des sites : une fiche par domaine, stockée dans Redis (Upstash REST).

Sans UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN, la mémoire reste en RAM :
pratique pour développer, perdue au redémarrage.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from typing import Protocol

import httpx
from pydantic import ValidationError

from orchestrator.contracts import SiteCard

from .models import SiteNotes

MAX_LINES = 12
# Tout ce qui ressemble à une donnée personnelle : email, numéro long, adresse avec numéro de rue.
_PERSONAL = re.compile(r"@|\d{4,}|\b\d{1,4}\s*(rue|avenue|bd|boulevard|chemin|place|allée)\b", re.IGNORECASE)


def sanitize(lines: list[str]) -> list[str]:
    """Garde seulement des lignes génériques sur l'usage du site, sans donnée personnelle."""
    clean = []
    for line in lines:
        text = " ".join(str(line).split())[:200]
        if text and not _PERSONAL.search(text) and text not in clean:
            clean.append(text)
    return clean[:MAX_LINES]


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
) -> SiteCard:
    """Ajoute une commande menée jusqu'au paiement à la fiche du site (contrat SiteCard)."""
    runs = old.runs if old else 0
    buttons = sanitize((old.useful_buttons if old else []) + (notes.useful_buttons if notes else []))
    return SiteCard(
        domain=domain,
        steps=sanitize((notes.steps if notes else []) or (old.steps if old else [])),
        useful_buttons=[button[:80] for button in buttons],
        pitfalls=sanitize((old.pitfalls if old else []) + (notes.pitfalls if notes else [])),
        runs=runs + 1,
        successful_runs=(old.successful_runs if old else 0) + 1,
        avg_duration_s=_mean(old.avg_duration_s if old else None, runs, seconds),
        avg_steps=_mean(old.avg_steps if old else None, runs, steps),
        updated_at=now or dt.datetime.now(dt.UTC),
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


def site_memory_from_env() -> SiteMemory:
    url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        return UpstashSiteMemory(url, token)
    return InMemorySiteMemory()
