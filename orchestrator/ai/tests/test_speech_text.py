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


async def test_browser_voice_setting_skips_hugging_face_synthesis(monkeypatch):
    from orchestrator.ai.hf import HFAI

    class Boom:
        async def text_to_speech(self, *a, **k):
            raise AssertionError("la synthèse Hugging Face ne doit pas être appelée")

    monkeypatch.setenv("PILOTE_VOICE", "navigateur")
    ai = HFAI(chat_client=Boom(), speech_client=Boom())
    assert await ai.speak("Bonjour") is None


def test_free_reservations_are_read_without_zero_euro_but_with_address_and_slots():
    from orchestrator.ai.speech_text import options_summary
    from orchestrator.contracts import Option

    def opt(rank, title, details, rating=None):
        return Option(
            id=f"o{rank}",
            rank=rank,
            title=title,
            price_cents=0,
            currency="EUR",
            rating=rating,
            url="https://www.thefork.fr/x",
            description=None,
            details=details,
            conditions=None,
        )

    text = options_summary(
        [
            opt(1, "Le Pompeï", {"address": "Presqu'île", "slots": "19 h 30, 20 h"}, 4.6),
            opt(2, "Casamore", {}),
        ]
    )
    assert "0 euro" not in text and "gratuite" in text
    assert "Presqu'île" in text and "disponible à 19 h 30, 20 h" in text and "noté 4,6 sur 5" in text


def test_spoken_fixes_heard_in_live_tests():
    assert for_speech("à 7 heures52 qui arrive") == "à 7 heures 52 qui arrive"
    assert for_speech("2e classe dès 69 €, 1re classe dès 180 €.. 09:00.") == (
        "seconde classe dès 69 euros, première classe dès 180 euros. 9 heures."
    )
    assert for_speech("le 20/11 à 8h") == "le 20 novembre à 8 heures"
    assert "2/3" in for_speech("2/3 des places") and "7j/7" in for_speech("ouvert 7j/7")


def test_train_hours_are_said_even_when_only_in_the_details():
    from orchestrator.ai.speech_text import options_summary
    from orchestrator.contracts import Option

    def train(rank: int, title: str, details: dict[str, str]) -> Option:
        return Option(
            id=f"o{rank}",
            rank=rank,
            title=title,
            price_cents=4500,
            currency="EUR",
            rating=None,
            description=None,
            conditions=None,
            details=details,
            url="https://www.sncf-connect.com",
        )

    text = options_summary(
        [
            train(1, "TGV INOUI", {"departure": "14:44", "arrival": "15:48"}),
            train(2, "TGV INOUI 16h12 → 17h20", {"departure": "16:12", "arrival": "17:20"}),
        ]
    )
    assert "TGV INOUI, 45 euros, départ à 14 heures 44, arrivée à 15 heures 48." in text
    assert "16h12 → 17h20, 45 euros." in text  # déjà dans le titre : pas répété
