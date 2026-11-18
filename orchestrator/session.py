"""Session Pilote : la machine à états qui relie la voix, l'IA et l'agent H.

Une seule session pour tout l'orchestrateur : l'interface vocale et l'écran du jury s'y connectent
chacun avec leur WebSocket et reçoivent les mêmes messages. Seule cette classe fait avancer l'état.

Parcours d'une commande (contracts/README.md) :
listening → understanding → searching → proposing → cart → confirm_1 → recheck → confirm_2
→ paying → done. Sorties possibles : cancelled, human_needed.

Règle de sécurité : l'agent n'appelle pay() qu'après le premier oui, la relecture de la page
(même hash) et le deuxième oui. Pendant pay(), l'outil H
request_payment_approval passe par approve_payment(), qui ne répond "approved" que si l'état est
`paying` et si la page montre toujours le récapitulatif validé. Tout le reste répond "denied".
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import datetime as dt
import hmac
import json
import logging
import re
import unicodedata
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, TypeAdapter, ValidationError

from orchestrator.agent_h.base import AgentError, NeedsHuman, PaymentDenied, UnapprovedPurchase
from orchestrator.ai.hf import QUESTIONS, SPEAK_MIME, AIError, complete_intent
from orchestrator.ai.speech_text import euros, readable_progress
from orchestrator.config import Settings
from orchestrator.contracts import (
    ClientAudio,
    ClientConfirm,
    ClientMessage,
    ClientText,
    Intent,
    Option,
    OrderSummary,
    ServerAgentView,
    ServerError,
    ServerIntent,
    ServerOptions,
    ServerReady,
    ServerSay,
    ServerState,
    ServerSummary,
    ServerTranscript,
    State,
    When,
)
from orchestrator.ports import (
    AI,
    AgentFactory,
    ApprovalDecision,
    HistoryTurn,
    NeedHumanDecision,
    ShoppingAgent,
)

log = logging.getLogger(__name__)
T = TypeVar("T")

INTRO = (
    "Je suis Pilote, un assistant automatique. Que puis-je faire pour vous ? Par exemple : un train de "
    "Paris pour Lille demain après 14 heures, ou une question comme « à quelle heure ferme la poste ? »."
)
NEXT = "Que puis-je faire d'autre pour vous ?"
# États où Pilote attend une réponse de la personne.
WAITING: set[State] = {"listening", "proposing", "confirm_1", "confirm_2", "human_needed"}
CLIENT_MESSAGE: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
SendFn = Callable[[dict[str, Any]], Awaitable[None]]


class Abort(Exception):
    """Fin anticipée de la commande. `message` est dit à l'oral ; `code` part aussi en message error."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


CODE_ATTEMPTS = 3
_DIGIT_WORDS = {
    "zero": "0",
    "un": "1",
    "une": "1",
    "deux": "2",
    "trois": "3",
    "quatre": "4",
    "cinq": "5",
    "six": "6",
    "sept": "7",
    "huit": "8",
    "neuf": "9",
}


def spoken_digits(text: str) -> str:
    """« 1 2 3 », « 123 », « un deux trois » -> « 123 ». Les autres mots sont ignorés."""
    digits = []
    for word in re.findall(r"[a-z]+|\d", _plain(text)):
        if word.isdigit():
            digits.append(word)
        elif word in _DIGIT_WORDS:
            digits.append(_DIGIT_WORDS[word])
    return "".join(digits)


# Commentaire en direct : seulement pendant que l'agent travaille seul, une phrase toutes les 6 s au plus.
PROGRESS_STATES = ("searching", "cart", "paying")
PROGRESS_GAP_S = 6.0


class Purchased(Exception):
    """L'achat a eu lieu sur le site hors du déroulé prévu : on le dit, on ne prétend jamais le contraire."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_EMAIL = re.compile(r"\S+@\S+")


def site_message_for_speech(message: str | None) -> str:
    """Première phrase du message du site, sans adresse e-mail (donnée personnelle, inutile à l'oral)."""
    if not message:
        return ""
    first = re.split(r"(?<=[.!?])\s", message.strip(), maxsplit=1)[0]
    return _EMAIL.sub("", first).strip()


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()


def _paris_today() -> dt.date:
    return dt.datetime.now(ZoneInfo("Europe/Paris")).date()


def _intent(kind: str, text: str) -> Intent:
    return Intent(
        kind=kind,  # type: ignore[arg-type]
        text=text,
        category=None,
        object=None,
        quantity=None,
        when=When(date=None, after=None, before=None, asap=False),
        budget_cents=None,
        details={},
        constraints=[],
        choice_index=None,
        missing=[],
        question=None,
    )


def merge_answer(pending: Intent, answer: Intent) -> Intent:
    """Complète une demande incomplète avec la réponse à la question posée.

    Les champs remplis dans la réponse s'ajoutent à la demande. Si le modèle n'a rien extrait
    (« Paris » tout seul), la phrase remplit directement l'information demandée.
    """
    data = pending.model_dump(mode="json")
    extracted = False
    for key in ("category", "object", "quantity", "budget_cents"):
        value = getattr(answer, key)
        if value is not None:
            data[key], extracted = value, True
    for key, value in answer.when.model_dump(mode="json").items():
        if value not in (None, False):
            data["when"][key], extracted = value, True
    if answer.details:
        data["details"].update(answer.details)
        extracted = True
    for constraint in answer.constraints:
        if constraint not in data["constraints"]:
            data["constraints"].append(constraint)
            extracted = True
    asked = pending.missing[0] if pending.missing else None
    if not extracted and asked and (asked == "object" or asked.startswith("details.")):
        value = re.sub(r"^(je pars de|depuis|de|d'|pour|a|à|vers)\s+", "", answer.text.strip(), flags=re.I)
        value = value.strip(" .!?")
        if value:
            if asked == "object":
                data["object"] = value
            else:
                data["details"][asked.split(".", 1)[1]] = value
    data["kind"] = "new_request"
    return Intent.model_validate(complete_intent(data, f"{pending.text} / {answer.text}"))


class Session:
    def __init__(
        self,
        *,
        ai: AI,
        agent_factory: AgentFactory,
        settings: Settings,
        today: Callable[[], dt.date] = _paris_today,
    ) -> None:
        self.ai = ai
        self.agent_factory = agent_factory
        self.settings = settings
        self.today = today
        self.session_id = uuid.uuid4().hex[:8]
        self.state: State = "listening"
        self.history: list[HistoryTurn] = []
        self._clients: set[SendFn] = set()
        self._snapshot: dict[str, dict[str, Any]] = {}
        self._inbox: asyncio.Queue[ClientMessage] = asyncio.Queue()
        self._answers: asyncio.Queue[Intent] = asyncio.Queue()
        self._waiting = False
        self._resume_state: State = "listening"
        self._agent: ShoppingAgent | None = None
        self._intent: Intent | None = None
        self._summary: OrderSummary | None = None
        self._armed_hash: str | None = None
        self._direct_limit: int | None = None  # achat direct : prix maximal accepté (centimes)
        self._last_progress = 0.0
        self._secret_mode = False  # pendant la demande du code secret
        self._payment_refusal: str | None = None
        self._flow: asyncio.Task[None] | None = None
        self._reader: asyncio.Task[None] | None = None
        self._cancelling = asyncio.Lock()

    # --- cycle de vie -----------------------------------------------------------------

    async def start(self) -> None:
        self._reader = asyncio.create_task(self._read_loop(), name="pilote-reader")
        self._flow = asyncio.create_task(self._flow_loop(), name="pilote-flow")

    async def stop(self) -> None:
        for task in (self._flow, self._reader):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        await self._close_agent()

    # --- connexions -------------------------------------------------------------------

    async def attach(self, send: SendFn) -> None:
        """Nouvel écran : il reçoit l'état courant, puis la phrase d'accueil (à lui seul)."""
        self._clients.add(send)
        await self._send_to(send, ServerReady(session_id=self.session_id))
        for key in ("state", "intent", "options", "summary", "agent_view"):
            if key in self._snapshot:
                await self._send_raw(send, self._snapshot[key])
        if self.state in ("listening", "done", "cancelled"):
            await self._send_to(send, await self._say_message(INTRO))

    def detach(self, send: SendFn) -> None:
        self._clients.discard(send)

    async def receive(self, data: Any) -> None:
        """Message reçu d'un écran. Annuler passe devant tout le reste."""
        try:
            message = CLIENT_MESSAGE.validate_python(data)
        except ValidationError:
            log.warning("Message hors contrat ignoré : %s", str(data)[:200])
            return
        if message.type == "cancel":
            await self.cancel_order("D'accord, j'annule. Rien n'a été acheté.")
        else:
            await self._inbox.put(message)

    # --- envoi --------------------------------------------------------------------------

    async def _send_raw(self, send: SendFn, data: dict[str, Any]) -> None:
        try:
            await send(data)
        except Exception:  # écran fermé : on l'oublie
            self.detach(send)

    async def _send_to(self, send: SendFn, message: BaseModel) -> None:
        await self._send_raw(send, message.model_dump(mode="json"))

    async def _emit(self, message: BaseModel) -> None:
        data = message.model_dump(mode="json")
        key = data["type"]
        if key in ("state", "intent", "options", "summary", "agent_view"):
            self._snapshot[key] = data
        for send in list(self._clients):
            await self._send_raw(send, data)

    async def _set_state(self, state: State) -> None:
        if state == self.state and "state" in self._snapshot:
            return
        self.state = state
        self._journal("state", state=state)
        await self._emit(ServerState(state=state))

    async def _say_message(self, text: str) -> ServerSay:
        audio: bytes | None = None
        try:
            audio = await self.ai.speak(text)
        except Exception:  # la voix du navigateur prend le relais
            log.exception("speak() a échoué")
        if not audio:
            return ServerSay(text=text, audio=None, mime=None)
        return ServerSay(text=text, audio=base64.b64encode(audio).decode("ascii"), mime=SPEAK_MIME)

    async def _progress(self, text: str) -> None:
        """Phrase courte pendant que l'agent travaille, hors historique (réservé à la compréhension)."""
        if self.state not in PROGRESS_STATES:
            return
        now = asyncio.get_running_loop().time()
        if now - self._last_progress < PROGRESS_GAP_S:
            return
        self._last_progress = now
        await self._emit(await self._say_message(text))

    async def _say(self, text: str) -> None:
        self.history.append({"role": "pilote", "text": text})
        await self._emit(ServerTranscript(role="pilote", text=text))
        await self._emit(await self._say_message(text))

    async def _error(self, code: str, message: str) -> None:
        await self._emit(ServerError(code=code, message=message))  # type: ignore[arg-type]

    def _journal(self, event: str, **fields: Any) -> None:
        """Journal des étapes : jamais d'audio ni de phrase prononcée."""
        entry = {
            "ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "session": self.session_id,
            "event": event,
            "order_id": self._summary.order_id if self._summary else None,
            **fields,
        }
        log.info("journal %s", entry)
        if self.settings.journal_path:
            try:
                path = Path(self.settings.journal_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                log.exception("journal illisible")

    # --- compréhension -----------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Transcrit et comprend chaque message dès qu'il arrive, pour que « annule » marche toujours."""
        while True:
            message = await self._inbox.get()
            try:
                intent = await self._understand(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Compréhension impossible")
                intent = None
            if intent is None:
                if self._waiting:
                    await self._set_state(self._resume_state)
                    await self._say("Je n'ai pas compris. Pouvez-vous répéter ?")
                continue
            if intent.kind == "cancel":
                await self.cancel_order("D'accord, j'annule. Rien n'a été acheté.")
            elif self._waiting:
                await self._answers.put(intent)
            else:
                await self._say("Un instant, je travaille sur votre commande. Dites « annule » pour arrêter.")

    async def _understand(self, message: ClientMessage) -> Intent | None:
        if isinstance(message, ClientConfirm):
            return _intent("confirm" if message.value else "deny", "oui" if message.value else "non")
        if self._waiting:
            self._resume_state = self.state
            await self._set_state("understanding")
        if isinstance(message, ClientAudio):
            audio = base64.b64decode(message.data)
            try:
                text = await self.ai.transcribe(audio, message.mime)
            except AIError:
                return None
            finally:
                del audio  # l'audio n'est gardé nulle part
        else:
            assert isinstance(message, ClientText)
            text = message.text
        if self._secret_mode:
            # Code secret : ni modèle de langage, ni historique, ni affichage. Comparé puis oublié.
            await self._emit(ServerTranscript(role="user", text="•••"))
            plain = _plain(text)
            if "annul" in plain:
                return _intent("cancel", "annule")
            if re.match(r"^(non|stop)\b", plain):
                return _intent("deny", "non")
            return _intent("other", text)
        await self._emit(ServerTranscript(role="user", text=text))
        try:
            intent = await self.ai.parse_intent(text, self.today(), list(self.history))
        except AIError:
            return None
        self.history.append({"role": "user", "text": text})
        await self._emit(ServerIntent(intent=intent))
        return intent

    async def _ask(self, state: State, wait_s: float | None = None) -> Intent:
        """Passe dans un état d'attente et renvoie la prochaine phrase comprise."""
        while not self._answers.empty():  # réponses arrivées pendant une étape longue : périmées
            self._answers.get_nowait()
        self._resume_state = state
        await self._set_state(state)
        self._waiting = True
        try:
            return await asyncio.wait_for(self._answers.get(), wait_s)
        except TimeoutError as error:
            raise Abort("Je n'ai pas eu de réponse, j'annule. Rien n'a été acheté.", "timeout") from error
        finally:
            self._waiting = False
        self._resume_state: State = "listening"

    async def _yes_no(self, state: State, question: str) -> bool:
        await self._say(question)
        while True:
            answer = await self._ask(state, self.settings.confirm_timeout_s)
            if answer.kind == "confirm":
                return True
            if answer.kind == "deny":
                return False
            await self._say("Répondez par oui ou par non.")

    # --- annulation ---------------------------------------------------------------------

    async def cancel_order(self, message: str) -> None:
        """Arrête tout de suite la commande en cours, dans n'importe quel état."""
        async with self._cancelling:
            if self._flow is not None and not self._flow.done():
                self._flow.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._flow
            await self._end_order("cancelled", message)
            self._flow = asyncio.create_task(self._flow_loop(), name="pilote-flow")

    async def _close_agent(self) -> None:
        agent, self._agent = self._agent, None
        self._armed_hash = None
        if agent is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(agent.cancel(), self.settings.step_timeouts["cancel"])

    async def _end_order(self, state: State, message: str) -> None:
        await self._close_agent()
        self._journal("end", outcome=state)
        self._intent = None
        self._summary = None
        await self._set_state(state)
        await self._say(f"{message} {NEXT}")

    # --- déroulé d'une commande ---------------------------------------------------------

    async def _flow_loop(self) -> None:
        while True:
            try:
                await self._order()
            except asyncio.CancelledError:
                raise
            except Abort as abort:
                if abort.code:
                    await self._error(abort.code, abort.message)
                await self._end_order("cancelled", abort.message)
            except Purchased as purchased:
                await self._end_order("done", purchased.message)
            except Exception:
                log.exception("Erreur inattendue dans la commande")
                await self._error("internal", "Erreur inattendue de l'orchestrateur.")
                await self._end_order("cancelled", "Une erreur est survenue. Rien n'a été acheté.")

    async def _order(self) -> None:
        intent = await self._get_request()
        for key in ("options", "summary", "agent_view"):
            self._snapshot.pop(key, None)
        self._intent = intent
        if intent.kind == "question":
            await self._answer_question(intent)
            return
        options = await self._search(intent)
        option = await self._propose(options)
        if self.settings.direct_buy:
            await self._buy_direct(option)
            return
        summary = await self._checkout(option)
        statement = await self.ai.confirm_statement(summary)
        if not await self._yes_no("confirm_1", f"{statement} D'accord ?"):
            raise Abort("D'accord, je n'achète rien.")
        await self._recheck(summary)
        question = f"Rien n'a changé : {euros(summary.total_cents)}. Je paie ?"
        if not await self._yes_no("confirm_2", question):
            raise Abort("D'accord, je ne paie pas.")
        await self._pay(summary)

    async def _answer_question(self, intent: Intent) -> None:
        """Demande libre : l'agent cherche la réponse sur le web, Pilote la dit. Rien n'est acheté."""
        await self._set_state("searching")
        self._agent = self.agent_factory(self.approve_payment, self.need_human)
        if hasattr(self._agent, "on_progress"):
            self._agent.on_progress = self._progress  # type: ignore[attr-defined]
        if hasattr(self._agent, "on_stuck"):
            self._agent.on_stuck = self._stuck  # type: ignore[attr-defined]
        await self._say("Je cherche la réponse sur le web, cela peut prendre une minute.")
        reply = await self._step("search", self._agent.ask(intent.text))
        self._journal("question_answered")
        await self._end_order("done", reply)

    async def _get_request(self) -> Intent:
        pending: Intent | None = None
        while True:
            answer = await self._ask("listening")
            if answer.kind == "question":
                return answer
            if answer.kind == "new_request" and (
                pending is None or (answer.category and answer.category != pending.category)
            ):
                intent = answer
            elif pending is not None and answer.kind in ("new_request", "refine", "other"):
                intent = merge_answer(pending, answer)
            else:
                await self._say("Dites-moi ce que vous voulez commander, ou posez-moi une question.")
                continue
            if intent.missing:
                pending = intent
                # Mêmes questions rédigées quelle que soit l'IA (la factice pose « details.origin »).
                question = QUESTIONS.get(intent.missing[0]) or intent.question
                await self._say(question or "Pouvez-vous préciser votre demande ?")
                continue
            return intent

    async def _step(self, name: str, call: Awaitable[T]) -> T:
        """Une étape de l'agent H, avec délai maximum et erreurs traduites pour l'oral."""
        try:
            return await asyncio.wait_for(call, self.settings.step_timeouts[name])
        except TimeoutError as error:
            raise Abort(
                "Le site met trop de temps à répondre. J'arrête, rien n'a été acheté.", "timeout"
            ) from error
        except PaymentDenied:
            raise
        except UnapprovedPurchase as bought:
            self._journal("payment", result=bought.result, unapproved=True)
            site = site_message_for_speech(bought.site_message)
            outcomes = {
                "accepted": "Attention : l'achat a été validé sur le site, sans attendre votre accord.",
                "refused": "Attention : le site a tenté un paiement, refusé. Rien n'a été débité.",
            }
            said = outcomes.get(bought.result, "Attention : un paiement a peut-être été lancé sur le site.")
            check = "Vérifiez la commande sur le site, et annulez-la si besoin."
            raise Purchased(f"{said} {site + ' ' if site else ''}{check}") from bought
        except NeedsHuman as error:
            raise Abort(
                f"Je suis bloqué sur le site : {error}. Rien n'a été acheté.", "agent_failed"
            ) from error
        except AgentError as error:
            raise Abort(
                "L'agent n'a pas pu continuer sur le site. Rien n'a été acheté.", "agent_failed"
            ) from error
        finally:
            with contextlib.suppress(Exception):
                await self._publish_agent_view()

    async def _publish_agent_view(self) -> None:
        url = getattr(self._agent, "agent_view_url", None) if self._agent else None
        if url and self._snapshot.get("agent_view", {}).get("agent_view_url") != url:
            await self._emit(ServerAgentView(agent_view_url=url))

    async def _search(self, intent: Intent) -> list[Option]:
        await self._set_state("searching")
        self._agent = self.agent_factory(self.approve_payment, self.need_human)
        if hasattr(self._agent, "on_progress"):
            self._agent.on_progress = self._progress  # type: ignore[attr-defined]
        if hasattr(self._agent, "on_stuck"):
            self._agent.on_stuck = self._stuck  # type: ignore[attr-defined]
        await self._say("Je cherche sur le site, cela peut prendre une minute.")
        await self._step("start", self._agent.start(intent, None))
        options = await self._step("search", self._agent.search())
        if not options:
            raise Abort("Je n'ai rien trouvé sur le site. Essayez une autre demande.")
        await self._emit(ServerOptions(options=options[:8]))
        return options[:8]

    def _option_at(self, options: list[Option], index: int | None) -> Option | None:
        if index is None:
            return None
        by_rank = next((o for o in options if o.rank == index), None)
        return by_rank or (options[index - 1] if 1 <= index <= len(options) else None)

    async def _propose(self, options: list[Option]) -> Option:
        assert self._agent is not None
        await self._say(await self.ai.summarize_options(options))
        while True:
            answer = await self._ask("proposing", self.settings.confirm_timeout_s * 2)
            option = self._option_at(options, answer.choice_index)
            if answer.kind == "choose" and option is not None:
                return option
            if answer.kind == "details" and option is not None:
                await self._say(self._describe(option))
            elif answer.kind == "confirm" and len(options) == 1:
                return options[0]
            elif answer.kind in ("choose", "details", "confirm"):
                await self._say(f"Dites le numéro de l'option, entre 1 et {len(options)}.")
            elif answer.kind in ("refine", "new_request"):
                await self._set_state("searching")
                options = (await self._step("refine", self._agent.refine(answer.text)))[:8]
                if not options:
                    raise Abort("Je n'ai rien trouvé avec cette précision. Essayez une autre demande.")
                await self._emit(ServerOptions(options=options))
                await self._say(await self.ai.summarize_options(options))
            elif answer.kind == "deny":
                await self._say("D'accord. Dites ce que vous voulez changer, ou « annule ».")
            else:
                await self._say("Dites « la première », « la deuxième », ou demandez des détails.")

    @staticmethod
    def _describe(option: Option) -> str:
        parts = [f"{option.title}, {euros(option.price_cents)}"]
        if option.rating is not None:
            parts.append(f"noté {option.rating:g} sur 5".replace(".", ","))
        if option.description:
            parts.append(option.description)
        parts.extend(f"{value}" for value in option.details.values())
        if option.conditions:
            parts.append(option.conditions)
        return ". ".join(parts) + ". Voulez-vous celle-ci ?"

    async def _checkout(self, option: Option) -> OrderSummary:
        assert self._agent is not None
        await self._set_state("cart")
        await self._say(f"Je mets le numéro {option.rank} dans le panier : {option.title}.")
        await self._step("choose", self._agent.choose(option.id))
        summary = await self._step("checkout", self._agent.checkout())
        self._summary = summary
        self._journal("checkout", total_cents=summary.total_cents, site=summary.site)
        await self._emit(ServerSummary(summary=summary))
        return summary

    async def _recheck(self, approved: OrderSummary) -> None:
        assert self._agent is not None
        await self._set_state("recheck")
        current = await self._step("recheck", self._agent.recheck())
        await self._emit(ServerSummary(summary=current))
        if current.hash != approved.hash or current.order_id != approved.order_id:
            self._journal("price_changed", before=approved.total_cents, after=current.total_cents)
            raise Abort(
                f"La page a changé depuis votre accord : le total est de {euros(current.total_cents)} "
                f"au lieu de {euros(approved.total_cents)}. Je n'achète rien.",
                "price_changed",
            )

    async def _check_code(self, option: Option) -> None:
        """Demande le code secret à 3 chiffres. Trois essais, puis rien n'est acheté."""
        assert self.settings.purchase_code is not None
        await self._say(
            f"Pour acheter {option.title}, {euros(option.price_cents)}, dites votre code à 3 chiffres."
        )
        attempts = CODE_ATTEMPTS
        self._secret_mode = True
        try:
            while True:
                answer = await self._ask("confirm_1", self.settings.confirm_timeout_s)
                if answer.kind == "deny":
                    raise Abort("D'accord, je n'achète rien.")
                if answer.kind == "confirm":  # touche Entrée ou bouton Oui : il faut le code, pas un oui
                    await self._say("Il me faut votre code à 3 chiffres.")
                    continue
                if hmac.compare_digest(spoken_digits(answer.text), self.settings.purchase_code):
                    self._journal("purchase_code", result="ok")
                    return
                attempts -= 1
                self._journal("purchase_code", result="wrong")
                if attempts == 0:
                    raise Abort("Code incorrect trois fois. Je n'achète rien.")
                await self._say(
                    f"Ce n'est pas le bon code. Encore {attempts} essai{'s' if attempts > 1 else ''}."
                )
        finally:
            self._secret_mode = False

    async def _buy_direct(self, option: Option) -> None:
        """Achat direct : le choix vaut ordre d'achat. Le résultat est toujours dit à l'oral."""
        assert self._agent is not None
        if self.settings.purchase_code:
            await self._check_code(option)  # le code vaut confirmation, même pour un billet gratuit
        elif option.price_cents > 0:  # sans code : un billet gratuit s'achète sans question
            question = f"J'achète bien {option.title}, {euros(option.price_cents)} ?"
            if not await self._yes_no("confirm_1", question):
                raise Abort("D'accord, je n'achète rien.")
        self._direct_limit, self._payment_refusal = option.price_cents, None
        await self._set_state("paying")
        await self._say(f"J'achète {option.title}, {euros(option.price_cents)}.")
        try:
            await self._step("choose", self._agent.choose(option.id))
            result = await self._step("buy", self._agent.buy())
        except PaymentDenied as error:
            reason = (
                self._payment_refusal
                or getattr(self._agent, "last_denial_reason", None)
                or "le site n'a pas permis l'achat"
            )
            raise Abort(f"Je n'ai pas acheté : {reason}. Rien n'a été payé.") from error
        finally:
            self._direct_limit = None
        self._journal("payment", result=result, direct=True)
        site = site_message_for_speech(getattr(self._agent, "last_payment_message", None))
        messages = {
            "accepted": f"C'est acheté : {option.title}, {euros(option.price_cents)}.",
            "refused": "La banque a refusé le paiement. Rien n'a été débité.",
            "unknown": "Je ne sais pas si l'achat est passé. Vérifiez sur le site avant de recommencer.",
        }
        said = messages.get(result, messages["unknown"])
        await self._end_order("done", f"{said} {site}".strip() if result == "accepted" and site else said)

    async def _pay(self, summary: OrderSummary) -> None:
        assert self._agent is not None
        self._armed_hash, self._payment_refusal = summary.hash, None
        await self._set_state("paying")
        await self._say("Je paie.")
        try:
            result = await self._step("pay", self._agent.pay())
        except PaymentDenied as error:
            reason = self._payment_refusal or "le site n'a pas permis le paiement"
            raise Abort(
                f"Je n'ai pas payé : {reason}.", "price_changed" if self._payment_refusal else None
            ) from error
        finally:
            self._armed_hash = None
        self._journal("payment", result=result)
        messages = {
            "refused": "La banque a refusé le paiement. Rien n'a été débité.",
            "accepted": "Le paiement est accepté. La commande est passée.",
            "unknown": "Je ne sais pas si le paiement est passé. Vérifiez sur le site avant de recommencer.",
        }
        await self._end_order("done", messages.get(result, messages["unknown"]))

    # --- callbacks donnés à l'agent H ----------------------------------------------------

    def _goal(self) -> str:
        """Le but de l'étape en cours, en clair, pour le modèle qui lit la page."""
        request = self._intent.text if self._intent else "la demande de la personne"
        if self._intent is not None and self._intent.kind == "question":
            return f"trouver sur le web la réponse à : {request}"
        goals = {
            "searching": f"trouver sur ce site les options correspondant à : {request}",
            "cart": "mettre l'option choisie dans le panier et aller jusqu'à la page de paiement, sans payer",
            "recheck": "relire le récapitulatif de la page de paiement, sans rien cliquer",
            "paying": "payer une seule fois avec la carte enregistrée, puis lire le résultat",
        }
        return goals.get(self.state, request)

    async def _stuck(self, image: bytes, reason: str) -> str | None:
        """Le surveillant de l'agent signale un blocage (ou un long silence) : un modèle de vision
        Hugging Face lit la capture. La description rassure la personne ; le conseil guide l'agent."""
        if self.state not in ("searching", "cart", "recheck", "paying"):
            return None
        try:
            reading = await self.ai.read_page(image, self._goal())
        except Exception:
            log.info("lecture de la page impossible (%s)", reason)
            return None
        self._journal("page_reading", reason=reason)
        description = readable_progress(reading.get("description", ""))
        if description:
            prefix = "Je regarde la page : " if reason != "silence" else ""
            await self._say(f"{prefix}{description}")
        return reading.get("hint") or None

    async def approve_payment(self, summary: OrderSummary) -> ApprovalDecision:
        """Outil request_payment_approval. Dernier verrou avant le clic qui engage de l'argent."""
        if self._direct_limit is not None and self.state == "paying":
            # Achat direct : l'ordre vaut accord, mais jamais plus cher que l'option choisie
            approved = summary.total_cents <= self._direct_limit
            if not approved:
                self._payment_refusal = (
                    f"le panier affichait {euros(summary.total_cents)} au lieu de {euros(self._direct_limit)}"
                )
            self._journal("payment_approval", decision="approved" if approved else "denied", direct=True)
            return "approved" if approved else "denied"
        approved = (
            self.state == "paying"
            and self._armed_hash is not None
            and self._summary is not None
            and summary.order_id == self._summary.order_id
            and summary.hash == self._armed_hash
        )
        if not approved and self.state == "paying" and self._summary is not None:
            self._payment_refusal = (
                f"au moment de payer, la page affichait {euros(summary.total_cents)} "
                f"au lieu de {euros(self._summary.total_cents)}"
            )
        self._journal("payment_approval", decision="approved" if approved else "denied")
        return "approved" if approved else "denied"

    async def need_human(self, reason: str) -> NeedHumanDecision:
        """Outil need_human : CAPTCHA, cryptogramme, connexion. Attend « c'est fait » ou « annule »."""
        previous = self.state
        await self._error("agent_failed", f"Intervention humaine nécessaire : {reason}")
        await self._say(
            f"J'ai besoin d'un humain sur l'ordinateur : {reason}. "
            "Faites le geste, puis dites « c'est fait ». Ou dites « annule »."
        )
        try:
            while True:
                answer = await self._ask("human_needed", self.settings.human_timeout_s)
                if answer.kind == "confirm" or re.search(r"\b(fait|termine|fini)\b", _plain(answer.text)):
                    await self._set_state(previous)
                    return "resolved"
                if answer.kind == "deny":
                    return "abort"
                await self._say("Dites « c'est fait » quand c'est réglé, ou « annule ».")
        except Abort:
            return "abort"
