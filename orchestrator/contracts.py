"""Modèles pydantic qui reflètent contracts/schemas/*.schema.json.

Les fichiers JSON de contracts/ font foi. Ce module en est la traduction Python,
et orchestrator/tests/test_contracts.py vérifie que les deux restent alignés.
Ne pas modifier sans PR sur contracts/ (membre 5).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
HHMM_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"

OrderId = Annotated[str, Field(pattern=UUID_PATTERN)]
Cents = Annotated[int, Field(ge=0)]
# URL lue telle quelle sur la page : pas de validation stricte (les faux sites mettent des | dans la query).
HttpUrlStr = Annotated[str, Field(pattern=r"^https?://")]
Category = Literal["train", "repas", "boutique"]

State = Literal[
    "listening",
    "understanding",
    "searching",
    "proposing",
    "cart",
    "confirm_1",
    "awaiting_relative",
    "recheck",
    "confirm_2",
    "paying",
    "done",
    "cancelled",
    "human_needed",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Intent -----------------------------------------------------------------


class When(_Strict):
    date: dt.date | None
    after: Annotated[str, Field(pattern=HHMM_PATTERN)] | None
    before: Annotated[str, Field(pattern=HHMM_PATTERN)] | None
    asap: bool


class Intent(_Strict):
    kind: Literal["new_request", "refine", "choose", "details", "confirm", "deny", "cancel", "other"]
    text: str
    category: Category | None
    object: str | None
    quantity: Annotated[int, Field(ge=1)] | None
    when: When
    budget_cents: Cents | None
    details: dict[str, str]
    constraints: list[str]
    choice_index: Annotated[int, Field(ge=1)] | None
    missing: list[str]
    question: str | None


# --- Option -----------------------------------------------------------------


class Option(_Strict):
    id: Annotated[str, Field(min_length=1)]
    rank: Annotated[int, Field(ge=1, le=8)]
    title: Annotated[str, Field(min_length=1)]
    price_cents: Cents
    currency: Literal["EUR"]
    rating: Annotated[float, Field(ge=0, le=5)] | None
    description: str | None
    conditions: str | None
    details: dict[str, str]


# --- OrderSummary -----------------------------------------------------------


class OrderItem(_Strict):
    name: Annotated[str, Field(min_length=1)]
    quantity: Annotated[int, Field(ge=1)]
    unit_price_cents: Cents | None
    total_cents: Cents
    options: list[str]


class Fee(_Strict):
    label: Annotated[str, Field(min_length=1)]
    amount_cents: Cents


class OrderSummary(_Strict):
    order_id: OrderId
    site: Annotated[str, Field(min_length=1)]
    page_url: HttpUrlStr
    items: Annotated[list[OrderItem], Field(min_length=1)]
    fees: list[Fee]
    total_cents: Cents
    currency: Literal["EUR"]
    when_label: str | None
    conditions: str | None
    payment_button_label: Annotated[str, Field(min_length=1)]
    hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    read_at: dt.datetime


# --- Approvals --------------------------------------------------------------


class Relative(_Strict):
    first_name: Annotated[str, Field(min_length=1)]
    phone: Annotated[str, Field(pattern=r"^\+[1-9][0-9]{6,14}$")]


class ApprovalRequest(_Strict):
    order_id: OrderId
    user_first_name: Annotated[str, Field(min_length=1)]
    site_name: Annotated[str, Field(min_length=1)]
    category: Category
    summary: OrderSummary
    relatives: Annotated[list[Relative], Field(min_length=1, max_length=3)]
    timeout_seconds: Annotated[int, Field(ge=10, le=300)]


class ApprovalStatus(_Strict):
    order_id: OrderId
    status: Literal["pending", "approved", "denied", "expired"]
    current_relative: Annotated[int, Field(ge=1, le=3)] | None
    relatives_count: Annotated[int, Field(ge=1, le=3)]
    decided_by: str | None
    decided_at: dt.datetime | None
    expires_at: dt.datetime | None
    updated_at: dt.datetime

    @property
    def is_final(self) -> bool:
        return self.status != "pending"


# --- SiteCard ---------------------------------------------------------------


class SiteCard(_Strict):
    domain: Annotated[str, Field(min_length=1)]
    steps: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=20)]
    useful_buttons: Annotated[list[Annotated[str, Field(max_length=80)]], Field(max_length=20)]
    pitfalls: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=20)]
    runs: Annotated[int, Field(ge=0)]
    successful_runs: Annotated[int, Field(ge=0)]
    avg_duration_s: Annotated[float, Field(ge=0)] | None
    avg_steps: Annotated[float, Field(ge=0)] | None
    updated_at: dt.datetime


# --- Messages WebSocket -----------------------------------------------------


class ClientAudio(_Strict):
    type: Literal["audio"]
    data: Annotated[str, Field(min_length=1)]
    mime: str


class ClientText(_Strict):
    type: Literal["text"]
    text: Annotated[str, Field(min_length=1)]


class ClientCancel(_Strict):
    type: Literal["cancel"]


ClientMessage = Annotated[ClientAudio | ClientText | ClientCancel, Field(discriminator="type")]


class ServerReady(_Strict):
    type: Literal["ready"] = "ready"
    session_id: Annotated[str, Field(min_length=1)]


class ServerState(_Strict):
    type: Literal["state"] = "state"
    state: State


class ServerSay(_Strict):
    type: Literal["say"] = "say"
    text: Annotated[str, Field(min_length=1)]
    audio: str | None = None
    mime: str | None = None


class ServerTranscript(_Strict):
    type: Literal["transcript"] = "transcript"
    role: Literal["user", "pilote"]
    text: str


class ServerIntent(_Strict):
    type: Literal["intent"] = "intent"
    intent: Intent


class ServerOptions(_Strict):
    type: Literal["options"] = "options"
    options: Annotated[list[Option], Field(max_length=8)]


class ServerSummary(_Strict):
    type: Literal["summary"] = "summary"
    summary: OrderSummary


class ServerApproval(_Strict):
    type: Literal["approval"] = "approval"
    status: ApprovalStatus


class ServerAgentView(_Strict):
    type: Literal["agent_view"] = "agent_view"
    agent_view_url: HttpUrlStr


class ServerError(_Strict):
    type: Literal["error"] = "error"
    code: Literal[
        "transcription_failed",
        "not_understood",
        "agent_failed",
        "approval_failed",
        "price_changed",
        "timeout",
        "internal",
    ]
    message: str


ServerMessage = Annotated[
    ServerReady
    | ServerState
    | ServerSay
    | ServerTranscript
    | ServerIntent
    | ServerOptions
    | ServerSummary
    | ServerApproval
    | ServerAgentView
    | ServerError,
    Field(discriminator="type"),
]


# --- Hash du récapitulatif --------------------------------------------------


def normalize_label(text: str) -> str:
    """Minuscules, sans accents, ponctuation remplacée par des espaces, espaces fusionnés."""
    decomposed = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^0-9a-z]+", " ", no_accents.lower())
    return cleaned.strip()


def summary_hash(items: list[OrderItem], total_cents: int) -> str:
    """Empreinte des articles, quantités et total. Voir contracts/README.md, section Hash.

    L'ordre des articles et la casse ou les accents des libellés ne changent pas le résultat.
    Un changement de quantité, d'option ou de total le change.
    """
    canonical_items = sorted(
        [normalize_label(item.name), sorted(normalize_label(o) for o in item.options), item.quantity]
        for item in items
    )
    payload = {"items": canonical_items, "total_cents": total_cents}
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()
