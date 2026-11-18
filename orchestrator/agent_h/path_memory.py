"""Mémoire des chemins : ce que l'agent apprend sur chaque site, gardé sur l'ordinateur d'une visite à l'autre.

Une « astuce » est un chemin ou un piège décrit de façon générale (« Tape le trajet complet dans
« Tout rechercher » : <ville> <ville> <date> <heure> », « Le bandeau « Ouverture des ventes » est une
publicité »). Elle a un compteur de réussites et d'échecs, rapportés par l'agent après chaque étape.

- Active : envoyée à l'agent à chaque visite, les plus fiables d'abord.
- Écartée (jugée inutile) après ECHECS_AVANT_MISE_DE_COTE échecs de suite : plus proposée d'office, et pas
  de réessai programmé.
- Toujours proposée en secours quand l'agent est bloqué et n'a plus d'autre chemin. Si elle marche alors,
  cette réussite est enregistrée et la remet en service.

Jamais de donnée personnelle : les textes passent par un filtre (e-mail, adresse, numéros, prix, dates,
heures) ; l'agent doit écrire <ville>, <date>, <plat>… à la place des vraies valeurs.

Fichier : PILOTE_MEMORY_FILE (par défaut ~/.pilote/memoire-sites.json). PILOTE_MEMORY=0 la coupe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Kind = Literal["raccourci", "étape", "piège"]
Phase = Literal["recherche", "achat"]

DEFAULT_FILE = Path.home() / ".pilote" / "memoire-sites.json"
ECHECS_AVANT_MISE_DE_COTE = 3
MAX_ASTUCES = 30  # par site
MAX_ENVOYEES = 8  # astuces actives envoyées par phase

# Donnée personnelle ou propre à une commande : e-mail, numéro de rue, nombre de 2 chiffres ou plus
# (prix, date, heure, carte, téléphone), montant en euros.
_PERSONAL = re.compile(
    r"@|\d{2,}|\d\s*€|€\s*\d|\b\d{1,4}\s*(rue|avenue|bd|boulevard|chemin|place|allée)\b", re.IGNORECASE
)


def clean_tip(text: str) -> str | None:
    """Texte d'astuce utilisable, ou None s'il contient une donnée personnelle ou propre à la commande."""
    text = " ".join(str(text).split())
    if len(text) < 8 or len(text) > 240 or _PERSONAL.search(text):
        return None
    return text


def tip_id(domain: str, text: str) -> str:
    normalized = re.sub(r"[^\w<>]+", " ", text.lower()).strip()
    return "T" + hashlib.sha1(f"{domain}|{normalized}".encode()).hexdigest()[:6]


@dataclass
class Tip:
    id: str
    text: str
    kind: Kind
    phase: Phase
    successes: int = 0
    failures: int = 0
    streak: int = 0  # échecs de suite
    status: Literal["active", "écartée"] = "active"
    last_visit: int = 0

    @property
    def score(self) -> float:
        return self.successes - 2 * self.failures + 0.01 * self.last_visit


@dataclass
class SiteRecord:
    domain: str
    visits: int = 0
    tips: dict[str, Tip] = field(default_factory=dict)


@dataclass
class Briefing:
    """Ce qu'on dit à l'agent pour cette visite."""

    visit: int
    active: list[Tip]
    fallback: list[Tip]  # écartées : seulement si l'agent est bloqué

    @property
    def empty(self) -> bool:
        return not (self.active or self.fallback)

    @property
    def ids(self) -> set[str]:
        return {t.id for t in self.active + self.fallback}


class PathMemory:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path).expanduser() if path else DEFAULT_FILE
        self.sites: dict[str, SiteRecord] = {}
        self._load()

    @classmethod
    def from_env(cls) -> PathMemory | None:
        if os.getenv("PILOTE_MEMORY", "1").strip() == "0":
            return None
        return cls(os.getenv("PILOTE_MEMORY_FILE", "").strip() or None)

    # --- fichier -----------------------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return  # pas encore de mémoire, ou fichier abîmé : on repart de zéro
        for domain, site in (raw.get("sites") or {}).items():
            tips = {}
            known = set(Tip.__dataclass_fields__)
            for data in (site.get("tips") or {}).values():
                try:
                    tip = Tip(**{k: v for k, v in data.items() if k in known})  # anciens champs ignorés
                except TypeError:
                    continue
                tips[tip.id] = tip
            self.sites[domain] = SiteRecord(domain=domain, visits=int(site.get("visits", 0)), tips=tips)

    def save(self) -> None:
        data = {
            "version": 1,
            "sites": {
                d: {"visits": s.visits, "tips": {i: asdict(t) for i, t in s.tips.items()}}
                for d, s in self.sites.items()
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def _site(self, domain: str) -> SiteRecord:
        return self.sites.setdefault(domain, SiteRecord(domain=domain))

    # --- visite ------------------------------------------------------------------------

    def begin_visit(self, domain: str) -> Briefing:
        site = self._site(domain)
        site.visits += 1
        self.save()
        tips = sorted(site.tips.values(), key=lambda t: t.score, reverse=True)
        active: list[Tip] = []
        for phase in ("recherche", "achat"):
            active += [t for t in tips if t.status == "active" and t.phase == phase][:MAX_ENVOYEES]
        parked = [t for t in tips if t.status == "écartée"]
        return Briefing(visit=site.visits, active=active, fallback=parked)

    def record(
        self,
        domain: str,
        feedback: list[tuple[str, bool]],
        learned: list[tuple[str, Kind, Phase]],
        phase_ok: bool,
    ) -> None:
        """Bilan d'une étape : astuces essayées (marché ou non), et astuces nouvelles si l'étape a réussi."""
        site = self._site(domain)
        for tid, worked in feedback:
            tip = site.tips.get(tid)
            if tip is not None:
                self._score(site, tip, worked)
        if phase_ok:
            for text, kind, phase in learned:
                clean = clean_tip(text)
                if clean is None:
                    continue
                tid = tip_id(domain, clean)
                tip = site.tips.get(tid)
                if tip is None:
                    site.tips[tid] = Tip(
                        id=tid, text=clean, kind=kind, phase=phase, successes=1, last_visit=site.visits
                    )
                else:
                    self._score(site, tip, True)
        self._trim(site)
        self.save()

    @staticmethod
    def _score(site: SiteRecord, tip: Tip, worked: bool) -> None:
        tip.last_visit = site.visits
        if worked:  # y compris un chemin écarté essayé en secours : il revient en service
            tip.successes += 1
            tip.streak = 0
            tip.status = "active"
            return
        tip.failures += 1
        tip.streak += 1
        if tip.streak >= ECHECS_AVANT_MISE_DE_COTE:
            tip.status = "écartée"

    @staticmethod
    def _trim(site: SiteRecord) -> None:
        if len(site.tips) <= MAX_ASTUCES:
            return
        worst = sorted(site.tips.values(), key=lambda t: (t.status == "active", t.score))
        for tip in worst[: len(site.tips) - MAX_ASTUCES]:
            del site.tips[tip.id]


def briefing_text(b: Briefing | None) -> str:
    """Section « mémoire du site » du message envoyé à l'agent."""
    if b is None:
        return ""
    lines = [
        "MÉMOIRE DE CE SITE (appris aux visites précédentes)."
        + (" Rien encore : c'est une des premières visites." if b.empty else "")
    ]

    def show(tip: Tip) -> str:
        record = f"marché {tip.successes} fois" + (f", raté {tip.failures} fois" if tip.failures else "")
        return f"- [{tip.id}] ({tip.kind}, {tip.phase}, {record}) {tip.text}"

    if b.active:
        lines.append("Chemins et pièges qui marchent : préfère-les au guide quand ils s'appliquent.")
        lines += [show(t) for t in b.active]
    if b.fallback:
        lines.append(
            "SI TU ES BLOQUÉ (plus aucun autre chemin ne marche), essaie aussi ces chemins mis de côté après "
            "des échecs ; ne les essaie pas sinon. Rapporte le résultat dans tips_feedback :"
        )
        lines += [show(t) for t in b.fallback]
    lines.append(
        "Dans ta réponse : tips_feedback = pour chaque [T…] que tu as réellement essayé, worked true ou false. "
        "new_tips = si l'étape a réussi, le chemin que tu as réellement suivi, résumé en 1 à 3 astuces (kind "
        "raccourci pour ce qui fait gagner des actions, étape sinon), plus chaque piège évité (kind piège), "
        "seulement s'ils ne sont pas déjà ci-dessus. Chaque astuce est générale et précise : texte exact des "
        "boutons et champs, place à l'écran, avec <ville>, <date>, <heure>, <plat> à la place des vraies valeurs ; "
        "jamais de nom, d'adresse, de prix, de numéro ni de carte."
    )
    return "\n".join(lines) + "\n"
