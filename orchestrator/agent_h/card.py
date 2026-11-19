"""Carte bancaire dictée à voix haute quand le site n'en a pas d'enregistrée, pour un seul paiement.

Règles :
- Pilote ne garde jamais la carte : en mémoire le temps du paiement, puis effacée ; jamais écrite dans un
  journal, une transcription, l'historique, la mémoire des sites ni un message envoyé à un écran.
- La carte n'est enregistrée sur le site que si la personne le demande, et seulement si le site le
  propose (case « enregistrer la carte ») : c'est le site qui la garde, pas Pilote.
- Les chiffres ne passent jamais par le modèle de H : l'agent clique dans un champ puis appelle l'outil
  fill_card_field ; Pilote tape lui-même la valeur dans le Chrome local (port de débogage 9222). L'agent ne
  reçoit que "ok". Limite : ce que la page affiche ensuite (souvent le numéro) reste visible sur les
  captures d'écran que l'agent regarde.
- Dictée : la transcription vocale (Hugging Face) entend les chiffres, et les personnes autour aussi.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

import httpx

CardField = Literal["number", "expiry", "expiry_month", "expiry_year", "cvc", "holder"]

_MONTHS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}  # fmt: skip
_LAST4 = re.compile(r"(?:fini\w*|termin\w*|se termin\w*)\s+(?:par\s+)?((?:\d\s*){4})\b", re.I)


@dataclass(frozen=True)
class SavedCard:
    """Carte déjà enregistrée dans le compte du site, désignée par ses 4 derniers chiffres."""

    last4: str


@dataclass(frozen=True)
class NewCard:
    """Carte donnée pour ce paiement seulement. Jamais affichée en entier (repr masqué)."""

    number: str = field(repr=False)
    expiry: str = field(repr=False)  # MMAA
    cvc: str = field(repr=False)
    holder: str | None = field(default=None, repr=False)

    @property
    def last4(self) -> str:
        return self.number[-4:]

    def __repr__(self) -> str:
        return f"NewCard(•••• {self.last4})"

    def value(self, name: CardField) -> str | None:
        return {
            "number": self.number,
            "expiry": f"{self.expiry[:2]}/{self.expiry[2:]}",
            "expiry_month": self.expiry[:2],
            "expiry_year": f"20{self.expiry[2:]}",
            "cvc": self.cvc,
            "holder": self.holder,
        }.get(name)


CardChoice = SavedCard | NewCard


# --- lecture de ce que la personne dit ou tape ---------------------------------------


_WORDS = {
    "zero": "0", "zéro": "0", "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4",
    "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9",
}  # fmt: skip


def digits(text: str) -> str:
    """Chiffres d'une phrase dictée : « 4111 1111 », « quatre un un un » ou un mélange des deux."""
    out = []
    for token in re.findall(r"\d+|[a-zA-Zéè]+", text.lower()):
        out.append(token if token.isdigit() else _WORDS.get(token, ""))
    return "".join(out)


def luhn_ok(number: str) -> bool:
    if not number.isdigit() or not 13 <= len(number) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def parse_number(text: str) -> str | None:
    number = digits(text)
    return number if luhn_ok(number) else None


def parse_expiry(text: str, today: dt.date | None = None) -> str | None:
    """« 03/27 », « mars 2027 », « zéro trois deux sept » -> « 0327 » ; None si illisible ou expirée."""
    today = today or dt.date.today()
    plain = text.lower()
    only = digits(text)
    month_named = any(name in plain for name in _MONTHS)
    if len(only) in (4, 6) and not month_named and not re.search(r"\d\s*[/\-. ]\s*\d", plain):
        plain = f"{only[:2]}/{only[2:]}"  # dicté chiffre par chiffre : MMAA ou MMAAAA
    month = year = None
    for name, number in _MONTHS.items():
        if name in plain:
            month = number
            found = re.search(r"\b(20\d{2}|\d{2})\b", plain)
            year = int(found.group(1)) if found else None
            break
    if month is None:
        found = re.search(r"\b(\d{1,2})\s*[/\-. ]\s*(20\d{2}|\d{2})\b", plain) or re.fullmatch(
            r"\s*(\d{2})(\d{2})\s*", plain
        )
        if found:
            month, year = int(found.group(1)), int(found.group(2))
    if month is None or year is None or not 1 <= month <= 12:
        return None
    year = year % 100
    if (2000 + year, month) < (today.year, today.month) or 2000 + year > today.year + 20:
        return None
    return f"{month:02d}{year:02d}"


def parse_cvc(text: str) -> str | None:
    value = digits(text)
    return value if len(value) in (3, 4) else None


def parse_last4(text: str) -> str | None:
    """« la carte qui finit par 1234 », « se termine par 12 34 », ou 4 chiffres seuls -> « 1234 »."""
    found = _LAST4.search(text)
    if found:
        return digits(found.group(1))
    only = digits(text)
    return only if len(only) == 4 and re.fullmatch(r"[\d\s.,]*", text.strip()) else None


# --- saisie dans le Chrome local ------------------------------------------------------


def _same_site(url: str, site: str) -> bool:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    want = (urlparse(site).hostname or site).removeprefix("www.")
    base = ".".join(want.split(".")[-2:])
    return bool(host) and (host == want or host.endswith("." + base) or host == base)


async def type_into_focused_field(text: str, site: str, port: int = 9222) -> None:
    """Tape `text` dans le champ qui a le focus, dans l'onglet du site, par le protocole de débogage.

    Input.insertText vise l'élément qui a le focus, y compris dans un cadre de paiement d'un autre
    domaine. La valeur ne transite que entre ce processus et le Chrome de cet ordinateur.
    """
    import websockets  # vient avec uvicorn[standard]

    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        targets = (await client.get(f"http://127.0.0.1:{port}/json")).json()
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    page = next((t for t in pages if _same_site(t.get("url", ""), site)), None)
    if page is None:
        raise RuntimeError("onglet du site introuvable dans le Chrome local")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Input.insertText", "params": {"text": text}}))
        while True:
            reply = json.loads(await ws.recv())
            if reply.get("id") == 1:
                if "error" in reply:
                    raise RuntimeError(f"saisie refusée par Chrome : {reply['error'].get('message')}")
                return
