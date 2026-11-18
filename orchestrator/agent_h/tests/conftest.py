import sys
from pathlib import Path

# Rend `orchestrator.agent_h` importable depuis la racine du dépôt.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _memory_in_tmp(tmp_path, monkeypatch):
    """Les tests n'écrivent jamais dans la vraie mémoire des sites (~/.pilote/memoire-sites.json)."""
    monkeypatch.setenv("PILOTE_MEMORY_FILE", str(tmp_path / "memoire-sites.json"))
