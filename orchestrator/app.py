"""Serveur de l'orchestrateur : WebSocket /ws pour les écrans, /health pour vérifier qu'il tourne.

Lancer : `python -m orchestrator` (port 8000, lit .env s'il existe).
Les versions factices sont choisies par USE_FAKE_AGENT et USE_FAKE_AI.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected, WebSocketState

from orchestrator.agent_h import local_chrome, make_agent_factory
from orchestrator.ai import build_ai
from orchestrator.config import Settings
from orchestrator.session import Session

log = logging.getLogger(__name__)


def warm_chrome_wanted() -> bool:
    """Chrome local (pas le navigateur cloud), sauf PILOTE_WARM_CHROME=0."""
    host = os.getenv("PILOTE_BROWSER_HOST") or "user_device"
    return host == "user_device" and os.getenv("PILOTE_WARM_CHROME", "1").strip() != "0"


def build_session(settings: Settings) -> Session:
    return Session(
        ai=build_ai(),
        agent_factory=make_agent_factory(fake=settings.use_fake_agent),
        settings=settings,
    )


def create_app(session_factory: Callable[[], Session] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = Settings.from_env()
        session = session_factory() if session_factory else build_session(settings)
        app.state.session = session
        app.state.settings = settings
        log.warning(
            "Pilote prêt. Agent %s, IA %s.",
            "FACTICE" if settings.use_fake_agent else "RÉEL (vrais sites)",
            "factice" if settings.use_fake_ai else "Hugging Face",
        )
        await session.start()
        if session_factory is None and not settings.use_fake_agent and warm_chrome_wanted():
            # Chrome dédié ouvert dès le démarrage : la première commande n'attend pas son lancement
            asyncio.get_running_loop().run_in_executor(None, local_chrome.ensure)
        try:
            yield
        finally:
            await session.stop()

    app = FastAPI(title="Pilote, orchestrateur", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        settings: Settings = app.state.settings
        return {
            "ok": True,
            "state": app.state.session.state,
            "fake_agent": settings.use_fake_agent,
            "fake_ai": settings.use_fake_ai,
        }

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        session: Session = app.state.session

        async def send(data: dict[str, Any]) -> None:
            await websocket.send_json(data)

        await session.attach(send)
        try:
            # Écran fermé pendant l'accueil (page rechargée, orchestrateur relancé) : l'envoi a échoué,
            # la connexion est déjà fermée ; la relire levait une erreur bruyante dans le journal.
            while websocket.client_state == WebSocketState.CONNECTED:
                try:
                    data = await websocket.receive_json()
                except ValueError:  # pas du JSON : ignoré
                    continue
                await session.receive(data)
        except (WebSocketDisconnect, WebSocketDisconnected):
            pass
        finally:
            session.detach(send)

    return app


app = create_app()
