"""Surveillant d'une étape de l'agent H : repère une boucle ou une étape qui n'avance plus.

Quand c'est le cas, l'agent envoie la dernière capture à l'orchestrateur (`on_stuck`), qui la fait
lire par un modèle de vision Hugging Face : la description est dite à la personne, le conseil est
renvoyé à l'agent. Le commentaire en direct reste celui de `narration.py`.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

LOOP_REPEATS = 3  # la même action 3 fois sur les 5 dernières = boucle
SLOW_AFTER_S = 90.0  # aucune action nouvelle depuis 90 s = l'agent n'avance plus
HELP_COOLDOWN_S = 60.0
MAX_HELPS = 3  # par étape
StuckCallback = Callable[[bytes, str], Awaitable[str | None]]
IGNORED_TOOLS = {"answer", "request_payment_approval", "need_human"}


def action_signature(name: str, args: dict[str, Any]) -> str:
    """Action sans les coordonnées : « click_web:fermer ». Deux clics sur « Fermer » décalés de
    quelques pixels sont la même action."""
    element = str(args.get("element") or "")
    quoted = re.search(r"[\"«]([^\"»]+)[\"»]", element)
    target = quoted.group(1) if quoted else " ".join(element.split()[:3])
    target = target or str(args.get("url") or "").split("?")[0] or str(args.get("keys") or args.get("text") or "")
    return f"{name}:{target.strip().lower()}"


def screenshot_in(event: dict[str, Any]) -> str | None:
    data = event.get("data") or {}
    if event.get("type") == "AgentEvent" and data.get("kind") == "observation_event":
        return (data.get("image") or {}).get("source") or None
    return None


class StepWatch:
    """Ce que le surveillant sait de l'étape en cours."""

    def __init__(self, now: float) -> None:
        self.actions: list[str] = []
        self.screenshot: str | None = None
        self.last_new_action = now
        self.last_help = -HELP_COOLDOWN_S
        self.helps = 0

    def saw_screenshot(self, url: str) -> None:
        self.screenshot = url

    def saw_action(self, name: str, args: dict[str, Any], now: float) -> None:
        if name in IGNORED_TOOLS:
            return
        signature = action_signature(name, args)
        if signature not in self.actions[-5:]:
            self.last_new_action = now
        self.actions.append(signature)

    def looping(self) -> bool:
        recent = self.actions[-5:]
        return any(recent.count(action) >= LOOP_REPEATS for action in set(recent))

    def stuck_reason(self, now: float) -> str | None:
        """« boucle » ou « lent » si l'orchestrateur doit regarder la page, sinon None."""
        if self.screenshot is None or self.helps >= MAX_HELPS or now - self.last_help < HELP_COOLDOWN_S:
            return None
        if self.looping():
            return "boucle"
        if now - self.last_new_action > SLOW_AFTER_S:
            return "lent"
        return None

    def helped(self, now: float) -> None:
        self.last_help = now
        self.helps += 1
        self.actions.clear()
        self.last_new_action = now
