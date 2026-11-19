"""Lecture directe des résultats, sans l'agent H : quelques secondes au lieu de 25 à 55.

La page de résultats est déjà ouverte dans le Chrome de l'agent (adresse directe, search_shortcuts). On lit
son texte par le port de débogage de Chrome, puis un modèle de langage rapide (Llama 3.3, routeur Hugging
Face) en extrait les options au format de l'agent. Chaque option est VÉRIFIÉE contre le texte de la page :
un prix ou un nom absent de la page fait écarter l'option (jamais d'option inventée lue à une personne
aveugle). Sans option vérifiée, l'agent H reprend la recherche comme avant.

Panier et paiement restent faits par l'agent H, à partir de cette même page.
PILOTE_FAST_SEARCH=0 coupe la lecture directe.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import unicodedata
import urllib.request
from typing import Any

from orchestrator.contracts import Intent

from .models import AgentOption

PORT = 9222
MAX_CHARS = 14000  # ≈ 4 000 tokens : assez pour une page de résultats, rapide à lire pour le modèle
WAIT_S = 10  # attente maximum que la page ait fini d'afficher ses résultats
LLM_TIMEOUT_S = 15

EXTRACT_PROMPT = """\
Tu lis le texte d'une page de résultats d'un site marchand ou de réservation. Extrais au plus {n} \
options qui répondent à la demande, dans l'ordre de la page, en suivant les contraintes (budget, \
horaire, préférence). Réponds UNIQUEMENT en JSON :
{{"options": [{{"id": "o1", "title": "nom exact tel qu'écrit sur la page", "price_eur": 12.5 ou null, \
"rating": 4.5 ou null, "description": "une phrase courte" ou null, "details": {{...}}}}]}}
Règles absolues :
- Recopie le nom et le prix EXACTEMENT comme sur la page. N'invente rien : une information absente reste null.
- Si aucun résultat ne respecte toutes les contraintes (par exemple « gratuit » ou un budget), renvoie \
quand même les {n} plus proches, en disant dans description ce qui ne correspond pas : ne renvoie jamais \
une liste vide quand la page affiche des résultats.
- Ignore les publicités et les résultats « Sponsorisé » quand d'autres résultats existent.
- details, clés possibles (seulement si la page l'affiche) : departure, arrival (HH:MM), duration, via \
(« direct » ou correspondances) pour un train, avec title = type de train et heures (« TGV INOUI 09:00 → \
11:04 ») ; brand, seller, delivery pour un produit ; \
address, cuisine, avg_price (texte, ex. « 20-30 € »), slots (UNIQUEMENT des créneaux de \
réservation proposés, jamais les horaires d'ouverture), phone, booking (« oui » si réservation \
en ligne) pour un \
restaurant ; restaurant, delivery pour un repas. Les horaires d'ouverture vont dans description.
- Billet de train à 0 € (abonnement) : price_eur = 0, c'est un vrai prix.
- Train : ne garde que les trajets qui partent d'une gare de la ville de départ demandée et arrivent \
dans la ville d'arrivée (une gare d'une autre commune, comme Marne-la-Vallée pour Paris, ne compte pas). \
Mets la gare de départ et la gare d'arrivée dans description.
- Restaurant ou réservation sans prix : price_eur = 0. Produit sans prix lisible : ne le renvoie pas.
- rating : la note affichée à côté du nom (ex. « 4,6 »), sur 5 (ramène-la sur 5 si elle est sur 10)."""


class FastReadError(Exception):
    """Lecture directe impossible : l'agent H reprend la recherche."""


def enabled() -> bool:
    return os.getenv("PILOTE_FAST_SEARCH", "").strip() != "0"


# --- lecture de la page dans Chrome -------------------------------------------------------------------


def _target(domain: str) -> str:
    """Adresse de débogage de l'onglet ouvert sur le site."""
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=3) as resp:
        targets = json.load(resp)
    for target in targets:
        if target.get("type") == "page" and domain in target.get("url", ""):
            return target["webSocketDebuggerUrl"]
    raise FastReadError(f"aucun onglet ouvert sur {domain}")


async def _evaluate(ws: Any, expression: str, ident: int) -> Any:
    await ws.send(
        json.dumps(
            {
                "id": ident,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True},
            }
        )
    )
    while True:
        message = json.loads(await ws.recv())
        if message.get("id") == ident:
            return message.get("result", {}).get("result", {}).get("value")


async def page_text(domain: str, wait_s: float = WAIT_S, min_prices: int = 0) -> str:
    """Texte visible de la page, une fois qu'il ne grandit plus (résultats chargés) ou après wait_s.
    min_prices : nombre de prix (« € ») à voir avant de lire, quand la liste met du temps à arriver."""
    import websockets

    url = await asyncio.to_thread(_target, domain)
    deadline = time.monotonic() + wait_s
    async with websockets.connect(url, max_size=None, open_timeout=5) as ws:
        last, stable, ident, text = -1, 0, 0, ""
        while time.monotonic() < deadline:
            ident += 1
            text = await _evaluate(ws, "document.body ? document.body.innerText : ''", ident) or ""
            ready = len(text) > 500 and text.count("€") >= min_prices
            stable = stable + 1 if len(text) == last and ready else 0
            if stable >= 2:  # même longueur 2 fois de suite (≈ 0,8 s) : la liste est affichée
                break
            last = len(text)
            await asyncio.sleep(0.4)
    return text


# --- extraction et vérification -----------------------------------------------------------------------


def _flat(text: str) -> str:
    text = text.replace("€", "eur")  # sinon le symbole disparaît avec les accents : « 69 € » introuvable
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[\s  ]+", " ", text)


def _price_on_page(price: float, flat_page: str) -> bool:
    if price == 0:
        return True
    euros, cents = int(price), round(price * 100) % 100
    compact = flat_page.replace(" ", "")
    forms = [f"{euros},{cents:02d}", f"{euros}.{cents:02d}", f"{euros}eur{cents:02d}"]
    if cents == 0:
        forms += [f"{euros},00", f"{euros}eur"]
    thousands = f"{euros:,}".replace(",", "")  # 1 234,50 écrit avec espace : compact le retire
    forms.append(f"{thousands},{cents:02d}")
    return any(form in compact for form in forms)


def _title_on_page(title: str, flat_page: str) -> bool:
    words = [w for w in re.findall(r"[a-z0-9]{3,}", _flat(title))][:6]
    if not words:
        return False
    found = sum(1 for w in words if w in flat_page)
    return found >= max(1, round(len(words) * 0.6))


def verified(options: list[AgentOption], text: str, free_allowed: bool) -> list[AgentOption]:
    """Ne garde que les options dont le nom et le prix figurent sur la page."""
    flat_page = _flat(text)
    kept = []
    for option in options:
        if option.price_eur is None or (option.price_eur == 0 and not free_allowed):
            continue
        if _title_on_page(option.title, flat_page) and _price_on_page(option.price_eur, flat_page):
            kept.append(option)
    return kept


def _parse(content: str) -> list[AgentOption]:
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise FastReadError("réponse du modèle illisible")
    data = json.loads(content[start : end + 1])
    options = []
    for raw in data.get("options") or []:
        try:
            options.append(AgentOption.model_validate(raw))
        except Exception:
            continue
    return options


async def _extract(text: str, request: str, n: int) -> list[AgentOption]:
    from openai import AsyncOpenAI

    token = os.getenv("HF_TOKEN")
    if not token:
        raise FastReadError("HF_TOKEN manquant")
    model = (
        os.getenv("PILOTE_FAST_SEARCH_MODEL")
        or os.getenv("PILOTE_LLM_MODEL")
        or "meta-llama/Llama-3.3-70B-Instruct"
    )
    chat = AsyncOpenAI(base_url="https://router.huggingface.co/v1", api_key=token, timeout=LLM_TIMEOUT_S)
    response = await chat.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=1200,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT.format(n=n)},
            {"role": "user", "content": f"Demande :\n{request}\n\nTexte de la page :\n{text[:MAX_CHARS]}"},
        ],
    )
    return _parse(response.choices[0].message.content or "")


async def find_options_when_ready(
    domain: str, intent: Intent, request: str, n: int
) -> tuple[list[AgentOption], dict[str, float]]:
    """Comme find_options, mais attend que la liste des résultats arrive (jusqu'à 25 s) : l'agent répond
    dès son clic sur « Rechercher » au lieu d'attendre lui-même l'affichage (≈ 15 s gagnées sur SNCF)."""
    return await find_options(domain, intent, request, n, wait_s=25, min_prices=3)


async def find_options(
    domain: str, intent: Intent, request: str, n: int, wait_s: float = WAIT_S, min_prices: int = 0
) -> tuple[list[AgentOption], dict[str, float]]:
    """Options lues directement sur la page de résultats ; FastReadError si rien de vérifié."""
    t0 = time.monotonic()
    text = await page_text(domain, wait_s, min_prices)
    t1 = time.monotonic()
    if len(text) < 300:
        raise FastReadError("page vide ou bloquée")
    options = verified(
        await _extract(text, request, n), text, free_allowed=intent.category in ("reservation", "train")
    )
    timings = {"lecture": t1 - t0, "extraction": time.monotonic() - t1}
    if not options:
        raise FastReadError("aucune option vérifiée sur la page")
    for i, option in enumerate(options[:n], start=1):
        option.id = f"o{i}"
    return options[:n], timings
