"""Agent H Company de Pilote (membre 1).

Usage côté orchestrateur :

    from orchestrator.agent_h import make_agent
    agent = make_agent()          # vrai agent H sur les vrais sites (par défaut)
    await agent.start(intent)
    options = await agent.search()
    await agent.choose(options[0].id)
    summary = await agent.checkout()   # page de paiement, rien n'est cliqué
    # ... l'utilisateur confirme qu'il veut payer ...
    result = await agent.pay()         # clic, puis validation dans l'application bancaire
"""

from __future__ import annotations

import os
from typing import Any

from .base import AgentError, NeedsHuman, PaymentDenied, ShoppingAgentProtocol
from .fake import FakeShoppingAgent
from .models import AgentAnswer, Intent, Option, OrderItem, OrderSummary, SiteCard, summary_hash


def make_agent(fake: bool | None = None, **kwargs: Any) -> ShoppingAgentProtocol:
    """Renvoie le vrai agent H, qui agit sur les vrais sites. C'est le comportement par défaut.

    La version factice n'est utilisée que si on la demande explicitement
    (fake=True ou USE_FAKE_AGENT=1) : tests automatiques, ou développement sans clé H.
    Elle n'est jamais utilisée pour la démo.
    """
    if fake is None:
        fake = os.getenv("USE_FAKE_AGENT") == "1"
    if fake:
        return FakeShoppingAgent(**kwargs)
    from .agent import ShoppingAgent  # importe le SDK H seulement si besoin

    return ShoppingAgent(**kwargs)


__all__ = [
    "AgentAnswer",
    "AgentError",
    "FakeShoppingAgent",
    "Intent",
    "NeedsHuman",
    "Option",
    "OrderItem",
    "OrderSummary",
    "PaymentDenied",
    "ShoppingAgentProtocol",
    "SiteCard",
    "make_agent",
    "summary_hash",
]
