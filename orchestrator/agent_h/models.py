"""Objets échangés par l'agent H.

Copie provisoire du contrat (Intent, Option, OrderSummary, SiteCard) en attendant
que le membre 5 publie contracts/. Dès que les schémas JSON existent, ces modèles
doivent les suivre champ pour champ : ne pas les faire diverger ici.
"""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field

PaymentResult = Literal["refused", "accepted", "unknown"]


class Intent(BaseModel):
    site: str = Field(description="Site visé, par exemple ubereats.com ou sncf-connect.com")
    item: str = Field(description="Ce que l'utilisateur veut : plat, trajet, produit")
    constraints: list[str] = Field(default_factory=list)
    date: str | None = None
    budget_max_eur: float | None = None
    missing: list[str] = Field(default_factory=list)


class Option(BaseModel):
    id: str
    title: str
    price_eur: float | None = None
    rating: float | None = None
    details: str = ""
    url: str | None = None


class OrderItem(BaseModel):
    name: str
    quantity: int = 1
    price_eur: float | None = None


class OrderSummary(BaseModel):
    order_id: str = ""
    site: str = ""
    items: list[OrderItem] = Field(default_factory=list)
    fees_eur: float | None = None
    total_eur: float | None = None
    delivery: str | None = None
    refund_terms: str | None = None
    hash: str = ""

    def with_hash(self) -> OrderSummary:
        return self.model_copy(update={"hash": summary_hash(self)})


class SiteCard(BaseModel):
    domain: str
    steps: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    avg_seconds: float = 0.0
    runs: int = 0


def _cents(value: float | None) -> str:
    if value is None:
        return "none"
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def summary_hash(summary: OrderSummary) -> str:
    """Empreinte du récapitulatif : articles + quantités + total, normalisés.

    Deux lectures de la même page donnent le même hash ; un prix ou une quantité
    qui change donne un hash différent.
    """
    items = sorted((" ".join(item.name.lower().split()), item.quantity) for item in summary.items)
    payload = json.dumps({"items": items, "total": _cents(summary.total_eur)}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --- Réponses structurées demandées à l'agent H ---------------------------------


class SiteNotes(BaseModel):
    """Notes sur la façon d'utiliser le site. Jamais de donnée personnelle."""

    steps: list[str] = Field(default_factory=list, description="Étapes suivies, en termes génériques")
    pitfalls: list[str] = Field(default_factory=list, description="Pièges rencontrés : bandeaux, pop-ups")


class AgentAnswer(BaseModel):
    """Format unique de réponse de l'agent, quelle que soit la phase."""

    options: list[Option] = Field(default_factory=list, description="Options trouvées, 8 au maximum")
    order_summary: OrderSummary | None = Field(
        default=None, description="Récapitulatif exact de la page de paiement"
    )
    payment_result: PaymentResult | None = Field(
        default=None, description="Résultat affiché après le clic de paiement"
    )
    payment_message: str | None = Field(default=None, description="Message exact du site ou de la banque")
    blocked_reason: str | None = Field(default=None, description="Raison si tu n'as pas pu continuer")
    site_notes: SiteNotes | None = None
