"""Temps et nombre d'étapes de chaque commande, ajoutés à docs/results-agent.md."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

RESULTS_PATH = Path(__file__).resolve().parents[2] / "docs" / "results-agent.md"
HEADER = (
    "# Résultats de l'agent H\n\n"
    "Une ligne par commande, ajoutée automatiquement par orchestrator/agent_h/metrics.py.\n\n"
    "| Date | Site | Agent | Issue | Durée (s) | Étapes H | Paiement |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
)


@dataclass
class RunMetrics:
    site: str
    agent: str
    started: float
    phases: dict[str, float] = field(default_factory=dict)
    steps: Optional[int] = None
    outcome: str = "en cours"
    payment: str = "-"

    def row(self, now: float) -> str:
        date = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        steps = "?" if self.steps is None else str(self.steps)
        return f"| {date} | {self.site} | {self.agent} | {self.outcome} | {now - self.started:.0f} | {steps} | {self.payment} |\n"


def append_result(metrics: RunMetrics, now: float, path: Path = RESULTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(HEADER, encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(metrics.row(now))
