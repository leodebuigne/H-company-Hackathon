"""Mémoire des sites : une fiche par domaine, stockée dans Redis (Upstash REST).

Sans UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN, la mémoire reste en RAM :
pratique pour développer, perdue au redémarrage.
"""

from __future__ import annotations

import os
import re
from typing import Protocol

import httpx

from .models import SiteCard, SiteNotes

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
    host = re.sub(r"^https?://", "", site.strip().lower()).split("/")[0]
    return host.removeprefix("www.")


def merge_card(old: SiteCard | None, domain: str, notes: SiteNotes | None, seconds: float) -> SiteCard:
    card = old or SiteCard(domain=domain)
    runs = card.runs + 1
    steps = sanitize((notes.steps if notes else []) or card.steps)
    pitfalls = sanitize(card.pitfalls + (notes.pitfalls if notes else []))
    avg = (card.avg_seconds * card.runs + seconds) / runs
    return SiteCard(domain=domain, steps=steps, pitfalls=pitfalls, avg_seconds=round(avg, 1), runs=runs)


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
        return SiteCard.model_validate_json(raw) if raw else None

    async def put(self, card: SiteCard) -> None:
        await self._cmd("SET", f"site:{card.domain}", card.model_dump_json())


def site_memory_from_env() -> SiteMemory:
    url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        return UpstashSiteMemory(url, token)
    return InMemorySiteMemory()
