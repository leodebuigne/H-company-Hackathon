"""Parcours complets de la machine à états, avec les versions factices de l'IA, de l'agent et des proches.

Chaque message envoyé aux écrans est vérifié contre contracts/schemas/ws-message.schema.json.
"""

import asyncio
import datetime as dt
from typing import Any

import pytest

from orchestrator.agent_h.fake import FakeShoppingAgent
from orchestrator.ai.fake import FakeAI
from orchestrator.approvals import FakeApprovals
from orchestrator.config import Settings
from orchestrator.contracts import Relative
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
        approvals: FakeApprovals | None = None,
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

        self.approvals = approvals or FakeApprovals("approved", delay_s=0)
        config = {
            "poll_interval_s": 0.01,
            "journal_path": None,
            "confirm_timeout_s": 5,
            "human_timeout_s": 5,
            **settings,
        }
        self.session = Session(
            ai=FakeAI(),
            agent_factory=factory,
            approvals=self.approvals,
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


async def test_full_order_with_triple_check():
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
            "confirm_1", "awaiting_relative", "recheck", "confirm_2", "understanding", "paying",
            "done", "listening",
        ]  # fmt: skip
        assert h.states() == expected
        assert h.of("approval")[-1]["status"]["status"] == "approved"
        assert "Léa a validé" in h.said() and "Le paiement est accepté" in h.said()


async def test_missing_information_is_asked_then_merged():
    async with Harness() as h:
        await h.text("Je veux un train pour Lille demain")
        await h.wait_said("De quelle ville partez-vous ?")
        await h.wait("listening")
        await h.text("Paris")
        await h.wait("proposing")
        assert h.agents[0]._intent.details == {"destination": "Lille", "origin": "Paris"}


async def test_first_no_buys_nothing_and_asks_no_relative():
    async with Harness() as h:
        await _to_confirm_1(h)
        await h.confirm(False)
        await h.wait("listening")
        assert h.approvals.requests == {} and h.paid == 0
        assert "cancelled" in h.states()


@pytest.mark.parametrize(
    ("decision", "spoken"), [("denied", "Léa a refusé"), ("expired", "Personne n'a répondu")]
)
async def test_relative_refusal_or_silence_buys_nothing(decision, spoken):
    async with Harness(approvals=FakeApprovals(decision, delay_s=0)) as h:
        await _to_confirm_1(h)
        await h.confirm(True)
        await h.wait("listening")
        assert h.paid == 0 and spoken in h.said()
        assert "confirm_2" not in h.states()


async def test_price_change_on_recheck_cancels():
    async with Harness(agent={"price_change_on_recheck": True}) as h:
        await _to_confirm_1(h)
        await h.confirm(True)
        await h.wait("listening")
        assert h.paid == 0
        assert h.of("error")[-1]["code"] == "price_changed"
        assert "La page a changé depuis la validation" in h.said()


async def test_cancel_message_stops_a_long_search():
    async with Harness(agent={"speed": 1}) as h:  # la recherche factice dure 6 s
        await h.text("Un train de Paris pour Lille demain")
        await h.wait("searching")
        await h.session.receive({"type": "cancel"})
        await h.wait("listening", limit_s=2)
        assert "cancelled" in h.states() and "Rien n'a été acheté" in h.said()


async def test_spoken_cancel_while_waiting_for_relative():
    async with Harness(approvals=FakeApprovals("approved", delay_s=60)) as h:
        await _to_confirm_1(h)
        await h.confirm(True)
        await h.wait("awaiting_relative")
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


async def test_no_relative_configured_with_real_approvals():
    async with Harness(use_fake_approvals=False) as h:
        await h.text("Un train de Paris pour Lille demain")
        await h.wait("proposing")
        await h.text("La première")
        await h.wait("listening")
        assert h.of("error")[-1]["code"] == "approval_failed" and h.paid == 0


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


def test_relatives_for_fake_and_real():
    assert (
        Settings(relatives=(Relative(first_name="Hugo", phone="+33600000002"),))
        .relatives_for_approval()[0]
        .first_name
        == "Hugo"
    )
