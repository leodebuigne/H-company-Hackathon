"""FakeShoppingAgent : même interface que ShoppingAgent, données inventées. JAMAIS pour la démo.

La démo et les tests réels passent par ShoppingAgent (agent.py), qui agit sur les vrais
sites (Uber Eats, SNCF Connect). Cette version factice ne sert qu'aux tests automatiques
et aux membres qui développent sans clé H ; make_agent() ne la renvoie que si on la
demande explicitement (USE_FAKE_AGENT=1).
Variable PILOTE_FAKE_SPEED (par défaut 1.0) : 0 pour des tests instantanés.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Optional

from .base import ApprovalCallback, NeedsHuman, PaymentDenied
from .models import Intent, Option, OrderItem, OrderSummary, PaymentResult, SiteCard

TRAIN_OPTIONS = [
    Option(id="o1", title="TGV INOUI 14 h 12 → 15 h 15, direct", price_eur=42.0, details="Durée 1 h 03, échangeable"),
    Option(id="o2", title="TGV INOUI 14 h 46 → 15 h 49, direct", price_eur=38.0, details="Durée 1 h 03, non remboursable"),
    Option(id="o3", title="TER 15 h 05 → 17 h 22, 1 correspondance", price_eur=27.5, details="Durée 2 h 17"),
]
FOOD_OPTIONS = [
    Option(id="o1", title="Pizza margherita, Pizzeria Napoli", price_eur=11.5, rating=4.6, details="Livraison 25-35 min"),
    Option(id="o2", title="Pizza margherita, Luigi & Co", price_eur=12.9, rating=4.4, details="Livraison 20-30 min"),
    Option(id="o3", title="Pizza margherita, Bella Italia", price_eur=10.0, rating=4.1, details="Livraison 40-50 min"),
]


class FakeShoppingAgent:
    def __init__(
        self,
        *,
        approval_callback: Optional[ApprovalCallback] = None,
        price_change_on_recheck: bool = False,
        need_human_at: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> None:
        logging.getLogger(__name__).warning("Agent FACTICE : aucune action sur un vrai site.")
        self.order_id = ""
        self._approval_callback = approval_callback
        self._price_change = price_change_on_recheck
        self._need_human_at = need_human_at
        self._speed = float(os.getenv("PILOTE_FAKE_SPEED", "1.0")) if speed is None else speed
        self._intent: Optional[Intent] = None
        self._options: list[Option] = []
        self._chosen: Optional[Option] = None

    async def _wait(self, seconds: float, phase: str) -> None:
        await asyncio.sleep(seconds * self._speed)
        if self._need_human_at == phase:
            raise NeedsHuman(f"CAPTCHA simulé pendant l'étape {phase}")

    def _is_train(self) -> bool:
        assert self._intent is not None
        return "sncf" in self._intent.site.lower() or "train" in self._intent.item.lower()

    async def start(self, intent: Intent, site_card: Optional[SiteCard] = None) -> None:
        self._intent = intent
        self.order_id = uuid.uuid4().hex[:12]
        await self._wait(1.0, "start")

    async def search(self) -> list[Option]:
        await self._wait(6.0, "search")
        self._options = list(TRAIN_OPTIONS if self._is_train() else FOOD_OPTIONS)
        return self._options

    async def refine(self, message: str) -> list[Option]:
        await self._wait(4.0, "refine")
        self._options = sorted(self._options, key=lambda o: o.price_eur or 0)
        return self._options

    async def choose(self, option_id: str) -> None:
        self._chosen = next((o for o in self._options if o.id == option_id), None)
        if self._chosen is None:
            raise ValueError(f"Option inconnue : {option_id}")

    def _summary(self, extra_eur: float = 0.0) -> OrderSummary:
        assert self._chosen is not None and self._intent is not None
        fees = 0.0 if self._is_train() else 2.5
        price = (self._chosen.price_eur or 0.0) + extra_eur
        return OrderSummary(
            order_id=self.order_id,
            site=self._intent.site,
            items=[OrderItem(name=self._chosen.title, quantity=1, price_eur=price)],
            fees_eur=fees,
            total_eur=round(price + fees, 2),
            delivery=self._chosen.details,
            refund_terms="Billet non remboursable" if self._is_train() else None,
        ).with_hash()

    async def checkout(self) -> OrderSummary:
        await self._wait(8.0, "checkout")
        return self._summary()

    async def recheck(self) -> OrderSummary:
        await self._wait(2.0, "recheck")
        return self._summary(extra_eur=8.0 if self._price_change else 0.0)

    async def pay(self) -> PaymentResult:
        summary = await self.recheck()
        decision = "approved"
        if self._approval_callback is not None:
            decision = await self._approval_callback(summary)
        if decision != "approved":
            raise PaymentDenied("Paiement non approuvé : rien n'a été cliqué.")
        await self._wait(4.0, "pay")  # le temps de valider dans l'application bancaire
        return "accepted"  # simulation : aucune commande réelle

    async def cancel(self) -> None:
        self._chosen = None
