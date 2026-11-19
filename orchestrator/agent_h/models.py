"""Ce que l'agent H lit sur les pages, et sa conversion vers les contrats communs.

L'agent H remplit `AgentAnswer` (prix en euros, aucun identifiant ni empreinte) : c'est plus fiable
pour un modèle que de lui faire produire des centimes, un UUID et un hash. Le code convertit ensuite
vers `orchestrator.contracts` (centimes entiers, `rank`, `order_id`, `read_at`, hash officiel).
Ce qui ne se convertit pas proprement (total illisible, article sans prix) lève `ValueError` : on ne
devine jamais un montant.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orchestrator.contracts import Fee, Option, OrderItem, OrderSummary, summary_hash
from orchestrator.ports import PaymentResult

MAX_OPTIONS = 8

# --- Ce que l'agent H renvoie ---------------------------------------------------------


class OptionDetails(BaseModel):
    """Détails d'une option. Champs connus pour les trains et les repas ; pour un produit, d'autres clés
    (color, size, dimensions…) sont acceptées : rejeter la réponse ferait perdre toute la boutique."""

    model_config = ConfigDict(extra="allow")

    departure: str | None = Field(default=None, description="Train : heure de départ, HH:MM")
    arrival: str | None = Field(default=None, description="Train : heure d'arrivée, HH:MM")
    duration: str | None = Field(default=None, description="Train : durée du trajet, ex. 1 h 04")
    via: str | None = Field(default=None, description="Train : direct ou correspondances")
    delivery: str | None = Field(default=None, description="Repas : délai ou heure de livraison")
    restaurant: str | None = Field(default=None, description="Repas : nom du restaurant")
    brand: str | None = Field(default=None, description="Produit : marque")
    seller: str | None = Field(default=None, description="Produit : vendeur")
    address: str | None = Field(default=None, description="Restaurant, lieu : quartier ou rue")
    slots: str | None = Field(default=None, description="Réservation : heures disponibles, ex. 19 h 30, 20 h")
    cuisine: str | None = Field(default=None, description="Restaurant : type de cuisine")
    avg_price: str | None = Field(default=None, description="Restaurant : prix moyen affiché, en texte")
    phone: str | None = Field(default=None, description="Restaurant, lieu : numéro de téléphone")
    booking: str | None = Field(default=None, description="« oui » si la réservation en ligne est possible")
    shop: str | None = Field(default=None, description="Achat en boutique : nom du site ou du vendeur")
    color: str | None = Field(default=None, description="Produit : couleur ou motif choisi")
    size: str | None = Field(default=None, description="Produit : taille, pointure ou dimensions")


class AgentOption(BaseModel):
    id: str = Field(description="Identifiant court : o1, o2, o3…")
    title: str
    price_eur: float | None = Field(default=None, description="Prix total en euros, tel qu'affiché")
    rating: float | None = Field(default=None, description="Note sur 5 si le site en affiche une")
    description: str | None = None
    conditions: str | None = Field(default=None, description="Conditions d'échange ou de remboursement")
    details: OptionDetails = Field(default_factory=OptionDetails)

    @field_validator("details", mode="before")
    @classmethod
    def _lenient_details(cls, value: object) -> object:
        """Texte libre ou valeurs non textuelles : on garde ce qui est lisible au lieu de tout rejeter."""
        if value is None:
            return {}
        if isinstance(value, str):
            return {"info": value[:200]} if value.strip() else {}
        if isinstance(value, dict):
            return {str(k): str(v)[:200] for k, v in value.items() if v not in (None, "", [], {})}
        return {}

    url: str | None = None

    @field_validator("details", mode="before")
    @classmethod
    def _empty_details(cls, value: object) -> object:
        """L'agent renvoie parfois « details: null » : c'est une fiche vide, pas une erreur (19/11)."""
        return {} if value is None else value


class AgentOrderItem(BaseModel):
    name: str
    quantity: int = 1
    unit_price_eur: float | None = None
    total_eur: float | None = Field(default=None, description="Total de la ligne en euros")
    options: list[str] = Field(default_factory=list, description="Options choisies : taille, classe…")


class AgentFee(BaseModel):
    label: str
    amount_eur: float | None = None


class AgentOrderSummary(BaseModel):
    items: list[AgentOrderItem] = Field(default_factory=list)
    fees: list[AgentFee] = Field(default_factory=list, description="Frais : livraison, service, réservation")
    total_eur: float | None = Field(default=None, description="Total à payer en euros, tel qu'affiché")
    page_url: str | None = Field(default=None, description="Adresse exacte de la page de paiement")
    when_label: str | None = Field(default=None, description="Date ou heure de livraison, de départ")
    conditions: str | None = Field(default=None, description="Conditions de remboursement si affichées")
    payment_button_label: str | None = Field(
        default=None, description="Texte exact du bouton qui engage l'argent"
    )


class SiteNotes(BaseModel):
    """Notes sur la façon d'utiliser le site. Jamais de donnée personnelle."""

    steps: list[str] = Field(default_factory=list, description="Étapes suivies, en termes génériques")
    pitfalls: list[str] = Field(default_factory=list, description="Pièges rencontrés : bandeaux, pop-ups")
    useful_buttons: list[str] = Field(default_factory=list, description="Libellés exacts des boutons utiles")


def parse_json_text(value: object) -> object:
    """« {\"items\": …} » (texte) -> dict. Tout autre valeur est rendue telle quelle."""
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def summary_from_cents(value: object) -> object:
    """Récapitulatif au format du contrat (centimes : total_cents…) -> format de l'agent (euros).

    L'agent remplit parfois le format du contrat ; sans cette conversion, le total paraissait
    illisible et le paiement était refusé à tort (mesuré le 2026-11-18).
    """
    if not isinstance(value, dict) or "total_eur" in value or "total_cents" not in value:
        return value

    def eur(cents: object) -> float | None:
        return None if cents is None else round(float(cents) / 100, 2)  # type: ignore[arg-type]

    converted = dict(value)
    converted["total_eur"] = eur(value.get("total_cents"))
    converted["items"] = [
        {
            **item,
            "unit_price_eur": eur(item.get("unit_price_cents")),
            "total_eur": eur(item.get("total_cents")),
        }
        for item in value.get("items") or []
        if isinstance(item, dict)
    ]
    converted["fees"] = [
        {**fee, "amount_eur": eur(fee.get("amount_cents"))}
        for fee in value.get("fees") or []
        if isinstance(fee, dict)
    ]
    return converted


class TipFeedback(BaseModel):
    id: str = Field(description="Identifiant [T…] d'une astuce de la mémoire du site que tu as essayée")
    worked: bool = Field(description="true si elle a mené au résultat attendu, false sinon")


class NewTip(BaseModel):
    text: str = Field(description="Chemin ou piège, général et précis, avec <ville>, <date>, <plat>…")
    kind: str = Field(default="étape", description="raccourci, étape ou piège")
    phase: str = Field(default="recherche", description="recherche ou achat")


class AgentAnswer(BaseModel):
    """Format unique de réponse de l'agent, quelle que soit la phase."""

    options: list[AgentOption] = Field(default_factory=list, description="Options trouvées, 8 au maximum")

    @field_validator("options", mode="before")
    @classmethod
    def _no_options(cls, value: object) -> object:
        # L'agent répond parfois options = null quand il n'a rien trouvé : c'est une liste vide
        return [] if value is None else value

    # Le modèle envoie parfois ces objets sous forme de texte JSON : on l'accepte au lieu de le rejeter
    # (sinon l'agent recommence sa réponse plusieurs fois, ou le paiement est refusé à tort).
    order_summary: AgentOrderSummary | str | None = Field(
        default=None, description="Récapitulatif exact de la page de paiement"
    )
    payment_result: PaymentResult | None = Field(
        default=None, description="Résultat affiché après le clic de paiement"
    )
    payment_message: str | None = Field(default=None, description="Message exact du site ou de la banque")
    blocked_reason: str | None = Field(default=None, description="Raison si tu n'as pas pu continuer")
    card_saved_on_site: bool | None = Field(
        default=None,
        description="Carte dictée : true si l'enregistrement sur le site est coché, sinon false",
    )
    site_notes: SiteNotes | str | None = None
    reply: str | None = Field(
        default=None, description="Réponse à une question : 1 à 3 phrases simples, à dire à voix haute"
    )
    reply_source: str | None = Field(default=None, description="Nom du site où la réponse a été trouvée")
    tips_feedback: list[TipFeedback] = Field(
        default_factory=list, description="Pour chaque astuce [T…] de la mémoire essayée : a-t-elle marché ?"
    )
    new_tips: list[NewTip] = Field(
        default_factory=list, description="Chemins plus rapides ou pièges découverts, absents de la mémoire"
    )

    @field_validator("tips_feedback", "new_tips", mode="before")
    @classmethod
    def _null_list(cls, value: object) -> object:
        return [] if value is None else value

    @field_validator("order_summary", "site_notes", mode="before")
    @classmethod
    def _json_text(cls, value: object) -> object:
        return summary_from_cents(parse_json_text(value))

    @field_validator("order_summary", mode="after")
    @classmethod
    def _summary_object(cls, value: object) -> object:
        return value if isinstance(value, AgentOrderSummary) else None

    @field_validator("site_notes", mode="after")
    @classmethod
    def _notes_object(cls, value: object) -> object:
        return value if isinstance(value, SiteNotes) else None


# --- Conversion vers les contrats -----------------------------------------------------


def cents(euros: float | None) -> int | None:
    """12,9 -> 1290. Passe par Decimal(str(...)) pour éviter 12.899999."""
    if euros is None or euros < 0:
        return None
    return int((Decimal(str(euros)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _http_url(value: str | None) -> str | None:
    return value if value and value.startswith(("http://", "https://")) else None


def to_options(options: list[AgentOption]) -> list[Option]:
    """Contrats `Option`, 8 au maximum, `rank` dans l'ordre de l'agent.

    Une option dont le prix n'est pas lisible est écartée : on n'annonce pas un prix inconnu.
    """
    converted: list[Option] = []
    seen: set[str] = set()
    for raw in options:
        price = cents(raw.price_eur)
        if price is None or not raw.title.strip() or not raw.id.strip() or raw.id in seen:
            continue
        seen.add(raw.id)
        rating = raw.rating if raw.rating is not None and 0 <= raw.rating <= 5 else None
        converted.append(
            Option(
                id=raw.id,
                rank=len(converted) + 1,
                title=raw.title.strip(),
                price_cents=price,
                currency="EUR",
                rating=rating,
                description=raw.description,
                conditions=raw.conditions,
                details={k: v for k, v in raw.details.model_dump().items() if v},
                url=_http_url(raw.url),
            )
        )
        if len(converted) == MAX_OPTIONS:
            break
    return converted


def to_order_summary(
    raw: AgentOrderSummary, *, order_id: str, site: str, now: dt.datetime | None = None
) -> OrderSummary:
    """Contrat `OrderSummary` avec le hash officiel. ValueError si un montant n'est pas lisible."""
    total = cents(raw.total_eur)
    if total is None:
        raise ValueError("total illisible")
    if not raw.items:
        raise ValueError("aucun article dans le récapitulatif")

    fees = [
        Fee(label=fee.label, amount_cents=amount)
        for fee in raw.fees
        if fee.label.strip() and (amount := cents(fee.amount_eur)) is not None
    ]
    items: list[OrderItem] = []
    for line in raw.items:
        quantity = max(1, line.quantity)
        unit = cents(line.unit_price_eur)
        line_total = cents(line.total_eur)
        if line_total is None and unit is not None:
            line_total = unit * quantity
        if line_total is None and len(raw.items) == 1:
            line_total = max(0, total - sum(fee.amount_cents for fee in fees))
        if line_total is None:
            raise ValueError(f"prix illisible pour « {line.name} »")
        items.append(
            OrderItem(
                name=line.name.strip(),
                quantity=quantity,
                unit_price_cents=unit,
                total_cents=line_total,
                options=[str(o) for o in line.options],
            )
        )

    return OrderSummary(
        order_id=order_id,
        site=site,
        page_url=_http_url(raw.page_url) or f"https://{site}",
        items=items,
        fees=fees,
        total_cents=total,
        currency="EUR",
        when_label=raw.when_label,
        conditions=raw.conditions,
        payment_button_label=(raw.payment_button_label or "").strip() or "Payer",
        hash=summary_hash(items, total),
        read_at=now or dt.datetime.now(dt.UTC),
    )
