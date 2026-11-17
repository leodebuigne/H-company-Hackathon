"""Tests sans réseau : hash, mémoire des sites, version factice, garde-fou de paiement."""

from __future__ import annotations

import pytest

from orchestrator.agent_h import FakeShoppingAgent, Intent, OrderItem, OrderSummary, PaymentDenied, summary_hash
from orchestrator.agent_h.agent import ShoppingAgent
from orchestrator.agent_h.models import SiteNotes
from orchestrator.agent_h.site_memory import InMemorySiteMemory, domain_of, merge_card, sanitize

PIZZA = Intent(site="ubereats.com", item="une pizza margherita", constraints=["livrée avant 20 h"])
TRAIN = Intent(site="https://www.sncf-connect.com", item="un train Paris Lille", date="2026-11-18")


def summary(total: float, name: str = "Pizza margherita", qty: int = 1) -> OrderSummary:
    return OrderSummary(items=[OrderItem(name=name, quantity=qty)], total_eur=total)


# --- hash ------------------------------------------------------------------------


def test_hash_ignores_case_spaces_and_order():
    a = OrderSummary(items=[OrderItem(name="Pizza  Margherita"), OrderItem(name="Coca", quantity=2)], total_eur=14)
    b = OrderSummary(items=[OrderItem(name="coca", quantity=2), OrderItem(name="pizza margherita")], total_eur=14.0)
    assert summary_hash(a) == summary_hash(b)


def test_hash_changes_with_price_or_quantity():
    base = summary_hash(summary(14.0))
    assert summary_hash(summary(14.01)) != base
    assert summary_hash(summary(14.0, qty=2)) != base


# --- mémoire des sites -----------------------------------------------------------


def test_sanitize_drops_personal_data():
    lines = ["Fermer le bandeau cookies", "Adresse : 12 rue de Lille", "leo@example.com", "Carte 4242424242424242"]
    assert sanitize(lines) == ["Fermer le bandeau cookies"]


def test_domain_of():
    assert domain_of("https://www.sncf-connect.com/app/home") == "sncf-connect.com"


def test_merge_card_counts_runs_and_average():
    first = merge_card(None, "ubereats.com", SiteNotes(steps=["Chercher le plat"], pitfalls=["Pop-up appli"]), 60)
    second = merge_card(first, "ubereats.com", SiteNotes(pitfalls=["Pop-up appli", "Bandeau cookies"]), 30)
    assert second.runs == 2 and second.avg_seconds == 45
    assert second.steps == ["Chercher le plat"]
    assert second.pitfalls == ["Pop-up appli", "Bandeau cookies"]


# --- version factice -------------------------------------------------------------


async def test_fake_full_flow_ends_accepted():
    agent = FakeShoppingAgent(speed=0)
    await agent.start(PIZZA)
    options = await agent.search()
    assert 1 <= len(options) <= 8
    await agent.choose(options[0].id)
    await agent.checkout()
    assert await agent.pay() == "accepted"  # pas de triple vérification : la banque valide


async def test_fake_callback_can_still_refuse():
    async def refuse(_: OrderSummary) -> str:
        return "denied"

    agent = FakeShoppingAgent(speed=0, approval_callback=refuse)
    await agent.start(TRAIN)
    await agent.choose((await agent.search())[0].id)
    await agent.checkout()
    with pytest.raises(PaymentDenied):
        await agent.pay()


# --- garde-fou de paiement du vrai agent (sans appeler H) ------------------------


def paying_agent(**kwargs) -> ShoppingAgent:
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False, **kwargs)  # type: ignore[arg-type]
    agent.order_id = "abc"
    return agent


async def test_gate_denies_outside_pay_step_and_approves_during_it():
    agent = paying_agent()
    s = summary(14.0)
    assert await agent._decide_payment(s) == "denied"  # recherche ou panier : jamais de paiement
    agent._paying = True
    assert await agent._decide_payment(s) == "approved"
    assert await agent._decide_payment(s) == "approved"  # appel répété : même réponse


async def test_real_gate_uses_orchestrator_callback():
    calls = []

    async def callback(summ: OrderSummary) -> str:
        calls.append(summ.order_id)
        return "approved"

    agent = paying_agent(approval_callback=callback)
    agent.order_id = "xyz"
    agent._paying = True
    assert await agent._decide_payment(summary(9.0)) == "approved"
    assert await agent._decide_payment(summary(9.0)) == "approved"
    assert calls == ["xyz"]  # appel répété : le callback n'est consulté qu'une fois


async def test_need_human_without_callback_aborts():
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    assert await agent._ask_human("CAPTCHA") == "abort"


async def test_payment_tool_accepts_raw_json_from_the_agent():
    agent = paying_agent()
    agent._paying = True
    pay_tool = {t.name: t for t in agent._tools()}["request_payment_approval"]
    raw = {"items": [{"name": "Pizza margherita", "quantity": 1}], "total_eur": 14.0}
    assert await pay_tool.fn(summary=raw) == "approved"
    assert await pay_tool.fn(summary="pas un récapitulatif") == "denied"


async def test_gate_refuses_above_ceiling_during_pay_step():
    agent = paying_agent(max_total_eur=30)
    agent._paying = True
    assert await agent._decide_payment(summary(42.0)) == "denied"
    assert await agent._decide_payment(OrderSummary(items=[OrderItem(name="Pizza")])) == "denied"


def test_default_ceiling_is_999(monkeypatch):
    monkeypatch.delenv("PILOTE_MAX_TOTAL_EUR", raising=False)
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    assert agent._max_total_eur == 999


def test_make_agent_is_real_by_default(monkeypatch):
    from orchestrator.agent_h import make_agent

    monkeypatch.delenv("USE_FAKE_AGENT", raising=False)
    assert isinstance(make_agent(), ShoppingAgent)
    monkeypatch.setenv("USE_FAKE_AGENT", "1")
    assert isinstance(make_agent(speed=0), FakeShoppingAgent)


def test_tools_declared_for_the_agent():
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    names = {t.name: t for t in agent._tools()}
    assert set(names) == {"request_payment_approval", "need_human"}
    assert "summary" in names["request_payment_approval"].input_schema["properties"]
