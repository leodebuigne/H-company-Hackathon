"""Vérifie le vrai agent H de Pilote sur un site, SANS JAMAIS PAYER : `python -m orchestrator.agent_h.check`.

Parcours : recherche → options → panier → page de paiement → relecture, puis annulation.
pay() n'est jamais appelé, et le callback d'approbation répond toujours "denied".

Lit .env : HAI_API_KEY, PILOTE_BROWSER_HOST (cloud ou user_device), PILOTE_SITE_TRAIN / PILOTE_SITE_REPAS.
    python -m orchestrator.agent_h.check            # train Paris → Lille demain après 14 h
    python -m orchestrator.agent_h.check --repas    # une pizza margherita
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
import time
from pathlib import Path

from orchestrator.agent_h.base import AgentError
from orchestrator.contracts import Intent, OrderSummary, When
from orchestrator.session import same_order


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(".env"))


def _intent(repas: bool) -> Intent:
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    if repas:
        return Intent(
            kind="new_request", text="Une pizza margherita", category="repas", object="pizza margherita",
            quantity=1, when=When(date=dt.date.today(), after=None, before=None, asap=True),
            budget_cents=None, details={}, constraints=[], choice_index=None, missing=[], question=None,
        )  # fmt: skip
    return Intent(
        kind="new_request", text="Un train de Paris pour Lille demain après 14 h", category="train",
        object=None, quantity=1, when=When(date=tomorrow, after="14:00", before=None, asap=False),
        budget_cents=None, details={"origin": "Paris", "destination": "Lille"}, constraints=[],
        choice_index=None, missing=[], question=None,
    )  # fmt: skip


def _show(summary: OrderSummary) -> str:
    items = ", ".join(f"{i.quantity} × {i.name} ({i.total_cents / 100:.2f} €)" for i in summary.items)
    return f"{items} | total {summary.total_cents / 100:.2f} € | bouton « {summary.payment_button_label} »"


async def main(repas: bool) -> int:
    _load_env()
    from orchestrator.agent_h import make_agent

    async def never_pay(summary: OrderSummary) -> str:
        print(
            f"   ⛔ demande de paiement refusée (outil de vérification) : {summary.total_cents / 100:.2f} €"
        )
        return "denied"

    async def human(reason: str) -> str:
        print(f"   ✋ l'agent demande un humain : {reason} → on arrête")
        return "abort"

    agent = make_agent(fake=False, approval_callback=never_pay, need_human_callback=human)
    intent = _intent(repas)
    t0 = time.monotonic()

    def lap() -> str:
        return f"{time.monotonic() - t0:.0f} s"

    try:
        print("1. Démarrage de la session H…", flush=True)
        await agent.start(intent, None)
        print(f"   ✓ {lap()} — vue en direct : {agent.agent_view_url or 'non fournie'}")
        print("2. Recherche…", flush=True)
        options = await agent.search()
        print(f"   ✓ {lap()} — {len(options)} option(s)")
        for o in options[:5]:
            print(f"     {o.rank}. {o.title} — {o.price_cents / 100:.2f} €")
        if not options:
            print("   ✗ aucune option")
            return 1
        print(f"3. Panier et page de paiement (option 1 : {options[0].title})…", flush=True)
        await agent.choose(options[0].id)
        summary = await agent.checkout()
        print(f"   ✓ {lap()} — {_show(summary)}")
        print("4. Relecture de la page…", flush=True)
        again = await agent.recheck()
        same = same_order(again, summary)  # même total et mêmes quantités, comme l'orchestrateur
        status = "✓ rien n’a changé" if same else "⚠ le récapitulatif a changé"
        print(f"   {status} ({lap()})")
        print("\nL'agent H fonctionne jusqu'à la page de paiement. Aucun paiement n'a été tenté.")
        return 0
    except AgentError as error:
        print(f"   ✗ {lap()} — {type(error).__name__} : {error}")
        return 1
    finally:
        try:
            await agent.cancel()
        except Exception:
            pass


CHECK_LIMIT_S = 300  # au-delà de 5 minutes, on arrête : c'est trop long pour une commande


async def limited(repas: bool) -> int:
    try:
        return await asyncio.wait_for(main(repas), CHECK_LIMIT_S)
    except TimeoutError:
        print(f"\n✗ Arrêt : plus de {CHECK_LIMIT_S // 60} minutes, c'est trop long.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(limited("--repas" in sys.argv)))
