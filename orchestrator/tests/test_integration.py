"""Les briques branchées ensemble : IA (partie 2) -> agent H (partie 1), à travers les contrats communs.

Aucun réseau : FakeAI ou HFAI avec un faux client, et l'agent factice. Ce test garde la fusion honnête :
si une brique change de format sans passer par contracts/, il casse ici.
"""

import datetime as dt
import json
from types import SimpleNamespace

from orchestrator.agent_h import make_agent_factory
from orchestrator.ai import HFAI, FakeAI
from orchestrator.contracts import OrderSummary
from orchestrator.ports import AI, ShoppingAgent

TODAY = dt.date(2026, 11, 18)


async def run_order(ai: AI, sentence: str) -> tuple[list[str], str]:
    """Phrase -> intention -> recherche -> résumé oral -> panier -> confirmation -> paiement."""
    approvals: list[OrderSummary] = []

    async def approval(summary: OrderSummary) -> str:
        approvals.append(summary)
        return "approved"

    async def need_human(reason: str) -> None:
        raise AssertionError(f"aide humaine inattendue : {reason}")

    intent = await ai.parse_intent(sentence, TODAY, [])
    assert intent.kind == "new_request" and intent.missing == []

    agent: ShoppingAgent = make_agent_factory(fake=True, speed=0)(approval, need_human)
    await agent.start(intent, None)
    options = await agent.search()
    spoken_options = await ai.summarize_options(options)
    await agent.choose(options[0].id)
    summary = await agent.checkout()
    spoken_summary = await ai.confirm_statement(summary)

    assert await agent.pay() == "accepted"
    assert [a.order_id for a in approvals] == [summary.order_id]  # l'orchestrateur a été consulté
    return [spoken_options, spoken_summary], summary.order_id


async def test_fake_ai_to_agent_meal():
    (options, statement), _ = await run_order(FakeAI(), "Une pizza margherita grande taille avant 20 h")
    assert "Numéro 1 : Pizza margherita" in options and options.endswith("« les détails du 1 ».")
    assert (
        statement.startswith("J'ai mis dans le panier 1 Pizza margherita") and "total 14 euros" in statement
    )


async def test_hf_ai_to_agent_train():
    """HFAI (modèle simulé) comprend la phrase, l'agent la traite : mêmes objets des deux côtés."""
    answer = json.dumps(
        {
            "kind": "new_request",
            "category": "train",
            "quantity": 1,
            "when": {"date": "2026-11-19", "after": "14:00", "before": None, "asap": False},
            "details": {"origin": "Paris", "destination": "Lille"},
        }
    )

    async def create(**_):
        message = SimpleNamespace(content=answer)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)

    chat = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    ai = HFAI(token="test", chat_client=chat, speech_client=object())
    (options, statement), _ = await run_order(ai, "Un train Paris Lille demain après 14 h")
    assert "TGV INOUI" in options and "42 euros" in options
    assert "total 42 euros" in statement and "Billet non remboursable" in statement
