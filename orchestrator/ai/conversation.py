"""Réponses de Pilote rédigées par un modèle de langage, avec des faits vérifiés par le code.

Le modèle reçoit la situation (ce que Pilote doit faire passer), les faits autorisés (options, prix,
heures, demande comprise), la phrase écrite d'avance et l'historique. Il reformule naturellement et
s'adapte à ce que la personne vient de dire.

Garde-fous : chaque nombre de la réponse doit venir des faits, de la phrase d'avance ou de la phrase
de la personne ; une réponse qui parle d'achat ou de paiement alors que la phrase d'avance n'en parle
pas est refusée ; au moindre doute, délai ou erreur, Pilote dit la phrase écrite d'avance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

REPLY_TIMEOUT_S = 4.0
MAX_CHARS = 420

SYSTEM = """\
Tu es Topil, un assistant vocal en français qui aide des personnes aveugles ou malvoyantes à faire \
leurs achats en ligne et à trouver des informations. Tu parles à voix haute : tes réponses sont \
écoutées, pas lues.

Style : chaleureux, bienveillant, calme et naturel, comme une personne attentionnée qui aime aider. \
Si la personne dit comment elle va, réagis avec sincérité (content pour elle, ou un mot de réconfort \
si elle va moins bien) avant de lui proposer ton aide. Tu peux prendre brièvement de ses nouvelles \
ou lui souhaiter une bonne journée, sans insister ni en faire trop. Phrases courtes, vocabulaire \
simple, pas de listes à puces, pas d'emoji, pas de markdown. Une à trois phrases. Adapte-toi à ce \
que la personne vient de dire (remerciement, hésitation, question sur toi, humeur) avant de \
revenir à la tâche.

Règles strictes :
- N'utilise QUE les faits fournis. N'invente jamais un prix, une heure, une gare, un train, un \
restaurant, une date ou un résultat.
- Ne dis jamais qu'un achat ou un paiement a été fait si la phrase de référence ne le dit pas.
- Garde le sens de la phrase de référence et la même demande finale (question posée, choix \
attendu).
- Écris toujours les nombres, heures et prix en chiffres (14 h 44, 49 euros), jamais en lettres.
- Vouvoie toujours la personne.
- Tu es une IA : ne prétends pas être humain.
Réponds uniquement avec la phrase à dire."""

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SPELLED = re.compile(
    r"\b(deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize|"
    r"vingt|trente|quarante|cinquante|soixante|cent|mille)\b",
    re.IGNORECASE,
)
_MONEY_WORDS = re.compile(r"\b(achet|pay[ée]|paiement|command[ée]e?\b|réserv)", re.IGNORECASE)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".").lstrip("0") or "0" for n in _NUMBER.findall(text)}


def facts_ok(reply: str, allowed: str, fallback: str) -> bool:
    """Nombres connus seulement, et pas d'achat annoncé si la référence n'en parle pas."""
    if not reply or len(reply) > MAX_CHARS:
        return False
    if not _numbers(reply) <= _numbers(allowed):
        return False
    if _SPELLED.search(reply) and not _SPELLED.search(allowed):
        return False  # un nombre en lettres échapperait à la vérification
    if _MONEY_WORDS.search(reply) and not _MONEY_WORDS.search(fallback):
        return False
    return True


def _clean(text: str) -> str:
    text = text.strip().strip('"').strip("«»").strip()
    text = re.sub(r"[*_#`]", "", text)
    return " ".join(text.split())


async def reply(
    chat_client: Any,
    model: str,
    *,
    situation: str,
    fallback: str,
    facts: str = "",
    heard: str = "",
    history: list[dict[str, str]] | None = None,
    timeout_s: float = REPLY_TIMEOUT_S,
) -> str:
    """Phrase naturelle à dire, ou `fallback` si le modèle échoue ou sort des faits."""
    turns = (history or [])[-6:]
    context = "\n".join(
        f"{'Personne' if t.get('role') == 'user' else 'Topil'} : {t.get('text', '')}" for t in turns
    )
    user = (
        f"Conversation récente :\n{context or '(début)'}\n\nLa personne vient de dire : « {heard} »\n\n"
        if heard
        else f"Conversation récente :\n{context or '(début)'}\n\n"
    )
    user += (
        f"Situation : {situation}\n"
        f"Faits autorisés : {facts or '(aucun)'}\n"
        f"Phrase de référence (à reformuler naturellement) : {fallback}"
    )
    try:
        response = await asyncio.wait_for(
            chat_client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                temperature=0.6,
                max_tokens=160,
            ),
            timeout_s,
        )
        text = _clean(response.choices[0].message.content or "")
    except Exception as error:  # délai, réseau, quota : la phrase d'avance
        log.info("réponse IA indisponible (%s)", type(error).__name__)
        return fallback
    if not facts_ok(text, f"{facts} {fallback} {heard}", fallback):
        log.info("réponse IA écartée (faits non vérifiés)")
        return fallback
    return text


QUESTION_SYSTEM = """\
Tu prépares une recherche sur le web pour Topil, un assistant vocal. On te donne la conversation \
récente et la dernière phrase de la personne (transcrite depuis la voix : elle peut contenir des \
mots mal entendus).

1. Complète la question avec la conversation : si la personne répond à une précision demandée \
(« Lyon » après « Pour aller où ? »), fusionne-la avec la question d'avant.
2. Si une information indispensable manque encore (un lieu, une date, un nom), ne devine jamais : \
demande-la en une phrase courte, au vouvoiement, qui finit par un point d'interrogation.
3. Sinon, écris la question complète et autonome, comme on la taperait dans un moteur de recherche.

Réponds uniquement en JSON : {"action": "search", "question": "..."} ou {"action": "ask", "say": "..."}."""


async def prepare_question(
    chat_client: Any,
    model: str,
    *,
    question: str,
    history: list[dict[str, str]] | None = None,
    timeout_s: float = 5.0,
) -> dict[str, str]:
    """Question prête pour la recherche, ou précision à demander. Échec : la question telle quelle."""
    turns = (history or [])[-8:]
    context = "\n".join(
        f"{'Personne' if t.get('role') == 'user' else 'Topil'} : {t.get('text', '')}" for t in turns
    )
    user = (
        f"Conversation récente :\n{context or '(début)'}\n\nDernière phrase de la personne : « {question} »"
    )
    try:
        response = await asyncio.wait_for(
            chat_client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": QUESTION_SYSTEM}, {"role": "user", "content": user}],
                temperature=0,
                max_tokens=160,
                response_format={"type": "json_object"},
            ),
            timeout_s,
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception as error:
        log.info("préparation de la question indisponible (%s)", type(error).__name__)
        return {"action": "search", "question": question}
    if data.get("action") == "ask" and str(data.get("say", "")).strip():
        return {"action": "ask", "say": _clean(str(data["say"]))}
    return {"action": "search", "question": _clean(str(data.get("question") or question))}
