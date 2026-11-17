"""Interface commune à ShoppingAgent (vrai agent H) et FakeShoppingAgent (données inventées)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

from .models import Intent, Option, OrderSummary, PaymentResult, SiteCard

Decision = Literal["approved", "denied"]
# Appelé quand l'agent veut cliquer sur un bouton qui engage de l'argent.
# Facultatif : sans callback, l'agent paie pendant l'étape pay() et la banque fait la vérification.
ApprovalCallback = Callable[[OrderSummary], Awaitable[Decision]]
# Appelé en cas de CAPTCHA, cryptogramme, connexion… Renvoie "resolved" quand un humain
# a fait le geste, ou "abort" pour annuler la commande.
NeedHumanCallback = Callable[[str], Awaitable[Literal["resolved", "abort"]]]


class AgentError(RuntimeError):
    """La session H a échoué, expiré ou s'est bloquée."""


class NeedsHuman(AgentError):
    """L'agent s'est arrêté et demande un geste humain."""


class PaymentDenied(AgentError):
    """L'agent n'a pas eu l'autorisation de payer : rien n'a été cliqué."""


class ShoppingAgentProtocol(Protocol):
    order_id: str

    async def start(self, intent: Intent, site_card: SiteCard | None = None) -> None: ...
    async def search(self) -> list[Option]: ...
    async def refine(self, message: str) -> list[Option]: ...
    async def choose(self, option_id: str) -> None: ...
    async def checkout(self) -> OrderSummary: ...
    async def recheck(self) -> OrderSummary: ...
    async def pay(self) -> PaymentResult: ...
    async def cancel(self) -> None: ...
