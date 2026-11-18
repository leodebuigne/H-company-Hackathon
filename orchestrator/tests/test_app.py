"""Le serveur de bout en bout : une vraie connexion WebSocket, les briques factices, un parcours texte."""

import datetime as dt

from fastapi.testclient import TestClient

from orchestrator.agent_h.fake import FakeShoppingAgent
from orchestrator.ai.fake import FakeAI
from orchestrator.app import create_app
from orchestrator.config import Settings
from orchestrator.session import Session

from .test_contracts import _validator

WS = _validator("ws-message.schema.json")


def _session() -> Session:
    return Session(
        ai=FakeAI(),
        agent_factory=lambda approve, human: FakeShoppingAgent(
            approval_callback=approve, need_human_callback=human, speed=0
        ),
        settings=Settings(journal_path=None),
        today=lambda: dt.date(2026, 11, 18),
    )


def _until(ws, predicate, limit: int = 200) -> list[dict]:
    seen = []
    for _ in range(limit):
        message = ws.receive_json()
        WS.validate(message)
        seen.append(message)
        if predicate(message):
            return seen
    raise AssertionError(f"jamais reçu, derniers messages : {seen[-5:]}")


def _state(name: str):
    return lambda m: m["type"] == "state" and m["state"] == name


def test_health_and_full_text_order_over_websocket():
    with TestClient(create_app(_session)) as client:
        assert client.get("/health").json()["fake_agent"] is True
        with client.websocket_connect("/ws") as ws:
            first = _until(ws, lambda m: m["type"] == "say")
            assert first[0]["type"] == "ready"
            assert first[-1]["text"].startswith("Je suis Pilote, un assistant automatique")
            ws.send_json({"type": "text", "text": "Un train de Paris pour Lille demain après 14 h"})
            seen = _until(ws, _state("proposing"))
            assert any(m["type"] == "options" for m in seen)
            ws.send_json({"type": "text", "text": "La première"})
            _until(ws, _state("confirm_1"))
            ws.send_json({"type": "confirm", "value": True})
            _until(ws, _state("confirm_2"))
            ws.send_json({"type": "confirm", "value": True})
            seen = _until(ws, _state("listening"))
            assert any(m["type"] == "state" and m["state"] == "done" for m in seen)
            ws.send_json("pas un objet")  # ignoré, la connexion reste ouverte
            ws.send_json({"type": "cancel"})
            _until(ws, _state("listening"))


def test_two_screens_share_one_session():
    with TestClient(create_app(_session)) as client:
        with client.websocket_connect("/ws") as main, client.websocket_connect("/ws") as jury:
            _until(main, lambda m: m["type"] == "say")
            _until(jury, lambda m: m["type"] == "say")
            main.send_json({"type": "text", "text": "Un train de Paris pour Lille demain"})
            _until(jury, _state("proposing"))
