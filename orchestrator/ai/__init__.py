"""IA de Pilote (membre 2). `build_ai()` choisit la version selon USE_FAKE_AI."""

import os

from orchestrator.ai.fake import FakeAI
from orchestrator.ai.hf import HFAI, AIError
from orchestrator.ports import AI

__all__ = ["AI", "AIError", "FakeAI", "HFAI", "build_ai"]


def build_ai() -> AI:
    """FakeAI si USE_FAKE_AI vaut 1 (valeur par défaut du .env.example), sinon HFAI avec HF_TOKEN."""
    if os.environ.get("USE_FAKE_AI", "1") == "1":
        return FakeAI()
    return HFAI()
