"""ShoppingAgent : pilote l'agent H Company sur un vrai site marchand.

Une session H par commande. Elle reste ouverte entre les étapes (recherche, panier,
relecture, paiement) : chaque étape est un message envoyé dans la même session, et
l'agent répond dans un format structuré unique (AgentAnswer).

C'est l'agent de la démo : il agit sur les vrais sites, avec la vraie carte enregistrée
dans le compte marchand. Un paiement "accepted" est une vraie commande, payée.

Paiement : l'agent doit appeler l'outil request_payment_approval avant tout clic qui engage de
l'argent. Cet outil répond "denied" en dehors de l'étape pay(), si le total dépasse
PILOTE_MAX_TOTAL_EUR (999 € par défaut), s'il est illisible, ou si l'approval_callback de
l'orchestrateur refuse, échoue ou ne répond pas. Sans approval_callback, il répond "denied" aussi :
payer sans l'approbation de l'orchestrateur demande un choix explicite (auto_approve=True ou
PILOTE_AUTO_APPROVE=1, réservé aux tests réels en solo, jamais en production). Après le clic, la
validation bancaire (DSP2) reste faite par le titulaire dans son application.

Variables d'environnement :
- HAI_API_KEY : clé H (lue par le SDK).
- PILOTE_H_AGENT : nom d'un agent créé sur la plateforme H (ex. pilote-shopper).
  Sans elle, l'agent est défini dans le code (consigne de prompts.py).
- PILOTE_BROWSER_HOST : user_device (Chrome dédié de l'ordinateur de démo, par défaut) ou cloud.
- PILOTE_MAX_TOTAL_EUR : plafond d'un paiement, en euros (999 par défaut).
- PILOTE_AUTO_APPROVE : 1 pour payer sans approval_callback (voir plus haut). Absent : refus.
- PILOTE_SITE_TRAIN, PILOTE_SITE_REPAS : site visé par catégorie (plan B : adresses des faux sites).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from hai_agents import AsyncClient
from hai_agents.tools import Tool, tool

from orchestrator.contracts import Intent, Option, OrderSummary, SiteCard
from orchestrator.ports import PaymentResult

from . import local_chrome, prompts
from .base import (
    AgentError,
    ApprovalCallback,
    NeedHumanCallback,
    NeedsHuman,
    PaymentDenied,
    UnapprovedPurchase,
)
from .metrics import RunMetrics, append_result
from .models import (
    AgentAnswer,
    AgentOrderSummary,
    parse_json_text,
    summary_from_cents,
    to_options,
    to_order_summary,
)
from .narration import actions_in, describe_action
from .site_memory import SiteMemory, card_for_order, domain_of, merge_card, site_memory_from_env, starter_card
from .watch import StepWatch, StuckCallback, screenshot_in

log = logging.getLogger(__name__)

OK_STATUSES = {"idle", "completed"}

# Site visé par catégorie d'achat (docs/sites.md). Le plan B remplace ces adresses par celles des
# faux sites avec PILOTE_SITE_TRAIN et PILOTE_SITE_REPAS.
DEFAULT_SITES = {"train": "https://www.sncf-connect.com", "repas": "https://www.ubereats.com/fr"}


NETWORK_RETRIES = 5  # coupures réseau tolérées d'affilée en attendant la réponse de l'agent


def site_for(intent: Intent) -> str:
    """Adresse du site pour la demande, ou "" si l'agent doit le choisir ; AgentError sans catégorie."""
    category = intent.category
    if category is None:
        raise AgentError("Catégorie d'achat inconnue : l'orchestrateur doit la demander d'abord.")
    # Sans site configuré (une boutique, par exemple), l'agent choisit lui-même le site : "".
    return os.getenv(f"PILOTE_SITE_{category.upper()}") or DEFAULT_SITES.get(category) or ""


def _fit_effort(spec: dict[str, Any]) -> dict[str, Any]:
    """Seul holo4-27b a des niveaux de réflexion ; les autres modèles n'acceptent que « disabled » (doc H)."""
    model = spec.get("model")
    if model and model != "holo4-27b" and spec.get("reasoning_effort") not in (None, "disabled"):
        spec["reasoning_effort"] = "disabled"
    return spec


class ShoppingAgent:
    def __init__(
        self,
        *,
        client: AsyncClient | None = None,
        agent: str | None = None,
        browser_host: str | None = None,
        approval_callback: ApprovalCallback | None = None,
        need_human_callback: NeedHumanCallback | None = None,
        memory: SiteMemory | None = None,
        step_timeout_s: float = 600,
        record_metrics: bool = True,
        max_total_eur: float | None = None,
        auto_approve: bool | None = None,
    ) -> None:
        self._client = client
        self._agent_name = agent if agent is not None else os.getenv("PILOTE_H_AGENT") or None
        self._browser_host = browser_host or os.getenv("PILOTE_BROWSER_HOST") or "user_device"
        self._approval_callback = approval_callback
        self._need_human_callback = need_human_callback
        self._memory = memory or site_memory_from_env()
        self._timeout = step_timeout_s
        self._record = record_metrics
        self._max_total_eur = (
            max_total_eur if max_total_eur is not None else float(os.getenv("PILOTE_MAX_TOTAL_EUR") or "999")
        )

        self._auto_approve = (
            auto_approve if auto_approve is not None else os.getenv("PILOTE_AUTO_APPROVE") == "1"
        )

        self.order_id = ""  # UUID créé par checkout() ; recheck() le conserve
        self.agent_view_url: str | None = None
        self._site = ""
        self._session: Any = None
        self._site_card: SiteCard | None = None
        self._real_client = False
        self._portal: dict[str, Any] | None = None
        self.last_payment_message: str | None = None  # message du site après un achat
        self.last_denial_reason: str | None = None  # pourquoi le garde-fou a refusé de payer
        # Commentaire en direct : appelé avec une phrase courte à chaque action notable de l'agent
        self.on_progress: Callable[[str], Awaitable[None]] | None = None
        # Rappelée avec la dernière capture quand l'agent est bloqué : renvoie un conseil, ou None.
        self.on_stuck: StuckCallback | None = None
        self._cursor = 0
        self._intent: Intent | None = None
        self._options: list[Option] = []
        self._chosen: Option | None = None
        self._paying = False
        self._pay_denied = False  # le garde-fou a refusé pendant pay()
        self._tool_cache: dict[tuple[str, str], str] = {}
        self._metrics: RunMetrics | None = None
        self._last_answer: AgentAnswer | None = None

    # --- outils exécutés dans ce processus quand l'agent les appelle ----------------

    def _tools(self) -> list[Tool]:
        agent = self

        @tool(name="request_payment_approval")
        async def request_payment_approval(summary: AgentOrderSummary) -> str:
            """À appeler AVANT tout clic qui engage de l'argent (Payer, Commander, Acheter, Valider la commande, Confirmer), avec le récapitulatif exact affiché. Renvoie "approved" ou "denied". Si "denied", ne clique pas."""
            return await agent._decide_payment(summary)

        @tool(name="need_human")
        async def need_human(reason: str) -> str:
            """À appeler en cas de CAPTCHA, de cryptogramme demandé ou de page de connexion (pas pour la validation dans l'application bancaire : celle-ci, attends-la). Attends la réponse : "resolved" (un humain a fait le geste, continue) ou "abort" (arrête-toi)."""
            return await agent._ask_human(reason)

        return [request_payment_approval, need_human]

    async def _decide_payment(self, summary: Any) -> str:
        """Décision de l'outil request_payment_approval. Tout ce qui est douteux donne "denied"."""
        # Le SDK passe les arguments tels que l'agent les envoie : un dict JSON, pas un objet.
        try:
            summary = summary_from_cents(parse_json_text(summary))  # texte JSON, ou centimes du contrat
            raw = (
                summary
                if isinstance(summary, AgentOrderSummary)
                else AgentOrderSummary.model_validate(summary)
            )
            order = to_order_summary(raw, order_id=self.order_id, site=self._site or "inconnu")
        except Exception:
            self.last_denial_reason = "le récapitulatif du panier était illisible"
            self._pay_denied = self._pay_denied or self._paying
            return "denied"  # récapitulatif illisible : on ne paie pas
        key = ("pay", order.hash)
        if key in self._tool_cache:  # appels répétés pour la même action : même réponse
            return self._tool_cache[key]
        if not self._paying or not self.order_id:
            return "denied"  # hors de l'étape pay() : l'agent ne paie jamais de lui-même (pas mis en cache)
        if order.total_cents > self._max_total_eur * 100:
            decision = "denied"  # paiement réel : jamais au-delà du plafond
            self.last_denial_reason = "le total dépassait le plafond autorisé"
        elif self._approval_callback is not None:
            try:
                answer = await self._approval_callback(order)
            except Exception:
                answer = "denied"  # erreur ou délai dépassé côté orchestrateur : refus
            decision = "approved" if answer == "approved" else "denied"
            if decision == "denied":
                self.last_denial_reason = "Pilote n'a pas autorisé ce paiement"
        else:
            decision = "approved" if self._auto_approve else "denied"
        self._tool_cache[key] = decision
        self._pay_denied = self._pay_denied or decision == "denied"
        return decision

    async def _ask_human(self, reason: str) -> str:
        key = ("human", reason.strip().lower())
        if key in self._tool_cache:
            return self._tool_cache[key]
        if self._need_human_callback is None:
            answer = "abort"
        else:
            try:
                # Le callback de ports.py ne renvoie rien : il rend la main quand l'humain a fini.
                result = await self._need_human_callback(reason)
                answer = "abort" if result == "abort" else "resolved"
            except Exception:
                answer = "abort"
        self._tool_cache[key] = answer
        return answer

    # --- session H -------------------------------------------------------------------

    @property
    def _vault_id(self) -> str | None:
        """Coffre-fort H, seulement sur un navigateur cloud (limite du SDK H)."""
        vault_id = (os.getenv("PILOTE_H_VAULT_ID") or "").strip()
        return vault_id if vault_id and self._browser_host == "cloud" else None

    @property
    def _mirror_portal_agent(self) -> bool:
        """Agent du portail H lancé sur le Chrome local : on recopie sa configuration (un agent du
        portail emporte son environnement cloud, où la connexion SNCF bloque sur un CAPTCHA)."""
        return bool(self._agent_name) and self._browser_host == "user_device"

    async def _load_portal_agent(self, client: AsyncClient) -> None:
        if not self._mirror_portal_agent or self._portal is not None:
            return
        agent = (await client.agents.get_agent(self._agent_name)).model_dump(mode="json")
        mode: dict[str, Any] = {"type": "visual"}
        for env_id in agent.get("environments") or []:
            if isinstance(env_id, str) and not env_id.startswith("h/"):
                env = (await client.environments.get_environment(env_id)).model_dump(mode="json")
                mode = {k: v for k, v in (env.get("mode") or mode).items() if v is not None}
                break
        self._portal = {"agent": agent, "mode": mode}

    def _mirrored_spec(self) -> dict[str, Any]:
        agent, mode = self._portal["agent"], dict(self._portal["mode"])
        # Texte de la page en plus de la capture : très lourd sur SNCF Connect (≈ 350 000 tokens par
        # commande), donc plus lent. PILOTE_H_PAGE_TEXT=0 le coupe.
        # Texte de la page en plus de la capture, par défaut (lecture exacte sur n'importe quel site)
        mode["markdown"] = os.getenv("PILOTE_H_PAGE_TEXT", "").strip() != "0"
        environment: dict[str, Any] = {"kind": "web", "id": "browser", "host": "user_device", "mode": mode}
        if self._site:
            environment["start_url"] = self._site
        spec: dict[str, Any] = {
            "name": f"{agent['name']}-local",
            "description": agent.get("description") or "Agent de navigation de Pilote.",
            "environments": [environment],
            "instructions": agent.get("instructions") or prompts.generic_instructions(),
        }
        if agent.get("skills"):
            spec["skills"] = agent["skills"]
        # Sous-agents du portail (lecture rapide du web) : ils gardent leurs propres navigateurs chez H,
        # l'agent principal reste sur le Chrome local (compte connecté, paiement).
        if agent.get("subagents"):
            spec["subagents"] = agent["subagents"]
        model = (os.getenv("PILOTE_H_MODEL") or "").strip() or agent.get("model")
        if model:
            spec["model"] = model
        effort = agent.get("reasoning_effort") or (os.getenv("PILOTE_H_REASONING_EFFORT") or "").strip()
        if effort and effort != "default":
            spec["reasoning_effort"] = effort
        return _fit_effort(spec)

    def _agent_spec(self) -> Any:
        if self._mirror_portal_agent and self._portal is not None:
            return self._mirrored_spec()
        if self._agent_name:
            return self._agent_name
        environment: dict[str, Any] = {"kind": "web", "id": "browser", "host": self._browser_host}
        # Texte de la page en plus de la capture : l'agent lit prix, libellés et boutons exacts, sur
        # n'importe quel site. Plus de jetons ; PILOTE_H_PAGE_TEXT=0 le coupe.
        if os.getenv("PILOTE_H_PAGE_TEXT", "").strip() != "0":
            environment["mode"] = {"type": "visual", "markdown": True}
        if self._site:
            environment["start_url"] = self._site  # le navigateur s'ouvre directement sur le site
        # Coffre-fort H : H saisit les identifiants du site à la place de l'agent, qui ne les voit jamais.
        # Uniquement sur un navigateur cloud (limite du SDK H).
        if self._vault_id:
            environment["vault_id"] = self._vault_id
        # Profil de navigateur H par défaut : reprend les cookies d'une connexion faite une fois
        # (python -m orchestrator.agent_h.login_session). Navigateur cloud seulement.
        if os.getenv("PILOTE_H_DEFAULT_PROFILE") == "1" and self._browser_host == "cloud":
            environment["use_default_browser_profile"] = True
        spec: dict[str, Any] = {
            "name": "pilote-shopper",
            "description": "Navigue sur les sites marchands pour Pilote et s'arrête avant tout paiement.",
            "environments": [environment],
            "instructions": prompts.generic_instructions(with_vault="vault_id" in environment),
        }
        # Moins de réflexion avant chaque clic = navigation plus rapide (disabled, low, medium, xhigh).
        effort = os.getenv("PILOTE_H_REASONING_EFFORT", "").strip() or "low"
        if effort != "default":
            spec["reasoning_effort"] = effort
        model = (os.getenv("PILOTE_H_MODEL") or "").strip()
        if model:
            spec["model"] = model
        return _fit_effort(spec)

    async def _ensure_client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient()
        return self._client

    async def _watch_progress(self, from_index: int) -> None:
        """Suit le flux d'événements H et annonce ce que l'agent s'apprête à faire."""
        index, last = from_index, None
        watch = StepWatch(time.monotonic())
        while True:
            changes = await self._session.changes(from_index=index, wait_for_seconds=10, include_events=True)
            now = time.monotonic()
            events = (
                [
                    e.model_dump(mode="json") if hasattr(e, "model_dump") else e
                    for e in changes.new_events or []
                ]
                if changes is not None
                else []
            )
            index = (changes.first_index or index) + len(events) if changes is not None and events else index
            for event in events:
                if url := screenshot_in(event):
                    watch.saw_screenshot(url)
                for name, args in actions_in(event):
                    watch.saw_action(name, args, now)
                    sentence = describe_action(name, args)
                    if sentence and sentence != last and self.on_progress is not None:
                        last = sentence
                        await self.on_progress(sentence)
            await self._help_if_stuck(watch, now)
            if changes is None:
                await asyncio.sleep(1)

    async def _help_if_stuck(self, watch: StepWatch, now: float) -> None:
        """Surveillant : boucle ou étape qui n'avance plus -> lecture de la page, conseil à l'agent."""
        reason = watch.stuck_reason(now) if self.on_stuck is not None else None
        if reason is None or self.on_stuck is None or watch.screenshot is None:
            return
        watch.helped(now)
        try:
            image = await self._fetch_screenshot(watch.screenshot)
            hint = await self.on_stuck(image, reason) if image else None
            if hint:
                await self._session.send_message(
                    f"Conseil pour avancer (lecture de la page) : {hint} "
                    "Si cela ne marche pas, change de méthode ou appelle need_human."
                )
        except Exception:  # le surveillant ne doit jamais gêner la commande
            return

    async def _wait(self, phase: str) -> AgentAnswer:
        """Attend que l'agent ait fini l'étape et renvoie sa réponse structurée."""
        watcher: asyncio.Task[None] | None = None
        if (self.on_progress is not None or self.on_stuck is not None) and hasattr(self._session, "changes"):
            watcher = asyncio.create_task(self._watch_progress(self._cursor))
        try:
            return await self._wait_answer(phase)
        finally:
            if watcher is not None:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await watcher

    async def _fetch_screenshot(self, url: str) -> bytes | None:
        """Capture de l'agent (adresse H protégée par la clé, redirigée vers l'image)."""
        from hai_agents.client import default_api_key

        key = default_api_key()
        if not key:
            return None
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
                response = await http.get(url, headers={"Authorization": f"Bearer {key}"})
            if response.status_code == 200 and response.headers.get("content-type", "").startswith("image/"):
                return response.content
        except httpx.HTTPError:
            pass
        return None

    async def _wait_answer(self, phase: str) -> AgentAnswer:
        started = time.monotonic()
        network_errors = 0
        for _ in range(30):
            try:
                result = await self._session.wait_for_completion(
                    from_index=self._cursor, timeout_seconds=self._timeout
                )
            except httpx.TransportError:
                # Coupure passagère avec H (ReadTimeout constaté le 18/11 pendant un achat) : l'agent
                # continue de son côté, on reprend la lecture au même endroit au lieu d'abandonner.
                network_errors += 1
                if network_errors > NETWORK_RETRIES:
                    raise
                await asyncio.sleep(2 * network_errors)
                continue
            network_errors = 0
            fresh = result.next_from_index > self._cursor
            self._cursor = result.next_from_index
            if result.status not in OK_STATUSES:
                raise AgentError(
                    f"Étape {phase} : session {result.status} ({result.error or result.error_code})"
                )
            if result.pending_approvals:  # garde-fou de la plateforme : on refuse tout ce qui n'est pas armé
                for call in result.pending_approvals:
                    await self._session.deny(call.tool_req.id, "Paiement non approuvé par Pilote.")
                continue
            if fresh and result.answer is not None:
                answer = (
                    result.answer
                    if isinstance(result.answer, AgentAnswer)
                    else AgentAnswer.model_validate(result.answer)
                )
                self._last_answer = answer
                if answer.payment_result is not None and not self._paying:
                    # Achat cliqué hors de pay() : on le signale au lieu de le prendre pour une erreur
                    await self._finish("achat hors étape paiement", answer.payment_result, answer)
                    raise UnapprovedPurchase(answer.payment_result, answer.payment_message)
                if self._metrics:
                    self._metrics.phases[phase] = round(time.monotonic() - started, 1)
                if (
                    answer.blocked_reason
                    and not answer.options
                    and not answer.order_summary
                    and not answer.payment_result
                ):
                    raise NeedsHuman(answer.blocked_reason)
                return answer
            await asyncio.sleep(1)  # le message n'a pas encore réveillé la session
        raise AgentError(f"Étape {phase} : aucune réponse de l'agent")

    async def _send(self, text: str, phase: str) -> AgentAnswer:
        if self._session is None:
            raise AgentError("Session non démarrée : appelle start() d'abord.")
        if self._fresh_session_per_step:
            await self._restart_session(text)
        else:
            await self._session.send_message(text)
        return await self._wait(phase)

    @property
    def _idle_timeout_s(self) -> int:
        """Garde la session H ouverte entre deux étapes (doc H : sans ce réglage, la session se termine dès
        que l'agent répond ; en Chrome local, le SDK débranche alors le navigateur). 0 = ancien comportement."""
        try:
            return max(0, int(os.getenv("PILOTE_H_IDLE_TIMEOUT_S") or "900"))
        except ValueError:
            return 900

    @property
    def _fresh_session_per_step(self) -> bool:
        # Chrome local : quand une session H se termine, le SDK débranche son pilote du navigateur et la
        # reprise suivante réutilise ce pilote mort (« Connection refused », mesuré le 2026-11-18). On
        # repart donc d'une session neuve à chaque étape ; le Chrome dédié garde la page.
        return self._browser_host == "user_device" and self._real_client and self._idle_timeout_s == 0

    async def _restart_session(self, step: str) -> None:
        await asyncio.to_thread(local_chrome.ensure_page, self._site)
        try:
            await self._session.cancel()  # session terminée en principe ; sans effet sinon
        except Exception:
            pass
        client = await self._ensure_client()
        spec = self._agent_spec()
        if isinstance(spec, dict):  # ne pas rouvrir l'accueil : on continue depuis la page actuelle
            spec["environments"][0].pop("start_url", None)
        self._session = await client.start_session(
            agent=spec,
            messages=prompts.continue_message(self._intent, self._site, self._site_card, self._chosen, step),
            answer_schema=AgentAnswer,
            tools=self._tools(),
            idempotency_key=uuid.uuid4().hex,
            timezone="Europe/Paris",
            **({"idle_timeout_s": self._idle_timeout_s} if self._idle_timeout_s else {}),
        )
        self._cursor = 0
        try:
            self.agent_view_url = getattr(await self._session.get(), "agent_view_url", None)
        except Exception:
            pass

    # --- interface publique ----------------------------------------------------------

    async def start(self, intent: Intent, site_card: SiteCard | None = None) -> None:
        self._site = site_for(intent)
        self._real_client = self._real_client or self._client is None  # client simulé dans les tests
        if self._browser_host == "user_device" and self._real_client:
            # Sinon le SDK lance Chrome sans --force-device-scale-factor=1 : clics décalés sur Retina
            await asyncio.to_thread(local_chrome.ensure, self._site)
            await asyncio.to_thread(local_chrome.fresh_page, self._site)
        client = await self._ensure_client()
        self._intent = intent
        self.order_id = ""
        self._chosen = None
        self._tool_cache.clear()
        self._paying = False
        domain = domain_of(self._site)
        if site_card is None:
            site_card = card_for_order(await self._memory.get(domain), starter_card(domain))
        self._site_card = site_card
        await self._load_portal_agent(client)
        self._metrics = RunMetrics(site=domain, agent=self._agent_name or "inline", started=time.monotonic())
        self._session = await client.start_session(
            agent=self._agent_spec(),
            messages=prompts.search_message(
                intent,
                self._site,
                site_card,
                with_instructions=bool(self._agent_name) and not self._mirror_portal_agent,
                with_vault=self._vault_id is not None,
            ),
            answer_schema=AgentAnswer,
            tools=self._tools(),
            idempotency_key=uuid.uuid4().hex,
            timezone="Europe/Paris",
            **({"idle_timeout_s": self._idle_timeout_s} if self._idle_timeout_s else {}),
        )
        self._cursor = 0
        try:
            session = await self._session.get()
            self.agent_view_url = getattr(session, "agent_view_url", None)
        except Exception:
            self.agent_view_url = None

    async def ask(self, question: str) -> str:
        """Demande libre : l'agent cherche la réponse sur le web, sans rien acheter."""
        client = await self._ensure_client()
        self._site, self.order_id, self._intent = "", "", None
        self._tool_cache.clear()
        self._paying = False  # le garde-fou refuse tout paiement
        self._metrics = RunMetrics(
            site="question", agent=self._agent_name or "inline", started=time.monotonic()
        )
        # Questions : agent du portail tel quel, dans le navigateur cloud de H, avec ses sous-agents de
        # lecture rapide (PILOTE_H_QUESTION_AGENT). Aucun compte ni paiement : le Chrome local reste aux commandes.
        question_agent = os.getenv("PILOTE_H_QUESTION_AGENT", "").strip() or None
        self._session = await client.start_session(
            agent=question_agent or self._agent_spec(),
            messages=prompts.question_message(
                question, with_instructions=bool(question_agent or self._agent_name)
            ),
            answer_schema=AgentAnswer,
            tools=self._tools(),
            idempotency_key=uuid.uuid4().hex,
            timezone="Europe/Paris",
        )
        self._cursor = 0
        try:
            self.agent_view_url = getattr(await self._session.get(), "agent_view_url", None)
        except Exception:
            self.agent_view_url = None
        answer = await self._wait("question")
        await self._finish("question", "-")
        reply = " ".join((answer.reply or "").split())
        if not reply:
            raise AgentError("L'agent n'a pas trouvé de réponse.")
        source = " ".join((answer.reply_source or "").split())
        # Une « source » qui décrit un échec (« demande incomplète ») n'est pas une source : on ne la dit pas
        if source and re.search(r"incompl|manquant|aucun|inconnu|erreur|demande", source, re.IGNORECASE):
            source = None
        return f"{reply} (Source : {source}.)" if source else reply

    async def search(self) -> list[Option]:
        answer = await self._wait("search")
        self._options = to_options(answer.options)
        return self._options

    async def refine(self, message: str) -> list[Option]:
        answer = await self._send(prompts.refine_message(message), "refine")
        self._options = to_options(answer.options)
        return self._options

    async def choose(self, option_id: str) -> None:
        chosen = next((o for o in self._options if o.id == option_id), None)
        if chosen is None:
            raise ValueError(f"Option inconnue : {option_id}")
        self._chosen = chosen

    def _summary_from(self, answer: AgentAnswer, phase: str) -> OrderSummary:
        if answer.order_summary is None:
            raise AgentError(f"Étape {phase} : pas de récapitulatif renvoyé")
        try:
            site = domain_of(self._site) or domain_of(answer.order_summary.page_url or "") or "site choisi"
            return to_order_summary(answer.order_summary, order_id=self.order_id, site=site)
        except ValueError as error:
            raise AgentError(f"Étape {phase} : récapitulatif inutilisable ({error})") from error

    async def checkout(self) -> OrderSummary:
        if self._chosen is None:
            raise AgentError("Aucune option choisie : appelle choose() d'abord.")
        if not self.order_id:
            self.order_id = str(uuid.uuid4())
        answer = await self._send(prompts.checkout_message(self._chosen), "checkout")
        return self._summary_from(answer, "checkout")

    async def recheck(self) -> OrderSummary:
        if not self.order_id:
            raise AgentError("Pas de commande en cours : appelle checkout() d'abord.")
        answer = await self._send(prompts.recheck_message(), "recheck")
        return self._summary_from(answer, "recheck")

    async def pay(self) -> PaymentResult:
        """Clique sur le bouton de paiement ; la validation se fait dans l'application bancaire."""
        self._paying, self._pay_denied = True, False
        try:
            answer = await self._send(prompts.pay_message(), "pay")
        except NeedsHuman as blocked:
            if not self._pay_denied:
                raise
            # Refus du garde-fou : l'agent explique pourquoi il s'arrête, ce n'est pas un CAPTCHA.
            await self._finish("paiement non effectué", "-")
            raise PaymentDenied(str(blocked)) from blocked
        finally:
            self._paying = False
        if answer.payment_result is None or self._pay_denied:
            await self._finish("paiement non effectué", "-")
            raise PaymentDenied(
                answer.blocked_reason or "L'agent n'a pas pu payer (plafond ou total illisible)."
            )
        await self._finish("paiement tenté", answer.payment_result, answer)
        return answer.payment_result

    async def buy(self) -> PaymentResult:
        """Achat direct de l'option choisie, en une étape : panier, approbation (outil), clic, résultat."""
        if self._chosen is None:
            raise AgentError("Aucune option choisie : appelle choose() d'abord.")
        if not self.order_id:
            self.order_id = str(uuid.uuid4())
        self.last_payment_message = None
        self.last_denial_reason = None
        self._paying, self._pay_denied = True, False
        try:
            answer = await self._send(prompts.buy_message(self._chosen), "buy")
        except NeedsHuman as blocked:
            if not self._pay_denied:
                raise
            await self._finish("achat non effectué", "-")
            raise PaymentDenied(str(blocked)) from blocked
        finally:
            self._paying = False
        if answer.payment_result is None or self._pay_denied:
            await self._finish("achat non effectué", "-")
            raise PaymentDenied(
                self.last_denial_reason or answer.blocked_reason or "L'agent n'a pas pu acheter."
            )
        self.last_payment_message = answer.payment_message
        await self._finish("achat direct", answer.payment_result, answer)
        return answer.payment_result

    async def cancel(self) -> None:
        if self._session is not None:
            try:
                await self._session.cancel()
            finally:
                await self._finish("annulée", "-")

    async def _finish(self, outcome: str, payment: str, answer: AgentAnswer | None = None) -> None:
        if self._metrics is None:
            return
        metrics, self._metrics = self._metrics, None
        metrics.outcome, metrics.payment = outcome, payment
        try:
            metrics.steps = (await self._session.status()).steps
        except Exception:
            pass
        now = time.monotonic()
        # Mémoire gardée à chaque fin de commande, achetée ou non : un échec apprend aussi (pièges,
        # raison du blocage). Seul un achat accepté compte comme réussi. Pas pour les questions libres.
        answer = answer or self._last_answer
        notes = answer.site_notes if answer is not None else None
        blocked = answer.blocked_reason if answer is not None and payment != "accepted" else None
        if outcome != "question" and (notes or blocked or payment == "accepted"):
            try:
                old = await self._memory.get(metrics.site)
                card = merge_card(
                    old,
                    metrics.site,
                    notes,
                    now - metrics.started,
                    metrics.steps,
                    success=payment == "accepted",
                    blocked=blocked,
                )
                await self._memory.put(card)
            except Exception:
                log.warning("mémoire du site non enregistrée", exc_info=True)
        if self._record:
            append_result(metrics, now)
