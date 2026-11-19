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

from orchestrator.contracts import Intent, Option, OrderSummary, SiteCard
from orchestrator.ports import PaymentResult

from .base import ApprovalCallback, NeedHumanCallback, NeedsHuman, PaymentDenied
from .models import (
    AgentFee,
    AgentOption,
    AgentOrderItem,
    AgentOrderSummary,
    OptionDetails,
    to_options,
    to_order_summary,
)
from .site_memory import domain_of

TRAIN_OPTIONS = [
    AgentOption(
        id="o1",
        title="TGV INOUI 14 h 12 → 15 h 15, direct",
        price_eur=42.0,
        conditions="Échangeable",
        details=OptionDetails(
            **{"departure": "14:12", "arrival": "15:15", "duration": "1 h 03", "via": "direct"}
        ),
    ),
    AgentOption(
        id="o2",
        title="TGV INOUI 14 h 46 → 15 h 49, direct",
        price_eur=38.0,
        conditions="Non remboursable",
        details=OptionDetails(
            **{"departure": "14:46", "arrival": "15:49", "duration": "1 h 03", "via": "direct"}
        ),
    ),
    AgentOption(
        id="o3",
        title="TER 15 h 05 → 17 h 22, 1 correspondance",
        price_eur=27.5,
        details=OptionDetails(
            **{"departure": "15:05", "arrival": "17:22", "duration": "2 h 17", "via": "1 correspondance"}
        ),
    ),
]
FOOD_OPTIONS = [
    AgentOption(
        id="o1",
        title="Pizza margherita, Pizzeria Napoli",
        price_eur=11.5,
        rating=4.6,
        details=OptionDetails(delivery="25-35 min"),
    ),
    AgentOption(
        id="o2",
        title="Pizza margherita, Luigi & Co",
        price_eur=12.9,
        rating=4.4,
        details=OptionDetails(delivery="20-30 min"),
    ),
    AgentOption(
        id="o3",
        title="Pizza margherita, Bella Italia",
        price_eur=10.0,
        rating=4.1,
        details=OptionDetails(delivery="40-50 min"),
    ),
]


class FakeShoppingAgent:
    """Mêmes sorties que ShoppingAgent (contrats communs). Sans callback, "pay" réussit : c'est un faux."""

    def __init__(
        self,
        *,
        approval_callback: ApprovalCallback | None = None,
        need_human_callback: NeedHumanCallback | None = None,
        price_change_on_recheck: bool = False,
        need_human_at: str | None = None,
        speed: float | None = None,
        needs_card: bool = False,
    ) -> None:
        logging.getLogger(__name__).warning("Agent FACTICE : aucune action sur un vrai site.")
        self.order_id = ""
        self.last_payment_message: str | None = None
        # Carte dictée : le site simulé n'a pas de carte enregistrée si needs_card
        self.on_card_needed = None  # posé par l'orchestrateur
        self._needs_card = needs_card
        self.card_used = None  # dernière carte « tapée » (tests), effacée comme dans le vrai agent
        self.last_card_saved: bool | None = None
        self.agent_view_url: str | None = None
        self._approval_callback = approval_callback
        self._need_human_callback = need_human_callback
        self._price_change = price_change_on_recheck
        self._need_human_at = need_human_at
        self._speed = float(os.getenv("PILOTE_FAKE_SPEED") or "1.0") if speed is None else speed
        self._intent: Intent | None = None
        self._options: list[Option] = []
        self._chosen: Option | None = None

    async def _wait(self, seconds: float, phase: str) -> None:
        await asyncio.sleep(seconds * self._speed)
        if self._need_human_at == phase:
            if self._need_human_callback is not None:
                await self._need_human_callback(f"CAPTCHA simulé pendant l'étape {phase}")
                return
            raise NeedsHuman(f"CAPTCHA simulé pendant l'étape {phase}")

    def _is_train(self) -> bool:
        assert self._intent is not None
        return self._intent.category == "train"

    async def start(self, intent: Intent, site_card: SiteCard | None = None) -> None:
        self._intent = intent
        self.order_id = ""
        self._chosen = None
        await self._wait(1.0, "start")

    async def ask(self, question: str) -> str:
        await self._wait(3, "question")
        return "D'après le site de la pharmacie, elle ferme à 20 heures ce soir. (Source : site officiel.)"

    async def search(self) -> list[Option]:
        await self._wait(6.0, "search")
        self._options = to_options(TRAIN_OPTIONS if self._is_train() else FOOD_OPTIONS)
        return self._options

    async def refine(self, message: str) -> list[Option]:
        await self._wait(4.0, "refine")
        cheapest_first = sorted(self._options, key=lambda o: o.price_cents)
        self._options = [o.model_copy(update={"rank": i}) for i, o in enumerate(cheapest_first, start=1)]
        return self._options

    async def choose(self, option_id: str) -> None:
        self._chosen = next((o for o in self._options if o.id == option_id), None)
        if self._chosen is None:
            raise ValueError(f"Option inconnue : {option_id}")

    def _summary(self, extra_eur: float = 0.0) -> OrderSummary:
        assert self._chosen is not None and self._intent is not None
        site = "www.sncf-connect.com" if self._is_train() else "www.ubereats.com"
        fee = 0.0 if self._is_train() else 2.5
        price = self._chosen.price_cents / 100 + extra_eur
        raw = AgentOrderSummary(
            items=[
                AgentOrderItem(name=self._chosen.title, quantity=1, unit_price_eur=price, total_eur=price)
            ],
            fees=[AgentFee(label="Frais de livraison", amount_eur=fee)] if fee else [],
            total_eur=round(price + fee, 2),
            page_url=f"https://{site}/paiement",
            when_label=self._chosen.details.get("delivery") or self._chosen.details.get("departure"),
            conditions="Billet non remboursable" if self._is_train() else None,
            payment_button_label="Payer",
        )
        return to_order_summary(raw, order_id=self.order_id, site=domain_of(site))

    async def checkout(self) -> OrderSummary:
        await self._wait(8.0, "checkout")
        if not self.order_id:
            self.order_id = str(uuid.uuid4())
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

    async def _use_dictated_card(self) -> None:
        """Comme le vrai agent : sans carte enregistrée, on fait dicter la carte, puis on l'oublie."""
        if not self._needs_card:
            return
        result = await self.on_card_needed("card") if self.on_card_needed else None
        if not result:
            raise PaymentDenied("carte non fournie")
        card, save = result
        self.card_used = card
        self.last_card_saved = bool(save)

    async def buy(self) -> PaymentResult:
        """Achat direct simulé : approbation demandée sur le récapitulatif du panier, puis « accepté »."""
        if not self.order_id:
            self.order_id = str(uuid.uuid4())
        summary = self._summary(extra_eur=8.0 if self._price_change else 0.0)
        decision = "approved"
        if self._approval_callback is not None:
            decision = await self._approval_callback(summary)
        if decision != "approved":
            raise PaymentDenied("Achat non approuvé : rien n'a été cliqué.")
        await self._use_dictated_card()
        await self._wait(4.0, "pay")
        self.last_payment_message = "Votre commande est confirmée."
        return "accepted"

    async def cancel(self) -> None:
        self._chosen = None
