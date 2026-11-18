import datetime as dt
import json
from pathlib import Path

import pytest

from orchestrator.ai import FakeAI
from orchestrator.ai.speech_text import for_speech
from orchestrator.contracts import Intent, Option, OrderSummary
from orchestrator.ports import AI

TODAY = dt.date(2026, 11, 18)
EXAMPLES = Path(__file__).resolve().parents[3] / "contracts" / "examples" / "valid"


def _load(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_fake_ai_respects_the_port():
    ai: AI = FakeAI()
    assert ai is not None


async def test_transcribe_returns_text():
    assert await FakeAI().transcribe(b"\x00", "audio/webm")


async def test_speak_falls_back_to_browser_voice():
    assert await FakeAI().speak("Bonjour") is None


@pytest.mark.parametrize(
    ("text", "kind", "extra"),
    [
        ("Je voudrais un train pour Lille demain après 14 h", "new_request", {"when.after": "14:00"}),
        ("Une pizza margherita grande taille livrée avant 20 h", "new_request", {"when.before": "20:00"}),
        ("La deuxième", "choose", {"choice_index": 2}),
        ("Donne-moi plus de détails sur la troisième", "details", {"choice_index": 3}),
        ("Oui, c'est bon", "confirm", {}),
        ("Non, pas celle-là", "deny", {}),
        ("Annule tout", "cancel", {}),
        ("Quel temps fera-t-il demain ?", "other", {}),
    ],
)
async def test_parse_intent_returns_valid_intent(text, kind, extra):
    intent = await FakeAI().parse_intent(text, TODAY, [])
    assert isinstance(intent, Intent)
    assert Intent.model_validate(intent.model_dump(mode="json"))  # reste conforme au schéma
    assert intent.kind == kind
    for path, expected in extra.items():
        value = intent
        for part in path.split("."):
            value = value[part] if isinstance(value, dict) else getattr(value, part)
        assert value == expected


async def test_parse_intent_reports_missing_origin_and_asks():
    intent = await FakeAI().parse_intent("Je voudrais un train pour Lille demain", TODAY, [])
    assert intent.details == {"destination": "Lille"}
    assert intent.missing == ["details.origin"]
    assert intent.question


async def test_parse_intent_unknown_purchase_asks_category():
    intent = await FakeAI().parse_intent("Je veux acheter un truc", TODAY, [])
    assert intent.category is None
    assert "object" in intent.missing
    assert intent.question


async def test_summarize_options_announces_three_at_most():
    option = Option.model_validate(_load("option-train.json"))
    options = [option.model_copy(update={"rank": r, "id": f"opt-{r}"}) for r in range(1, 6)]
    text = await FakeAI().summarize_options(options)
    assert "4," not in text
    assert text.endswith("l'une d'elles ?")
    assert len(text.split()) <= 60


async def test_confirm_statement_is_an_assertion_with_total():
    summary = OrderSummary.model_validate(_load("order-summary-repas.json"))
    text = await FakeAI().confirm_statement(summary)
    assert text.startswith("J'ai mis dans le panier")
    assert "total" in text
    assert "?" not in text


async def test_describe_product_returns_text():
    assert await FakeAI().describe_product(b"\x89PNG", "De quelle couleur ?")


@pytest.mark.parametrize(
    ("shown", "spoken"),
    [
        ("TGV 14:44 → 15:48", "TGV 14 heures 44 vers 15 heures 48"),
        ("TGV INOUI 14 h 12 → 15 h 15", "TGV Inoui 14 heures 12 vers 15 heures 15"),
        ("Durée 1h56, avant 20 h", "Durée 1 heure 56, avant 20 heures"),
        (
            "2de classe dès 115 €, 1re classe dès 180 €",
            "seconde classe dès 115 euros, première classe dès 180 euros",
        ),
        ("Direct — 42,00 €", "Direct, 42 euros"),
        ("Trouvé : 1, TGV inOui. 2, TER", "Trouvé : Première option : TGV Inoui. Deuxième option : TER"),
        ("Livraison 19h30 · 3,50 € de frais", "Livraison 19 heures 30, 3 euros 50 de frais"),
        ("Départ à 10:00, 45 min", "Départ à 10 heures, 45 minutes"),
    ],
)
def test_for_speech_reads_times_prices_and_arrows_aloud(shown, spoken):
    assert for_speech(shown) == spoken
