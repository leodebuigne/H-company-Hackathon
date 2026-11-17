"""Interfaces des briques branchées sur l'orchestrateur.

Chaque brique fournit une vraie version et une version factice (Fake...) qui respectent
ces Protocols. L'orchestrateur choisit avec USE_FAKE_AGENT, USE_FAKE_AI, USE_FAKE_APPROVALS.
Changer une signature ici = changer un contrat : issue GitHub, le membre 5 tranche.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, TypedDict

from orchestrator.contracts import (
    ApprovalRequest,
    ApprovalStatus,
    Intent,
    Option,
    OrderSummary,
    SiteCard,
)

ApprovalDecision = Literal["approved", "denied"]
PaymentResult = Literal["refused", "accepted", "unknown"]

# Appelé par l'outil H request_payment_approval. Ne répond qu'après la triple vérification.
# Toute erreur, tout délai dépassé ou tout écart donne "denied".
ApprovalCallback = Callable[[OrderSummary], Awaitable[ApprovalDecision]]

# Appelé par l'outil H need_human (CAPTCHA, cryptogramme, connexion). La session est en pause.
NeedHumanCallback = Callable[[str], Awaitable[None]]


class ShoppingAgent(Protocol):
    """Membre 1 : orchestrator/agent_h. Une instance = une session H = une commande."""

    @property
    def agent_view_url(self) -> str | None:
        """Lien vers la vue en direct de la session H, dès qu'il est connu."""
        ...

    async def start(self, intent: Intent, site_card: SiteCard | None) -> None: ...

    async def search(self) -> list[Option]:
        """8 options au maximum."""
        ...

    async def refine(self, message: str) -> list[Option]: ...

    async def choose(self, option_id: str) -> None: ...

    async def checkout(self) -> OrderSummary:
        """Panier puis page de paiement, sans cliquer sur le bouton final.
        L'agent crée order_id (UUID) ici : c'est la clé d'idempotence des outils."""
        ...

    async def recheck(self) -> OrderSummary:
        """Relit la page de paiement. Même order_id, hash recalculé."""
        ...

    async def pay(self) -> PaymentResult:
        """Après "approved" : clique sur le bouton de paiement et lit le résultat affiché."""
        ...

    async def cancel(self) -> None: ...


# Signature attendue pour construire l'agent (vrai ou factice).
AgentFactory = Callable[[ApprovalCallback, NeedHumanCallback], ShoppingAgent]


class HistoryTurn(TypedDict):
    role: Literal["user", "pilote"]
    text: str


class AI(Protocol):
    """Membre 2 : orchestrator/ai. Tout passe par Hugging Face avec HF_TOKEN."""

    async def transcribe(self, audio: bytes, mime: str) -> str:
        """L'appelant supprime l'audio juste après : ne le garder nulle part."""
        ...

    async def parse_intent(self, text: str, today: dt.date, history: list[HistoryTurn]) -> Intent: ...

    async def summarize_options(self, options: list[Option]) -> str:
        """3 options au maximum, environ 50 mots, finit en proposant les détails."""
        ...

    async def confirm_statement(self, summary: OrderSummary) -> str: ...

    async def describe_product(self, image: bytes, question: str) -> str: ...

    async def speak(self, text: str) -> bytes | None:
        """Audio prêt à jouer, ou None si trop lent : l'interface utilise alors la voix du navigateur."""
        ...


class Approvals(Protocol):
    """Client de l'API web/app/api/approvals (membre 3), côté orchestrateur (membre 5)."""

    async def create(self, request: ApprovalRequest) -> ApprovalStatus: ...

    async def get(self, order_id: str) -> ApprovalStatus: ...
