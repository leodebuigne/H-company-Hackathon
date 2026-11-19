"""Interfaces des briques branchées sur l'orchestrateur.

Chaque brique fournit une vraie version et une version factice (Fake...) qui respectent
ces Protocols. L'orchestrateur choisit avec USE_FAKE_AGENT et USE_FAKE_AI.
Changer une signature ici = changer un contrat : issue GitHub, le membre 5 tranche.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol, TypedDict

from orchestrator.contracts import (
    Intent,
    Option,
    OrderSummary,
    SiteCard,
)

# "fix_cart" : ne pas payer encore ; le panier contient des articles que la personne n'a pas choisis
# (restes d'une commande précédente, quantité en trop), l'agent les retire puis redemande l'accord.
ApprovalDecision = Literal["approved", "denied", "fix_cart"]
PaymentResult = Literal["refused", "accepted", "unknown"]

# Appelé par l'outil H request_payment_approval. Ne répond "approved" que si le récapitulatif
# de la page est celui que la personne a accepté.
# Toute erreur, tout délai dépassé ou tout écart donne "denied".
ApprovalCallback = Callable[[OrderSummary], Awaitable[ApprovalDecision]]

# Appelé par l'outil H need_human (CAPTCHA, cryptogramme, connexion). Rend la main quand un humain
# a fait le geste ("resolved", ou None) ou quand il faut arrêter la commande ("abort").
NeedHumanDecision = Literal["resolved", "abort"]
NeedHumanCallback = Callable[[str], Awaitable[NeedHumanDecision | None]]


class ShoppingAgent(Protocol):
    """Membre 1 : orchestrator/agent_h. Une instance = une session H = une commande."""

    @property
    def agent_view_url(self) -> str | None:
        """Lien vers la vue en direct de la session H, dès qu'il est connu."""
        ...

    async def start(self, intent: Intent, site_card: SiteCard | None) -> None: ...

    async def ask(self, question: str) -> str:
        """Demande libre (Intent.kind = "question") : cherche la réponse sur le web, sans rien acheter,
        et renvoie 1 à 3 phrases à dire, avec la source."""
        ...

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
        """Appelé par l'orchestrateur seulement après le premier oui, la relecture et le deuxième oui.
        Avant de cliquer, l'agent appelle request_payment_approval : l'orchestrateur répond "approved"
        seulement si la page montre toujours le récapitulatif validé (même hash). Puis l'agent lit le
        résultat affiché. Lève PaymentDenied si rien n'a été cliqué."""
        ...

    async def cancel(self) -> None: ...


# Signature attendue pour construire l'agent (vrai ou factice).
AgentFactory = Callable[[ApprovalCallback, NeedHumanCallback], ShoppingAgent]


class PageReading(TypedDict):
    """Lecture d'une page par le modèle de vision : pour la personne, et pour l'agent."""

    description: str  # « La page montre la liste des trains ; le moins cher est à 29 euros. »
    hint: str  # « Clique sur le bouton bleu « Rechercher » en bas du formulaire. »


class HistoryTurn(TypedDict):
    role: Literal["user", "pilote"]
    text: str


class AI(Protocol):
    """Membre 2 : orchestrator/ai. Tout passe par Hugging Face avec HF_TOKEN."""

    async def transcribe(self, audio: bytes, mime: str) -> str:
        """L'appelant supprime l'audio juste après : ne le garder nulle part."""
        ...

    async def parse_intent(self, text: str, today: dt.date, history: list[HistoryTurn]) -> Intent: ...

    async def prepare_question(self, question: str, history: Any = None) -> dict[str, str]:
        """{"action": "search", "question": ...} ou {"action": "ask", "say": ...} (précision à demander)."""
        ...

    async def reply(
        self, *, situation: str, fallback: str, facts: str = "", heard: str = "", history: Any = None
    ) -> str:
        """Phrase de Pilote reformulée par le modèle de langage ; `fallback` si les faits ne sont pas sûrs."""
        ...

    async def summarize_options(self, options: list[Option]) -> str:
        """3 options au maximum, environ 50 mots, finit en proposant les détails."""
        ...

    async def confirm_statement(self, summary: OrderSummary) -> str: ...

    async def describe_product(self, image: bytes, question: str) -> str: ...

    async def read_page(self, image: bytes, goal: str) -> PageReading:
        """Lit une capture d'écran de l'agent (modèle de vision Hugging Face) : ce que montre la page,
        en mots simples pour la personne, et un conseil pour que l'agent avance vers `goal`."""
        ...

    async def speak(self, text: str) -> bytes | None:
        """Audio prêt à jouer, ou None si trop lent : l'interface utilise alors la voix du navigateur."""
        ...
