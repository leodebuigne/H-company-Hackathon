"""Vraie IA : tout passe par Hugging Face Inference Providers avec un seul HF_TOKEN.

- voix -> texte : Whisper (huggingface_hub, AsyncInferenceClient)
- compréhension, vision : routeur compatible OpenAI https://router.huggingface.co/v1
- texte -> voix : Kokoro, voix française. Renvoie None si trop lent : l'interface prend alors la
  voix du navigateur.

Les modèles se changent par variables d'environnement (PILOTE_ASR_MODEL, PILOTE_LLM_MODEL,
PILOTE_VLM_MODEL, PILOTE_TTS_MODEL, PILOTE_TTS_VOICE, PILOTE_TTS_PROVIDER).
Voir docs/decisions.md pour les mesures.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import io
import json
import logging
import os
import re
import time
import wave
from typing import Any

from pydantic import ValidationError

from orchestrator.ai import conversation
from orchestrator.ai.local_voice import LocalVoice, available_voices
from orchestrator.ai.speech_text import for_speech, options_summary, order_statement, spell_numbers
from orchestrator.contracts import Intent, Option, OrderSummary
from orchestrator.ports import HistoryTurn, PageReading

log = logging.getLogger(__name__)

ROUTER_URL = "https://router.huggingface.co/v1"
DEFAULT_ASR_MODEL = "openai/whisper-large-v3-turbo"
DEFAULT_LLM_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
DEFAULT_VLM_MODEL = "Qwen/Qwen3-VL-30B-A3B-Instruct"
DEFAULT_TTS_MODEL = "hexgrad/Kokoro-82M"
DEFAULT_TTS_VOICE = "ff_siwis"
# Fournisseur imposé pour la voix : sans lui, Hugging Face peut router Kokoro vers fal-ai, qui
# n'a que des voix anglaises (erreur 422 sur ff_siwis, constaté le 18/11).
DEFAULT_TTS_PROVIDER = "deepinfra"

DEFAULT_SPEAK_TIMEOUT_S = 6.0
LOCAL_VOICE_TIMEOUT_S = 20.0  # voix locale : 4 fois plus vite que le temps réel, large marge
VOICE_PAUSE_S = 45  # panne du service de voix : durée pendant laquelle le navigateur parle seul
SPEAK_HEDGE_S = 1.8  # un morceau prend 1 à 2 s : au-delà, une deuxième requête part en parallèle
SPEAK_CHUNK_TIMEOUT_S = 3.5  # dernière attente quand toutes les requêtes d'un morceau traînent
SPEAK_ATTEMPTS = 3  # Hugging Face renvoie parfois 503 : on réessaie avant la voix du navigateur
SPEAK_CHUNK_CHARS = 60
SPEAK_MIME = "audio/wav"
LLM_TIMEOUT_S = 15.0
VISION_TIMEOUT_S = 25.0
ASR_TIMEOUT_S = 15.0
HISTORY_TURNS = 6

# Phrases que Whisper invente sur du silence ou du bruit (sous-titres de vidéos) : ce n'est pas l'utilisateur.
ASR_HALLUCINATIONS = (
    "sous-titres réalisés par",
    "sous-titrage",
    "amara.org",
    "merci d'avoir regardé",
    "abonnez-vous",
)
# Pas de « prompt » de vocabulaire : mesuré le 2026-11-18, il vidait « La deuxième » et changeait
# « Non, annule » en « Nantes ».

WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

INTENT_SYSTEM_PROMPT = """\
Tu es le module de compréhension de Topil, un assistant vocal qui aide une personne aveugle à \
faire ses démarches en ligne : acheter (train, repas, n'importe quel produit), réserver (restaurant, \
hôtel, rendez-vous, spectacle) ou chercher une information. Tu reçois une phrase transcrite à \
l'oral (elle peut contenir des hésitations ou des noms de villes mal écrits) et tu réponds par \
UN SEUL objet JSON, sans texte autour, avec exactement ces champs, tous présents (null, [] ou {} si inconnu) :

{
  "kind": "new_request" | "refine" | "choose" | "details" | "confirm" | "deny" | "cancel" | "question" \
| "other",
  "category": "train" | "repas" | "boutique" | "reservation" | null,
  "object": "ce qu'on veut acheter ou réserver" | null,
  "quantity": nombre entier >= 1 | null,
  "when": {"date": "AAAA-MM-JJ" | null, "after": "HH:MM" | null, "before": "HH:MM" | null, \
"asap": true | false},
  "budget_cents": montant maximal en centimes entiers | null,
  "details": {"clé": "valeur"},
  "constraints": ["contrainte courte en minuscules"],
  "choice_index": numéro de l'option choisie (1, 2, 3) | null,
  "needs": {"key": "clé de details en anglais", "question": "question courte au vouvoiement ?"} | null
}

Sens de kind :
- new_request : nouvelle demande d'achat ou de réservation. refine : change un critère de la demande \
en cours (« plus tôt », « moins cher »). choose : choisit une option (« la deuxième »). details : \
veut plus de détails sur une option. confirm : « oui », « c'est bon ». deny : « non », « pas celle- \
là ». cancel : « annule tout ». question : la personne veut une information ou une recherche sur le \
web, sans acheter (« à quelle heure ferme la pharmacie ? », « quel temps fera-t-il demain à Lille ? \
», « trouve-moi le prix d'un iPhone 17 »). other : bavardage ou phrase incompréhensible.
- confirm, deny, cancel, question, other : tout le reste est null, [] ou {} (when : dates et heures \
null, asap false).
- choose et details : renseigne choice_index. refine : ne remplis que ce qui change.

Catégories :
- train : un billet de train. repas : un repas livré (Uber Eats). boutique : un produit à acheter \
en ligne (électronique, vêtements, livres, maison…). reservation : réserver une table au restaurant, \
un hôtel, un rendez-vous (médecin, coiffeur…) ou une place de spectacle.

needs (seulement pour new_request) : la SEULE information indispensable qui manque encore pour \
choisir correctement ce qu'on achète ou réserve, et que la personne doit donner (ex. la taille d'un \
vêtement → size, la pointure → size, le modèle de téléphone pour une coque → phone_model, \
l'imprimante pour des cartouches → printer, le nombre de personnes pour une table → people). \
null si rien d'indispensable ne manque : ne pose pas de question de confort (couleur, marque) si \
la personne ne l'a pas évoquée.

Règles :
- Ne devine jamais : une information absente de la phrase et de l'historique reste null. Le système \
demandera ce qui manque.
- object : ce qu'on commande, même vague, jamais null pour un repas demandé (« pizza margherita », \
« sushis », « smash classic et frites », « plat thaï »). Mais « un truc », « quelque chose » tout \
seuls, sans précision : object null et category null (« Je veux acheter un truc » = new_request sans \
catégorie). Pour un train, object vaut null.
- Une ville transcrite de travers (« l'île » pour Lille, « Nante » pour Nantes) se corrige avec la \
ville de gare la plus proche à l'oreille parmi : {cities}. Une ville absente de cette liste reste \
telle quelle.
- details : clés en anglais, villes et noms propres avec leur majuscule : origin, destination \
(train), class (première classe, seconde), size, restaurant, cuisine (repas), brand, size, color \
(boutique), place (ville ou quartier), people (nombre de personnes), kind (type de rendez-vous) \
(reservation). Pour une réservation, object dit ce qu'on réserve (« table pour 2 », « rendez-vous \
chez un dentiste », « chambre d'hôtel »).
- constraints : contraintes libres en minuscules, par exemple « direct », « échangeable », \
« remboursable ».
- Heures : « matin » = before 12:00 ; « après-midi » = after 12:00 ; « ce soir » = after 18:00 \
aujourd'hui ; « midi » = 12:00 ; « avant 20 h » pour un repas = before 20:00 aujourd'hui ; \
« à partir de 18 h » ou « après 14 h » = after ; « pour 19 h 30 » pour un repas = before 19:30 \
aujourd'hui ; « le plus vite possible » = asap true.
- Heure exacte d'une réservation ou d'un rendez-vous (« une table à 20 h », « rendez-vous à 9 h 30 ») : \
details.time = "20:00", et after et before restent null (ce n'est ni « avant » ni « après »).
- Aucune heure ni moment de la journée dans la phrase : after et before restent null. N'invente jamais \
une heure (un repas demandé sans heure n'est pas « après 18 h »).
- Date : un repas sans autre jour se commande aujourd'hui. Calcule « demain », « vendredi », \
« le 24 novembre » à partir de la date du jour fournie (jamais une date passée).
- Argent : 60 euros = 6000 centimes.
- L'historique sert à comprendre les réponses courtes ; n'y recopie jamais une information de \
santé ou de handicap.
"""

# Grandes villes de gare : sert à corriger les noms mal transcrits (« l'île » pour Lille).
STATION_CITIES = (
    "Paris, Lyon, Marseille, Lille, Bordeaux, Toulouse, Nantes, Strasbourg, Rennes, Montpellier, "
    "Nice, Dijon, Grenoble, Angers, Tours, Le Mans, Reims, Metz, Nancy, Rouen, Le Havre, Avignon, "
    "Nîmes, Perpignan, Clermont-Ferrand, Limoges, Poitiers, La Rochelle, Brest, Quimper, Caen, "
    "Amiens, Mulhouse, Besançon, Saint-Étienne, Aix-en-Provence, Cannes, Toulon, Biarritz, Pau"
)

# Informations indispensables par catégorie (chemins dans Intent), dans l'ordre où on les demande.
REQUIRED = {
    "train": ["details.origin", "details.destination", "when.date"],
    "repas": ["object"],
    "boutique": ["object"],
    "reservation": ["object", "when.date"],
    None: ["category", "object"],
}
QUESTIONS = {
    "category": "Que voulez-vous faire : acheter quelque chose, réserver, ou chercher une information ?",
    "object": "Qu'est-ce qu'il vous faut exactement ?",
    "details.origin": "De quelle ville partez-vous ?",
    "details.destination": "Pour quelle ville voulez-vous un billet ?",
    "when.date": "Pour quel jour ?",
}

_ASK_PARTS = {
    "details.origin": "de quelle ville partez-vous",
    "details.destination": "pour quelle ville",
    "when.date": "quel jour",
}


def question_for(missing: list[str]) -> str | None:
    """Une seule question pour tout ce qui manque à un trajet (au lieu d'un tour de parole par
    information : 4 à 6 s chacun). Sinon la question de référence de la première information."""
    parts = [_ASK_PARTS[path] for path in missing if path in _ASK_PARTS]
    if len(parts) >= 2 and len(parts) == len(missing):
        text = ", ".join(parts[:-1]) + f", et {parts[-1]} ?"
        return text[0].upper() + text[1:]
    return QUESTIONS.get(missing[0]) if missing else None


VISION_SYSTEM_PROMPT = (
    "Tu aides une personne aveugle à choisir un produit. Réponds en français, en trois phrases au "
    "maximum, à l'oral : couleur, aspect, matière ou taille visibles, et si la page affiche des avis, "
    "résume-les en une phrase. Ne décris que ce que tu vois ; si tu ne peux pas répondre, dis-le."
)


PAGE_READING_PROMPT = """\
Tu aides un agent qui navigue sur un site web pour une personne aveugle. Tu reçois une capture \
d'écran de la page actuelle et le but de l'agent. Réponds par UN SEUL objet JSON, sans texte autour :
{"description": "...", "hint": "..."}
- description : pour la personne aveugle, une ou deux phrases courtes en français simple sur ce que \
montre la page (quelle page, l'information utile visible : prix, horaires, message). Pas de détail \
technique, pas d'adresse web, pas de coordonnées.
- hint : pour l'agent, un conseil concret pour avancer vers le but depuis cette page : quel élément \
visible utiliser (son texte exact et sa position : en haut à droite…), ou quoi fermer (fenêtre, chat, \
bandeau) qui gêne. Si le but semble atteint ou si rien n'est faisable, dis-le simplement.
Ne décris que ce que tu vois. N'invente rien."""


class AIError(Exception):
    """Échec d'une fonction IA. `code` reprend les codes de l'objet `error` des messages WebSocket."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


def _image_mime(image: bytes) -> str:
    if image.startswith(b"\x89PNG"):
        return "image/png"
    if image.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def shrink_image(image: bytes, max_width: int = 1280) -> bytes:
    """Capture réduite en JPEG (≈ 10 fois plus légère) : la lecture par le modèle est plus rapide."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image)) as picture:
            picture = picture.convert("RGB")
            if picture.width > max_width:
                ratio = max_width / picture.width
                picture = picture.resize((max_width, int(picture.height * ratio)))
            out = io.BytesIO()
            picture.save(out, format="JPEG", quality=80)
            return out.getvalue()
    except Exception:  # Pillow absent ou image illisible : on envoie l'original
        return image


def extract_json(content: str) -> dict[str, Any]:
    """Premier objet JSON d'une réponse de modèle (retire <think>, les clôtures ``` et le bavardage)."""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("aucun objet JSON dans la réponse")
    value = json.loads(content[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("la réponse n'est pas un objet JSON")
    return value


def split_for_speech(text: str, max_chars: int = SPEAK_CHUNK_CHARS) -> list[str]:
    """Découpe en morceaux courts (fin de phrase, sinon virgule) : la synthèse ralentit avec la longueur."""
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[.!?:])\s+", text.strip()):
        if len(sentence) <= max_chars:
            pieces.append(sentence)
        else:
            pieces.extend(part for part in re.split(r"(?<=,)\s+", sentence) if part)
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + 1 + len(piece) <= max_chars:
            chunks[-1] += " " + piece
        else:
            chunks.append(piece)
    return [chunk for chunk in chunks if chunk]


def join_wav(parts: list[bytes]) -> bytes:
    """Colle des fichiers WAV de même format l'un après l'autre."""
    if len(parts) == 1:
        return parts[0]
    out = io.BytesIO()
    params = None
    with wave.open(out, "wb") as writer:
        for part in parts:
            with wave.open(io.BytesIO(part), "rb") as reader:
                if params is None:
                    params = reader.getparams()
                    writer.setparams(params)
                elif reader.getparams()[:3] != params[:3]:
                    raise ValueError("formats audio différents")
                writer.writeframes(reader.readframes(reader.getnframes()))
    return out.getvalue()


# Informations indispensables selon ce qu'on achète ou réserve (règles sûres, sans modèle)
_SHOES = re.compile(
    r"\b(chaussures?|baskets?|sneakers?|bottes?|bottines?|sandales?|escarpins?|mocassins?|tongs?|chaussons?)\b",
    re.I,
)
_CLOTHES = re.compile(
    r"\b(t-?shirts?|tee-?shirts?|chemises?|chemisiers?|pantalons?|jeans?|robes?|jupes?|shorts?|pulls?|"
    r"sweats?|hoodies?|vestes?|manteaux?|manteau|blousons?|doudounes?|gilets?|polos?|maillots?|"
    r"leggings?|survêtements?|pyjamas?|soutien-gorges?|culottes?|caleçons?|boxers?|chaussettes?|"
    r"costumes?|tailleurs?|parkas?|imperméables?|débardeurs?|tops?|blazers?|vêtements?)\b",
    re.I,
)
_TABLE = re.compile(r"\b(table|restaurant|resto|dîner|déjeuner|brunch)\b", re.I)


def _object_needs(intent: dict[str, Any]) -> list[tuple[str, str]]:
    """(chemin, question) indispensables pour cet objet : taille d'un vêtement, pointure, table…"""
    what = f"{intent.get('object') or ''} {intent.get('text') or ''}"
    needs: list[tuple[str, str]] = []
    if intent.get("category") == "boutique":
        if _SHOES.search(what):
            needs.append(("details.size", "Quelle pointure faites-vous ?"))
        elif _CLOTHES.search(what):
            needs.append(("details.size", "Quelle taille faut-il ? Par exemple S, M, L, ou 38, 40."))
    if intent.get("category") == "reservation" and _TABLE.search(what):
        needs.append(("details.people", "Pour combien de personnes ?"))
        needs.append(("when.after", "Pour quelle heure ?"))
    return needs


def _is_filled(data: dict[str, Any], path: str) -> bool:
    value: Any = data
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value not in (None, "", [], {})


# Une heure ou un moment de la journée a été dit (chiffres, « matin », « ce soir », « tôt »…)
_MENTIONS_TIME = re.compile(
    r"\d|\b(matin\w*|midi|apr[eè]s-midi|soir\w*|nuit|heures?|minuit|t[oô]t|tard|d[ée]jeuner|d[iî]ner)\b"
)


def complete_intent(data: dict[str, Any], text: str) -> dict[str, Any]:
    """Rend la sortie du modèle conforme au contrat, sans lui faire confiance pour ce qui se calcule.

    Les champs absents ou null prennent leur valeur vide ; `text` est la phrase reçue ;
    `missing` et `question` viennent des informations indispensables du plan (REQUIRED),
    une question à la fois pour que ce soit facile à écouter.
    """
    when = data.get("when") if isinstance(data.get("when"), dict) else {}
    details = data.get("details") if isinstance(data.get("details"), dict) else {}
    constraints = data.get("constraints") if isinstance(data.get("constraints"), list) else []
    intent = {
        "kind": data.get("kind"),
        "text": text,
        "category": data.get("category"),
        "object": data.get("object"),
        "quantity": data.get("quantity"),
        "when": {
            "date": when.get("date"),
            "after": when.get("after"),
            "before": when.get("before"),
            "asap": bool(when.get("asap")),
        },
        "budget_cents": data.get("budget_cents"),
        "details": {str(k): str(v) for k, v in details.items() if v not in (None, "")},
        "constraints": [str(c) for c in constraints if c],
        "choice_index": data.get("choice_index"),
        "missing": [],
        "question": None,
    }
    if intent["kind"] == "new_request" and not _MENTIONS_TIME.search(text.lower()):
        # Le modèle invente parfois une heure (« après 18 h » pour un repas sans heure) : sans heure
        # ni moment de la journée dans ce que la personne a dit, il n'y en a pas.
        intent["when"]["after"] = intent["when"]["before"] = None
        intent["details"].pop("time", None)
    if intent["details"].get("time"):  # heure exacte : ni « avant » ni « après »
        intent["when"]["after"] = intent["when"]["before"] = None
    if intent["kind"] == "new_request":
        required = REQUIRED.get(intent["category"], REQUIRED[None])
        intent["missing"] = [path for path in required if not _is_filled(intent, path)]
        if intent["missing"]:
            intent["question"] = QUESTIONS[intent["missing"][0]]
        else:
            # Puis ce qui dépend de l'objet (taille, pointure…), et enfin ce que le modèle juge
            # indispensable pour bien choisir (« needs »), une question à la fois.
            for path, question in _object_needs(intent):
                timed = _is_filled(intent, "when.before") or _is_filled(intent, "details.time")
                if path == "when.after" and (timed or intent["when"]["asap"]):
                    continue
                if not _is_filled(intent, path):
                    intent["missing"], intent["question"] = [path], question
                    break
            needs = data.get("needs") if isinstance(data.get("needs"), dict) else None
            key = str((needs or {}).get("key") or "").strip()
            ask = str((needs or {}).get("question") or "").strip()
            # Le plat est déjà dit (« pizza margherita ») : ne pas demander en plus le type de cuisine
            if key == "cuisine" and _is_filled(intent, "object"):
                key = ""
            if not intent["missing"] and re.fullmatch(r"[a-z_]{2,20}", key) and ask.endswith("?"):
                if not _is_filled(intent, f"details.{key}"):
                    intent["missing"], intent["question"] = [f"details.{key}"], ask
    return intent


class HFAI:
    """Implémente `orchestrator.ports.AI`.

    Les clients se passent en argument pour les tests ; par défaut ils sont créés avec HF_TOKEN.
    `usage` cumule les jetons consommés par les appels de chat (benchmark).
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        llm_model: str | None = None,
        chat_client: Any = None,
        speech_client: Any = None,
    ) -> None:
        self.token = token or os.environ.get("HF_TOKEN")
        if (chat_client is None or speech_client is None) and not self.token:
            raise AIError("internal", "HF_TOKEN manquant : définissez-le dans .env ou USE_FAKE_AI=1")
        self.asr_model = _env("PILOTE_ASR_MODEL", DEFAULT_ASR_MODEL)
        self.llm_model = llm_model or _env("PILOTE_LLM_MODEL", DEFAULT_LLM_MODEL)
        self.vlm_model = _env("PILOTE_VLM_MODEL", DEFAULT_VLM_MODEL)
        self.tts_model = _env("PILOTE_TTS_MODEL", DEFAULT_TTS_MODEL)
        self.tts_voice = _env("PILOTE_TTS_VOICE", DEFAULT_TTS_VOICE)
        self.tts_provider = _env("PILOTE_TTS_PROVIDER", DEFAULT_TTS_PROVIDER)
        self.speak_timeout = float(_env("PILOTE_TTS_TIMEOUT_S", str(DEFAULT_SPEAK_TIMEOUT_S)))
        self._local_voice_broken = False
        self._voice_failures = 0  # phrases de suite sans voix
        self._voice_down_until = 0.0  # jusqu'à quand on ne demande plus la voix (panne du service)
        # PILOTE_VOICE=navigateur : pas de synthèse Hugging Face, la page parle avec la voix de
        # l'ordinateur (voix Premium du Mac), sans attente réseau.
        voice = _env("PILOTE_VOICE", "huggingface").strip().lower()
        self.browser_voice = voice == "navigateur"
        # PILOTE_VOICE=jerem : voix française qui tourne sur cet ordinateur (local_voice.py).
        # La voix en ligne reste en secours si le paquet manque ou si la synthèse échoue.
        self.local_voice: LocalVoice | None = None
        if voice in available_voices():
            self.local_voice = LocalVoice(voice)
        elif voice not in ("huggingface", "navigateur", ""):
            log.warning("PILOTE_VOICE=%s inconnue : voix en ligne utilisée.", voice)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        self._chat = chat_client
        self._speech = speech_client
        self._tts = speech_client  # client injecté (tests) : sert aussi à la voix

    @property
    def chat_client(self) -> Any:
        if self._chat is None:
            from openai import AsyncOpenAI

            self._chat = AsyncOpenAI(base_url=ROUTER_URL, api_key=self.token, timeout=LLM_TIMEOUT_S)
        return self._chat

    @property
    def speech_client(self) -> Any:
        if self._speech is None:
            from huggingface_hub import AsyncInferenceClient

            self._speech = AsyncInferenceClient(token=self.token)
        return self._speech

    @property
    def tts_client(self) -> Any:
        if self._tts is None:
            from huggingface_hub import AsyncInferenceClient

            self._tts = AsyncInferenceClient(token=self.token, provider=self.tts_provider)
        return self._tts

    # --- voix -> texte -----------------------------------------------------

    async def transcribe(self, audio: bytes, mime: str) -> str:
        """Whisper, en français. L'audio n'est écrit nulle part ; l'appelant le supprime ensuite."""
        try:
            result = await asyncio.wait_for(
                self.speech_client.automatic_speech_recognition(
                    audio,
                    model=self.asr_model,
                    extra_body={"language": "fr"},
                ),
                ASR_TIMEOUT_S,
            )
        except Exception as error:
            raise AIError("transcription_failed", f"transcription impossible : {error}") from error
        text = (result.text or "").strip()
        lowered = text.lower()
        if not text or any(marker in lowered for marker in ASR_HALLUCINATIONS):
            raise AIError("transcription_failed", "aucune parole détectée")
        return text

    # --- compréhension -----------------------------------------------------

    async def _chat_json(self, messages: list[dict[str, Any]], model: str) -> str:
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 700}
        try:
            response = await self.chat_client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs
            )
        except Exception as error:
            if "response_format" not in str(error).lower() and "json" not in str(error).lower():
                raise
            response = await self.chat_client.chat.completions.create(**kwargs)
        if response.usage is not None:
            self.usage["prompt_tokens"] += response.usage.prompt_tokens or 0
            self.usage["completion_tokens"] += response.usage.completion_tokens or 0
        self.usage["calls"] += 1
        return response.choices[0].message.content or ""

    async def prepare_question(self, question: str, history: Any = None) -> dict[str, str]:
        """Question complétée avec la conversation, ou précision à demander (voir conversation.py)."""
        return await conversation.prepare_question(
            self.chat_client, self.llm_model, question=question, history=list(history or [])
        )

    async def reply(
        self, *, situation: str, fallback: str, facts: str = "", heard: str = "", history: Any = None
    ) -> str:
        """Phrase de Pilote rédigée par le modèle de langage, faits vérifiés (voir conversation.py)."""
        if _env("PILOTE_CONVERSATION", "1").strip() == "0":
            return fallback
        return await conversation.reply(
            self.chat_client,
            self.llm_model,
            situation=situation,
            fallback=fallback,
            facts=facts,
            heard=heard,
            history=list(history or []),
        )

    async def parse_intent(self, text: str, today: dt.date, history: list[HistoryTurn]) -> Intent:
        """Un seul appel au modèle par phrase, sortie validée contre le contrat Intent.

        Une seconde tentative renvoie l'erreur de validation au modèle ; après quoi
        AIError("not_understood").
        """
        payload = {
            "date_du_jour": f"{WEEKDAYS[today.weekday()]} {today.isoformat()}",
            "historique": list(history[-HISTORY_TURNS:]),
            "phrase": text,
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT.replace("{cities}", STATION_CITIES)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        last_error = "réponse vide"
        for _attempt in range(2):
            try:
                content = await self._chat_json(messages, self.llm_model)
            except Exception as error:
                raise AIError("not_understood", f"le modèle n'a pas répondu : {error}") from error
            try:
                return Intent.model_validate(complete_intent(extract_json(content), text))
            except (ValueError, ValidationError) as error:
                last_error = str(error)[:600]
                log.warning("intention invalide (%s)", last_error)
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": "Ce JSON est refusé : " + last_error + " Corrige-le et renvoie "
                        "uniquement l'objet JSON complet.",
                    },
                ]
        raise AIError("not_understood", f"intention illisible : {last_error}")

    # --- phrases dites (écrites à la main, pas de modèle) -----------------

    async def summarize_options(self, options: list[Option]) -> str:
        return options_summary(options)

    async def confirm_statement(self, summary: OrderSummary) -> str:
        return order_statement(summary)

    # --- vision ------------------------------------------------------------

    async def describe_product(self, image: bytes, question: str) -> str:
        data_url = f"data:{_image_mime(image)};base64,{base64.b64encode(image).decode('ascii')}"
        messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": question},
                ],
            },
        ]
        try:
            response = await self.chat_client.chat.completions.create(
                model=self.vlm_model, messages=messages, temperature=0.2, max_tokens=300
            )
        except Exception as error:
            raise AIError("internal", f"description impossible : {error}") from error
        return (response.choices[0].message.content or "").strip()

    async def read_page(self, image: bytes, goal: str) -> PageReading:
        """Lecture de page par le modèle de vision (PILOTE_VLM_MODEL), réponse JSON validée."""
        data_url = f"data:image/jpeg;base64,{base64.b64encode(shrink_image(image)).decode('ascii')}"
        messages = [
            {"role": "system", "content": PAGE_READING_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": f"But de l'agent : {goal}"},
                ],
            },
        ]
        try:
            content = await asyncio.wait_for(self._chat_json(messages, self.vlm_model), VISION_TIMEOUT_S)
            data = extract_json(content)
        except Exception as error:
            raise AIError("internal", f"lecture de page impossible : {error}") from error
        description, hint = str(data.get("description") or "").strip(), str(data.get("hint") or "").strip()
        if not description and not hint:
            raise AIError("internal", "lecture de page vide")
        return {"description": description, "hint": hint}

    # --- texte -> voix -----------------------------------------------------

    def voices(self) -> dict[str, Any]:
        """Voix locales proposées à l'interface, et celle qui parle en ce moment (None : voix en ligne)."""
        current = self.local_voice.name if self.local_voice and not self._local_voice_broken else None
        return {"current": current, "available": [] if self._local_voice_broken else available_voices()}

    def set_voice(self, name: str) -> None:
        """Change de voix locale sans redémarrer. ValueError si le nom n'existe pas."""
        self.local_voice = LocalVoice(name)
        self._local_voice_broken = False

    async def speak(self, text: str) -> bytes | None:
        """Audio WAV (SPEAK_MIME), ou None si plus de `speak_timeout` secondes (voix du navigateur).

        Le texte est découpé en phrases synthétisées en parallèle, puis recollées.
        """
        if self.browser_voice:
            return None
        if self.local_voice is not None and not self._local_voice_broken:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self.local_voice.synthesize, spell_numbers(for_speech(text))),
                    LOCAL_VOICE_TIMEOUT_S,
                )
            except ImportError:
                self._local_voice_broken = True  # paquet pocket-tts absent : inutile de réessayer
                log.warning("Voix locale indisponible (pip install pocket-tts) : voix en ligne utilisée.")
            except Exception as error:
                # Pas de voix de secours (décision du 2026-11-19) : une autre voix arrivait en retard,
                # après que la personne avait coupé la phrase. La phrase reste affichée à l'écran.
                log.warning("voix locale en échec (%s) : phrase affichée sans voix", type(error).__name__)
                return None

        async def request(chunk: str) -> bytes:
            return await self.tts_client.text_to_speech(
                chunk, model=self.tts_model, extra_body={"voice": self.tts_voice, "lang_code": "f"}
            )

        async def one(chunk: str) -> bytes:
            """Un morceau de phrase. Le service répond en 1 à 2 s, mais parfois en 6 s ou par une
            erreur 503 (mesuré le 2026-11-19). Si la requête traîne, une deuxième part en parallèle et
            la première réponse gagne ; après une erreur, on réessaie après une courte pause. Le délai
            global de speak() arrête le tout : la voix du navigateur prend alors le relais."""
            tasks: list[asyncio.Future[bytes]] = []
            sent = 0
            try:
                while True:
                    if sent < SPEAK_ATTEMPTS * 3 and len(tasks) < 2:
                        tasks.append(asyncio.ensure_future(request(chunk)))
                        sent += 1
                    elif not tasks:
                        raise TimeoutError("voix indisponible")
                    done, _ = await asyncio.wait(tasks, timeout=SPEAK_HEDGE_S, return_when="FIRST_COMPLETED")
                    failed = False
                    for task in done:
                        tasks.remove(task)
                        if task.exception() is None:
                            return task.result()
                        failed = True
                    if failed:
                        await asyncio.sleep(0.4)  # erreur du service (503) : courte pause avant de réessayer
            finally:
                for task in tasks:
                    task.cancel()

        chunks = split_for_speech(for_speech(text))
        if not chunks:
            return None
        if time.monotonic() < self._voice_down_until:
            return None  # service de voix en panne : voix du navigateur tout de suite, sans attendre
        try:
            # Une longue phrase (lecture des options) a droit à un peu plus de temps qu'une courte
            limit = self.speak_timeout + min(4.0, 0.4 * max(0, len(chunks) - 2))
            parts = await asyncio.wait_for(asyncio.gather(*(one(c) for c in chunks)), limit)
            self._voice_failures = 0
            return join_wav(list(parts))
        except Exception as error:
            log.info("synthèse vocale abandonnée (%s), voix du navigateur", type(error).__name__)
            # Deux phrases de suite sans voix = service en panne (503 en série, mesuré le 2026-11-19) :
            # pendant VOICE_PAUSE_S, la voix du navigateur parle tout de suite. Sinon chaque phrase
            # attendait plusieurs secondes pour rien, et les deux voix se mélangeaient.
            self._voice_failures += 1
            if self._voice_failures >= 2:
                self._voice_down_until = time.monotonic() + VOICE_PAUSE_S
                log.warning("voix de Pilote indisponible : voix du navigateur pendant %d s", VOICE_PAUSE_S)
            return None
