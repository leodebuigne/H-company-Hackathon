"""Réglages de l'orchestrateur, lus dans les variables d'environnement (voir .env.example)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

# Délai maximum de chaque étape de l'agent H, en secondes. Large : une étape peut contenir
# un geste humain (CAPTCHA) et le paiement attend la validation bancaire.
DEFAULT_STEP_TIMEOUTS: dict[str, float] = {
    "start": 180,
    "search": 600,
    "refine": 600,
    "choose": 300,
    "checkout": 600,
    "recheck": 300,
    "pay": 600,
    "buy": 900,  # achat direct : panier + paiement en une étape
    "cancel": 30,
}


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name, "").strip()
    if value == "":
        return default
    return value in ("1", "true", "True", "oui")


def _number(env: Mapping[str, str], name: str, default: float) -> float:
    value = env.get(name, "").strip()
    return float(value) if value else default


@dataclass(frozen=True)
class Settings:
    use_fake_agent: bool = True
    use_fake_ai: bool = True
    confirm_timeout_s: float = 180.0
    human_timeout_s: float = 600.0
    step_timeouts: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_STEP_TIMEOUTS))
    journal_path: str | None = "logs/journal.jsonl"
    # Achat direct : choisir une option vaut ordre d'achat (pas de « oui » ni de relecture).
    # Seul garde-fou gardé : le total affiché ne doit pas dépasser le prix de l'option choisie.
    direct_buy: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            # Par défaut tout est factice : rien ne touche un vrai site sans le demander.
            use_fake_agent=_flag(env, "USE_FAKE_AGENT", True),
            use_fake_ai=_flag(env, "USE_FAKE_AI", True),
            journal_path=env.get("PILOTE_JOURNAL_PATH", "").strip() or "logs/journal.jsonl",
            direct_buy=_flag(env, "PILOTE_DIRECT_BUY", False),
        )
