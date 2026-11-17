"""Compare des modèles de langage sur les 20 phrases de docs/test-phrases.json.

    python -m orchestrator.ai.benchmark Qwen/Qwen3-30B-A3B-Instruct-2507 meta-llama/Llama-3.3-70B-Instruct

Écrit le tableau dans docs/benchmark-llm.md (option --write). Règles de correction : docs/test-phrases.md.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import statistics
import time
import unicodedata
from pathlib import Path
from typing import Any

from orchestrator.ai.hf import HFAI, AIError
from orchestrator.ports import HistoryTurn

ROOT = Path(__file__).resolve().parents[2]
PHRASES = ROOT / "docs" / "test-phrases.json"
REPORT = ROOT / "docs" / "benchmark-llm.md"

HISTORY: list[HistoryTurn] = [
    {"role": "user", "text": "Je voudrais un train de Paris pour Lille demain après 14 h"},
    {
        "role": "pilote",
        "text": "J'ai trouvé : 1, Train de 14 h 27, direct, 43 euros. 2, Train de 15 h 02, 38 euros. "
        "3, Train de 16 h 12, 51 euros. Voulez-vous des détails sur l'une d'elles ?",
    },
]
PHRASES_WITH_HISTORY = range(14, 20)


def plain(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def lookup(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def check(intent: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Liste des écarts (vide = bonne réponse)."""
    errors = []
    for key, want in expected.items():
        contains = key.endswith("~")
        path = key.rstrip("~")
        got = lookup(intent, path)
        if want == "non null":
            ok = got is not None
        elif contains:
            items = got if isinstance(got, list) else [got]
            ok = any(plain(str(want)) in plain(str(item)) for item in items if item is not None)
        elif isinstance(want, list):
            ok = isinstance(got, list) and sorted(got) == sorted(want)
        else:
            ok = got == want
        if not ok:
            errors.append(f"{key} : attendu {want!r}, reçu {got!r}")
    return errors


async def run_model(model: str, phrases: list[dict[str, Any]], today: dt.date) -> dict[str, Any]:
    ai = HFAI(llm_model=model)
    rows = []
    for item in phrases:
        history = HISTORY if item["id"] in PHRASES_WITH_HISTORY else []
        before = dict(ai.usage)
        started = time.perf_counter()
        try:
            intent = (await ai.parse_intent(item["text"], today, history)).model_dump(mode="json")
            errors = check(intent, item["expected"])
        except AIError as error:
            errors = [f"{error.code} : {error}"]
        rows.append(
            {
                "id": item["id"],
                "seconds": time.perf_counter() - started,
                "errors": errors,
                "tokens": ai.usage["prompt_tokens"]
                + ai.usage["completion_tokens"]
                - before["prompt_tokens"]
                - before["completion_tokens"],
            }
        )
    return {"model": model, "rows": rows}


def render(results: list[dict[str, Any]], today: dt.date) -> str:
    lines = [
        "# Benchmark des modèles de langage (`parse_intent`)",
        "",
        f"20 phrases de `docs/test-phrases.md`, date du jour `{today}`, Hugging Face Inference Providers, "
        "température 0. Une réponse est bonne si elle passe le schéma `Intent` et que tous les champs "
        "attendus sont exacts. Objectif : 18 sur 20.",
        "",
        "**Attention : le prompt a été réglé en regardant ces mêmes 20 phrases, le score est donc "
        "optimiste.** À confirmer sur des phrases nouvelles avant la démo. `missing` et `question` "
        "sont calculés en code (règles du plan), pas par le modèle.",
        "",
        "| Modèle | Bonnes réponses | Temps médian | Temps max | Jetons par phrase |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in results:
        rows = result["rows"]
        good = sum(1 for r in rows if not r["errors"])
        times = [r["seconds"] for r in rows]
        tokens = statistics.mean(r["tokens"] for r in rows)
        lines.append(
            f"| `{result['model']}` | {good} / {len(rows)} | {statistics.median(times):.1f} s "
            f"| {max(times):.1f} s | {tokens:.0f} |"
        )
    lines += ["", "## Écarts", ""]
    for result in results:
        lines.append(f"### `{result['model']}`")
        bad = [r for r in result["rows"] if r["errors"]]
        if not bad:
            lines.append("Aucun.")
        for row in bad:
            lines.append(f"- Phrase {row['id']} : " + " ; ".join(row["errors"]))
        lines.append("")
    lines.append(
        "Le prix par jeton dépend du fournisseur que Hugging Face choisit : voir le tableau de bord "
        "Inference Providers de votre compte pour le coût réel."
    )
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--write", action="store_true", help=f"écrit {REPORT.relative_to(ROOT)}")
    args = parser.parse_args()
    data = json.loads(PHRASES.read_text(encoding="utf-8"))
    today = dt.date.fromisoformat(data["today"])
    results = await asyncio.gather(*(run_model(m, data["phrases"], today) for m in args.models))
    report = render(list(results), today)
    print(report)
    if args.write:
        REPORT.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
