"""Réglages de l'orchestrateur, lus dans les variables d'environnement (voir .env.example)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import ValidationError

from orchestrator.contracts import Relative

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

# Proche fictif, utilisé seulement avec la validation factice si PILOTE_RELATIVES est vide.
FAKE_RELATIVE = Relative(first_name="Léa", phone="+33600000000")


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name, "").strip()
    if value == "":
        return default
    return value in ("1", "true", "True", "oui")


def _number(env: Mapping[str, str], name: str, default: float) -> float:
    value = env.get(name, "").strip()
    return float(value) if value else default


def parse_relatives(raw: str) -> tuple[Relative, ...]:
    """« Léa:+33600000001, Hugo:+33600000002 » -> proches dans l'ordre (3 au maximum)."""
    relatives = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        name, sep, phone = entry.partition(":")
        if not sep:
            raise ValueError(f"PILOTE_RELATIVES : « {entry} » doit s'écrire Prénom:+33...")
        try:
            relatives.append(Relative(first_name=name.strip(), phone=phone.strip().replace(" ", "")))
        except ValidationError as error:
            raise ValueError(f"PILOTE_RELATIVES : « {entry} » invalide (numéro au format +33...)") from error
    if len(relatives) > 3:
        raise ValueError("PILOTE_RELATIVES : 3 proches au maximum")
    return tuple(relatives)


def _purchase_code(raw: str) -> str | None:
    code = raw.strip()
    if not code:
        return None
    if len(code) != 3 or not code.isdigit():
        raise ValueError("PILOTE_PURCHASE_CODE : exactement 3 chiffres")
    return code


@dataclass(frozen=True)
class Settings:
    use_fake_agent: bool = True
    use_fake_ai: bool = True
    use_fake_approvals: bool = True
    user_first_name: str = "Utilisateur"
    relatives: tuple[Relative, ...] = ()
    approval_timeout_s: int = 300
    approval_timeout_repas_s: int = 120
    approvals_api_url: str | None = None
    shared_secret: str | None = None
    poll_interval_s: float = 2.0
    confirm_timeout_s: float = 180.0
    human_timeout_s: float = 600.0
    step_timeouts: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_STEP_TIMEOUTS))
    journal_path: str | None = "logs/journal.jsonl"
    fake_approval_decision: str = "approved"
    fake_approval_delay_s: float = 5.0
    # Achat direct : choisir une option vaut ordre d'achat (pas de « oui », ni proche, ni relecture).
    # Seul garde-fou gardé : le total affiché ne doit pas dépasser le prix de l'option choisie.
    direct_buy: bool = False
    # Code secret à 3 chiffres demandé à l'oral avant chaque achat (achat direct). None = pas de code.
    purchase_code: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        decision = env.get("PILOTE_FAKE_APPROVAL_DECISION", "").strip() or "approved"
        if decision not in ("approved", "denied", "expired"):
            raise ValueError("PILOTE_FAKE_APPROVAL_DECISION : approved, denied ou expired")
        return cls(
            # Par défaut tout est factice : rien ne touche un vrai site sans le demander.
            use_fake_agent=_flag(env, "USE_FAKE_AGENT", True),
            use_fake_ai=_flag(env, "USE_FAKE_AI", True),
            use_fake_approvals=_flag(env, "USE_FAKE_APPROVALS", True),
            user_first_name=env.get("PILOTE_USER_FIRST_NAME", "").strip() or "Utilisateur",
            relatives=parse_relatives(env.get("PILOTE_RELATIVES", "")),
            approval_timeout_s=int(_number(env, "APPROVAL_TIMEOUT_SECONDS", 300)),
            approval_timeout_repas_s=int(_number(env, "APPROVAL_TIMEOUT_SECONDS_REPAS", 120)),
            approvals_api_url=env.get("APPROVALS_API_URL", "").strip() or None,
            shared_secret=env.get("PILOTE_SHARED_SECRET", "").strip() or None,
            journal_path=env.get("PILOTE_JOURNAL_PATH", "").strip() or "logs/journal.jsonl",
            fake_approval_decision=decision,
            fake_approval_delay_s=_number(env, "PILOTE_FAKE_APPROVAL_DELAY_S", 5.0),
            direct_buy=_flag(env, "PILOTE_DIRECT_BUY", False),
            purchase_code=_purchase_code(env.get("PILOTE_PURCHASE_CODE", "")),
        )

    def approval_timeout(self, category: str | None) -> int:
        seconds = self.approval_timeout_repas_s if category == "repas" else self.approval_timeout_s
        return max(10, min(300, seconds))  # bornes du contrat ApprovalRequest

    def relatives_for_approval(self) -> tuple[Relative, ...]:
        if self.relatives:
            return self.relatives
        return (FAKE_RELATIVE,) if self.use_fake_approvals else ()
