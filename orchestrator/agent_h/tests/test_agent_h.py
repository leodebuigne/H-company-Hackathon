"""Tests sans réseau : contrats, mémoire des sites, version factice, garde-fou de paiement."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from orchestrator.agent_h import (
    AgentError,
    FakeShoppingAgent,
    Intent,
    NeedsHuman,
    OrderSummary,
    PaymentDenied,
    SiteCard,
    make_agent,
    make_agent_factory,
    summary_hash,
)
from orchestrator.agent_h.agent import ShoppingAgent, site_for
from orchestrator.agent_h.models import (
    AgentFee,
    AgentOption,
    AgentOrderItem,
    AgentOrderSummary,
    SiteNotes,
    cents,
    to_options,
    to_order_summary,
)
from orchestrator.agent_h.prompts import intent_text, site_card_text
from orchestrator.agent_h.site_memory import InMemorySiteMemory, domain_of, merge_card, sanitize
from orchestrator.contracts import OrderItem
from orchestrator.ports import ShoppingAgent as ShoppingAgentPort

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
ORDER_ID = "7c0f3c2a-5b1e-4d7a-9a3b-1f2e3d4c5b6a"


def _example(name: str) -> Intent:
    return Intent.model_validate(json.loads((CONTRACTS / "examples" / "valid" / name).read_text("utf-8")))


PIZZA = _example("intent-repas.json")
TRAIN = _example("intent-train-missing-origin.json")


def _validator(schema_file: str) -> Draft202012Validator:
    schemas = {p.name: json.loads(p.read_text("utf-8")) for p in (CONTRACTS / "schemas").glob("*.json")}
    registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in schemas.values()])
    return Draft202012Validator(schemas[schema_file], registry=registry, format_checker=FormatChecker())


def raw_summary(total: float = 14.0, name: str = "Pizza margherita", qty: int = 1) -> AgentOrderSummary:
    return AgentOrderSummary(items=[AgentOrderItem(name=name, quantity=qty)], total_eur=total)


def contract_summary(total: float = 14.0, name: str = "Pizza margherita", qty: int = 1) -> OrderSummary:
    return to_order_summary(raw_summary(total, name, qty), order_id=ORDER_ID, site="www.ubereats.com")


# --- conversion vers les contrats --------------------------------------------------


def test_cents_avoids_float_noise():
    assert cents(12.9) == 1290
    assert cents(0.1 + 0.2) == 30
    assert cents(14.505) == 1451  # arrondi commercial
    assert cents(None) is None and cents(-1.0) is None


def test_to_options_ranks_drops_unpriced_and_caps_at_eight():
    raw = [AgentOption(id=f"o{i}", title=f"Option {i}", price_eur=10.0 + i) for i in range(1, 12)]
    raw[1] = AgentOption(id="o2", title="Sans prix", price_eur=None)
    options = to_options(raw)
    assert len(options) == 8
    assert [o.rank for o in options] == list(range(1, 9))
    assert "o2" not in {o.id for o in options}
    assert options[0].price_cents == 1100 and options[0].currency == "EUR"


def test_to_options_cleans_rating_url_and_duplicates():
    options = to_options(
        [
            AgentOption(id="o1", title="A", price_eur=5, rating=9.0, url="ftp://x"),
            AgentOption(id="o1", title="Doublon", price_eur=5),
            AgentOption(id="o2", title="B", price_eur=6, rating=4.5, url="https://shop.test/b"),
        ]
    )
    assert [o.id for o in options] == ["o1", "o2"]
    assert options[0].rating is None and options[0].url is None
    assert options[1].rating == 4.5 and options[1].url == "https://shop.test/b"


def test_to_order_summary_matches_official_hash_and_schema():
    raw = AgentOrderSummary(
        items=[AgentOrderItem(name="Pizza margherita", quantity=2, unit_price_eur=11.5, options=["Grande"])],
        fees=[AgentFee(label="Livraison", amount_eur=2.5), AgentFee(label="Inconnu", amount_eur=None)],
        total_eur=25.5,
        page_url="https://www.ubereats.com/fr/checkout",
        when_label="Avant 20 h",
        payment_button_label="Commander",
    )
    s = to_order_summary(raw, order_id=ORDER_ID, site="www.ubereats.com")
    assert s.total_cents == 2550 and s.items[0].total_cents == 2300
    assert [(f.label, f.amount_cents) for f in s.fees] == [("Livraison", 250)]
    assert s.hash == summary_hash(s.items, s.total_cents)
    _validator("order-summary.schema.json").validate(json.loads(s.model_dump_json()))


def test_single_item_without_line_price_takes_total_minus_fees():
    raw = AgentOrderSummary(
        items=[AgentOrderItem(name="Billet")], fees=[AgentFee(label="Frais", amount_eur=3)], total_eur=45
    )
    assert to_order_summary(raw, order_id=ORDER_ID, site="x.test").items[0].total_cents == 4200


@pytest.mark.parametrize(
    "raw",
    [
        AgentOrderSummary(items=[AgentOrderItem(name="A", total_eur=1)], total_eur=None),
        AgentOrderSummary(items=[], total_eur=10),
        AgentOrderSummary(items=[AgentOrderItem(name="A"), AgentOrderItem(name="B")], total_eur=10),
    ],
    ids=["total illisible", "aucun article", "prix de ligne illisible"],
)
def test_unreadable_amounts_are_refused_not_guessed(raw):
    with pytest.raises(ValueError):
        to_order_summary(raw, order_id=ORDER_ID, site="x.test")


def test_page_url_and_button_fall_back_when_missing():
    s = contract_summary()
    assert s.page_url == "https://www.ubereats.com" and s.payment_button_label == "Payer"


def test_hash_ignores_case_spaces_and_order_but_not_price_or_quantity():
    a = [OrderItem(name="Pizza  Margherita", quantity=1, unit_price_cents=None, total_cents=1, options=[])]
    b = [OrderItem(name="pizza margherita", quantity=1, unit_price_cents=None, total_cents=1, options=[])]
    assert summary_hash(a, 1400) == summary_hash(b, 1400)
    assert summary_hash(a, 1401) != summary_hash(a, 1400)
    assert contract_summary(14.0).hash != contract_summary(14.0, qty=2).hash


# --- mémoire des sites -------------------------------------------------------------


def test_sanitize_drops_personal_data():
    lines = [
        "Fermer le bandeau cookies",
        "Adresse : 12 rue de Lille",
        "leo@example.com",
        "Carte 4242424242424242",
    ]
    assert sanitize(lines) == ["Fermer le bandeau cookies"]


def test_domain_matches_docs_sites():
    assert domain_of("https://www.sncf-connect.com/app/home") == "www.sncf-connect.com"
    assert domain_of("https://www.ubereats.com/fr") == "www.ubereats.com"


def test_merge_card_follows_the_site_card_contract():
    now = dt.datetime(2026, 11, 17, 18, 0, tzinfo=dt.UTC)
    first = merge_card(
        None,
        "www.ubereats.com",
        SiteNotes(steps=["Chercher le plat"], pitfalls=["Pop-up appli"], useful_buttons=["Voir le panier"]),
        60,
        steps=10,
        now=now,
    )
    second = merge_card(
        first, "www.ubereats.com", SiteNotes(pitfalls=["Pop-up appli", "Bandeau cookies"]), 30, steps=20
    )
    assert (second.runs, second.successful_runs) == (2, 2)
    assert second.avg_duration_s == 45 and second.avg_steps == 15
    assert second.steps == ["Chercher le plat"] and second.useful_buttons == ["Voir le panier"]
    assert second.pitfalls == ["Pop-up appli", "Bandeau cookies"]
    _validator("site-card.schema.json").validate(json.loads(second.model_dump_json()))


def test_site_card_text_lists_steps_buttons_and_pitfalls():
    card = merge_card(None, "x.test", SiteNotes(steps=["a"], pitfalls=["b"], useful_buttons=["c"]), 1)
    text = site_card_text(card)
    assert "Étape connue : a" in text and "Bouton utile : c" in text and "Piège connu : b" in text
    assert "première visite" in site_card_text(None)


# --- demande de l'utilisateur ------------------------------------------------------


def test_site_for_uses_category_and_env_override(monkeypatch):
    monkeypatch.delenv("PILOTE_SITE_REPAS", raising=False)
    assert "ubereats" in site_for(PIZZA) and "sncf-connect" in site_for(TRAIN)
    monkeypatch.setenv("PILOTE_SITE_REPAS", "https://faux-repas.test")
    assert site_for(PIZZA) == "https://faux-repas.test"


def test_site_for_refuses_unknown_category():
    with pytest.raises(AgentError):
        site_for(PIZZA.model_copy(update={"category": None}))


# --- recherche rapide généralisée et boutiques -----------------------------------------


def _shop(**kw):
    base = {
        "category": "boutique",
        "object": "abat-jour style moderne",
        "budget_cents": 300000,
        "constraints": [],
    }
    base.update(kw)
    return PIZZA.model_copy(update={**base, "details": {}, "text": kw.get("text", "abat-jour moderne")})


def test_shopping_goes_to_amazon_by_default_or_to_the_shop_named(monkeypatch):
    from orchestrator.agent_h.agent import start_url_for

    monkeypatch.delenv("PILOTE_SITE_BOUTIQUE", raising=False)
    lamp = _shop()
    assert site_for(lamp) == "https://www.amazon.fr"
    assert start_url_for(lamp, site_for(lamp)) == "https://www.amazon.fr/s?k=abat-jour+style+moderne"
    assert site_for(_shop(text="un livre chez la Fnac", object="livre")) == "https://www.fnac.com"
    assert site_for(_shop(constraints=["sur Leroy-Merlin"])) == "https://www.leroymerlin.fr"
    monkeypatch.setenv("PILOTE_SITE_BOUTIQUE", "https://www.darty.com")
    assert site_for(lamp) == "https://www.darty.com"


def test_search_text_has_the_object_and_criteria_but_never_the_budget_or_shop():
    from orchestrator.agent_h.shops import search_query

    casque = _shop(
        object="casque sans fil", constraints=["réduction de bruit", "sur amazon", "moins de 200 €"]
    )
    assert search_query(casque) == "casque sans fil réduction de bruit"
    train = TRAIN.model_copy(
        update={
            "details": {"origin": "Paris", "destination": "Lille"},
            "when": TRAIN.when.model_copy(update={"date": dt.date(2026, 11, 19), "after": "14:00"}),
        }
    )
    assert search_query(train) == "Paris Lille 19 novembre 14h"


def test_the_agent_is_told_to_search_in_one_go_and_filter_the_budget():
    from orchestrator.agent_h.prompts import generic_instructions

    rules = generic_instructions()
    assert "Recherche rapide (tous les sites)" in rules and "filtre de prix" in rules
    text = intent_text(_shop(), "https://www.amazon.fr")
    assert "Texte de recherche : « abat-jour style moderne »" in text
    assert "3000,00 €" in text and "jamais dans la barre de recherche" in text


def test_intent_text_describes_the_contract_intent():
    text = intent_text(PIZZA, "https://www.ubereats.com/fr")
    assert "repas pizza margherita" in text and "avant 20:00" in text and "20,00 €" in text
    assert "size : grande" in text


# --- version factice ---------------------------------------------------------------


async def test_fake_full_flow_returns_valid_contract_objects():
    agent = FakeShoppingAgent(speed=0)
    await agent.start(PIZZA)
    options = await agent.search()
    assert 1 <= len(options) <= 8
    for option in options:
        _validator("option.schema.json").validate(json.loads(option.model_dump_json()))
    await agent.choose(options[0].id)
    checkout = await agent.checkout()
    _validator("order-summary.schema.json").validate(json.loads(checkout.model_dump_json()))
    assert checkout.order_id == agent.order_id
    assert (await agent.recheck()).order_id == checkout.order_id  # recheck conserve l'order_id
    assert await agent.pay() == "accepted"


async def test_fake_price_change_is_visible_in_the_hash():
    agent = FakeShoppingAgent(speed=0, price_change_on_recheck=True)
    await agent.start(TRAIN)
    await agent.choose((await agent.search())[0].id)
    first, second = await agent.checkout(), await agent.recheck()
    assert first.hash != second.hash and second.total_cents == first.total_cents + 800


async def test_fake_callback_can_refuse():
    async def refuse(_: OrderSummary) -> str:
        return "denied"

    agent = FakeShoppingAgent(speed=0, approval_callback=refuse)
    await agent.start(TRAIN)
    await agent.choose((await agent.search())[0].id)
    await agent.checkout()
    with pytest.raises(PaymentDenied):
        await agent.pay()


async def test_fake_need_human_uses_callback_or_raises():
    reasons = []

    async def need_human(reason: str) -> None:
        reasons.append(reason)

    helped = FakeShoppingAgent(speed=0, need_human_at="search", need_human_callback=need_human)
    await helped.start(PIZZA)
    await helped.search()
    assert reasons and "CAPTCHA" in reasons[0]

    alone = FakeShoppingAgent(speed=0, need_human_at="search")
    await alone.start(PIZZA)
    with pytest.raises(NeedsHuman):
        await alone.search()


def test_agents_satisfy_the_orchestrator_port():
    fake: ShoppingAgentPort = FakeShoppingAgent(speed=0)
    real: ShoppingAgentPort = ShoppingAgent(client=object(), memory=InMemorySiteMemory())  # type: ignore[arg-type]
    for agent in (fake, real):
        for name in ("start", "search", "refine", "choose", "checkout", "recheck", "pay", "cancel"):
            assert callable(getattr(agent, name))
        assert agent.agent_view_url is None


async def test_factory_matches_agent_factory_signature(monkeypatch):
    monkeypatch.setenv("USE_FAKE_AGENT", "1")
    approvals, humans = [], []

    async def approval(summary: OrderSummary) -> str:
        approvals.append(summary.order_id)
        return "approved"

    async def need_human(reason: str) -> None:
        humans.append(reason)

    agent = make_agent_factory(speed=0)(approval, need_human)
    await agent.start(PIZZA)
    await agent.choose((await agent.search())[0].id)
    await agent.checkout()
    assert await agent.pay() == "accepted"
    assert approvals == [agent.order_id]  # l'orchestrateur est bien consulté avant le paiement


# --- garde-fou de paiement du vrai agent (sans appeler H) --------------------------


def paying_agent(**kwargs) -> ShoppingAgent:
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False, **kwargs)  # type: ignore[arg-type]
    agent.order_id, agent._site = ORDER_ID, "https://www.ubereats.com/fr"
    return agent


async def test_gate_denies_outside_pay_step():
    agent = paying_agent(auto_approve=True)
    assert await agent._decide_payment(raw_summary()) == "denied"  # recherche ou panier
    agent._paying = True
    assert await agent._decide_payment(raw_summary()) == "approved"


async def test_gate_denies_by_default_without_orchestrator_callback(monkeypatch):
    monkeypatch.delenv("PILOTE_AUTO_APPROVE", raising=False)
    agent = paying_agent()
    agent._paying = True
    assert await agent._decide_payment(raw_summary()) == "denied"  # pas d'approbation : on ne paie pas


async def test_auto_approve_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("PILOTE_AUTO_APPROVE", "1")
    agent = paying_agent()
    agent._paying = True
    assert await agent._decide_payment(raw_summary()) == "approved"


async def test_gate_uses_orchestrator_callback_once_per_summary():
    calls = []

    async def callback(summ: OrderSummary) -> str:
        calls.append(summ.order_id)
        return "approved"

    agent = paying_agent(approval_callback=callback)
    agent._paying = True
    assert await agent._decide_payment(raw_summary(9.0)) == "approved"
    assert await agent._decide_payment(raw_summary(9.0)) == "approved"
    assert calls == [ORDER_ID]  # appel répété : le callback n'est consulté qu'une fois


@pytest.mark.parametrize("answer", ["denied", "peut-être", None])
async def test_gate_treats_anything_but_approved_as_denied(answer):
    async def callback(_: OrderSummary) -> str:
        return answer  # type: ignore[return-value]

    agent = paying_agent(approval_callback=callback)
    agent._paying = True
    assert await agent._decide_payment(raw_summary()) == "denied"


async def test_gate_denies_when_the_callback_fails():
    async def callback(_: OrderSummary) -> str:
        raise TimeoutError

    agent = paying_agent(approval_callback=callback)
    agent._paying = True
    assert await agent._decide_payment(raw_summary()) == "denied"


async def test_a_new_price_is_decided_again():
    answers = iter(["approved", "denied"])

    async def callback(_: OrderSummary) -> str:
        return next(answers)

    agent = paying_agent(approval_callback=callback)
    agent._paying = True
    assert await agent._decide_payment(raw_summary(14.0)) == "approved"
    assert await agent._decide_payment(raw_summary(22.0)) == "denied"  # prix changé : nouvelle décision


async def test_gate_refuses_above_ceiling_or_unreadable_total():
    agent = paying_agent(max_total_eur=30, auto_approve=True)
    agent._paying = True
    assert await agent._decide_payment(raw_summary(42.0)) == "denied"
    assert await agent._decide_payment(AgentOrderSummary(items=[AgentOrderItem(name="Pizza")])) == "denied"


async def test_gate_denies_without_order_id():
    agent = paying_agent(auto_approve=True)
    agent.order_id = ""
    agent._paying = True
    assert await agent._decide_payment(raw_summary()) == "denied"


async def test_payment_tool_accepts_raw_json_from_the_agent():
    agent = paying_agent(auto_approve=True)
    agent._paying = True
    pay_tool = {t.name: t for t in agent._tools()}["request_payment_approval"]
    raw = {"items": [{"name": "Pizza margherita", "quantity": 1}], "total_eur": 14.0}
    assert await pay_tool.fn(summary=raw) == "approved"
    assert await pay_tool.fn(summary="pas un récapitulatif") == "denied"


async def test_need_human_callback_rules():
    alone = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    assert await alone._ask_human("CAPTCHA") == "abort"

    async def done(_: str) -> None:  # forme de ports.py : rend la main quand l'humain a fini
        return None

    async def broken(_: str) -> None:
        raise RuntimeError

    helped = ShoppingAgent(client=object(), need_human_callback=done, memory=InMemorySiteMemory())  # type: ignore[arg-type]
    assert await helped._ask_human("CAPTCHA") == "resolved"
    failing = ShoppingAgent(client=object(), need_human_callback=broken, memory=InMemorySiteMemory())  # type: ignore[arg-type]
    assert await failing._ask_human("CAPTCHA") == "abort"


def test_default_ceiling_is_999(monkeypatch):
    monkeypatch.delenv("PILOTE_MAX_TOTAL_EUR", raising=False)
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    assert agent._max_total_eur == 999


def test_make_agent_is_real_by_default(monkeypatch):
    monkeypatch.delenv("USE_FAKE_AGENT", raising=False)
    assert isinstance(make_agent(), ShoppingAgent)
    monkeypatch.setenv("USE_FAKE_AGENT", "1")
    assert isinstance(make_agent(speed=0), FakeShoppingAgent)


def test_tools_declared_for_the_agent():
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    names = {t.name: t for t in agent._tools()}
    assert set(names) == {"request_payment_approval", "need_human", "request_card", "fill_card_field"}
    assert "summary" in names["request_payment_approval"].input_schema["properties"]


# --- une session H simulée, de bout en bout ----------------------------------------


class _Result:
    def __init__(self, answer: dict, index: int) -> None:
        self.status, self.error, self.error_code = "idle", None, None
        self.pending_approvals, self.answer, self.next_from_index = [], answer, index


class _FakeSession:
    """Session H simulée : renvoie les réponses dans l'ordre, et appelle l'outil de paiement au pay()."""

    def __init__(self, answers: list[dict], agent: ShoppingAgent) -> None:
        self.answers, self.agent, self.sent, self.pay_decision = list(answers), agent, [], None

    async def get(self):
        return type("S", (), {"agent_view_url": "https://hub.test/view/1"})()

    async def status(self):
        return type("St", (), {"steps": 12})()

    async def send_message(self, text: str) -> None:
        self.sent.append(text)

    async def wait_for_completion(self, from_index: int, timeout_seconds: float):
        answer = self.answers.pop(0)
        if "payment_result" in answer:  # l'agent H appelle l'outil avant de cliquer
            tool = {t.name: t for t in self.agent._tools()}["request_payment_approval"]
            self.pay_decision = await tool.fn(summary=answer["_page"])
            if self.pay_decision != "approved":
                answer = {"blocked_reason": "paiement refusé par Pilote"}
        return _Result({k: v for k, v in answer.items() if k != "_page"}, from_index + 1)

    async def cancel(self) -> None: ...


class _FakeClient:
    def __init__(self, session_factory) -> None:
        self.factory, self.started = session_factory, {}

    async def start_session(self, **kwargs):
        self.started = kwargs
        return self.factory()


ANSWERS = [
    {
        "options": [
            {
                "id": "o1",
                "title": "Pizza A",
                "price_eur": 11.5,
                "rating": 4.6,
                "details": {"delivery": "25 min"},
            },
            {"id": "o2", "title": "Pizza B", "price_eur": 12.9},
        ]
    },
    {
        "order_summary": {
            "items": [{"name": "Pizza A", "quantity": 1, "total_eur": 11.5}],
            "fees": [{"label": "Livraison", "amount_eur": 2.5}],
            "total_eur": 14.0,
            "page_url": "https://www.ubereats.com/fr/checkout",
            "payment_button_label": "Commander",
        }
    },
    {
        "payment_result": "refused",
        "payment_message": "Carte refusée",
        "_page": {"items": [{"name": "Pizza A", "quantity": 1, "total_eur": 11.5}], "total_eur": 14.0},
        "site_notes": {"steps": ["Chercher la pizza"], "pitfalls": [], "useful_buttons": ["Commander"]},
    },
]


async def test_real_agent_full_flow_with_simulated_h_session():
    holder = {}

    def make_session():
        holder["session"] = _FakeSession(ANSWERS, agent)
        return holder["session"]

    approvals = []

    async def approval(summary: OrderSummary) -> str:
        approvals.append(summary)
        return "approved"

    memory = InMemorySiteMemory()
    agent = ShoppingAgent(
        client=_FakeClient(make_session),  # type: ignore[arg-type]
        memory=memory,
        approval_callback=approval,
        record_metrics=False,
    )

    await agent.start(PIZZA)
    assert agent.agent_view_url == "https://hub.test/view/1"
    assert agent._session is holder["session"]
    options = await agent.search()
    assert [(o.rank, o.price_cents) for o in options] == [(1, 1150), (2, 1290)]

    await agent.choose("o1")
    summary = await agent.checkout()
    assert summary.total_cents == 1400 and summary.site == "www.ubereats.com"
    assert summary.payment_button_label == "Commander"
    assert summary.order_id == agent.order_id and len(agent.order_id) == 36
    assert summary.hash == summary_hash(summary.items, summary.total_cents)

    assert await agent.pay() == "refused"
    assert holder["session"].pay_decision == "approved"
    assert approvals and approvals[0].order_id == summary.order_id  # le callback a vu la commande

    card = await memory.get("www.ubereats.com")  # la mémoire s'est enrichie, au format du contrat
    assert isinstance(card, SiteCard) and card.runs == 1 and card.avg_steps == 12
    assert card.useful_buttons == ["Commander"]


async def test_real_agent_without_callback_never_clicks_pay():
    holder = {}

    def make_session():
        holder["session"] = _FakeSession(ANSWERS, agent)
        return holder["session"]

    agent = ShoppingAgent(client=_FakeClient(make_session), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    await agent.start(PIZZA)
    await agent.choose((await agent.search())[0].id)
    await agent.checkout()
    with pytest.raises(PaymentDenied):
        await agent.pay()
    assert holder["session"].pay_decision == "denied"


def test_inline_agent_opens_on_the_site_with_low_reasoning(monkeypatch):
    monkeypatch.delenv("PILOTE_H_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("PILOTE_MAX_OPTIONS", raising=False)
    agent = ShoppingAgent(agent="", browser_host="cloud", record_metrics=False)
    agent._site = "https://www.sncf-connect.com"
    spec = agent._agent_spec()
    assert spec["environments"][0]["start_url"] == "https://www.sncf-connect.com"
    assert spec["reasoning_effort"] == "low"
    assert "au plus 3 options" in spec["instructions"]


def test_reasoning_effort_and_option_count_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("PILOTE_H_REASONING_EFFORT", "default")
    monkeypatch.setenv("PILOTE_MAX_OPTIONS", "50")
    spec = ShoppingAgent(agent="", browser_host="cloud", record_metrics=False)._agent_spec()
    assert "reasoning_effort" not in spec
    assert "start_url" not in spec["environments"][0]
    assert "au plus 8 options" in spec["instructions"]


def test_vault_is_bound_to_the_cloud_browser_only(monkeypatch):
    monkeypatch.setenv("PILOTE_H_VAULT_ID", "vault-123")
    cloud = ShoppingAgent(agent="", browser_host="cloud", record_metrics=False)._agent_spec()
    local = ShoppingAgent(agent="", browser_host="user_device", record_metrics=False)._agent_spec()
    assert cloud["environments"][0]["vault_id"] == "vault-123"
    assert "vault_id" not in local["environments"][0]
    assert "coffre-fort" in cloud["instructions"] and "page de connexion" not in cloud["instructions"]
    assert "coffre-fort" not in local["instructions"] and "page de connexion" in local["instructions"]


def test_with_a_vault_the_agent_logs_in_before_searching():
    from orchestrator.agent_h.prompts import search_message

    with_vault = search_message(TRAIN, "https://www.sncf-connect.com", None, True, with_vault=True)
    without = search_message(TRAIN, "https://www.sncf-connect.com", None, True)
    assert "Avant toute recherche, connecte-toi" in with_vault
    assert "price_eur = 0" in with_vault
    assert "déjà connecté" not in with_vault and "coffre-fort (il remplit" in with_vault
    assert "connecte-toi" not in without and "déjà connecté" in without


def test_a_free_ticket_is_kept_not_dropped_as_unpriced():
    options = to_options([AgentOption(id="o1", title="TGV MAX 10:00", price_eur=0)])
    assert len(options) == 1 and options[0].price_cents == 0


def test_default_profile_is_used_on_cloud_when_enabled(monkeypatch):
    monkeypatch.setenv("PILOTE_H_DEFAULT_PROFILE", "1")
    cloud = ShoppingAgent(agent="", browser_host="cloud", record_metrics=False)._agent_spec()
    local = ShoppingAgent(agent="", browser_host="user_device", record_metrics=False)._agent_spec()
    assert cloud["environments"][0]["use_default_browser_profile"] is True
    assert "use_default_browser_profile" not in local["environments"][0]


def test_login_session_uses_vault_and_default_profile():
    from orchestrator.agent_h.login_session import agent_spec

    env = agent_spec("https://www.sncf-connect.com", "vault-1")["environments"][0]
    assert env == {
        "kind": "web",
        "id": "browser",
        "host": "cloud",
        "start_url": "https://www.sncf-connect.com",
        "use_default_browser_profile": True,
        "vault_id": "vault-1",
    }


def test_sncf_has_a_starter_card_with_the_promo_pitfall(monkeypatch):
    from orchestrator.agent_h.site_memory import starter_card

    monkeypatch.setenv("PILOTE_SNCF_QUICK_SEARCH", "0")  # formulaire Trains (repli)
    card = starter_card("www.sncf-connect.com")
    assert card is not None and any("Ouverture des ventes" in p for p in card.pitfalls)
    assert any("Trains" in s for s in card.steps)
    assert starter_card("www.ubereats.com") is None


def test_agent_answer_with_null_options_means_nothing_found():
    from orchestrator.agent_h.models import AgentAnswer

    assert AgentAnswer.model_validate({"options": None}).options == []


async def test_local_chrome_starts_a_fresh_session_per_step_with_full_context(monkeypatch):
    from orchestrator.agent_h import local_chrome

    monkeypatch.setenv("PILOTE_H_IDLE_TIMEOUT_S", "0")  # ancien comportement, gardé en secours
    monkeypatch.setattr(local_chrome, "ensure", lambda *a, **k: True)
    monkeypatch.setattr(local_chrome, "fresh_page", lambda *a, **k: None)
    monkeypatch.setattr(local_chrome, "ensure_page", lambda *a, **k: None)
    answers = list(ANSWERS)
    sessions: list[_FakeSession] = []
    starts: list[dict] = []

    class Recording(_FakeClient):
        async def start_session(self, **kwargs):
            starts.append(kwargs)
            return await super().start_session(**kwargs)

    def make_session():
        sessions.append(_FakeSession([answers.pop(0)], agent))
        return sessions[-1]

    agent = ShoppingAgent(
        client=Recording(make_session),
        browser_host="user_device",
        agent="",
        memory=InMemorySiteMemory(),
        record_metrics=False,
    )  # type: ignore[arg-type]
    agent._real_client = True  # comme en vrai : pas de client simulé
    await agent.start(PIZZA)
    options = await agent.search()
    await agent.choose(options[0].id)
    await agent.checkout()

    assert len(starts) == 2 and sessions[0].sent == []  # pas de message à une session terminée
    follow_up = starts[1]["messages"]
    assert "Pizza A" in follow_up and "tu reprends une commande en cours" in follow_up
    assert "Étape : panier" in follow_up
    assert "start_url" not in starts[1]["agent"]["environments"][0]  # on reste sur la page actuelle


async def test_portal_agent_is_mirrored_onto_the_local_chrome(monkeypatch):
    from orchestrator.agent_h import local_chrome

    monkeypatch.setattr(local_chrome, "ensure", lambda *a, **k: True)
    monkeypatch.setattr(local_chrome, "fresh_page", lambda *a, **k: None)
    monkeypatch.delenv("PILOTE_H_REASONING_EFFORT", raising=False)

    class _Dump:
        def __init__(self, data):
            self.data = data

        def model_dump(self, mode="json"):
            return self.data

    class _Agents:
        async def get_agent(self, name):
            return _Dump(
                {
                    "name": name,
                    "description": "Agent du portail",
                    "environments": ["chrome"],
                    "instructions": "CONSIGNES DU PORTAIL",
                    "skills": ["h/visual-browser", "h/answering"],
                    "model": None,
                    "reasoning_effort": "medium",
                }
            )

    class _Envs:
        async def get_environment(self, env_id):
            return _Dump({"host": "cloud", "mode": {"type": "visual", "markdown": True, "width": None}})

    client = _FakeClient(lambda: _FakeSession(list(ANSWERS), agent))
    client.agents, client.environments = _Agents(), _Envs()
    agent = ShoppingAgent(
        client=client,
        agent="pilote-shopper",
        browser_host="user_device",
        memory=InMemorySiteMemory(),
        record_metrics=False,
    )  # type: ignore[arg-type]
    await agent.start(TRAIN)

    spec = client.started["agent"]
    env = spec["environments"][0]
    assert spec["instructions"] == "CONSIGNES DU PORTAIL" and spec["skills"] == [
        "h/visual-browser",
        "h/answering",
    ]
    assert spec["reasoning_effort"] == "medium" and "model" not in spec
    assert env["host"] == "user_device" and env["mode"] == {"type": "visual", "markdown": True}
    assert "vault_id" not in env
    assert "CONSIGNES DU PORTAIL" not in client.started["messages"]  # pas de doublon dans le message


async def test_payment_reported_outside_pay_step_raises_unapproved_purchase(monkeypatch):
    from orchestrator.agent_h.base import UnapprovedPurchase

    answers = [ANSWERS[0], {"payment_result": "accepted", "payment_message": "Paiement de 0 € effectué !"}]

    class ClickedWithoutAsking(_FakeSession):  # comme le vrai agent le 2026-11-18 : pas d'appel à l'outil
        async def wait_for_completion(self, from_index: int, timeout_seconds: float):
            return _Result(self.answers.pop(0), from_index + 1)

    agent = ShoppingAgent(
        client=_FakeClient(lambda: ClickedWithoutAsking(answers, agent)),
        memory=InMemorySiteMemory(),
        record_metrics=False,
    )  # type: ignore[arg-type]
    await agent.start(PIZZA)
    await agent.choose((await agent.search())[0].id)
    with pytest.raises(UnapprovedPurchase) as bought:
        await agent.checkout()
    assert bought.value.result == "accepted" and "0 €" in (bought.value.site_message or "")


def test_fast_model_gets_reasoning_disabled(monkeypatch):
    monkeypatch.setenv("PILOTE_H_MODEL", "holo4-35b-a3b")
    monkeypatch.setenv("PILOTE_H_REASONING_EFFORT", "medium")
    spec = ShoppingAgent(agent="", browser_host="cloud", record_metrics=False)._agent_spec()
    assert spec["model"] == "holo4-35b-a3b" and spec["reasoning_effort"] == "disabled"


async def test_session_stays_open_between_steps_so_the_agent_keeps_its_memory(monkeypatch):
    from orchestrator.agent_h import local_chrome

    monkeypatch.setattr(local_chrome, "ensure", lambda *a, **k: True)
    monkeypatch.setattr(local_chrome, "fresh_page", lambda *a, **k: None)
    monkeypatch.delenv("PILOTE_H_IDLE_TIMEOUT_S", raising=False)
    starts: list[dict] = []
    sessions: list[_FakeSession] = []

    class Recording(_FakeClient):
        async def start_session(self, **kwargs):
            starts.append(kwargs)
            return await super().start_session(**kwargs)

    def make_session():
        sessions.append(_FakeSession(list(ANSWERS), agent))
        return sessions[-1]

    agent = ShoppingAgent(
        client=Recording(make_session),
        browser_host="user_device",
        agent="",
        memory=InMemorySiteMemory(),
        record_metrics=False,
    )  # type: ignore[arg-type]
    agent._real_client = True
    await agent.start(PIZZA)
    await agent.choose((await agent.search())[0].id)
    await agent.checkout()
    assert len(starts) == 1 and starts[0]["idle_timeout_s"] == 900  # une seule session, gardée ouverte
    assert len(sessions[0].sent) == 1 and "Étape : panier" in sessions[0].sent[0]


def test_answer_accepts_summary_and_notes_sent_as_json_text():
    from orchestrator.agent_h.models import AgentAnswer

    answer = AgentAnswer.model_validate(
        {
            "order_summary": '{"items": [{"name": "TGV", "quantity": 1, "total_eur": 0}], "total_eur": 0}',
            "site_notes": '{"steps": ["Clique sur le train"]}',
            "payment_result": "accepted",
        }
    )
    assert answer.order_summary is not None and answer.order_summary.total_eur == 0
    assert answer.site_notes is not None and answer.site_notes.steps == ["Clique sur le train"]
    assert AgentAnswer.model_validate({"site_notes": "texte libre"}).site_notes is None


async def test_payment_tool_reads_a_summary_sent_as_json_text():
    approvals = []

    async def approve(summary):
        approvals.append(summary.total_cents)
        return "approved"

    agent = ShoppingAgent(
        client=object(), approval_callback=approve, memory=InMemorySiteMemory(), record_metrics=False
    )  # type: ignore[arg-type]
    agent.order_id, agent._paying, agent._site = ORDER_ID, True, "https://www.sncf-connect.com"
    text = '{"items": [{"name": "TGV INOUI 06:32", "quantity": 1, "total_eur": 0}], "total_eur": 0}'
    assert await agent._decide_payment(text) == "approved" and approvals == [0]
    assert await agent._decide_payment("pas du JSON") == "denied"
    assert agent.last_denial_reason == "le récapitulatif du panier était illisible"


async def test_payment_tool_accepts_the_contract_cents_format_sent_by_the_agent():
    # Récapitulatif exact envoyé par l'agent H le 2026-11-18 (refusé à tort : « total illisible »)
    sent = (
        '{"order_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "site": "SNCF Connect", '
        '"page_url": "https://www.sncf-connect.com/cart", "items": [{"name": "TGV INOUI 2de classe", '
        '"quantity": 1, "unit_price_cents": 0, "total_cents": 0, "options": ["2de classe"]}], "fees": [], '
        '"total_cents": 0, "currency": "EUR", "payment_button_label": "Valider et payer"}'
    )
    totals = []

    async def approve(summary):
        totals.append(summary.total_cents)
        return "approved"

    agent = ShoppingAgent(
        client=object(), approval_callback=approve, memory=InMemorySiteMemory(), record_metrics=False
    )  # type: ignore[arg-type]
    agent.order_id, agent._paying, agent._site = ORDER_ID, True, "https://www.sncf-connect.com"
    assert await agent._decide_payment(sent) == "approved" and totals == [0]


def test_sncf_quick_search_is_the_default(monkeypatch):
    from orchestrator.agent_h.site_memory import starter_card

    monkeypatch.delenv("PILOTE_SNCF_QUICK_SEARCH", raising=False)
    card = starter_card("www.sncf-connect.com")
    assert card is not None and any("Tout rechercher" in step for step in card.steps)
    assert any("Valider et payer" in pitfall for pitfall in card.pitfalls)  # garde-fou toujours là


# --- carte dictée : outils request_card et fill_card_field ------------------------------

from orchestrator.agent_h.card import NewCard  # noqa: E402

VISA_TEST = "4111111111111111"


async def test_card_is_only_asked_while_paying_and_typed_without_the_agent_seeing_it(monkeypatch):
    typed: list[str] = []

    async def fake_type(text, site, port=9222):
        typed.append(text)

    monkeypatch.setattr("orchestrator.agent_h.agent.type_into_focused_field", fake_type)
    asked: list[str] = []

    async def on_card_needed(kind):
        asked.append(kind)
        return (NewCard(VISA_TEST, "0327", "123"), True) if kind == "card" else "Leo Test"

    agent = paying_agent()
    agent.on_card_needed = on_card_needed
    tools = {t.name: t for t in agent._tools()}
    assert await tools["request_card"].fn() == "abort"  # hors de l'achat : jamais de carte
    agent._paying = True
    assert await tools["request_card"].fn() == "ready save_on_site=yes"
    assert await tools["request_card"].fn() == "ready save_on_site=yes" and asked == ["card"]  # une fois
    replies = [await tools["fill_card_field"].fn(field=f) for f in ("number", "expiry", "cvc", "holder")]
    assert replies == ["ok"] * 4 and all(VISA_TEST not in r for r in replies)
    assert typed == [VISA_TEST, "03/27", "123", "Leo Test"] and asked == ["card", "holder"]
    await agent.cancel()
    assert agent._card is None, "carte effacée"


async def test_without_local_chrome_no_card_is_asked():
    agent = paying_agent(browser_host="cloud")
    agent._paying = True

    async def never(kind):
        raise AssertionError("ne doit pas demander de carte sans Chrome local")

    agent.on_card_needed = never
    assert await agent._request_card() == "abort"


def test_agent_instructions_have_the_card_rule():
    from orchestrator.agent_h.prompts import generic_instructions

    text = generic_instructions()
    assert "request_card" in text and "fill_card_field" in text and "DÉCOCHÉE" in text
