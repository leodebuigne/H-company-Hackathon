import json

import httpx
import pytest

from orchestrator.approvals import ApprovalsError, FakeApprovals, HttpApprovals, build_approvals
from orchestrator.config import FAKE_RELATIVE, Settings, parse_relatives
from orchestrator.contracts import ApprovalRequest

from .test_contracts import VALID, _load


def _example(name: str) -> dict:
    return _load(next(p for p in VALID if p.name == name))


REQUEST = ApprovalRequest.model_validate(_example("approval-request-repas.json"))
STATUS = _example("approval-status-approved.json")


def test_parse_relatives():
    relatives = parse_relatives(" Léa:+33600000001, Hugo : +33 6 00 00 00 02 ,")
    assert [(r.first_name, r.phone) for r in relatives] == [("Léa", "+33600000001"), ("Hugo", "+33600000002")]
    assert parse_relatives("") == ()


FOUR = "A:+33600000001,B:+33600000002,C:+33600000003,D:+33600000004"


@pytest.mark.parametrize("raw", ["Léa", "Léa:0600000001", FOUR])
def test_parse_relatives_rejects(raw):
    with pytest.raises(ValueError):
        parse_relatives(raw)


def test_settings_default_to_fakes():
    s = Settings.from_env({})
    assert (s.use_fake_agent, s.use_fake_ai, s.use_fake_approvals) == (True, True, True)
    assert s.relatives_for_approval() == (FAKE_RELATIVE,)


def test_settings_real_needs_relatives_and_bounds_timeouts():
    s = Settings.from_env(
        {"USE_FAKE_APPROVALS": "0", "APPROVAL_TIMEOUT_SECONDS": "900", "APPROVAL_TIMEOUT_SECONDS_REPAS": "5"}
    )
    assert s.relatives_for_approval() == ()
    assert s.approval_timeout("train") == 300
    assert s.approval_timeout("repas") == 10
    with pytest.raises(ValueError):
        build_approvals(s)  # ni URL ni secret


async def test_fake_approvals_pending_then_decision():
    t = [0.0]
    fake = FakeApprovals("denied", delay_s=5, clock=lambda: t[0])
    first = await fake.create(REQUEST)
    assert first.status == "pending" and first.current_relative == 1
    t[0] = 6
    final = await fake.get(REQUEST.order_id)
    assert final.status == "denied" and final.decided_by == "Léa" and final.is_final
    with pytest.raises(ApprovalsError):
        await fake.get("00000000-0000-4000-8000-000000000000")


async def test_http_approvals_sends_secret_and_contract():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=STATUS)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api = HttpApprovals("https://pilote.example/", "s3cret", client)
    created = await api.create(REQUEST)
    got = await api.get(REQUEST.order_id)
    assert created.status == got.status == "approved"
    assert seen[0].method == "POST" and seen[0].url.path == "/api/approvals"
    assert seen[0].headers["authorization"] == "Bearer s3cret"
    assert json.loads(seen[0].content)["order_id"] == REQUEST.order_id
    assert seen[1].url.path == f"/api/approvals/{REQUEST.order_id}"


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, json={"status": "maybe"}), httpx.Response(200, text="oops")],
)
async def test_http_approvals_errors_become_approvals_error(response):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response))
    with pytest.raises(ApprovalsError):
        await HttpApprovals("https://x", "s", client).get(REQUEST.order_id)


def test_purchase_code_must_be_three_digits():
    import pytest as _pytest

    from orchestrator.config import Settings

    assert Settings.from_env({"PILOTE_PURCHASE_CODE": " 472 "}).purchase_code == "472"
    assert Settings.from_env({}).purchase_code is None
    with _pytest.raises(ValueError):
        Settings.from_env({"PILOTE_PURCHASE_CODE": "12a"})
