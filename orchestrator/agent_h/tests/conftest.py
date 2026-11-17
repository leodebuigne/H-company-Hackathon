import sys
from pathlib import Path

# Rend `orchestrator.agent_h` importable depuis la racine du dépôt.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
