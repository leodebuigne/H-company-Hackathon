"""Mémoire des chemins : apprentissage, mise de côté, réessais espacés, secours, données personnelles."""

from __future__ import annotations

import json

from orchestrator.agent_h.path_memory import PathMemory, briefing_text, clean_tip

SITE = "www.sncf-connect.com"
QUICK = "Tape <ville> <ville> <date> <heure> d'un coup dans le champ « Tout rechercher » puis Entrée"


def test_personal_or_order_data_is_never_learned():
    assert clean_tip(QUICK) == QUICK
    for bad in (
        "Tape « Paris Lille 19 novembre 14h » dans Tout rechercher",  # date, heure
        "Le menu à 9,90 € est en haut",  # prix
        "Connecte-toi avec leo@example.com",  # e-mail
        "Livre au 12 rue de Lille",  # adresse
        "Carte 4111 1111 1111 1111",  # carte
    ):
        assert clean_tip(bad) is None, bad


def _memory(tmp_path) -> PathMemory:
    return PathMemory(tmp_path / "memoire.json")


def _learn_quick(mem: PathMemory) -> str:
    mem.begin_visit(SITE)
    mem.record(SITE, [], [(QUICK, "raccourci", "recherche")], phase_ok=True)
    return next(iter(mem.sites[SITE].tips))


def test_a_tip_is_learned_only_after_a_step_that_worked(tmp_path):
    mem = _memory(tmp_path)
    mem.begin_visit(SITE)
    mem.record(SITE, [], [(QUICK, "raccourci", "recherche")], phase_ok=False)
    assert mem.sites[SITE].tips == {}
    tid = _learn_quick(mem)
    assert mem.begin_visit(SITE).active[0].id == tid
    saved = json.loads((tmp_path / "memoire.json").read_text())
    assert saved["sites"][SITE]["tips"][tid]["successes"] == 1, "gardé sur le disque"
    assert PathMemory(tmp_path / "memoire.json").sites[SITE].tips[tid].text == QUICK


def test_failing_path_is_parked_then_retried_with_growing_gaps_and_offered_when_stuck(tmp_path):
    mem = _memory(tmp_path)
    tid = _learn_quick(mem)  # visite 1
    mem.begin_visit(SITE)  # visite 2 : raté
    mem.record(SITE, [(tid, False)], [], phase_ok=True)
    assert mem.sites[SITE].tips[tid].status == "active", "un seul échec ne suffit pas"
    mem.begin_visit(SITE)  # visite 3 : raté encore -> écarté, réessai à la visite 6
    mem.record(SITE, [(tid, False)], [], phase_ok=True)
    tip = mem.sites[SITE].tips[tid]
    assert tip.status == "écartée" and tip.retry_at == 6

    b4 = mem.begin_visit(SITE)  # visite 4 : pas encore dû -> seulement en secours
    assert tid not in {t.id for t in b4.active + b4.retry_now} and tid in {t.id for t in b4.fallback}
    assert "SI TU ES BLOQUÉ" in briefing_text(b4)
    mem.begin_visit(SITE)  # visite 5
    b6 = mem.begin_visit(SITE)  # visite 6 : dû -> à réessayer en premier
    assert tid in {t.id for t in b6.retry_now} and "À RÉESSAYER" in briefing_text(b6)

    mem.record(SITE, [(tid, False)], [], phase_ok=True)  # réessai raté : écart doublé (6)
    assert mem.sites[SITE].tips[tid].retry_gap == 6 and mem.sites[SITE].tips[tid].retry_at == 12

    for _ in range(6):  # jusqu'à la visite 12
        b = mem.begin_visit(SITE)
    assert tid in {t.id for t in b.retry_now}
    mem.record(SITE, [(tid, True)], [], phase_ok=True)  # il remarche : remis en service
    tip = mem.sites[SITE].tips[tid]
    assert tip.status == "active" and tip.retry_at is None and tip.retry_gap == 3


def test_retry_gap_is_capped(tmp_path):
    mem = _memory(tmp_path)
    tid = _learn_quick(mem)
    for _ in range(12):
        mem.begin_visit(SITE)
        mem.record(SITE, [(tid, False)], [], phase_ok=True)
    assert mem.sites[SITE].tips[tid].retry_gap == 50


def test_feedback_on_an_unknown_tip_is_ignored(tmp_path):
    mem = _memory(tmp_path)
    mem.begin_visit(SITE)
    mem.record(SITE, [("T000000", False)], [], phase_ok=True)
    assert mem.sites[SITE].tips == {}


def test_memory_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("PILOTE_MEMORY", "0")
    assert PathMemory.from_env() is None


async def test_agent_reports_feed_the_memory(tmp_path, monkeypatch):
    from orchestrator.agent_h.agent import ShoppingAgent
    from orchestrator.agent_h.models import AgentAnswer
    from orchestrator.agent_h.site_memory import InMemorySiteMemory

    monkeypatch.setenv("PILOTE_MEMORY_FILE", str(tmp_path / "m.json"))
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    agent._site = "https://www.sncf-connect.com"
    agent._briefing = agent._paths.begin_visit(SITE)
    answer = AgentAnswer.model_validate(
        {
            "options": [{"id": "o1", "title": "TGV 14:44", "price_eur": 71}],
            "new_tips": [
                {"text": QUICK, "kind": "raccourci", "phase": "recherche"},
                {"text": "Tape Paris Lille 19 novembre", "kind": "raccourci"},  # refusé : données
            ],
            "tips_feedback": None,
        }
    )
    agent._learn(answer, "search")
    tips = list(agent._paths.sites[SITE].tips.values())
    assert [t.text for t in tips] == [QUICK] and tips[0].kind == "raccourci"


async def test_values_of_the_order_are_replaced_before_learning(tmp_path, monkeypatch):
    from orchestrator.agent_h.agent import ShoppingAgent
    from orchestrator.agent_h.models import AgentAnswer
    from orchestrator.agent_h.site_memory import InMemorySiteMemory
    from orchestrator.contracts import Intent

    monkeypatch.setenv("PILOTE_MEMORY_FILE", str(tmp_path / "m.json"))
    agent = ShoppingAgent(client=object(), memory=InMemorySiteMemory(), record_metrics=False)  # type: ignore[arg-type]
    agent._site = "https://www.sncf-connect.com"
    agent._intent = Intent.model_validate(
        {
            "kind": "new_request",
            "text": "train",
            "category": "train",
            "object": None,
            "quantity": None,
            "when": {"date": None, "after": None, "before": None, "asap": False},
            "budget_cents": None,
            "details": {"origin": "Paris", "destination": "Lille"},
            "constraints": [],
            "choice_index": None,
            "missing": [],
            "question": None,
        }
    )
    agent._briefing = agent._paths.begin_visit(SITE)
    tip = "Sélectionne 'Paris - Ville' puis 'Lille - Ville' dans la liste Villes et gares"
    answer = AgentAnswer.model_validate(
        {"options": [{"id": "o1", "title": "TGV", "price_eur": 71}], "new_tips": [{"text": tip}]}
    )
    agent._learn(answer, "search")
    (learned,) = agent._paths.sites[SITE].tips.values()
    assert "Paris" not in learned.text and "Lille" not in learned.text
    assert "<ville de départ>" in learned.text and "<ville d'arrivée>" in learned.text
