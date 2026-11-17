"""Client de l'API de validation des proches (web/app/api/approvals, membre 3).

HttpApprovals parle à la vraie API (Vercel ou localhost). FakeApprovals répond seule, sans SMS,
pour développer et tester tant que la partie 3 n'existe pas (USE_FAKE_APPROVALS=1).
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx

from orchestrator.config import Settings
from orchestrator.contracts import ApprovalRequest, ApprovalStatus
from orchestrator.ports import Approvals

log = logging.getLogger(__name__)


class ApprovalsError(RuntimeError):
    """Le service de validation n'a pas répondu correctement. Toujours traité comme un refus."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class HttpApprovals:
    def __init__(self, base_url: str, secret: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {secret}"}

    async def _call(self, method: str, path: str, **kwargs: object) -> ApprovalStatus:
        try:
            response = await self._client.request(method, self._base + path, headers=self._headers, **kwargs)
        except httpx.HTTPError as error:
            raise ApprovalsError(f"{method} {path} : {error}") from error
        if response.status_code >= 400:
            raise ApprovalsError(f"{method} {path} : HTTP {response.status_code}")
        try:
            return ApprovalStatus.model_validate(response.json())
        except ValueError as error:  # JSON illisible ou hors contrat
            raise ApprovalsError(f"{method} {path} : réponse hors contrat") from error

    async def create(self, request: ApprovalRequest) -> ApprovalStatus:
        return await self._call("POST", "/api/approvals", json=request.model_dump(mode="json"))

    async def get(self, order_id: str) -> ApprovalStatus:
        return await self._call("GET", f"/api/approvals/{order_id}")


@dataclass
class _Pending:
    request: ApprovalRequest
    created: float


class FakeApprovals:
    """Répond `decision` au bout de `delay_s` secondes, comme si le proche n° 1 avait répondu."""

    def __init__(
        self,
        decision: Literal["approved", "denied", "expired"] = "approved",
        delay_s: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.decision = decision
        self.delay_s = delay_s
        self._clock = clock
        self.requests: dict[str, _Pending] = {}

    def _status(self, pending: _Pending) -> ApprovalStatus:
        request = pending.request
        count = len(request.relatives)
        now = _now()
        if self._clock() - pending.created < self.delay_s:
            return ApprovalStatus(
                order_id=request.order_id,
                status="pending",
                current_relative=1,
                relatives_count=count,
                decided_by=None,
                decided_at=None,
                expires_at=now + dt.timedelta(seconds=request.timeout_seconds),
                updated_at=now,
            )
        decided = self.decision != "expired"
        return ApprovalStatus(
            order_id=request.order_id,
            status=self.decision,
            current_relative=None,
            relatives_count=count,
            decided_by=request.relatives[0].first_name if decided else None,
            decided_at=now if decided else None,
            expires_at=None,
            updated_at=now,
        )

    async def create(self, request: ApprovalRequest) -> ApprovalStatus:
        log.warning("Validation FACTICE : aucun SMS envoyé.")
        pending = self.requests.setdefault(request.order_id, _Pending(request, self._clock()))
        return self._status(pending)

    async def get(self, order_id: str) -> ApprovalStatus:
        pending = self.requests.get(order_id)
        if pending is None:
            raise ApprovalsError(f"Demande inconnue : {order_id}")
        return self._status(pending)


def build_approvals(settings: Settings) -> Approvals:
    if settings.use_fake_approvals:
        return FakeApprovals(settings.fake_approval_decision, settings.fake_approval_delay_s)  # type: ignore[arg-type]
    if not settings.approvals_api_url or not settings.shared_secret:
        raise ValueError("USE_FAKE_APPROVALS=0 demande APPROVALS_API_URL et PILOTE_SHARED_SECRET")
    return HttpApprovals(settings.approvals_api_url, settings.shared_secret)
