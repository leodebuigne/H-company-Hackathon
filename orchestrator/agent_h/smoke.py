"""Test de fumée de l'agent H : vérifie la clé, puis le navigateur cloud, puis le Chrome local.

Depuis la racine du dépôt :
    export HAI_API_KEY=...            # ou : holo login
    python -m orchestrator.agent_h.smoke            # cloud puis Chrome local
    python -m orchestrator.agent_h.smoke --cloud    # cloud seulement

Le mode Chrome local (host user_device) pilote un Chrome dédié sur le port 9222,
profil ~/.hai/chrome-profile. Le SDK le lance tout seul s'il n'est pas déjà ouvert.
Doc : https://hub.hcompany.ai/agents-api/your-browser.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from hai_agents import AsyncClient
from hai_agents.client import default_api_key

TASK = "Ouvre https://example.com et renvoie le titre principal de la page, mot pour mot."


async def run(label: str, agent: object) -> bool:
    print(f"\n== {label} ==")
    started = time.monotonic()
    async with AsyncClient() as client:
        result = await client.run_session(agent=agent, messages=TASK, timeout_seconds=300)
    print(f"statut : {result.status} en {time.monotonic() - started:.0f} s")
    print(f"réponse : {result.answer}")
    if result.error:
        print(f"erreur : {result.error} ({result.error_code})")
    return result.status == "completed"


async def main(cloud_only: bool) -> int:
    if not default_api_key():
        print("Pas de clé H : définis HAI_API_KEY ou lance `holo login`.", file=sys.stderr)
        return 2
    ok = await run("1. Navigateur cloud, agent h/web-surfer-flash", "h/web-surfer-flash")
    if not cloud_only:
        local_agent = {
            "name": "pilote-smoke-local",
            "description": "Test de fumée sur le Chrome dédié de l'ordinateur de démo.",
            "environments": [{"kind": "web", "id": "browser", "host": "user_device"}],
        }
        ok = await run("2. Chrome local (votre navigateur)", local_agent) and ok
    print("\nOK" if ok else "\nÉCHEC : voir ci-dessus")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cloud", action="store_true", help="tester seulement le navigateur cloud")
    sys.exit(asyncio.run(main(parser.parse_args().cloud)))
