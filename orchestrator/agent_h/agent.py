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
import os
import time
import uuid
from typing import Any

from hai_agents import AsyncClient
from hai_agents.tools import Tool, tool

from orchestrator.contracts import Intent, Option, OrderSummary, SiteCard
from orchestrator.ports import PaymentResult

from . import prompts
from .base import AgentError, ApprovalCallback, NeedHumanCallback, NeedsHuman, PaymentDenied
from .metrics import RunMetrics, append_result
from .models import AgentAnswer, AgentOrderSummary, to_options, to_order_summary
from .site_memory import SiteMemory, domain_of, merge_card, site_memory_from_env

OK_STATUSES = {"idle", "completed"}

# Site visé par catégorie d'achat (docs/sites.md). Le plan B remplace ces adresses par celles des
# faux sites avec PILOTE_SITE_TRAIN et PILOTE_SITE_REPAS.
DEFAULT_SITES = {"train": "https://www.sncf-connect.com", "repas": "https://www.ubereats.com/fr"}


def site_for(intent: Intent) -> str:
    """Adresse du site pour la demande ; AgentError si la catégorie n'est pas prise en charge."""
    category = intent.category
    if category is None:
        raise AgentError("Catégorie d'achat inconnue : l'orchestrateur doit la demander d'abord.")
    site = os.getenv(f"PILOTE_SITE_{category.upper()}") or DEFAULT_SITES.get(category)
    if site is None:
        raise AgentError(f"Aucun site configuré pour la catégorie « {category} ».")
    return site


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
        self._browser_host = browser_host or os.getenv("PILOTE_BROWSER_HOST", "user_device")
        self._approval_callback = approval_callback
        self._need_human_callback = need_human_callback
        self._memory = memory or site_memory_from_env()
        self._timeout = step_timeout_s
        self._record = record_metrics
        self._max_total_eur = (
            max_total_eur if max_total_eur is not None else float(os.getenv("PILOTE_MAX_TOTAL_EUR", "999"))
        )

        self._auto_approve = (
            auto_approve if auto_approve is not None else os.getenv("PILOTE_AUTO_APPROVE") == "1"
        )

        self.order_id = ""  # UUID créé par checkout() ; recheck() le conserve
        self.agent_view_url: str | None = None
        self._site = ""
        self._session: Any = None
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
        async def request_payment_approval(summary: OrderSummary) -> str:
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
            raw = (
                summary
                if isinstance(summary, AgentOrderSummary)
                else AgentOrderSummary.model_validate(summary)
            )
            order = to_order_summary(raw, order_id=self.order_id, site=self._site or "inconnu")
        except Exception:
            return "denied"  # récapitulatif illisible : on ne paie pas
        key = ("pay", order.hash)
        if key in self._tool_cache:  # appels répétés pour la même action : même réponse
            return self._tool_cache[key]
        if not self._paying or not self.order_id:
            return "denied"  # hors de l'étape pay() : l'agent ne paie jamais de lui-même (pas mis en cache)
        if order.total_cents > self._max_total_eur * 100:
            decision = "denied"  # paiement réel : jamais au-delà du plafond
        elif self._approval_callback is not None:
            try:
                answer = await self._approval_callback(order)
            except Exception:
                answer = "denied"  # erreur ou délai dépassé côté orchestrateur : refus
            decision = "approved" if answer == "approved" else "denied"
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

    def _agent_spec(self) -> Any:
        if self._agent_name:
            return self._agent_name
        return {
            "name": "pilote-shopper",
            "description": "Navigue sur les sites marchands pour Pilote et s'arrête avant tout paiement.",
            "environments": [{"kind": "web", "id": "browser", "host": self._browser_host}],
            "instructions": prompts.GENERIC_INSTRUCTIONS,
        }

    async def _ensure_client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient()
        return self._client

    async def _wait(self, phase: str) -> AgentAnswer:
        """Attend que l'agent ait fini l'étape et renvoie sa réponse structurée."""
        started = time.monotonic()
        for _ in range(30):
            result = await self._session.wait_for_completion(
                from_index=self._cursor, timeout_seconds=self._timeout
            )
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
        await self._session.send_message(text)
        return await self._wait(phase)

    # --- interface publique ----------------------------------------------------------

    async def start(self, intent: Intent, site_card: SiteCard | None = None) -> None:
        self._site = site_for(intent)
        client = await self._ensure_client()
        self._intent = intent
        self.order_id = ""
        self._chosen = None
        self._tool_cache.clear()
        self._paying = False
        domain = domain_of(self._site)
        if site_card is None:
            site_card = await self._memory.get(domain)
        self._metrics = RunMetrics(site=domain, agent=self._agent_name or "inline", started=time.monotonic())
        self._session = await client.start_session(
            agent=self._agent_spec(),
            messages=prompts.search_message(
                intent, self._site, site_card, with_instructions=bool(self._agent_name)
            ),
            answer_schema=AgentAnswer,
            tools=self._tools(),
            idempotency_key=uuid.uuid4().hex,
            timezone="Europe/Paris",
        )
        self._cursor = 0
        try:
            session = await self._session.get()
            self.agent_view_url = getattr(session, "agent_view_url", None)
        except Exception:
            self.agent_view_url = None

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
            return to_order_summary(answer.order_summary, order_id=self.order_id, site=domain_of(self._site))
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
        if answer.payment_result is None:
            await self._finish("paiement non effectué", "-")
            raise PaymentDenied(
                answer.blocked_reason or "L'agent n'a pas pu payer (plafond ou total illisible)."
            )
        await self._finish("paiement tenté", answer.payment_result, answer)
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
        if answer is not None and answer.payment_result is not None:
            old = await self._memory.get(metrics.site)
            card = merge_card(old, metrics.site, answer.site_notes, now - metrics.started, metrics.steps)
            await self._memory.put(card)
        if self._record:
            append_result(metrics, now)
