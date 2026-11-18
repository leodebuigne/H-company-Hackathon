"""Version factice de l'IA : mêmes méthodes que `AI` (orchestrator/ports.py), sans réseau ni HF_TOKEN.

Sert à brancher l'orchestrateur et l'interface dès le jour 1 (USE_FAKE_AI=1). Les réponses sont
inventées mais valides : `parse_intent` reconnaît quelques mots-clés, pas le français en général.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import unicodedata

from orchestrator.ai.speech_text import options_summary, order_statement
from orchestrator.contracts import Intent, Option, OrderSummary, When
from orchestrator.ports import HistoryTurn

FAKE_TRANSCRIPT = "Un train pour Lille demain après 14 h"

_ORDINALS = {"premiere": 1, "premier": 1, "deuxieme": 2, "second": 2, "seconde": 2, "troisieme": 3}
_WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_CITIES = ["Paris", "Lyon", "Lille", "Marseille", "Bordeaux", "Toulouse", "Nantes", "Strasbourg"]
_MEALS = ["pizza", "sushi", "poke", "burger", "smash", "frites", "pad thai"]


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _empty_intent(kind: str, text: str) -> Intent:
    return Intent(
        kind=kind,  # type: ignore[arg-type]
        text=text,
        category=None,
        object=None,
        quantity=None,
        when=When(date=None, after=None, before=None, asap=False),
        budget_cents=None,
        details={},
        constraints=[],
        choice_index=None,
        missing=[],
        question=None,
    )


_QUESTION = re.compile(
    r"\?\s*$|^(quel|quelle|quels|quelles|combien|est-ce|a quelle heure|ou se trouve|cherche"
    r"|trouve-moi|dis-moi)\b"
)


class FakeAI:
    """Réponses déterministes. `delay` simule la latence d'un vrai modèle (secondes)."""

    def __init__(self, delay: float = 0.0, transcript: str = FAKE_TRANSCRIPT) -> None:
        self.delay = delay
        self.transcript = transcript

    async def _wait(self) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)

    async def transcribe(self, audio: bytes, mime: str) -> str:
        await self._wait()
        return self.transcript

    async def parse_intent(self, text: str, today: dt.date, history: list[HistoryTurn]) -> Intent:
        await self._wait()
        plain = _plain(text)

        if "annule" in plain:
            return _empty_intent("cancel", text)
        if re.match(r"^(non|pas celle)", plain.strip()):
            return _empty_intent("deny", text)
        if re.match(r"^(oui|ok|d'accord|c'est bon)", plain.strip()):
            return _empty_intent("confirm", text)
        for word, index in _ORDINALS.items():
            if word in plain:
                intent = _empty_intent("details" if "detail" in plain else "choose", text)
                intent.choice_index = index
                return intent

        if _QUESTION.search(plain) and "acheter" not in plain and "commande" not in plain:
            return _empty_intent("question", text)

        category = "train" if "train" in plain or "billet" in plain else None
        if category is None and any(meal in plain for meal in _MEALS):
            category = "repas"
        if category is None:
            intent = _empty_intent("new_request" if "acheter" in plain else "other", text)
            if intent.kind == "new_request":
                intent.missing = ["category", "object"]
                intent.question = "Qu'est-ce que vous voulez acheter ?"
            return intent

        intent = _empty_intent("new_request", text)
        intent.category = category  # type: ignore[assignment]
        intent.quantity = 1
        self._fill_when(intent, plain, today)
        if category == "train":
            self._fill_train(intent, text, plain)
        else:
            self._fill_meal(intent, plain)
        if intent.missing:
            intent.question = "Pouvez-vous préciser : " + ", ".join(intent.missing) + " ?"
        return intent

    @staticmethod
    def _fill_when(intent: Intent, plain: str, today: dt.date) -> None:
        if "demain" in plain:
            intent.when.date = today + dt.timedelta(days=1)
        elif "ce soir" in plain or "avant 20" in plain or intent.category == "repas":
            intent.when.date = today
        for i, name in enumerate(_WEEKDAYS):
            if name in plain:
                intent.when.date = today + dt.timedelta(days=(i - today.weekday()) % 7 or 7)
        if "le plus vite" in plain:
            intent.when.asap = True
        if "matin" in plain:
            intent.when.before = "12:00"
        if "ce soir" in plain:
            intent.when.after = "18:00"
        match = re.search(r"(apres|a partir de)\s+(\d{1,2})\s*h", plain)
        if match:
            intent.when.after = f"{int(match.group(2)):02d}:00"
        match = re.search(r"avant\s+(\d{1,2})\s*h", plain)
        if match:
            intent.when.before = f"{int(match.group(1)):02d}:00"

    @staticmethod
    def _fill_train(intent: Intent, text: str, plain: str) -> None:
        cities = sorted((text.find(c), c) for c in _CITIES if c in text)
        names = [c for _, c in cities]
        if len(names) >= 2:
            intent.details = {"origin": names[0], "destination": names[1]}
        elif names:
            intent.details = {"destination": names[0]}
        if "direct" in plain:
            intent.constraints.append("direct")
        if "echangeable" in plain:
            intent.constraints.append("échangeable")
        if "origin" not in intent.details:
            intent.missing.append("details.origin")
        if "destination" not in intent.details:
            intent.missing.append("details.destination")
        if intent.when.date is None:
            intent.missing.append("when.date")

    @staticmethod
    def _fill_meal(intent: Intent, plain: str) -> None:
        for meal in _MEALS:
            if meal in plain:
                intent.object = meal
                break
        if intent.object is None:
            intent.missing.append("object")

    async def summarize_options(self, options: list[Option]) -> str:
        await self._wait()
        return options_summary(options)

    async def confirm_statement(self, summary: OrderSummary) -> str:
        await self._wait()
        return order_statement(summary)

    async def describe_product(self, image: bytes, question: str) -> str:
        await self._wait()
        return "Je vois un produit de couleur claire, au contour net. Les avis sont plutôt positifs."

    async def speak(self, text: str) -> bytes | None:
        await self._wait()
        return None
