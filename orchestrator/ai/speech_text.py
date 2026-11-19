"""Phrases dites à l'utilisateur : résumé des options et confirmation de commande.

Écrites à la main plutôt que générées par un modèle : un prix ou un article inventé au moment de
la confirmation serait grave. Elles sont aussi plus rapides, et identiques dans FakeAI et HFAI.
"""

from __future__ import annotations

import re

from orchestrator.contracts import Option, OrderSummary

MAX_SPOKEN_OPTIONS = 3


def euros(cents: int) -> str:
    """1450 -> « 14 euros 50 », 1400 -> « 14 euros »."""
    whole, rest = divmod(cents, 100)
    return f"{whole} euros" if rest == 0 else f"{whole} euros {rest:02d}"


def _rating(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def options_summary(options: list[Option]) -> str:
    """3 options au maximum : numéro, nom, prix, note. Se termine en proposant les détails."""
    if not options:
        return "Je n'ai rien trouvé. Voulez-vous que je cherche autrement ?"
    spoken = options[:MAX_SPOKEN_OPTIONS]
    # Réservation gratuite (restaurant…) : dire « 0 euro » pour chaque option n'aide personne
    all_free = all(option.price_cents == 0 for option in spoken)
    parts = []
    for number, option in enumerate(spoken, start=1):
        note = f", noté {_rating(option.rating)} sur 5" if option.rating is not None else ""
        price = "" if all_free else f", {euros(option.price_cents)}"
        extra = ""
        if option.details.get("address"):
            extra += f", {option.details['address']}"
        if option.details.get("slots"):
            extra += f", disponible à {option.details['slots']}"
        parts.append(f"Numéro {number} : {option.title}{price}{note}{extra}")
    # Dire exactement quoi répondre : « Voulez-vous des détails ? » laissait croire qu'il fallait
    # répondre oui ou non (retour du 18/11).
    example = "le 2" if len(spoken) > 1 else "le 1"
    return (
        f"J'ai trouvé {len(spoken)} possibilité{'s' if len(spoken) > 1 else ''}"
        + (", la réservation est gratuite. " if all_free else ". ")
        + ". ".join(parts)
        + f". Dites le numéro que vous voulez, par exemple « {example} », ou demandez « les détails du 1 »."
    )


def order_statement(summary: OrderSummary) -> str:
    """Confirmation sous forme d'affirmation, jamais de question : le oui est demandé à part."""
    articles = []
    for item in summary.items:
        label = f"{item.quantity} {item.name}"
        if item.options:
            label += " (" + ", ".join(item.options) + ")"
        articles.append(label)
    sentence = f"J'ai mis dans le panier {', '.join(articles)}, total {euros(summary.total_cents)}"
    fees = sum(fee.amount_cents for fee in summary.fees)
    if fees:
        sentence += f" dont {euros(fees)} de frais"
    if summary.when_label:
        sentence += f", {summary.when_label}"
    sentence += "."
    if summary.conditions:
        sentence += f" {summary.conditions.rstrip('.')}."
    return sentence


_ORDINAL_OPTIONS = [
    "Première",
    "Deuxième",
    "Troisième",
    "Quatrième",
    "Cinquième",
    "Sixième",
    "Septième",
    "Huitième",
]

_SPOKEN_REPLACEMENTS = [
    # « 1, TGV… » est mal lu (« Zon ») : on dit « Première option : TGV… »
    (
        re.compile(r"(^|[:.]\s*)([1-8]),\s+"),
        lambda m: f"{m.group(1)}{_ORDINAL_OPTIONS[int(m.group(2)) - 1]} option : ",
    ),
    (re.compile(r"\binoui\b", re.IGNORECASE), "Inoui"),
    (re.compile(r"\s*(→|->|⟶)\s*"), " vers "),
    (re.compile(r"\s+[·•|—–]\s+"), ", "),
    (re.compile(r"\b1(?:re|ère)\b"), "première"),
    (re.compile(r"\b2(?:de|nde)\b"), "seconde"),
    (re.compile(r"\b2(?:e|ème)\s+classe\b", re.IGNORECASE), "seconde classe"),
    (re.compile(r"\b(\d+)(?:e|ème)\b"), r"\1ième"),
    # « h » seul est épelé par Kokoro (« 14, H44 ») : on écrit « heures » en toutes lettres.
    (re.compile(r"\b(\d{1,2})\s*[:h]\s*(\d{2})\b"), lambda m: _hours(m.group(1), m.group(2))),
    (re.compile(r"\b(\d{1,2})\s*h\b"), lambda m: _hours(m.group(1), "00")),
    # « 7 heures52 » (écrit par le modèle de langage) : la voix lit mal sans l'espace
    (re.compile(r"\b(heures?)(\d)"), r"\1 \2"),
    (re.compile(r"(\d+),00\s*(?:€|EUR\b)"), r"\1 euros"),
    (re.compile(r"(\d+),(\d{2})\s*(?:€|EUR\b)"), r"\1 euros \2"),
    (re.compile(r"(\d+)\s*(?:€|EUR\b)"), r"\1 euros"),
    (re.compile(r"\b(\d+)\s*min\b"), r"\1 minutes"),
    (re.compile(r"\s{2,}"), " "),
]


def _hours(hours: str, minutes: str) -> str:
    unit = "heure" if int(hours) <= 1 else "heures"
    return f"{int(hours)} {unit}" if minutes == "00" else f"{int(hours)} {unit} {minutes}"


_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)  # fmt: skip
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
# « 20/11 » sans année (le mois sur deux chiffres : « 24h/24 » et « 2/3 » ne sont pas des dates)
_DATE_SHORT = re.compile(r"(?<![\d/])(\d{1,2})/(0[1-9]|1[0-2])(?![\d/])")
# Identifiants internes de l'agent : « o2 », « opt-3 », « option o1 »
_OPTION_ID = re.compile(r"\b(?:opt-?|o)(\d{1,2})\b", re.IGNORECASE)
# Jargon -> mots de tous les jours (en minuscules, comparés sans tenir compte de la casse)
_JARGON = {
    r"\s*\(?\b(?:simulation\s+)?DSP2\)?": "",
    r"\b(?:la\s+)?simulation\s+de\s+l['’]authentification\s+forte\b": "la validation par votre banque",
    r"\bl['’]authentification\s+forte\b": "la validation par votre banque",
    r"\bauthentification\s+forte\b": "validation par votre banque",
    r"\b3-?D\s*Secure\b": "validation par votre banque",
    r"\bcheckout\b": "paiement",
    r"\b(?:le|la|un|une)\s+pop-?up\b": "la fenêtre",
    r"\bpop-?up\b": "fenêtre",
    r"\bURL\b": "adresse",
    r"\bCTA\b": "bouton",
    r"\bdropdown\b": "liste",
    r"\bscroll(?:er|e)?\b": "faire défiler",
}


def _date(day: int, month: int, year: int) -> str:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return f"{day}/{month}/{year}"
    return f"{'1er' if day == 1 else day} {_MONTHS[month - 1]} {year}"


def _slash_date(m: re.Match[str]) -> str:
    a, b, year = int(m[1]), int(m[2]), int(m[3])
    # 11/19/2026 : format américain (le 2e nombre dépasse 12) ; sinon format français jour/mois
    return _date(b, a, year) if b > 12 >= a else _date(a, b, year)


def for_speech(text: str) -> str:
    """Réécrit un texte affiché pour qu'il sonne juste à l'oral (dates, identifiants, jargon, heures,
    flèches, prix, abréviations).

    « 14:44 → 15:48, 2de classe » -> « 14 heures 44 vers 15 heures 48, seconde classe ».
    Ne change que la prononciation : le texte affiché à l'écran reste celui du site.
    """
    text = _DATE_ISO.sub(lambda m: _date(int(m[3]), int(m[2]), int(m[1])), text)
    text = _DATE_SLASH.sub(_slash_date, text)
    text = _DATE_SHORT.sub(
        lambda m: (
            f"{'1er' if int(m[1]) == 1 else int(m[1])} {_MONTHS[int(m[2]) - 1]}"
            if 1 <= int(m[1]) <= 31
            else m[0]
        ),
        text,
    )
    text = _OPTION_ID.sub(lambda m: f"numéro {int(m[1])}", text)
    for pattern, plain in _JARGON.items():
        text = re.sub(pattern, plain, text, flags=re.IGNORECASE)
    for pattern, replacement in _SPOKEN_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"(\d+)\s*×\s*", r"\1 ", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)  # « .. » : un seul point
    return re.sub(r"\s{2,}", " ", text).strip()


# --- Ce que l'agent dit faire : seulement si un humain lambda le comprend --------------------

_TECHNICAL = re.compile(
    r"https?://|www\.|\.(?:com|app|fr|io)\b|[{}\[\]<>]|\b\w+_\w+\b|\bjson\b|\bapi\b|\bsch[ée]ma|"
    r"format structur|\boutil|\btool|\bcallback|\bsession\b|\btoken\b|\buuid\b|\bhash\b|"
    r"\bchamp\b|\bpayment\b|\bapproval\b|\banswer\b|\bstep\b|\bxpath\b|\bselector\b|\bdom\b",
    re.IGNORECASE,
)
_ENGLISH = {"the", "is", "and", "to", "of", "i", "i'm", "it", "this", "now", "will", "click", "page",
            "button", "on", "with", "for", "be", "need", "should", "let", "me", "my", "we"}  # fmt: skip
_FRENCH = {"le", "la", "les", "un", "une", "des", "je", "j", "de", "du", "et", "sur", "pour", "est",
           "à", "a", "en", "il", "ce", "cette", "mon", "vers", "page", "bouton"}  # fmt: skip


def readable_progress(line: str) -> str | None:
    """Garde une phrase de progression seulement si elle est claire pour tout le monde, sinon None.

    Écarte ce qui contient des traces techniques (adresse web, nom d'outil, code, identifiant) ou
    ce qui est en anglais ; le reste passe ensuite par for_speech (dates, heures, prix).
    """
    text = " ".join(line.replace("**", "").replace("`", "").split())
    if len(text) < 10 or _TECHNICAL.search(text):
        return None
    words = re.findall(r"[a-zà-ÿ']+", text.lower())
    if sum(w in _ENGLISH for w in words) > sum(w in _FRENCH for w in words):
        return None
    return text
