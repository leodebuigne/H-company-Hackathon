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


def test_path_is_judged_useless_after_three_failures_and_only_offered_when_stuck(tmp_path):
    mem = _memory(tmp_path)
    tid = _learn_quick(mem)  # visite 1
    for visit in (2, 3):  # deux échecs : toujours en service
        mem.begin_visit(SITE)
        mem.record(SITE, [(tid, False)], [], phase_ok=True)
        assert mem.sites[SITE].tips[tid].status == "active", f"visite {visit}"
    mem.begin_visit(SITE)  # visite 4 : troisième échec de suite -> écarté
    mem.record(SITE, [(tid, False)], [], phase_ok=True)
    assert mem.sites[SITE].tips[tid].status == "écartée"

    for _ in range(60):  # aucune visite ne le repropose d'office : pas de réessai programmé
        b = mem.begin_visit(SITE)
        assert tid not in {t.id for t in b.active} and tid in {t.id for t in b.fallback}
    text = briefing_text(b)
    assert "SI TU ES BLOQUÉ" in text and "ne les essaie pas sinon" in text and "RÉESSAYER" not in text


def test_a_parked_path_that_works_when_stuck_is_saved_and_back_in_use(tmp_path):
    mem = _memory(tmp_path)
    tid = _learn_quick(mem)
    for _ in range(3):
        mem.begin_visit(SITE)
        mem.record(SITE, [(tid, False)], [], phase_ok=True)
    assert mem.sites[SITE].tips[tid].status == "écartée"
    mem.begin_visit(SITE)
    mem.record(SITE, [(tid, True)], [], phase_ok=True)  # essayé en secours : il marche
    tip = PathMemory(tmp_path / "memoire.json").sites[SITE].tips[tid]  # relu depuis le disque
    assert tip.status == "active" and tip.streak == 0 and tip.successes == 2
    assert tid in {t.id for t in mem.begin_visit(SITE).active}


def test_a_success_resets_the_failure_count(tmp_path):
    mem = _memory(tmp_path)
    tid = _learn_quick(mem)
    for worked in (False, False, True, False, False):  # jamais 3 échecs de suite
        mem.begin_visit(SITE)
        mem.record(SITE, [(tid, worked)], [], phase_ok=True)
    assert mem.sites[SITE].tips[tid].status == "active"


def test_old_memory_files_still_load(tmp_path):
    old = {"version": 1, "sites": {SITE: {"visits": 3, "tips": {"T1": {
        "id": "T1", "text": QUICK, "kind": "raccourci", "phase": "recherche", "successes": 2,
        "failures": 0, "streak": 0, "status": "active", "retry_at": None, "retry_gap": 3, "last_visit": 3,
    }}}}}  # fmt: skip
    (tmp_path / "memoire.json").write_text(json.dumps(old))
    assert PathMemory(tmp_path / "memoire.json").sites[SITE].tips["T1"].successes == 2


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
