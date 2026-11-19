"""Tests de HFAI sans réseau : de faux clients répondent à la place de Hugging Face."""

import asyncio
import datetime as dt
import io
import json
import wave
from types import SimpleNamespace

import pytest

from orchestrator.ai import HFAI, AIError, FakeAI, build_ai
from orchestrator.ai.benchmark import check
from orchestrator.ai.hf import complete_intent, extract_json, join_wav, split_for_speech

TODAY = dt.date(2026, 11, 18)


def wav(frames: int, rate: int = 16000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)
    return out.getvalue()


def chat_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
    )


class StubChat:
    """Faux client OpenAI : renvoie les réponses dans l'ordre et garde les appels."""

    def __init__(self, *answers: str | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return chat_response(answer)


class StubSpeech:
    def __init__(self, *, text="bonjour", audio=None, delay=0.0, error: Exception | None = None):
        self.text, self.audio, self.delay, self.error = text, audio, delay, error
        self.tts_calls: list[str] = []

    async def automatic_speech_recognition(self, audio, **kwargs):
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)

    async def text_to_speech(self, text, **kwargs):
        self.tts_calls.append(text)
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.audio if self.audio is not None else wav(100)


def make_ai(chat=None, speech=None) -> HFAI:
    return HFAI(token="test", chat_client=chat or StubChat(), speech_client=speech or StubSpeech())


TRAIN_JSON = json.dumps(
    {
        "kind": "new_request",
        "category": "train",
        "object": None,
        "quantity": 1,
        "when": {"date": "2026-11-19", "after": "14:00", "before": None, "asap": False},
        "budget_cents": None,
        "details": {"destination": "Lille"},
        "constraints": [],
        "choice_index": None,
    }
)


# --- extraction et normalisation --------------------------------------------


def test_extract_json_ignores_think_fences_and_chatter():
    raw = '<think>hmm {pas ça}</think>Voici :\n```json\n{"kind": "cancel"}\n```'
    assert extract_json(raw) == {"kind": "cancel"}


def test_extract_json_rejects_text_without_object():
    with pytest.raises(ValueError):
        extract_json("désolé, je ne sais pas")


def test_complete_intent_computes_missing_and_asks_one_question():
    data = json.loads(TRAIN_JSON)
    intent = complete_intent(data, "Un train pour Lille")
    assert intent["missing"] == ["details.origin"]
    assert intent["question"] == "De quelle ville partez-vous ?"
    assert intent["text"] == "Un train pour Lille"


def test_complete_intent_ignores_what_the_model_says_about_missing():
    data = {**json.loads(TRAIN_JSON), "missing": ["when.date"], "question": "n'importe quoi"}
    data["details"] = {"origin": "Paris", "destination": "Lille"}
    intent = complete_intent(data, "x")
    assert intent["missing"] == []
    assert intent["question"] is None


def test_complete_intent_unknown_category_needs_category_and_object():
    intent = complete_intent({"kind": "new_request"}, "Je veux acheter un truc")
    assert intent["missing"] == ["category", "object"]
    assert intent["question"]


def test_complete_intent_short_answers_never_ask():
    intent = complete_intent({"kind": "choose", "choice_index": 2}, "La deuxième")
    assert intent["missing"] == []
    assert intent["question"] is None


def test_complete_intent_repairs_nulls_and_absent_fields():
    intent = complete_intent({"kind": "other", "when": None, "details": None, "constraints": None}, "x")
    assert intent["when"] == {"date": None, "after": None, "before": None, "asap": False}
    assert intent["details"] == {}
    assert intent["constraints"] == []


# --- compréhension -----------------------------------------------------------


async def test_parse_intent_returns_validated_intent_and_sends_today():
    chat = StubChat(TRAIN_JSON)
    intent = await make_ai(chat).parse_intent("Un train pour Lille demain après 14 h", TODAY, [])
    assert intent.category == "train"
    assert intent.when.after == "14:00"
    assert intent.missing == ["details.origin"]
    user_message = json.loads(chat.calls[0]["messages"][1]["content"])
    assert user_message["date_du_jour"] == "mercredi 2026-11-18"


async def test_parse_intent_retries_once_when_json_is_invalid():
    chat = StubChat("pas du json", TRAIN_JSON)
    intent = await make_ai(chat).parse_intent("x", TODAY, [])
    assert intent.category == "train"
    assert len(chat.calls) == 2
    assert chat.calls[1]["messages"][-1]["role"] == "user"


async def test_parse_intent_gives_up_after_two_failures():
    chat = StubChat("non", "toujours non")
    with pytest.raises(AIError) as error:
        await make_ai(chat).parse_intent("x", TODAY, [])
    assert error.value.code == "not_understood"


async def test_parse_intent_retries_without_response_format_when_provider_refuses_it():
    chat = StubChat(RuntimeError("response_format json_object not supported"), TRAIN_JSON)
    intent = await make_ai(chat).parse_intent("x", TODAY, [])
    assert intent.category == "train"
    assert "response_format" not in chat.calls[1]


async def test_parse_intent_keeps_only_recent_history():
    history = [{"role": "user", "text": f"phrase {i}"} for i in range(10)]
    chat = StubChat(TRAIN_JSON)
    await make_ai(chat).parse_intent("x", TODAY, history)
    sent = json.loads(chat.calls[0]["messages"][1]["content"])
    assert len(sent["historique"]) == 6
    assert sent["historique"][-1]["text"] == "phrase 9"


async def test_usage_counts_tokens():
    ai = make_ai(StubChat(TRAIN_JSON))
    await ai.parse_intent("x", TODAY, [])
    assert ai.usage == {"prompt_tokens": 100, "completion_tokens": 20, "calls": 1}


# --- voix -> texte -----------------------------------------------------------


async def test_transcribe_returns_stripped_text():
    ai = make_ai(speech=StubSpeech(text="  Un train pour Lille  "))
    assert await ai.transcribe(b"audio", "audio/webm") == "Un train pour Lille"


async def test_transcribe_raises_on_silence_and_on_error():
    with pytest.raises(AIError) as silent:
        await make_ai(speech=StubSpeech(text="  ")).transcribe(b"a", "audio/webm")
    assert silent.value.code == "transcription_failed"
    with pytest.raises(AIError) as failed:
        await make_ai(speech=StubSpeech(error=RuntimeError("503"))).transcribe(b"a", "audio/webm")
    assert failed.value.code == "transcription_failed"


# --- texte -> voix -----------------------------------------------------------


def test_split_for_speech_cuts_at_sentences_and_keeps_short_ones_together():
    text = (
        "J'ai trouvé : 1, Train de 14 h 27, direct, 43 euros. 2, Train de 15 h 02, 38 euros. "
        "Voulez-vous des détails sur l'une d'elles ?"
    )
    chunks = split_for_speech(text)
    assert len(chunks) == 3
    assert all(len(c) <= 60 for c in chunks)
    assert split_for_speech("Oui. D'accord.") == ["Oui. D'accord."]
    assert split_for_speech("   ") == []


def test_join_wav_concatenates_frames():
    joined = join_wav([wav(100), wav(50)])
    with wave.open(io.BytesIO(joined)) as w:
        assert w.getnframes() == 150


def test_join_wav_refuses_different_formats():
    with pytest.raises(ValueError):
        join_wav([wav(10, rate=16000), wav(10, rate=24000)])


async def test_speak_synthesizes_chunks_and_joins_them():
    speech = StubSpeech()
    audio = await make_ai(speech=speech).speak(
        "Première phrase assez longue pour être seule ici. Seconde phrase aussi assez longue."
    )
    assert audio is not None and audio[:4] == b"RIFF"
    assert len(speech.tts_calls) == 2


async def test_speak_returns_none_when_too_slow():
    ai = make_ai(speech=StubSpeech(delay=1.0))
    ai.speak_timeout = 0.05
    assert await ai.speak("Bonjour") is None


async def test_speak_returns_none_on_error_so_the_browser_voice_takes_over():
    assert await make_ai(speech=StubSpeech(error=RuntimeError("402"))).speak("Bonjour") is None


async def test_speak_retries_a_failed_chunk_before_giving_up():
    class FlakySpeech(StubSpeech):
        async def text_to_speech(self, text, **kwargs):
            self.tts_calls.append(text)
            if len(self.tts_calls) == 1:
                raise RuntimeError("503")
            return wav(100)

    speech = FlakySpeech()
    audio = await make_ai(speech=speech).speak("Bonjour")
    assert audio is not None and audio[:4] == b"RIFF"
    assert len(speech.tts_calls) == 2


@pytest.mark.parametrize("invented", ["Sous-titres réalisés par Amara.org", "Merci d'avoir regardé !"])
async def test_transcribe_rejects_whisper_silence_hallucinations(invented):
    with pytest.raises(AIError):
        await make_ai(speech=StubSpeech(text=invented)).transcribe(b"audio", "audio/webm")


# --- vision ------------------------------------------------------------------


async def test_describe_product_sends_image_as_data_url():
    chat = StubChat("  Rouge, lisse.  ")
    text = await make_ai(chat).describe_product(b"\x89PNG\r\n", "Quelle couleur ?")
    assert text == "Rouge, lisse."
    content = chat.calls[0]["messages"][1]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1]["text"] == "Quelle couleur ?"


async def test_describe_product_wraps_errors():
    chat = StubChat(RuntimeError("boom"))
    with pytest.raises(AIError):
        await make_ai(chat).describe_product(b"\xff\xd8", "?")


# --- choix de la version -----------------------------------------------------


def test_build_ai_follows_use_fake_ai(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "test")
    monkeypatch.setenv("USE_FAKE_AI", "1")
    assert isinstance(build_ai(), FakeAI)
    monkeypatch.setenv("USE_FAKE_AI", "0")
    assert isinstance(build_ai(), HFAI)


def test_hfai_without_token_explains_what_to_do(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(AIError, match="HF_TOKEN"):
        HFAI()


# --- correcteur du benchmark -------------------------------------------------


def test_benchmark_check_rules():
    intent = {
        "kind": "new_request",
        "details": {"class": "Première"},
        "missing": ["when.date"],
        "question": "?",
    }
    assert check(intent, {"kind": "new_request", "details.class~": "premi", "question": "non null"}) == []
    assert check(intent, {"missing": []}) != []
    assert check(intent, {"missing": ["when.date"]}) == []
    assert check(intent, {"kind": "cancel"}) != []


def test_a_free_ticket_request_is_kept():
    from orchestrator.ai.hf import complete_intent

    data = {"kind": "new_request", "category": "train", "budget_cents": 0}
    data["constraints"] = ["gratuit"]
    intent = complete_intent(data, "un train gratuit")
    assert intent["budget_cents"] == 0 and intent["constraints"] == ["gratuit"]


def _base(**over):
    data = {"kind": "new_request", "category": "boutique", "object": "t-shirt blanc"}
    data.update({"when": {}, "details": {}})
    data.update(over)
    return data


def test_clothes_and_shoes_ask_for_the_size():
    from orchestrator.ai.hf import complete_intent

    shirt = complete_intent(_base(), "un t-shirt blanc")
    assert shirt["missing"] == ["details.size"] and "taille" in shirt["question"]
    shoes = complete_intent(_base(object="baskets Nike"), "des baskets Nike")
    assert shoes["missing"] == ["details.size"] and "pointure" in shoes["question"]
    sized = complete_intent(_base(details={"size": "M"}), "un t-shirt blanc taille M")
    assert sized["missing"] == []


def test_restaurant_table_asks_people_then_time():
    from orchestrator.ai.hf import complete_intent

    table = _base(category="reservation", object="table au restaurant italien", when={"date": "2026-11-20"})
    assert complete_intent(table, "une table")["missing"] == ["details.people"]
    table["details"] = {"people": "2"}
    assert complete_intent(table, "une table pour 2")["missing"] == ["when.after"]


def test_model_flagged_essential_is_asked():
    from orchestrator.ai.hf import complete_intent

    needs = {"key": "phone_model", "question": "Pour quel téléphone ?"}
    case = _base(object="coque de téléphone", needs=needs)
    out = complete_intent(case, "une coque")
    assert out["missing"] == ["details.phone_model"] and out["question"] == "Pour quel téléphone ?"
    case["needs"] = {"key": "color", "question": "Quelle couleur"}  # pas une question : ignorée
    assert complete_intent(case, "une coque")["missing"] == []


def test_complete_intent_drops_an_invented_hour_and_keeps_a_spoken_one():
    raw = {"kind": "new_request", "category": "repas", "object": "pizza", "when": {"after": "18:00"}}
    assert complete_intent(dict(raw), "Je voudrais une pizza margherita")["when"]["after"] is None
    assert complete_intent(dict(raw), "Une pizza pour ce soir")["when"]["after"] == "18:00"


def test_an_exact_time_is_neither_before_nor_after():
    raw = {
        "kind": "new_request",
        "category": "reservation",
        "object": "table pour 2",
        "when": {"before": "20:00"},
        "details": {"time": "20:00"},
    }
    intent = complete_intent(raw, "Une table pour deux à 20 heures")
    assert intent["details"]["time"] == "20:00" and intent["when"]["before"] is None
