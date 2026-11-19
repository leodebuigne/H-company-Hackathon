"""Parcours complets de la machine à états, avec les versions factices de l'IA et de l'agent.

Chaque message envoyé aux écrans est vérifié contre contracts/schemas/ws-message.schema.json.
"""

import asyncio
import datetime as dt
import json
import uuid
from typing import Any

import pytest

from orchestrator.agent_h.fake import FakeShoppingAgent
from orchestrator.ai.fake import FakeAI
from orchestrator.config import Settings
from orchestrator.contracts import Fee, Option, OrderItem, OrderSummary
from orchestrator.session import WAITING, Session, merge_answer

from .test_contracts import _validator

WS = _validator("ws-message.schema.json")
TODAY = dt.date(2026, 11, 18)


async def _until(condition, limit_s: float) -> None:
    """Attend qu'une condition devienne vraie (les tests observent la session de l'extérieur)."""

    async def poll() -> None:
        while not condition():  # noqa: ASYNC110
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), limit_s)


class Harness:
    def __init__(
        self,
        *,
        agent: dict[str, Any] | None = None,
        **settings: Any,
    ) -> None:
        self.messages: list[dict[str, Any]] = []
        self.agents: list[FakeShoppingAgent] = []
        self.paid = 0
        agent_options = {"speed": 0, **(agent or {})}

        def factory(approve, need_human):
            fake = FakeShoppingAgent(
                approval_callback=approve, need_human_callback=need_human, **agent_options
            )
            original_pay = fake.pay

            async def pay():
                self.paid += 1
                return await original_pay()

            fake.pay = pay  # type: ignore[method-assign]
            self.agents.append(fake)
            return fake

        config = {
            "journal_path": None,
            "confirm_timeout_s": 5,
            "human_timeout_s": 5,
            **settings,
        }
        self.session = Session(
            ai=FakeAI(),
            agent_factory=factory,
            settings=Settings(**config),
            today=lambda: TODAY,
        )

    async def __aenter__(self) -> "Harness":
        await self.session.start()
        await self.session.attach(self.collect)
        await self.wait("listening")
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.session.stop()

    async def collect(self, data: dict[str, Any]) -> None:
        WS.validate(data)  # hors contrat = test en échec
        self.messages.append(data)

    async def text(self, text: str) -> None:
        await self.session.receive({"type": "text", "text": text})

    async def confirm(self, value: bool) -> None:
        await self.session.receive({"type": "confirm", "value": value})

    async def wait(self, state: str, limit_s: float = 5) -> None:
        session = self.session
        await _until(lambda: session.state == state and (state not in WAITING or session._waiting), limit_s)

    async def wait_said(self, text: str, limit_s: float = 5) -> None:
        await _until(lambda: text in self.said(), limit_s)

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["type"] == kind]

    def said(self) -> str:
        return " | ".join(m["text"] for m in self.of("say"))

    def states(self) -> list[str]:
        return [m["state"] for m in self.of("state")]


async def _to_confirm_1(h: Harness) -> None:
    await h.text("Un train de Paris pour Lille demain après 14 h")
    await h.wait("proposing")
    await h.text("La deuxième")
    await h.wait("confirm_1")


async def test_full_order_with_two_confirmations():
    async with Harness() as h:
        assert h.of("ready") and "Je suis Pilote, un assistant automatique" in h.of("say")[0]["text"]
        await _to_confirm_1(h)
        assert h.of("options") and h.of("summary")
        await h.confirm(True)
        await h.wait("confirm_2")
        assert h.paid == 0, "rien n'est payé avant le deuxième oui"
        await h.text("Oui")
        await h.wait("listening")
        assert h.paid == 1
        expected = [
            "listening", "understanding", "searching", "proposing", "understanding", "cart",
            "confirm_1", "recheck", "confirm_2", "understanding", "paying",
            "done", "listening",
        ]  # fmt: skip
        assert h.states() == expected
        assert "Rien n'a changé" in h.said() and "Le paiement est accepté" in h.said()


async def test_missing_information_is_asked_then_merged():
    async with Harness() as h:
        await h.text("Je veux un train pour Lille demain")
        await h.wait_said("De quelle ville partez-vous ?")
        await h.wait("listening")
        await h.text("Paris")
        await h.wait("proposing")
        assert h.agents[0]._intent.details == {"destination": "Lille", "origin": "Paris"}


async def test_first_no_buys_nothing():
    async with Harness() as h:
        await _to_confirm_1(h)
        await h.confirm(False)
        await h.wait("listening")
        assert h.paid == 0
        assert "cancelled" in h.states()


async def test_price_change_on_recheck_cancels():
    async with Harness(agent={"price_change_on_recheck": True}) as h:
        await _to_confirm_1(h)
        await h.confirm(True)
        await h.wait("listening")
        assert h.paid == 0
        assert h.of("error")[-1]["code"] == "price_changed"
        assert "La page a changé depuis votre accord" in h.said()


async def test_cancel_message_stops_a_long_search():
    async with Harness(agent={"speed": 1}) as h:  # la recherche factice dure 6 s
        await h.text("Un train de Paris pour Lille demain")
        await h.wait("searching")
        await h.session.receive({"type": "cancel"})
        await h.wait("listening", limit_s=2)
        assert "cancelled" in h.states() and "Rien n'a été acheté" in h.said()


async def test_spoken_cancel_while_waiting_for_the_second_yes():
    async with Harness() as h:
        await _to_confirm_1(h)
        await h.confirm(True)
        await h.wait("confirm_2")
        await h.text("Annule")
        await h.wait("listening")
        assert h.paid == 0 and h.states()[-2] == "cancelled"


async def test_speaking_during_a_long_step_is_not_lost_silently():
    async with Harness(agent={"speed": 1}) as h:
        await h.text("Un train de Paris pour Lille demain")
        await h.wait("searching")
        await h.text("la première")
        await h.wait_said("Un instant")
        await h.session.receive({"type": "cancel"})


async def test_payment_approval_is_denied_outside_paying():
    async with Harness() as h:
        await _to_confirm_1(h)
        summary = h.of("summary")[-1]["summary"]
        from orchestrator.contracts import OrderSummary

        assert await h.session.approve_payment(OrderSummary.model_validate(summary)) == "denied"
        await h.session.receive({"type": "cancel"})


async def test_need_human_pauses_until_done():
    async with Harness(agent={"need_human_at": "search"}) as h:
        await h.text("Un train de Paris pour Lille demain")
        await h.wait("human_needed")
        assert "J'ai besoin d'un humain" in h.said()
        await h.text("C'est fait")
        await h.wait("proposing")
        await h.session.receive({"type": "cancel"})


async def test_second_screen_gets_current_state():
    async with Harness() as h:
        await h.text("Un train de Paris pour Lille demain")
        await h.wait("proposing")
        late: list[dict[str, Any]] = []

        async def spectator(data):
            WS.validate(data)
            late.append(data)

        await h.session.attach(spectator)
        kinds = [m["type"] for m in late]
        assert kinds[0] == "ready" and "options" in kinds and "intent" in kinds
        assert next(m for m in late if m["type"] == "state")["state"] == "proposing"
        assert "say" not in kinds, "pas de phrase d'accueil au milieu d'une commande"
        before = len(late)
        await h.text("La première")
        await h.wait("confirm_1")
        assert any(m["type"] == "summary" for m in late[before:]), "les deux écrans reçoivent la suite"


async def test_invalid_client_message_is_ignored():
    async with Harness() as h:
        await h.session.receive({"type": "pay_now"})
        await h.session.receive({"type": "text"})
        await asyncio.sleep(0.02)
        assert h.session.state == "listening"


def test_merge_answer_fills_the_asked_field():
    from orchestrator.session import _intent

    pending = _intent("new_request", "train pour Lille demain")
    pending = pending.model_copy(
        update={
            "category": "train",
            "details": {"destination": "Lille"},
            "when": pending.when.model_copy(update={"date": TODAY}),
            "missing": ["details.origin"],
        }
    )
    merged = merge_answer(pending, _intent("other", "Je pars de Paris."))
    assert merged.details == {"destination": "Lille", "origin": "Paris"}
    assert merged.missing == [] and merged.kind == "new_request"


async def test_a_purchase_clicked_during_checkout_is_announced_not_hidden():
    from orchestrator.agent_h.base import UnapprovedPurchase

    async with Harness() as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")

        async def bought_on_the_site():
            raise UnapprovedPurchase(
                "accepted",
                "Votre paiement de 0 € a bien été effectué ! Un e-mail vous a été envoyé à a@b.fr.",
            )

        h.agents[-1].checkout = bought_on_the_site  # type: ignore[method-assign]
        await h.text("La deuxième")
        await h.wait_said("l'achat a été validé sur le site")
        said = h.said()
        assert "Votre paiement de 0 € a bien été effectué !" in said
        assert "a@b.fr" not in said  # pas d'e-mail lu à l'oral
        assert "Rien n'a été acheté" not in said
        assert "done" in h.states()


def test_site_message_for_speech_keeps_first_sentence_without_email():
    from orchestrator.session import site_message_for_speech

    assert (
        site_message_for_speech("Paiement effectué ! Mail envoyé à x@y.fr avec les détails.")
        == "Paiement effectué !"
    )
    assert site_message_for_speech(None) == ""


async def test_direct_buy_asks_once_for_a_paid_ticket_then_says_it():
    async with Harness(direct_buy=True) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait("confirm_1")
        assert "J'achète bien" in h.said()
        await h.confirm(True)
        await h.wait_said("C'est acheté")
        said = h.said()
        assert "J'achète" in said and "Votre commande est confirmée." in said
        assert "confirm_2" not in h.states()  # pas de 2e oui
        assert "done" in h.states()


async def test_direct_buy_explains_a_higher_total_and_lets_the_person_decide():
    async with Harness(direct_buy=True, agent={"price_change_on_recheck": True}) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait_said("le total est plus cher")
        assert "au lieu de" in h.said() and "au total ?" in h.said()
        await h.confirm(False)
        await h.wait_said("je n'achète rien")
        assert h.paid == 0 and "C'est acheté" not in h.said()


async def test_a_leftover_ticket_in_the_cart_is_named_and_removed_on_yes():
    async with Harness(direct_buy=True, agent={"stale_cart": True}) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait_said("Je le retire du panier ?")
        assert "Billet Paris → Lyon, départ 10 h 12, 35 euros" in h.said()
        await h.confirm(True)  # retirer le billet en trop
        await h.wait_said("J'achète bien")
        assert "le total est plus cher" not in h.said(), "panier propre : plus rien à expliquer"
        await h.confirm(True)
        await h.wait_said("C'est acheté")
        assert h.agents[0].cart_fix_requests == 1


async def test_a_leftover_ticket_kept_on_no_is_paid_only_after_the_full_total_is_said():
    async with Harness(direct_buy=True, agent={"stale_cart": True}) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait_said("Je le retire du panier ?")
        await h.confirm(False)  # la personne garde les deux billets
        await h.wait_said("au total ?")
        assert "le total est plus cher" in h.said() and h.paid == 0
        await h.confirm(False)
        await h.wait_said("je n'achète rien")
        assert h.paid == 0 and "C'est acheté" not in h.said()


async def test_a_cart_the_agent_cannot_clean_is_said_and_not_asked_twice():
    async with Harness(direct_buy=True, agent={"stale_cart": True, "cart_fixable": False}) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait_said("Je le retire du panier ?")
        await h.confirm(True)
        await h.wait_said("Je n'ai pas réussi à tout retirer du panier")
        await h.wait_said("au total ?")
        assert h.said().count("Je le retire du panier ?") == 1


def _cart(*items: tuple[str, int, int]) -> OrderSummary:
    lines = [
        OrderItem(name=n, quantity=q, unit_price_cents=u, total_cents=q * u, options=[]) for n, q, u in items
    ]
    return OrderSummary(
        order_id=str(uuid.uuid4()), site="www.ubereats.com", page_url="https://www.ubereats.com/checkout",
        items=lines, fees=[], total_cents=sum(i.total_cents for i in lines), currency="EUR", when_label=None,
        conditions=None, payment_button_label="Commander", hash="0" * 64, read_at=dt.datetime.now(dt.UTC),
    )  # fmt: skip


def test_cart_extras_finds_a_doubled_burger_and_a_leftover_ticket_but_not_a_detailed_menu():
    from orchestrator.session import cart_extras

    big_mac = Option(
        id="o1", rank=1, title="Big Mac", price_cents=550, currency="EUR", rating=None,
        description=None, conditions=None, details={}, url=None,
    )  # fmt: skip
    assert cart_extras(big_mac, _cart(("Big Mac", 2, 550))) == ["Big Mac en 2 exemplaires au lieu de 1"]
    assert cart_extras(big_mac, _cart(("Big Mac", 2, 550)), wanted=2) == []
    assert cart_extras(big_mac, _cart(("Big Mac", 1, 550), ("McFlurry", 1, 350))) == ["McFlurry, 3 euros 50"]
    menu = big_mac.model_copy(update={"title": "Menu Big Mac", "price_cents": 900})
    assert cart_extras(menu, _cart(("Big Mac", 1, 550), ("Frites", 1, 350))) == []


def test_the_price_breakdown_names_each_fee():
    from orchestrator.session import price_breakdown

    option = Option(
        id="o1", rank=1, title="Burger", price_cents=500, currency="EUR", rating=None,
        description=None, conditions=None, details={}, url=None,
    )  # fmt: skip
    summary = OrderSummary(
        order_id=str(uuid.uuid4()),
        site="www.ubereats.com",
        page_url="https://www.ubereats.com/checkout",
        items=[OrderItem(name="Burger", quantity=1, unit_price_cents=500, total_cents=500, options=[])],
        fees=[
            Fee(label="Frais de livraison", amount_cents=99),
            Fee(label="Frais de service", amount_cents=549),
        ],
        total_cents=1148,
        currency="EUR",
        when_label=None,
        conditions=None,
        payment_button_label="Commander",
        hash="0" * 64,
        read_at=dt.datetime.now(dt.UTC),
    )
    said = price_breakdown(option, summary)
    assert said == (
        "Attention, le total est plus cher : 11 euros 48. Il comprend Burger à 5 euros, comme annoncé, "
        "frais de livraison : 99 centimes, frais de service : 5 euros 49."
    )


async def test_direct_buy_asks_the_code_only_once_the_agent_is_at_the_pay_button():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        await _to_code_prompt(h)
        assert h.session._direct_option is not None  # dans l'étape d'achat : l'agent a le panier
        assert "juste avant de payer" in h.said()
        assert h.said().index("juste avant de payer") < h.said().index("dites votre code")


async def test_direct_buy_saying_no_buys_nothing():
    async with Harness(direct_buy=True) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait("confirm_1")
        await h.confirm(False)
        await h.wait_said("je n'achète rien")
        assert h.paid == 0 and "C'est acheté" not in h.said()


async def test_progress_is_spoken_while_searching_but_throttled_and_kept_out_of_history():
    async with Harness() as h:
        session = h.session
        await session._set_state("searching")
        await session._progress("J'ouvre SNCF Connect.")
        await session._progress("J'ouvre la recherche de trains.")  # trop tôt : pas dit
        said = [m["text"] for m in h.of("say")]
        assert said.count("J'ouvre SNCF Connect.") == 1 and "J'ouvre la recherche de trains." not in said
        assert all(turn["text"] != "J'ouvre SNCF Connect." for turn in session.history)
        await session._set_state("listening")
        session._last_progress = 0.0
        await session._progress("Je parcours les résultats.")  # hors recherche : silence
        assert "Je parcours les résultats." not in [m["text"] for m in h.of("say")]


async def _to_code_prompt(h: Harness) -> None:
    await h.text("Un train de Paris pour Lille demain après 14 h")
    await h.wait("proposing")
    await h.text("La deuxième")
    await h.wait("confirm_1")
    assert "dites votre code à 3 chiffres" in h.said()


async def test_right_code_buys_and_the_code_is_never_shown_nor_kept():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        parsed: list[str] = []
        original = h.session.ai.parse_intent

        async def spy(text, today, history):
            parsed.append(text)
            return await original(text, today, history)

        h.session.ai.parse_intent = spy  # type: ignore[method-assign]
        await _to_code_prompt(h)
        await h.text("quatre 7 deux")
        await h.wait_said("C'est acheté")
        typed = [m["text"] for m in h.of("transcript") if m["role"] == "user"]
        assert "•••" in typed and not any("47" in t or "quatre" in t for t in typed)
        assert not any("quatre" in t for t in parsed)  # jamais envoyé au modèle de langage
        assert not any("quatre" in turn["text"] for turn in h.session.history)


async def test_wrong_code_three_times_buys_nothing():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        await _to_code_prompt(h)
        await h.text("111")
        await h.wait_said("Encore 2 essais.")
        await h.text("111")
        await h.wait_said("Encore 1 essai.")
        await h.text("111")
        await h.wait_said("Code incorrect trois fois")
        assert "C'est acheté" not in h.said()


async def test_saying_no_at_the_code_prompt_buys_nothing():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        await _to_code_prompt(h)
        await h.text("non")
        await h.wait_said("je n'achète rien")
        assert "C'est acheté" not in h.said()


def test_spoken_digits_reads_words_and_figures():
    from orchestrator.session import spoken_digits

    assert spoken_digits("Un, deux, trois.") == "123"
    assert spoken_digits("1 2 3") == "123" and spoken_digits("mon code est 908") == "908"


async def test_direct_buy_asks_only_the_code():
    async with Harness(direct_buy=True, purchase_code="123") as h:
        await _to_code_prompt(h)
        await h.text("un deux trois")
        await h.wait_said("C'est acheté")
        assert "confirm_2" not in h.states()


async def test_stuck_agent_gets_a_hint_and_the_person_hears_the_page():
    async with Harness() as h:
        h.session.state = "searching"
        hint = await h.session._stuck(b"capture", "boucle")
        assert hint and "Rechercher" in hint
        assert "Je regarde la page : La page montre un formulaire de recherche" in h.said()
        silent = await h.session._stuck(b"capture", "silence")
        assert silent  # le conseil est renvoyé, mais l'agent ne l'envoie pas pour un simple silence
        h.session.state = "listening"
        assert await h.session._stuck(b"capture", "boucle") is None, "rien hors d'une étape de l'agent"


async def test_a_question_is_answered_without_buying_anything():
    async with Harness() as h:
        await h.text("À quelle heure ferme la pharmacie de la gare ?")
        await h.wait_said("ferme à 20 heures")
        assert h.paid == 0 and "cart" not in h.states()
        await h.wait("listening")


def test_same_order_ignores_wording_but_not_price():
    from orchestrator.contracts import OrderSummary
    from orchestrator.session import same_order

    from .test_contracts import VALID, _load

    base = OrderSummary.model_validate(_load(next(p for p in VALID if p.name == "order-summary-train.json")))
    reworded = base.model_copy(
        update={
            "items": [i.model_copy(update={"name": i.name + " (direct)"}) for i in base.items],
            "hash": "0" * 64,
        }
    )
    assert same_order(base, reworded), "un libellé différent n'est pas un changement de prix"
    assert not same_order(base, base.model_copy(update={"total_cents": base.total_cents + 1}))
    more = base.model_copy(update={"items": [i.model_copy(update={"quantity": 2}) for i in base.items]})
    assert not same_order(base, more)


@pytest.mark.parametrize(
    ("state", "text", "kind", "index"),
    [
        ("proposing", "La deuxième", "choose", 2),
        ("proposing", "le 3", "choose", 3),
        ("proposing", "je prends le premier s'il vous plaît", "choose", 1),
        ("proposing", "les détails du 2", "details", 2),
        ("confirm_1", "Oui, d'accord.", "confirm", None),
        ("confirm_2", "Non merci", "deny", None),
        ("searching", "Annule", "cancel", None),
    ],
)
def test_quick_intent_understands_short_answers(state, text, kind, index):
    from orchestrator.session import quick_intent

    intent = quick_intent(state, text)
    assert intent is not None and intent.kind == kind and intent.choice_index == index


@pytest.mark.parametrize(
    ("state", "text"),
    [
        ("proposing", "plutôt un train plus tôt"),  # pas un numéro : le modèle s'en charge
        ("proposing", "le 1 ou le 2, je ne sais pas"),  # deux numéros : ambigu
        ("confirm_1", "c'est combien déjà ?"),
        ("listening", "un train pour Lille"),
    ],
)
def test_quick_intent_leaves_the_rest_to_the_model(state, text):
    from orchestrator.session import quick_intent

    assert quick_intent(state, text) is None


async def test_repeating_the_same_request_does_not_search_again():
    async with Harness() as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        searches = len(h.agents)
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await _until(lambda: h.said().count("J'ai trouvé") == 2, 5)
        assert len(h.agents) == searches, "pas de nouvelle recherche pour la même demande"
        await h.session.receive({"type": "cancel"})


def test_pilote_repeats_what_it_understood_before_searching():
    from orchestrator.contracts import When
    from orchestrator.session import _intent, describe_request

    intent = _intent("new_request", "train").model_copy(
        update={
            "category": "train",
            "details": {"origin": "Paris", "destination": "Lille"},
            "when": When(date=TODAY + dt.timedelta(days=1), after="14:00", before=None, asap=False),
        }
    )
    expected = "Je cherche un train de Paris à Lille demain, jeudi 19 novembre après 14:00."
    assert describe_request(intent, TODAY).startswith(expected)


async def test_a_correction_updates_the_whole_request_sent_to_the_agent():
    async with Harness() as h:
        await h.text("Un train de Paris pour Lille ce soir")
        await h.wait("proposing")
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await _until(lambda: h.said().count("J'ai trouvé") == 2, 5)
        assert h.session._intent.when.date == TODAY + dt.timedelta(days=1)
        assert h.agents[0]._intent.when.date == TODAY + dt.timedelta(days=1), "l'agent a la demande à jour"
        assert "demain, jeudi 19 novembre" in h.said()
        await h.session.receive({"type": "cancel"})


async def test_pilote_says_clearly_that_the_order_is_finished():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        await _to_code_prompt(h)
        await h.text("472")
        await h.wait_said("C'est terminé.")
        assert "C'est acheté" in h.said()


async def test_lost_contact_after_payment_approval_never_says_nothing_was_bought():
    from orchestrator.agent_h.base import AgentError
    from orchestrator.session import UNSURE

    async with Harness(direct_buy=True, purchase_code="472") as h:
        # Le code se demande au bouton de paiement, pendant buy() : l'agent est remplacé avant le choix
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        agent = h.agents[-1]

        async def buy_then_lose_contact():
            summary = await agent.checkout()
            assert await h.session.approve_payment(summary) == "approved"
            raise AgentError("coupure réseau avec H")

        agent.buy = buy_then_lose_contact  # type: ignore[method-assign]
        await h.text("La deuxième")
        await h.wait("confirm_1")
        assert "dites votre code à 3 chiffres" in h.said()
        await h.text("472")
        await h.wait_said("Je ne sais pas si l'achat est passé")
        assert UNSURE in h.said() and "Rien n'a été acheté" not in h.said()


async def test_incomplete_question_asks_for_the_missing_detail_then_merges_the_answer():
    async with Harness() as h:
        asked: list[str] = []

        async def prepare(question, history=None):
            asked.append(question)
            if "précision" not in question:
                return {"action": "ask", "say": "Pour aller où, et depuis quelle ville ?"}
            return {"action": "search", "question": "temps de trajet Paris Lyon en train"}

        h.session.ai.prepare_question = prepare  # type: ignore[method-assign]
        await h.text("Combien de temps je mets pour aller ?")
        await h.wait_said("Pour aller où")
        assert "searching" not in h.states(), "pas de recherche web sur une question incomplète"
        await h.wait("listening")
        await h.text("De Paris à Lyon")
        await h.wait_said("Je cherche la réponse")
        assert any("précision : De Paris à Lyon" in q for q in asked)


async def test_agent_is_prepared_while_pilote_asks_and_reused_for_the_search(monkeypatch):
    prepared: list[Any] = []

    async def prepare(self, intent):
        prepared.append(intent)

    monkeypatch.setattr(FakeShoppingAgent, "prepare", prepare, raising=False)
    async with Harness() as h:
        await h.text("Je veux un train pour Lille demain")
        await h.wait_said("De quelle ville partez-vous ?")
        await _until(lambda: prepared, 2)
        assert prepared[0].category == "train", "le Chrome de l'agent se prépare pendant la question"
        await h.wait("listening")
        await h.text("Paris")
        await h.wait("proposing")
        assert len(h.agents) == 1, "l'agent préparé fait la recherche"
        assert h.agents[0]._intent.details == {"destination": "Lille", "origin": "Paris"}


async def test_a_waiting_h_session_is_started_before_the_request_and_reused(monkeypatch):
    warmed: list[bool] = []

    async def warm(self):
        warmed.append(True)

    monkeypatch.setattr(FakeShoppingAgent, "warm", warm, raising=False)
    h = Harness()
    h.session.agent_factory.can_warm = True  # type: ignore[attr-defined]
    async with h:
        await _until(lambda: warmed, 2)
        assert len(h.agents) == 1, "agent préparé dès l'écoute, avant toute demande"
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        assert len(h.agents) == 1, "la session d'attente fait la recherche"


async def test_agent_opens_while_pilote_restates_the_request():
    """Chrome et la session H s'ouvrent pendant que Pilote parle, pas après."""
    marks: dict[str, float] = {}
    now = lambda: asyncio.get_running_loop().time()  # noqa: E731
    async with Harness() as h:
        speak, factory = h.session.ai.speak, h.session.agent_factory

        async def slow_speak(text: str):
            if "annule" in text:  # la phrase qui redit la demande avant la recherche
                await asyncio.sleep(0.3)
                marks.setdefault("said", now())
            return await speak(text)

        def spying_factory(approve, need_human):
            agent = factory(approve, need_human)
            start = agent.start

            async def timed_start(*args):
                marks.setdefault("agent", now())
                return await start(*args)

            agent.start = timed_start
            return agent

        h.session.ai.speak = slow_speak  # type: ignore[method-assign]
        h.session.agent_factory = spying_factory
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
    assert marks["agent"] < marks["said"]  # l'agent a démarré avant la fin de la phrase


async def test_journal_says_why_and_where_an_order_ended(tmp_path):
    journal = tmp_path / "journal.jsonl"
    async with Harness(agent={"speed": 1}, journal_path=str(journal)) as h:
        await h.text("Un train de Paris pour Lille demain")
        await h.wait("searching")
        await h.session.receive({"type": "cancel"})
        await h.wait("listening", limit_s=2)
    ends = [json.loads(line) for line in journal.read_text().splitlines() if '"end"' in line]
    last = ends[-1]
    assert last["outcome"] == "cancelled" and last["code"] == "user_cancel"
    assert last["state_before"] == "searching" and last["step"] in ("start", "search")
    assert isinstance(last["seconds"], int)
    assert "Rien" not in json.dumps(last)  # jamais la phrase dite


def test_answer_for_speech_says_the_source_simply():
    from orchestrator.session import answer_for_speech

    said = answer_for_speech("La tour ferme à 23 heures. (Source : toureiffel.paris (site officiel).)")
    assert said == "La tour ferme à 23 heures. C'est d'après toureiffel.paris."
    assert answer_for_speech("Réponse sans source.") == "Réponse sans source."


def test_describe_has_no_repeated_information():
    from orchestrator.contracts import Option

    option = Option(
        id="o2",
        rank=2,
        title="TGV INOUI 09:00 → 10:56 Lyon Part Dieu",
        price_cents=6900,
        currency="EUR",
        rating=None,
        description="Direct, 1h56, TGV INOUI.",
        conditions=None,
        details={"departure": "09:00", "arrival": "10:56", "duration": "1h56", "stops": "Direct"},
        url=None,
    )
    said = Session._describe(option)
    assert said.count("1h56") == 1 and said.count("09:00") == 1 and ".." not in said


async def test_repeat_rereads_the_options_and_a_new_screen_gets_no_stale_options():
    async with Harness() as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        before = h.said().count("14")
        await h.text("Répète les options s'il te plaît")
        await _until(lambda: h.said().count("14") > before, 5)
        assert "entre 1 et" not in h.said()  # pas « Dites le numéro de l'option, entre 1 et 3 »
        await h.session.receive({"type": "cancel"})
        await h.wait("listening")
        late: list[dict[str, Any]] = []

        async def collect(data: dict[str, Any]) -> None:
            late.append(data)

        await h.session.attach(collect)
        assert not [m for m in late if m["type"] in ("options", "summary")]


async def test_everything_missing_is_asked_in_one_question_and_answered_in_one_sentence():
    async with Harness() as h:
        await h.text("Je voudrais un billet de train")
        await h.wait_said("De quelle ville partez-vous, pour quelle ville, et quel jour ?")
        await h.text("Un train de Paris pour Lille demain")  # l'IA factice ne comprend qu'avec « train »
        await h.wait("proposing")


async def test_a_screen_opened_midway_gets_the_recent_conversation_before_the_state():
    async with Harness() as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        late: list[dict[str, Any]] = []

        async def collect(data: dict[str, Any]) -> None:
            WS.validate(data)
            late.append(data)

        await h.session.attach(collect)
        kinds = [m["type"] for m in late]
        assert kinds[0] == "ready" and "transcript" in kinds
        assert kinds.index("transcript") < kinds.index("state")  # rejoué avant l'état courant
        assert any("Paris pour Lille" in m["text"] for m in late if m["type"] == "transcript")

        assert "confirm_2" not in h.states()


# --- carte dictée quand le site n'en a pas d'enregistrée ------------------------------

VISA_TEST = "4111111111111111"  # numéro de test public


async def _dictate_card(h: Harness, save: bool) -> None:
    await h.text("Un train de Paris pour Lille demain après 14 h")
    await h.wait("proposing")
    await h.text("La deuxième")
    await h.wait("confirm_1")
    await h.confirm(True)  # « J'achète bien … ? »
    await h.wait_said("Dites le numéro de la carte")
    await h.wait("confirm_1")
    await h.text("4111 1111 1111 1111")
    await h.wait_said("La date d'expiration")
    await h.wait("confirm_1")
    await h.text("zéro trois deux sept")
    await h.wait_said("Le cryptogramme")
    await h.wait("confirm_1")
    await h.text("un deux trois")
    await h.wait_said("C'est bien ça ?")
    await h.wait("confirm_1")
    assert "finit par 1 1 1 1" in h.said()
    await h.confirm(True)
    await h.wait_said("Voulez-vous enregistrer cette carte sur SNCF Connect")
    await h.wait("confirm_1")
    await h.confirm(save)


async def test_dictated_card_pays_and_is_saved_on_the_site_only_if_asked(tmp_path):
    journal = tmp_path / "journal.jsonl"
    async with Harness(direct_buy=True, agent={"needs_card": True}, journal_path=str(journal)) as h:
        await _dictate_card(h, save=True)
        await h.wait_said("C'est acheté")
        agent = h.agents[0]
        assert agent.card_used.number == VISA_TEST and agent.card_used.expiry == "0327"
        assert "Votre carte est maintenant enregistrée sur le site." in h.said()
        import json

        shown = json.dumps(h.messages, ensure_ascii=False)
        assert VISA_TEST not in shown and "4111 1111" not in shown, "le numéro ne part vers aucun écran"
        assert all("4111" not in turn["text"] for turn in h.session.history)
        assert "4111" not in journal.read_text() and '"save_on_site": true' in journal.read_text()
        typed = [m["text"] for m in h.of("transcript") if m["role"] == "user"]
        assert typed.count("•••") >= 3


async def test_dictated_card_not_saved_when_the_user_says_no():
    async with Harness(direct_buy=True, agent={"needs_card": True}) as h:
        await _dictate_card(h, save=False)
        await h.wait_said("C'est acheté")
        assert "La carte n'a pas été enregistrée sur le site." in h.said()


async def test_saying_no_instead_of_the_card_number_buys_nothing():
    async with Harness(direct_buy=True, agent={"needs_card": True}) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait("confirm_1")
        await h.confirm(True)
        await h.wait_said("Dites le numéro de la carte")
        await h.wait("confirm_1")
        await h.text("non")
        await h.wait_said("Rien n'a été payé")
        assert "C'est acheté" not in h.said()


# --- achat sur le site choisi par la personne -------------------------------------------


def test_pilote_asks_for_the_site_only_when_needed(monkeypatch):
    from orchestrator.session import Session, _intent

    monkeypatch.delenv("PILOTE_SITE_BOUTIQUE", raising=False)
    shop = _intent("new_request", "un aspirateur Dyson V15").model_copy(
        update={"category": "boutique", "object": "aspirateur Dyson V15"}
    )
    assert Session._needs_site(shop)
    assert not Session._needs_site(shop.model_copy(update={"text": "un aspirateur Dyson V15 chez Darty"}))
    assert not Session._needs_site(shop.model_copy(update={"details": {"site": "Vinted"}}))
    assert not Session._needs_site(shop.model_copy(update={"category": "train"}))


def test_the_answer_to_the_site_question_fills_the_site():
    from orchestrator.agent_h.shops import resolve_site
    from orchestrator.session import _intent

    pending = _intent("new_request", "un pull").model_copy(
        update={"category": "boutique", "object": "pull", "missing": ["details.site"]}
    )
    merged = merge_answer(pending, _intent("other", "Petit Bateau"))
    choice = resolve_site(merged)
    assert choice is not None and choice.name == "Petit Bateau" and choice.lookup


def test_the_site_is_asked_for_a_shop_but_never_for_a_reservation_or_a_train(monkeypatch):
    from orchestrator.session import Session, _intent

    monkeypatch.delenv("PILOTE_SITE_BOUTIQUE", raising=False)
    base = _intent("new_request", "une lampe")
    shop = base.model_copy(update={"category": "boutique", "object": "lampe"})
    assert Session._needs_site(shop) is True
    named = shop.model_copy(update={"text": "une lampe chez Zalando"})
    assert Session._needs_site(named) is False
    table = base.model_copy(update={"category": "reservation", "object": "restaurant italien"})
    assert Session._needs_site(table) is False
    assert Session._needs_site(base.model_copy(update={"category": "train"})) is False


async def test_a_free_ticket_also_needs_a_yes_and_a_no_buys_nothing(monkeypatch):
    """Sans code secret : un billet à 0 € ne s'achète jamais sans un oui, demandé au bouton de paiement."""
    import orchestrator.agent_h.fake as fake

    free = [o.model_copy(update={"price_eur": 0.0}) for o in fake.TRAIN_OPTIONS]
    monkeypatch.setattr(fake, "TRAIN_OPTIONS", free)
    async with Harness(direct_buy=True) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait("confirm_1")
        assert "J'achète bien" in h.said() and "gratuit ?" in h.said()
        await h.confirm(False)
        await h.wait("listening")
        assert "je n'achète rien" in h.said() and "C'est acheté" not in h.said()


# --- nouvelle conversation, et vieille question qui ne se mêle plus aux demandes -------------


def test_reset_phrases_are_recognised_but_not_ordinary_requests():
    from orchestrator.session import wants_reset

    for phrase in (
        "Nouvelle conversation",
        "On recommence à zéro",
        "Efface la conversation",
        "Oublie tout",
        "Remets la conversation à zéro",
        "Mets à jour la conversation",
        "Clear la conversation",
    ):
        assert wants_reset(phrase), phrase
    for phrase in ("Un train de Paris pour Lille demain", "Efface le dernier article", "zéro euro"):
        assert not wants_reset(phrase), phrase


async def test_reset_forgets_the_conversation_but_keeps_the_learned_paths():
    async with Harness() as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        old_id = h.session.session_id
        await h.text("On recommence à zéro")
        await h.wait_said("on repart de zéro")
        assert "rien n'a été acheté" in h.said()
        assert h.session.session_id != old_id, "les écrans vident la conversation"
        assert [t["text"] for t in h.session.history] == [h.session.history[-1]["text"]]
        assert "Paris pour Lille" not in str(h.session._context())
        assert h.paid == 0
        await h.text("Nouvelle conversation")  # rien en cours : pas de « j'ai arrêté »
        await _until(lambda: h.said().count("on repart de zéro") == 2, 5)
        assert h.said().count("rien n'a été acheté") == 1
        await h.text("Un train de Paris pour Lille demain après 14 h")  # Pilote repart normalement
        await h.wait("proposing")


async def test_a_new_train_request_is_not_glued_to_a_question_waiting_for_a_precision(monkeypatch):
    from orchestrator.ai.fake import FakeAI

    async def prepare(self, question, history=None):
        if "(précision :" in question or "CAF" not in question:
            return {"action": "search", "question": question}
        return {"action": "ask", "say": "Quelle CAF : celle de quelle ville ?"}

    monkeypatch.setattr(FakeAI, "prepare_question", prepare)
    async with Harness() as h:
        await h.text("Quels sont les horaires de la CAF ?")
        await h.wait_said("celle de quelle ville")
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")  # le train est cherché, pas « la CAF (précision : un train…) »
        assert all("CAF" not in t["text"] for t in h.session._context())


async def _pay_button_reached_then_hang(h: Harness) -> None:
    """Direct buy : le code est donné, le verrou autorise le clic, puis l'agent ne répond plus."""
    await h.text("Un train de Paris pour Lille demain après 14 h")
    await h.wait("proposing")
    agent = h.agents[-1]

    async def authorised_then_hang():
        summary = await agent.checkout()
        assert await h.session.approve_payment(summary) == "approved"
        await asyncio.sleep(60)

    agent.buy = authorised_then_hang  # type: ignore[method-assign]
    await h.text("La deuxième")
    await h.wait("confirm_1")
    await h.text("472")
    await _until(lambda: h.session._payment_cleared, 5)


async def test_cancelling_after_the_payment_was_authorised_never_says_nothing_was_bought():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        await _pay_button_reached_then_hang(h)
        await h.session.receive({"type": "cancel"})
        await h.wait_said("je ne sais pas si l'achat est passé")
        assert "Rien n'a été acheté" not in h.said()
        assert h.session._payment_cleared is False  # la commande suivante repart de zéro


async def test_resetting_after_the_payment_was_authorised_never_says_nothing_was_bought():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        await _pay_button_reached_then_hang(h)
        await h.text("Nouvelle conversation")
        await h.wait_said("je ne sais pas si l'achat est passé")
        assert "rien n'a été acheté" not in h.said().lower()
        assert h.session._payment_cleared is False


async def test_cancelling_before_any_payment_authorisation_still_says_nothing_was_bought():
    async with Harness() as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.session.receive({"type": "cancel"})
        await h.wait_said("Rien n'a été acheté")


# --- écho : la voix de Pilote captée par le micro ----------------------------------------------


async def _audio(h: Harness, transcript: str, overlapped: bool = False) -> None:
    h.session.ai.transcript = transcript  # type: ignore[attr-defined]
    await h.session.receive({"type": "audio", "data": "AAAA", "mime": "audio/webm", "overlapped": overlapped})
    await asyncio.sleep(0.15)


async def test_pilotes_own_sentence_heard_by_the_microphone_is_ignored_in_silence():
    async with Harness() as h:
        await h.session._say("Je cherche un train de Paris à Lille, demain après quatorze heures.")
        users_before = len([m for m in h.of("transcript") if m["role"] == "user"])
        said_before = h.said()
        await _audio(h, "Je cherche un train de Paris à Lille demain après quatorze heures")
        assert len([m for m in h.of("transcript") if m["role"] == "user"]) == users_before  # pas affiché
        assert (
            h.said() == said_before
        )  # et surtout : aucun « je n'ai pas compris », ce serait un écho de plus
        assert h.session.state == "listening" and h.session._waiting


async def test_a_yes_captured_while_pilote_was_speaking_never_confirms_the_purchase():
    async with Harness(direct_buy=True) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait("confirm_1")
        await _audio(h, "oui", overlapped=True)  # l'écho de « dites oui pour confirmer »
        assert "C'est acheté" not in h.said() and h.session.state == "confirm_1"
        await _audio(h, "oui", overlapped=False)  # le vrai « oui », après la fin de la phrase
        await h.wait_said("C'est acheté")


async def test_a_code_captured_while_pilote_was_speaking_is_ignored_and_costs_no_attempt():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        await _to_code_prompt(h)
        await _audio(h, "quatre sept deux", overlapped=True)  # même le bon code : il peut venir de Pilote
        assert "C'est acheté" not in h.said() and "pas le bon code" not in h.said()
        await _audio(h, "un un un")  # un vrai mauvais essai : il reste bien 2 essais, aucun n'a été perdu
        await h.wait_said("Encore 2 essais.")
        await _audio(h, "quatre sept deux")
        await h.wait_said("C'est acheté")


async def test_a_short_real_answer_after_pilote_finished_is_still_understood():
    async with Harness() as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await _audio(h, "la deuxième")  # reprend un mot de la phrase des options, mais sans chevauchement
        await h.wait("confirm_1")


# --- redémarrer et annuler ---------------------------------------------------------------------


def test_recommence_alone_restarts_but_a_longer_request_does_not():
    from orchestrator.session import wants_reset

    for phrase in (
        "Recommence",
        "On recommence",
        "Recommence tout",
        "Tout recommencer",
        "On repart",
        "Repartons !",
    ):
        assert wants_reset(phrase), phrase
    for phrase in (
        "Recommence la recherche avec un train plus tôt",
        "Je veux recommencer avec un autre billet",
        "Un train pour Lille",
    ):
        assert not wants_reset(phrase), phrase


async def test_cancel_during_a_long_search_does_not_wait_for_the_language_model():
    async with Harness(agent={"speed": 1}) as h:  # la recherche factice dure 6 s
        asked: list[str] = []
        original = h.session.ai.parse_intent

        async def spy(text, today, history):
            asked.append(text)
            return await original(text, today, history)

        h.session.ai.parse_intent = spy  # type: ignore[method-assign]
        await h.text("Un train de Paris pour Lille demain")
        await h.wait("searching")
        await h.text("Annule")
        await h.wait("listening", limit_s=2)
        assert "cancelled" in h.states()
        assert not any("nnule" in t for t in asked)  # compris tout de suite, sans appeler le modèle


async def test_a_reset_phrase_works_even_while_the_code_is_being_asked():
    async with Harness(direct_buy=True, purchase_code="472") as h:
        await _to_code_prompt(h)
        await h.text("On recommence")
        await h.wait_said("on repart de zéro")
        assert "C'est acheté" not in h.said() and h.session._secret_mode is False
