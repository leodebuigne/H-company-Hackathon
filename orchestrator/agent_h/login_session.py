"""Connexion unique d'un compte marchand dans le profil de navigateur H par défaut.

L'agent ouvre le site dans un navigateur cloud, se connecte avec le coffre-fort H
(PILOTE_H_VAULT_ID) et s'arrête. Vous suivez en direct (lien « vue en direct ») et vous lui
transmettez le code de sécurité si le site en demande un. À la fin de la session, H enregistre
les cookies dans le profil par défaut : les commandes de Pilote (PILOTE_H_DEFAULT_PROFILE=1)
démarrent alors déjà connectées.

Depuis la racine du dépôt :
    python -m orchestrator.agent_h.login_session                  # SNCF Connect
    python -m orchestrator.agent_h.login_session --site https://www.ubereats.com/fr

Doc : https://hub.hcompany.ai/agents-api/browser/profiles.md
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from hai_agents import AsyncClient
from hai_agents.client import default_api_key

TASK = """\
Mission unique : te connecter au compte de ce site, puis t'arrêter.
1. Refuse les cookies non essentiels.
2. Clique sur « Se connecter », « Mon compte » ou l'équivalent.
3. Connecte-toi uniquement avec les identifiants du coffre-fort (il les remplit pour toi). N'écris jamais \
toi-même de mot de passe.
4. Si le site demande un code reçu par e-mail ou SMS, arrête-toi et réponds exactement : \
« CODE DEMANDÉ : » suivi de l'endroit où le code a été envoyé. Le code te sera donné dans le message suivant.
5. Quand tu es connecté (prénom ou espace client visible), réponds : « CONNECTÉ » et le prénom affiché.
Ne cherche rien, n'ajoute rien au panier, ne clique sur aucun bouton de paiement.
"""


def agent_spec(site: str, vault_id: str | None) -> dict:
    environment: dict = {
        "kind": "web",
        "id": "browser",
        "host": "cloud",
        "start_url": site,
        "use_default_browser_profile": True,  # les cookies sont enregistrés à la fin de la session
    }
    if vault_id:
        environment["vault_id"] = vault_id
    return {
        "name": "pilote-login",
        "description": "Connecte un compte marchand une fois, pour le profil de navigateur de Pilote.",
        "environments": [environment],
        "reasoning_effort": "low",
    }


async def ask(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip()


async def main(site: str) -> int:
    if not default_api_key():
        print("Pas de clé H : définis HAI_API_KEY (fichier .env) ou lance `holo login`.", file=sys.stderr)
        return 2
    vault_id = (os.getenv("PILOTE_H_VAULT_ID") or "").strip() or None
    if not vault_id:
        print("Attention : pas de PILOTE_H_VAULT_ID, l'agent n'aura pas les identifiants.\n")

    async with AsyncClient() as client:
        session = await client.start_session(agent=agent_spec(site, vault_id), messages=TASK)
        info = await session.get()
        print(f"\nSession H lancée sur {site}")
        view = getattr(info, "agent_view_url", None) or "(voir le portail H, menu Sessions)"
        print(f"Vue en direct : {view}\n")
        try:
            cursor = 0
            while True:
                result = await session.wait_for_completion(from_index=cursor, timeout_seconds=600)
                cursor = result.next_from_index
                answer = str(getattr(result, "answer", "") or "").strip()
                print(f"\nAgent : {answer or '(pas de réponse)'}\n")
                if answer.upper().startswith("CONNECTÉ") or answer.upper().startswith("CONNECTE"):
                    print("Connexion réussie. Fermeture de la session : H enregistre le profil.")
                    return 0
                reply = await ask("Code ou message pour l'agent (Entrée vide pour arrêter) : ")
                if not reply:
                    print("Arrêt demandé.")
                    return 1
                await session.send_message(f"Voici le code ou la précision demandée : {reply}")
        finally:
            try:
                await session.cancel()  # fin de session : le profil par défaut est enregistré
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--site", default="https://www.sncf-connect.com", help="site à connecter")
    sys.exit(asyncio.run(main(parser.parse_args().site)))
