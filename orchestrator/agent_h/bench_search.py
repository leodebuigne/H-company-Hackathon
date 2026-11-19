"""Mesure la vitesse de RECHERCHE de l'agent H (aucun panier, aucun paiement) :
`python -m orchestrator.agent_h.bench_search [train] [produit] [restaurant] [--label avant]`.

Pour chaque cas : temps de la recherche, nombre d'actions de l'agent, options trouvées. Une ligne par
cas est ajoutée à docs/bench-recherche.md pour comparer avant / après une modification de la consigne.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
import time
from pathlib import Path

from orchestrator.contracts import Intent, When

RESULTS = Path("docs/bench-recherche.md")
HEADER = (
    "# Vitesse de recherche de l'agent H\n\n"
    "Mesures de `python -m orchestrator.agent_h.bench_search` : recherche seule, sans panier ni paiement.\n\n"
    "| date | version | cas | durée (s) | actions | options | première option |\n"
    "|---|---|---|---|---|---|---|\n"
)
LIMIT_S = 300


def _intent(case: str) -> Intent:
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    base = dict(
        kind="new_request", quantity=1, budget_cents=None, constraints=[], choice_index=None, missing=[],
        question=None,
    )  # fmt: skip
    if case == "train":
        return Intent(
            **base, text="Un train de Paris pour Lyon demain après 9 h", category="train", object=None,
            when=When(date=tomorrow, after="09:00", before=None, asap=False),
            details={"origin": "Paris", "destination": "Lyon"},
        )  # fmt: skip
    if case == "produit":
        return Intent(
            **base, text="Un casque Bluetooth Sony WH-1000XM5", category="boutique",
            object="casque Bluetooth Sony WH-1000XM5",
            when=When(date=None, after=None, before=None, asap=False),
            details={"brand": "Sony"},
        )  # fmt: skip
    if case == "restaurant":
        return Intent(
            **base, text="Une table pour deux demain soir dans un restaurant italien à Lyon",
            category="reservation", object="table au restaurant",
            when=When(date=tomorrow, after="20:00", before=None, asap=False),
            details={"cuisine": "italien", "place": "Lyon", "people": "2"},
        )  # fmt: skip
    raise ValueError(f"Cas inconnu : {case}")


async def run_case(case: str, label: str, prepare: bool = False) -> str:
    from orchestrator.agent_h import make_agent

    async def never_pay(summary: object) -> str:
        return "denied"

    async def human(reason: str) -> str:
        print(f"   ✋ l'agent demande un humain : {reason}")
        return "abort"

    agent = make_agent(fake=False, approval_callback=never_pay, need_human_callback=human)

    async def quiet(sentence: str) -> None:  # active le suivi des actions (instant de la première)
        return None

    agent.on_progress = quiet
    if prepare:  # comme pendant une question de Pilote : page et configuration prêtes avant le lancement
        await agent.prepare(_intent(case))
        await asyncio.sleep(4)
    t0 = time.monotonic()
    options, steps, error = [], None, ""
    try:
        await agent.start(_intent(case), None)
        options = await asyncio.wait_for(agent.search(), LIMIT_S)
    except Exception as exc:  # une erreur est un résultat de mesure comme un autre
        error = f"{type(exc).__name__}: {exc}"[:80]
    seconds = time.monotonic() - t0
    try:
        steps = (await agent._session.status()).steps  # noqa: SLF001 (mesure seulement)
    except Exception:
        pass
    try:
        await agent.cancel()
    except Exception:
        pass
    if options:
        first = f"{options[0].title[:40]} — {options[0].price_cents / 100:.2f} €"
    else:
        first = error or "aucune"
    when = f"{dt.datetime.now():%Y-%m-%d %H:%M}"
    row = f"| {when} | {label} | {case} | {seconds:.0f} | {steps or '?'} | {len(options)} | {first} |\n"
    _record(row)
    fast = agent.fast_timings
    if fast.get("repli"):
        note = f"   lecture directe impossible ({agent.last_fast_error}) : recherche par l'agent H\n"
    elif fast:
        read, extract = fast["lecture"], fast["extraction"]
        note = f"   lecture directe : page lue en {read:.1f} s, options extraites en {extract:.1f} s\n"
    else:
        note = ""
    for option in options:
        note += f"     - {option.title[:60]} — {option.price_cents / 100:.2f} € {dict(option.details)}\n"
    return row + _departure(agent.timings, t0) + note


def _departure(timings: dict[str, float], t0: float) -> str:
    """Découpe le temps avant la première action : Chrome, session H (création + configuration), puis
    première réflexion du modèle (chargement de la page compris)."""
    marks = [("Chrome prêt", "chrome"), ("session H créée", "session"), ("première action", "first_action")]
    parts = [f"{label} {timings[key] - t0:.1f} s" for label, key in marks if key in timings]
    return "   départ : " + " → ".join(parts) + "\n" if parts else ""


def _record(row: str) -> None:
    if not RESULTS.exists():
        RESULTS.write_text(HEADER, encoding="utf-8")
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(row)


async def main(argv: list[str]) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(".env"))
    except ImportError:
        pass
    label = argv[argv.index("--label") + 1] if "--label" in argv else "?"
    cases = [a for a in argv if a in ("train", "produit", "restaurant")] or ["train", "produit", "restaurant"]
    for case in cases:
        print(f"→ {case}…", flush=True)
        print(await run_case(case, label, "--prepare" in argv), end="", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
