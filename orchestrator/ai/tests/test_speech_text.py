import pytest

from orchestrator.ai.speech_text import for_speech


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        (
            "Paris → Lille 14:14 → 15:16, 38 euros",
            "Paris vers Lille 14 heures 14 vers 15 heures 16, 38 euros",
        ),
        ("Train 14:57", "Train 14 heures 57"),
        ("départ 14:00", "départ 14 heures"),
        ("à partir de 9h05", "à partir de 9 heures 05"),
        ("Durée 1 h 11", "Durée 1 heure 11"),
        ("Payer 29,00 €", "Payer 29 euros"),
        ("total 14,50 €", "total 14 euros 50"),
        ("1 × Billet", "1 Billet"),
        ("La demande a été **refusée**.", "La demande a été refusée."),
        ("vers 19 h, livraison", "vers 19 heures, livraison"),
        ("le 19 novembre 2026", "le 19 novembre 2026"),
        ("Paris vers Lille, 11/19/2026, 14:00", "Paris vers Lille, 19 novembre 2026, 14 heures"),
        ("départ le 19/11/2026", "départ le 19 novembre 2026"),
        ("date 2026-12-01", "date 1er décembre 2026"),
        ("Je choisis le train o2.", "Je choisis le train numéro 2."),
        (
            "La page de validation bancaire (simulation DSP2) s'ouvre.",
            "La page de validation bancaire s'ouvre.",
        ),
        ("Je ferme le pop-up.", "Je ferme la fenêtre."),
        (
            "La page s'affiche — c'est la simulation de l'authentification forte.",
            "La page s'affiche, c'est la validation par votre banque.",
        ),
    ],
)
def test_for_speech(written, spoken):
    assert for_speech(written) == spoken


@pytest.mark.parametrize(
    "line",
    [
        "Je choisis le train de 14 h 37.",
        "Le bandeau de cookies est revenu. Je le ferme d'abord.",
        "J'arrive sur la page de paiement.",
        "J'ai les 8 trains disponibles.",
    ],
)
def test_readable_progress_keeps_plain_french(line):
    from orchestrator.ai.speech_text import readable_progress

    assert readable_progress(line) == line


@pytest.mark.parametrize(
    "line",
    [
        "Je vais sur https://h-company-hackathon-rail-demo.vercel.app/resultats.html",
        "J'appelle l'outil request_payment_approval avec le récapitulatif.",
        "Je renvoie le format structuré avec order_summary.",
        "I need to click the button to continue.",
        "OK.",
        "Le champ { total } est vide.",
    ],
)
def test_readable_progress_drops_technical_or_english(line):
    from orchestrator.ai.speech_text import readable_progress

    assert readable_progress(line) is None
