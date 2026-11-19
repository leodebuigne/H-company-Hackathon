"""Accès à l'orchestrateur : qui a le droit de lui parler (jeton d'appairage, origines, essais ratés).

L'orchestrateur pilote le Chrome de la machine, avec les comptes qui y sont connectés : quiconque lui parle
peut commander, annuler, confirmer. Tant qu'il n'écoute que `127.0.0.1`, seule la machine y accède et rien
n'est exigé (comme avant). Dès qu'il est joignable d'ailleurs (téléphone par un tunnel https, réseau local),
un jeton est obligatoire :

- `PILOTE_TOKEN` (au moins 24 caractères) le fixe ; sinon il est tiré au hasard au démarrage ;
- l'interface le présente dans le sous-protocole du WebSocket (jamais dans l'adresse, qui finit dans les
  journaux) et en en-tête `Authorization: Bearer` pour `/voice` et `/health` ;
- `PILOTE_ALLOWED_ORIGINS` : pages autorisées en plus de localhost (par exemple l'interface sur Vercel) ;
- trop d'essais ratés d'affilée : les jetons faux sont refusés d'emblée pendant une minute.
"""

from __future__ import annotations

import hmac
import secrets
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlparse

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MIN_TOKEN_CHARS = 24
WS_PROTOCOL = "pilote"
WS_TOKEN_PREFIX = "token."


class FailureLimiter:
    """Compte les essais ratés récents : au-delà de `limit` en `window_s` secondes, on refuse d'emblée."""

    def __init__(
        self, limit: int = 10, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit, self.window_s, self._clock = limit, window_s, clock
        self._failures: deque[float] = deque()

    def _forget_old(self) -> None:
        now = self._clock()
        while self._failures and now - self._failures[0] > self.window_s:
            self._failures.popleft()

    def failed(self) -> None:
        self._forget_old()
        self._failures.append(self._clock())

    def blocked(self) -> bool:
        self._forget_old()
        return len(self._failures) >= self.limit


@dataclass
class Access:
    token: str | None = None  # None : personne n'a besoin de jeton (machine seule)
    allowed_origins: tuple[str, ...] = ()
    generated: bool = False  # jeton tiré au hasard au démarrage : à montrer une fois
    limiter: FailureLimiter = field(default_factory=FailureLimiter)

    @property
    def required(self) -> bool:
        return self.token is not None

    def accepts(self, provided: str | None) -> bool:
        """Le jeton présenté est le bon ? Comparaison à temps constant. Le bon jeton passe toujours ; un jeton
        faux compte comme raté, et après trop de ratés d'affilée il est refusé d'emblée (voir `blocked`)."""
        if not self.required:
            return True
        if provided and self.token and hmac.compare_digest(provided.encode(), self.token.encode()):
            return True
        if not self.limiter.blocked():
            self.limiter.failed()
        return False

    @property
    def blocked(self) -> bool:
        return self.limiter.blocked()

    def origin_allowed(self, origin: str | None) -> bool:
        """Une page ni locale ni listée ne parle pas à l'orchestrateur (quand un jeton est exigé)."""
        if not self.required or not origin:
            return True  # hors navigateur (pas d'Origin) : le jeton suffit
        host = urlparse(origin).hostname or ""
        return host in LOOPBACK_HOSTS or origin.rstrip("/") in self.allowed_origins


def access_from_env(env: Mapping[str, str]) -> Access:
    host = env.get("PILOTE_HOST", "").strip() or "127.0.0.1"
    token = env.get("PILOTE_TOKEN", "").strip() or None
    if token is not None and len(token) < MIN_TOKEN_CHARS:
        raise ValueError(f"PILOTE_TOKEN : {MIN_TOKEN_CHARS} caractères au moins")
    generated = False
    if token is None and host not in LOOPBACK_HOSTS:
        token, generated = secrets.token_urlsafe(32), True  # joignable d'ailleurs : jamais sans jeton
    origins = tuple(
        o.strip().rstrip("/") for o in env.get("PILOTE_ALLOWED_ORIGINS", "").split(",") if o.strip()
    )
    return Access(token=token, allowed_origins=origins, generated=generated)


def token_from_protocols(header: str | None) -> tuple[str | None, str | None]:
    """« pilote, token.XXXX » -> (jeton, sous-protocole à répondre). Le jeton passe par ce en-tête et non par
    l'adresse du WebSocket, qui se retrouverait dans les journaux du tunnel."""
    offered = [part.strip() for part in (header or "").split(",") if part.strip()]
    token = next((p[len(WS_TOKEN_PREFIX) :] for p in offered if p.startswith(WS_TOKEN_PREFIX)), None)
    return token, (WS_PROTOCOL if WS_PROTOCOL in offered else None)


def bearer_token(header: str | None) -> str | None:
    """« Bearer XXXX » -> « XXXX »."""
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    return value.strip() or None if scheme.lower() == "bearer" else None


def pairing_link(web_url: str, server_ws_url: str, token: str) -> str:
    """Lien à ouvrir sur le téléphone : l'adresse du serveur et le jeton sont dans le fragment (après #),
    que le navigateur n'envoie jamais à Vercel ni au tunnel."""
    from urllib.parse import quote

    return f"{web_url.rstrip('/')}/#server={quote(server_ws_url, safe='')}&token={quote(token, safe='')}"
