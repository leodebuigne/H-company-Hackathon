"""Serveur de l'orchestrateur : WebSocket /ws pour les écrans, /health pour vérifier qu'il tourne.

Lancer : `python -m orchestrator` (port 8000, lit .env s'il existe).
Les versions factices sont choisies par USE_FAKE_AGENT et USE_FAKE_AI.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnected, WebSocketState

from orchestrator.access import Access, access_from_env, bearer_token, pairing_link, token_from_protocols
from orchestrator.agent_h import local_chrome, make_agent_factory
from orchestrator.ai import build_ai
from orchestrator.ai.hf import SPEAK_MIME
from orchestrator.config import Settings
from orchestrator.session import Session

log = logging.getLogger(__name__)


VOICE_SAMPLE = "Bonjour, je suis Pilote. C'est avec cette voix que je vous parlerai."


class VoiceChoice(BaseModel):
    name: str


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


def announce_access(access: Access) -> None:
    """Dit au démarrage comment appairer un téléphone. Un jeton choisi par la personne reste secret."""
    if not access.required:
        return
    if not access.generated:
        log.warning("Accès protégé : jeton lu dans PILOTE_TOKEN.")
        return
    web, server = (
        os.environ.get("PILOTE_WEB_URL", "").strip(),
        os.environ.get("PILOTE_PUBLIC_WS_URL", "").strip(),
    )
    assert access.token is not None
    if web and server:
        log.warning(
            "Accès protégé. Ouvrez ce lien sur le téléphone (une seule fois) : %s",
            pairing_link(web, server, access.token),
        )
    else:
        log.warning(
            "Accès protégé. Jeton tiré au hasard : %s. Avec PILOTE_WEB_URL et PILOTE_PUBLIC_WS_URL, ce "
            "serait un lien d'appairage prêt à ouvrir.",
            access.token,
        )


def create_app(session_factory: Callable[[], Session] | None = None, access: Access | None = None) -> FastAPI:
    access = access if access is not None else access_from_env(os.environ)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = Settings.from_env()
        session = session_factory() if session_factory else build_session(settings)
        app.state.session = session
        app.state.settings = settings
        app.state.access = access
        announce_access(access)
        log.warning(
            "Pilote prêt. Agent %s, IA %s.",
            "FACTICE" if settings.use_fake_agent else "RÉEL (vrais sites)",
            "factice" if settings.use_fake_ai else "Hugging Face",
        )
        await session.start()
        if session_factory is None and not settings.use_fake_agent and warm_chrome_wanted():
            # Chrome dédié ouvert dès le démarrage : la première commande n'attend pas son lancement
            asyncio.get_running_loop().run_in_executor(None, local_chrome.ensure)
        local_voice = getattr(session.ai, "local_voice", None)
        if session_factory is None and local_voice is not None:
            # Voix locale chargée dès le démarrage (quelques secondes) : la première phrase n'attend pas
            def warm_voice() -> None:
                try:
                    local_voice.load()
                except Exception as error:  # paquet absent : speak() reprendra la voix en ligne
                    log.warning("voix locale non chargée (%s)", type(error).__name__)

            asyncio.get_running_loop().run_in_executor(None, warm_voice)
        try:
            yield
        finally:
            await session.stop()

    app = FastAPI(title="Pilote, orchestrateur", lifespan=lifespan)
    # L'interface (autre port, ou page autorisée comme celle de Vercel) lit et change la voix
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(access.allowed_origins),
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST"],
        allow_headers=["content-type", "authorization"],
    )

    def authorized(request: Request) -> bool:
        return access.accepts(bearer_token(request.headers.get("authorization")))

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        settings: Settings = app.state.settings
        if not authorized(request):
            return {"ok": True}  # le serveur répond, sans rien dire de plus à qui n'a pas le jeton
        return {
            "ok": True,
            "state": app.state.session.state,
            "fake_agent": settings.use_fake_agent,
            "fake_ai": settings.use_fake_ai,
        }

    @app.get("/voice")
    async def voices(request: Request) -> dict[str, Any]:
        """Voix que la personne peut choisir dans les réglages (vide avec l'IA factice)."""
        if not authorized(request):
            raise HTTPException(status_code=401, detail="Jeton d'appairage manquant ou faux.")
        ai = app.state.session.ai
        return ai.voices() if hasattr(ai, "voices") else {"current": None, "available": []}

    @app.post("/voice")
    async def choose_voice(choice: VoiceChoice, request: Request) -> dict[str, Any]:
        """Change la voix de Pilote et renvoie un court extrait pour l'entendre tout de suite."""
        if not authorized(request):
            raise HTTPException(status_code=401, detail="Jeton d'appairage manquant ou faux.")
        ai = app.state.session.ai
        if not hasattr(ai, "set_voice"):
            raise HTTPException(status_code=404, detail="Pas de voix au choix avec cette configuration.")
        try:
            ai.set_voice(choice.name)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        audio = await ai.speak(VOICE_SAMPLE)
        sample = base64.b64encode(audio).decode("ascii") if audio else None
        return {**ai.voices(), "sample": sample, "mime": SPEAK_MIME, "text": VOICE_SAMPLE}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        token, subprotocol = token_from_protocols(websocket.headers.get("sec-websocket-protocol"))
        if access.required:
            if not access.origin_allowed(websocket.headers.get("origin")):
                await websocket.close(code=4403)  # page inconnue
                return
            if not access.accepts(token):
                await websocket.close(code=4429 if access.blocked else 4401)  # trop d'essais / jeton faux
                return
        await websocket.accept(subprotocol=subprotocol)
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
