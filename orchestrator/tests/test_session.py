"""Parcours complets de la machine à états, avec les versions factices de l'IA et de l'agent.

Chaque message envoyé aux écrans est vérifié contre contracts/schemas/ws-message.schema.json.
"""

import asyncio
import datetime as dt
import json
from typing import Any

import pytest

from orchestrator.agent_h.fake import FakeShoppingAgent
from orchestrator.ai.fake import FakeAI
from orchestrator.config import Settings
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


async def test_direct_buy_refuses_a_cart_more_expensive_than_the_choice():
    async with Harness(direct_buy=True, agent={"price_change_on_recheck": True}) as h:
        await h.text("Un train de Paris pour Lille demain après 14 h")
        await h.wait("proposing")
        await h.text("La deuxième")
        await h.wait("confirm_1")
        await h.confirm(True)
        await h.wait_said("Je n'ai pas acheté")
        assert "au lieu de" in h.said() and "C'est acheté" not in h.said()


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
        await _to_code_prompt(h)
        agent = h.agents[-1]

        async def buy_then_lose_contact():
            summary = await agent.checkout()
            assert await h.session.approve_payment(summary) == "approved"
            raise AgentError("coupure réseau avec H")

        agent.buy = buy_then_lose_contact  # type: ignore[method-assign]
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
