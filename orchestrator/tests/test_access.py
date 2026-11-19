import datetime as dt

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from orchestrator.access import (
    Access,
    FailureLimiter,
    access_from_env,
    bearer_token,
    pairing_link,
    token_from_protocols,
)
from orchestrator.agent_h.fake import FakeShoppingAgent
from orchestrator.ai.fake import FakeAI
from orchestrator.app import create_app
from orchestrator.config import Settings
from orchestrator.session import Session

TOKEN = "t" * 32
VERCEL = "https://pilote-demo.vercel.app"


def _session() -> Session:
    return Session(
        ai=FakeAI(),
        agent_factory=lambda approve, human: FakeShoppingAgent(
            approval_callback=approve, need_human_callback=human, speed=0
        ),
        settings=Settings(journal_path=None),
        today=lambda: dt.date(2026, 11, 19),
    )


def _client(**kwargs) -> TestClient:
    return TestClient(create_app(_session, access=Access(token=TOKEN, allowed_origins=(VERCEL,), **kwargs)))


def _protocols(token: str) -> list[str]:
    return ["pilote", f"token.{token}"]


# --- réglages ------------------------------------------------------------------------------------


def test_nothing_is_required_while_the_server_only_listens_to_this_machine():
    for env in ({}, {"PILOTE_HOST": "127.0.0.1"}, {"PILOTE_HOST": "localhost"}, {"PILOTE_HOST": "::1"}):
        access = access_from_env(env)
        assert not access.required and access.accepts(None)  # comme avant : rien ne change en local


def test_a_server_reachable_from_elsewhere_never_runs_without_a_token():
    access = access_from_env({"PILOTE_HOST": "0.0.0.0"})
    assert access.required and access.generated and access.token and len(access.token) >= 32
    assert access_from_env({"PILOTE_HOST": "0.0.0.0"}).token != access.token  # tiré au hasard à chaque fois


def test_a_chosen_token_is_used_as_is_and_must_be_long_enough():
    access = access_from_env({"PILOTE_TOKEN": TOKEN})
    assert access.token == TOKEN and access.required and not access.generated
    with pytest.raises(ValueError):
        access_from_env({"PILOTE_TOKEN": "court"})


def test_allowed_origins_are_listed_without_trailing_slashes():
    access = access_from_env(
        {"PILOTE_TOKEN": TOKEN, "PILOTE_ALLOWED_ORIGINS": f"{VERCEL}/, https://autre.example"}
    )
    assert access.allowed_origins == (VERCEL, "https://autre.example")


def test_origins_local_or_listed_pass_and_others_do_not():
    access = Access(token=TOKEN, allowed_origins=(VERCEL,))
    assert access.origin_allowed("http://localhost:3000") and access.origin_allowed(VERCEL)
    assert access.origin_allowed(None)  # pas un navigateur : le jeton suffit
    assert not access.origin_allowed("https://pirate.example")
    assert Access().origin_allowed("https://pirate.example")  # sans jeton exigé, aucune restriction (local)


def test_the_token_travels_in_the_protocol_header_and_the_bearer_header():
    assert token_from_protocols("pilote, token.abc123") == ("abc123", "pilote")
    assert token_from_protocols("pilote") == (None, "pilote")
    assert token_from_protocols(None) == (None, None)
    assert bearer_token("Bearer abc") == "abc" and bearer_token("bearer abc") == "abc"
    assert (
        bearer_token("Basic abc") is None and bearer_token(None) is None and bearer_token("Bearer ") is None
    )


def test_the_pairing_link_keeps_the_token_in_the_fragment():
    link = pairing_link(f"{VERCEL}/", "wss://x.example/ws", TOKEN)
    assert link.startswith(f"{VERCEL}/#server=wss%3A%2F%2Fx.example%2Fws&token=")
    assert "?" not in link and link.endswith(TOKEN)


def test_too_many_wrong_tokens_are_refused_at_once_but_the_right_one_still_passes():
    now = [0.0]
    access = Access(token=TOKEN, limiter=FailureLimiter(limit=3, window_s=60, clock=lambda: now[0]))
    for _ in range(3):
        assert not access.accepts("faux")
    assert access.blocked and not access.accepts("faux")
    assert access.accepts(TOKEN)  # la bonne personne n'est jamais bloquée
    now[0] = 61
    assert not access.blocked  # la fenêtre passe


# --- le serveur ----------------------------------------------------------------------------------


def _refusal_code(client: TestClient, protocols: list[str], headers: dict[str, str] | None = None) -> int:
    """Le serveur accepte puis ferme avec un code : l'interface sait ainsi pourquoi elle est refusée."""
    with client.websocket_connect("/ws", subprotocols=protocols, headers=headers or {}) as ws:
        with pytest.raises(WebSocketDisconnect) as refused:
            ws.receive_json()
        return refused.value.code


def test_a_phone_without_the_token_cannot_use_the_websocket():
    with _client() as client:
        for protocols in ([], ["pilote"], _protocols("x" * 32)):
            assert _refusal_code(client, protocols) == 4401


def test_the_right_token_opens_the_websocket_and_the_page_is_welcomed():
    with _client() as client, client.websocket_connect("/ws", subprotocols=_protocols(TOKEN)) as ws:
        assert ws.receive_json()["type"] == "ready"
        assert ws.accepted_subprotocol == "pilote"


def test_a_page_from_an_unknown_site_is_refused_even_with_the_right_token():
    with _client() as client:
        assert _refusal_code(client, _protocols(TOKEN), {"origin": "https://pirate.example"}) == 4403
        with client.websocket_connect(
            "/ws", subprotocols=_protocols(TOKEN), headers={"origin": VERCEL}
        ) as ws:  # la page Vercel autorisée passe
            assert ws.receive_json()["type"] == "ready"


def test_too_many_wrong_tokens_get_the_blocked_code_but_the_right_one_still_opens():
    with _client(limiter=FailureLimiter(limit=3)) as client:
        codes = [_refusal_code(client, _protocols("x" * 32)) for _ in range(5)]
        # la limite est de 3 : le 3e essai raté la atteint, et déjà on dit « bloqué »
        assert codes == [4401, 4401, 4429, 4429, 4429]
        with client.websocket_connect("/ws", subprotocols=_protocols(TOKEN)) as ws:
            assert ws.receive_json()["type"] == "ready"


def test_voice_and_health_need_the_token_when_one_is_required():
    with _client() as client:
        assert client.get("/voice").status_code == 401
        assert client.post("/voice", json={"name": "jerem"}).status_code == 401
        assert client.get("/voice", headers={"Authorization": "Bearer faux"}).status_code == 401
        assert client.get("/voice", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
        assert client.get("/health").json() == {"ok": True}  # répond, sans rien dire de plus
        assert client.get("/health", headers={"Authorization": f"Bearer {TOKEN}"}).json()["fake_ai"] is True


def test_cors_lets_the_vercel_page_send_the_authorization_header():
    with _client() as client:
        answer = client.options(
            "/voice",
            headers={
                "Origin": VERCEL,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert answer.headers["access-control-allow-origin"] == VERCEL
        assert "authorization" in answer.headers["access-control-allow-headers"].lower()
        other = client.options(
            "/voice",
            headers={"Origin": "https://pirate.example", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in other.headers


def test_nothing_changes_for_the_local_default():
    with TestClient(create_app(_session)) as client:  # pas de jeton exigé
        assert client.get("/voice").status_code == 200
        assert client.get("/health").json()["fake_ai"] is True
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "ready"
