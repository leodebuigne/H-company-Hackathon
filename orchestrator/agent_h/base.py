"""Interface commune à ShoppingAgent (vrai agent H) et FakeShoppingAgent (données inventées).

Les types viennent de orchestrator/ports.py (membre 5) : ne pas les redéfinir ici.
"""

from __future__ import annotations

from orchestrator.ports import (
    ApprovalCallback,
    ApprovalDecision,
    NeedHumanCallback,
    PaymentResult,
    ShoppingAgent,
)

# Nom historique de l'interface de l'agent.
ShoppingAgentProtocol = ShoppingAgent

__all__ = [
    "AgentError",
    "ApprovalCallback",
    "ApprovalDecision",
    "NeedHumanCallback",
    "NeedsHuman",
    "PaymentDenied",
    "PaymentResult",
    "ShoppingAgent",
    "ShoppingAgentProtocol",
]


class AgentError(RuntimeError):
    """La session H a échoué, expiré ou s'est bloquée."""


class NeedsHuman(AgentError):
    """L'agent s'est arrêté et demande un geste humain."""


class PaymentDenied(AgentError):
    """L'agent n'a pas eu l'autorisation de payer : rien n'a été cliqué."""
