"""Adresses de recherche directes, méthode de recherche et mémoire des sites."""

from __future__ import annotations

import datetime as dt

import pytest

from orchestrator.agent_h import prompts, search_shortcuts
from orchestrator.agent_h.models import AgentAnswer, SiteNotes
from orchestrator.agent_h.site_memory import learn_search, merge_card, with_starter
from orchestrator.contracts import Intent, When

NOW = dt.datetime(2026, 11, 19, tzinfo=dt.UTC)


def _intent(category: str, obj: str | None = None, **details: str) -> Intent:
    return Intent(
        kind="new_request", text="", category=category, object=obj, quantity=1,
        when=When(date=None, after=None, before=None, asap=False), budget_cents=None, details=details,
        constraints=[], choice_index=None, missing=[], question=None,
    )  # fmt: skip


@pytest.fixture(autouse=True)
def _shortcuts_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PILOTE_SEARCH_SHORTCUTS", raising=False)


def test_produit_va_droit_aux_resultats_amazon() -> None:
    shortcut = search_shortcuts.plan(_intent("boutique", "casque Bluetooth", brand="Sony"), "", None)
    assert shortcut is not None
    assert shortcut.domain == "www.amazon.fr"
    assert shortcut.url == "https://www.amazon.fr/s?k=casque+Bluetooth+Sony"


def test_restaurant_par_google_maps() -> None:
    intent = _intent("reservation", "table au restaurant", cuisine="italien", place="Lyon", people="2")
    shortcut = search_shortcuts.plan(intent, "", None)
    assert shortcut is not None
    assert shortcut.url == "https://www.google.com/maps/search/restaurant+italien+Lyon"


def test_hotel_par_booking_et_rendez_vous_par_le_moteur() -> None:
    hotel = search_shortcuts.plan(_intent("reservation", "chambre d'hôtel", place="Nice"), "", None)
    assert hotel is not None and hotel.url == "https://www.booking.com/searchresults.fr.html?ss=Nice"
    dentiste = search_shortcuts.plan(_intent("reservation", "rendez-vous dentiste", place="Paris"), "", None)
    assert dentiste is not None and dentiste.domain == "duckduckgo.com"


def test_train_garde_la_recherche_rapide_sncf() -> None:
    intent = _intent("train", origin="Paris", destination="Lyon")
    assert search_shortcuts.plan(intent, "www.sncf-connect.com", None) is None


def test_site_inconnu_sans_adresse_apprise() -> None:
    assert search_shortcuts.plan(_intent("boutique", "pull"), "www.boutique-inconnue.fr", None) is None


def test_coupure_pour_mesurer_avant_apres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PILOTE_SEARCH_SHORTCUTS", "0")
    assert search_shortcuts.plan(_intent("boutique", "casque"), "", None) is None


def test_adresse_apprise_depuis_la_page_de_resultats() -> None:
    url = "https://www.decathlon.fr/search?Ntt=chaussures+de+running&sessionId=abc123&page=2"
    template = search_shortcuts.template_from(url, "chaussures de running")
    assert template == "https://www.decathlon.fr/search?Ntt={q}"  # ni session ni page gardées
    assert search_shortcuts.template_from("https://www.x.fr/recherche/pull-laine", "pull laine") == (
        "https://www.x.fr/recherche/{q}"
    )
    assert search_shortcuts.template_from("https://www.x.fr/", "pull") is None


def test_adresse_apprise_reutilisee() -> None:
    card = learn_search(None, "www.decathlon.fr", "https://www.decathlon.fr/search?Ntt={q}", NOW)
    shortcut = search_shortcuts.plan(_intent("boutique", "gourde"), "www.decathlon.fr", card)
    assert shortcut is not None and shortcut.url == "https://www.decathlon.fr/search?Ntt=gourde"
    assert card.runs == 0  # apprendre une adresse ne compte pas comme une visite


def test_fiche_apprise_garde_la_recherche_rapide_sncf() -> None:
    learned = merge_card(
        None, "www.sncf-connect.com", SiteNotes(steps=["Panier → Valider et payer"]), 200, 9, NOW
    )
    card = with_starter(learned, "www.sncf-connect.com")
    assert card is not None
    assert any("Tout rechercher" in step for step in card.steps)  # perdu avant la correction
    assert "Panier → Valider et payer" in card.steps


def test_un_achat_ne_fait_pas_oublier_l_adresse_apprise() -> None:
    card = learn_search(None, "www.x.fr", "https://www.x.fr/s?q={q}", NOW)
    after = merge_card(card, "www.x.fr", SiteNotes(steps=["Ajouter au panier"]), 60, 5, NOW)
    assert search_shortcuts.learned_template(after) == "https://www.x.fr/s?q={q}"


def test_message_de_recherche_contient_la_methode_et_l_adresse() -> None:
    intent = _intent("boutique", "casque")
    shortcut = search_shortcuts.plan(intent, "", None)
    text = prompts.search_message(intent, "", None, with_instructions=False, shortcut=shortcut)
    assert "Méthode de recherche rapide" in text
    assert "déjà ouvert sur la page de résultats de www.amazon.fr" in text
    assert "Site : https://www.amazon.fr" in text
    assert "{max_options}" not in text


def test_reponse_avec_adresse_des_resultats() -> None:
    answer = AgentAnswer.model_validate({"options": [], "results_url": "https://www.amazon.fr/s?k=casque"})
    assert answer.results_url == "https://www.amazon.fr/s?k=casque"


def test_lecture_directe_ecarte_les_options_absentes_de_la_page() -> None:
    from orchestrator.agent_h.fast_read import verified
    from orchestrator.agent_h.models import AgentOption

    page = "Résultats\nSony WH-1000XM5 Casque Bluetooth sans fil\n237,83 €\nLivraison GRATUITE demain"
    real = AgentOption(id="o1", title="Sony WH-1000XM5 Casque Bluetooth sans fil", price_eur=237.83)
    wrong_price = AgentOption(id="o2", title="Sony WH-1000XM5 Casque Bluetooth sans fil", price_eur=199.0)
    invented = AgentOption(id="o3", title="Bose QuietComfort Ultra", price_eur=237.83)
    assert verified([real, wrong_price, invented], page, free_allowed=False) == [real]


def test_lecture_directe_accepte_une_reservation_gratuite() -> None:
    from orchestrator.agent_h.fast_read import verified
    from orchestrator.agent_h.models import AgentOption

    page = "Angelo Lyon 4,6 (1 234) Italien · 20-30 € · 12 rue Mercière Ouvert"
    table = AgentOption(id="o1", title="Angelo Lyon", price_eur=0)
    assert verified([table], page, free_allowed=True) == [table]
    assert verified([table], page, free_allowed=False) == []


def test_train_l_agent_s_arrete_sur_la_liste_que_le_code_lit() -> None:
    intent = _intent("train", origin="Paris", destination="Lyon")
    text = prompts.search_message(intent, "https://www.sncf-connect.com", None, False, stop_at_results=True)
    assert "ARRÊTE-TOI" in text and "laisse le champ options vide" in text
    assert "ARRÊTE-TOI" not in prompts.search_message(intent, "https://www.sncf-connect.com", None, False)


def test_lecture_directe_trouve_un_prix_sans_centimes() -> None:
    from orchestrator.agent_h.fast_read import verified
    from orchestrator.agent_h.models import AgentOption

    page = (
        "TGV INOUI Départ de Paris - Gare De Lyon 09:00 à destination de Lyon Part Dieu 10:56\n"
        "Seconde classe\nDès\n69\xa0€"
    )
    train = AgentOption(id="o1", title="TGV INOUI 09:00 → 10:56", price_eur=69)
    assert verified([train], page, free_allowed=True) == [train]
    assert verified([train.model_copy(update={"price_eur": 59.0})], page, free_allowed=True) == []
