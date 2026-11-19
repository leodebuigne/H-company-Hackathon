"""Vérification avant la démo : `python -m orchestrator.check`.

Dit en clair ce qui est prêt et ce qui ne l'est pas : clés, crédits H, modèles Hugging Face (compréhension
et voix), Chrome dédié, connexion au compte SNCF, serveurs. Ne lance aucune commande et n'achète rien.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.request
from collections.abc import Awaitable, Callable

OK, KO, WARN = "OK  ", "ÉCHEC", "À VOIR"


def _get(url: str, timeout: float = 4) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except Exception as error:
        return 0, type(error).__name__


async def check_keys() -> tuple[str, str]:
    missing = [name for name in ("HAI_API_KEY", "HF_TOKEN") if not os.getenv(name)]
    return (
        (KO, f"clé absente du fichier .env : {', '.join(missing)}")
        if missing
        else (OK, "clés H et Hugging Face présentes")
    )


async def check_settings() -> tuple[str, str]:
    from orchestrator.config import Settings

    settings = Settings.from_env()
    if settings.use_fake_agent or settings.use_fake_ai:
        return (
            WARN,
            "mode factice activé (USE_FAKE_AGENT ou USE_FAKE_AI) : rien ne se passe sur les vrais sites",
        )
    parts = ["vrais sites"]
    parts.append("achat direct" if settings.direct_buy else "achat avec relecture")
    parts.append("code secret demandé" if settings.purchase_code else "SANS code secret")
    if os.getenv("PILOTE_PLAN_B", "").strip() == "1":
        parts.append("PLAN B (faux sites)")
    return (OK if settings.purchase_code else WARN), ", ".join(parts)


async def check_h() -> tuple[str, str]:
    from hai_agents import AsyncClient

    quota = await AsyncClient().quota.get_token_quota()
    used = 100 * quota.used / quota.limit if quota.limit else 0
    return (OK if used < 85 else WARN), f"H Company répond, {used:.0f} % du quota du mois utilisé"


async def check_language() -> tuple[str, str]:
    import datetime as dt

    from orchestrator.ai.hf import HFAI

    started = time.monotonic()
    intent = await HFAI().parse_intent("Un train de Paris pour Lyon demain matin", dt.date.today(), [])
    good = intent.category == "train" and intent.details.get("destination") == "Lyon"
    return (OK if good else KO), f"compréhension en {time.monotonic() - started:.1f} s"


async def check_voice() -> tuple[str, str]:
    from orchestrator.ai.hf import HFAI

    started = time.monotonic()
    audio = await HFAI().speak("Je suis Topil, un assistant automatique.")
    took = time.monotonic() - started
    if not audio:
        return WARN, "la voix de Topil ne répond pas : la voix du navigateur prendra le relais"
    return (OK if took < 4 else WARN), f"voix de Topil en {took:.1f} s"


async def check_chrome() -> tuple[str, str]:
    from orchestrator.agent_h import local_chrome

    if (os.getenv("PILOTE_BROWSER_HOST") or "user_device") != "user_device":
        return OK, "navigateur cloud H (pas de Chrome local)"
    if not await asyncio.to_thread(local_chrome.listening):
        return WARN, "Chrome dédié fermé : il s'ouvrira au démarrage du serveur"
    return OK, f"Chrome dédié ouvert ({await asyncio.to_thread(local_chrome.open_pages)} onglet)"


async def check_sncf() -> tuple[str, str]:
    """Compte SNCF connecté dans le Chrome dédié ? On lit la page d'accueil, sans rien cliquer."""
    from orchestrator.agent_h import local_chrome

    if (os.getenv("PILOTE_BROWSER_HOST") or "user_device") != "user_device":
        return WARN, "non vérifié en navigateur cloud"
    if not await asyncio.to_thread(local_chrome.listening):
        return WARN, "non vérifié : Chrome dédié fermé"
    import websockets

    await asyncio.to_thread(local_chrome.fresh_page, "https://www.sncf-connect.com")
    await asyncio.sleep(6)
    tabs = json.loads(_get(f"http://127.0.0.1:{local_chrome.PORT}/json")[1])
    page = next((t for t in tabs if t.get("type") == "page" and "sncf" in t.get("url", "")), None)
    if page is None:
        return WARN, "page SNCF Connect non ouverte"
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        script = "document.body.innerText.slice(0, 1500)"
        await ws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": script, "returnByValue": True},
                }
            )
        )
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if message.get("id") == 1:
                text = message.get("result", {}).get("result", {}).get("value", "")
                break
    if "Se connecter" in text or "Connexion" in text.split("Aide")[-1][:80]:
        return KO, "compte SNCF déconnecté : reconnectez-vous à la main dans le Chrome dédié"
    if "Compte" in text:
        return OK, "compte SNCF connecté"
    return WARN, "page SNCF lue, mais état du compte incertain (captcha ou bandeau ?)"


async def check_servers() -> tuple[str, str]:
    status, body = await asyncio.to_thread(_get, "http://localhost:8000/health")
    web, _ = await asyncio.to_thread(_get, "http://localhost:3000")
    if status != 200:
        return KO, "orchestrateur arrêté (port 8000)"
    health = json.loads(body)
    fake = " (agent FACTICE)" if health.get("fake_agent") else ""
    return (
        OK if web == 200 else KO
    ), f"orchestrateur en marche{fake}, interface {'en marche' if web == 200 else 'arrêtée (port 3000)'}"


CHECKS: list[tuple[str, Callable[[], Awaitable[tuple[str, str]]]]] = [
    ("Clés", check_keys),
    ("Réglages", check_settings),
    ("Agent H", check_h),
    ("Compréhension", check_language),
    ("Voix", check_voice),
    ("Chrome", check_chrome),
    ("Compte SNCF", check_sncf),
    ("Serveurs", check_servers),
]


async def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(".env")
    except ImportError:
        pass
    worst = 0
    for name, check in CHECKS:
        try:
            status, detail = await asyncio.wait_for(check(), 45)
        except Exception as error:
            status, detail = KO, f"{type(error).__name__} : {str(error)[:120]}"
        worst = max(worst, {OK: 0, WARN: 1, KO: 2}[status])
        print(f"[{status}] {name:<14} {detail}", flush=True)
    print(
        [
            "Tout est prêt pour la démo.",
            "Prêt, avec des points à regarder.",
            "PAS PRÊT : corrigez les échecs ci-dessus.",
        ][worst]
    )
    return 0 if worst < 2 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
