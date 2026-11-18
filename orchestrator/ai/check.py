"""Vérifie la connexion à Hugging Face, sans micro : `python -m orchestrator.ai.check`.

1. Synthèse vocale : Pilote dit une phrase (Kokoro).
2. Transcription : cette phrase est retranscrite (Whisper).
3. Compréhension : la phrase devient une intention (Llama).

Lit HF_TOKEN dans .env. N'affiche jamais le token ; rien n'est enregistré, sauf l'audio de test
dans logs/check-voix.wav si --garder-audio est passé (pour l'écouter).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
import time
from pathlib import Path

from orchestrator.ai.hf import HFAI, AIError

PHRASE = "Je voudrais un train de Paris pour Lille demain après quatorze heures."


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(".env"))


def _save(audio: bytes) -> None:
    Path("logs").mkdir(exist_ok=True)
    Path("logs/check-voix.wav").write_bytes(audio)


async def main(keep_audio: bool) -> int:
    _load_env()
    try:
        ai = HFAI()
    except AIError as error:
        print(f"✗ {error}")
        return 1
    ok = True

    print("1. Synthèse vocale…", end=" ", flush=True)
    ai.speak_timeout = 20  # pour le test : on attend, même si c'est lent
    started = time.monotonic()
    audio = await ai.speak(PHRASE)
    took = time.monotonic() - started
    if audio:
        print(
            f"✓ {len(audio) // 1024} Ko en {took:.1f} s"
            + ("  (⚠ plus de 2,5 s : la voix du navigateur prendra le relais)" if took > 2.5 else "")
        )
        if keep_audio:
            _save(audio)
            print("   audio enregistré dans logs/check-voix.wav")
    else:
        ok = False
        print("✗ pas d'audio (modèle indisponible, crédits épuisés ou token sans droit Inference)")

    print("2. Transcription…", end=" ", flush=True)
    if audio:
        started = time.monotonic()
        try:
            text = await ai.transcribe(audio, "audio/wav")
            print(f"✓ en {time.monotonic() - started:.1f} s : « {text} »")
        except AIError as error:
            ok = False
            text = PHRASE
            print(f"✗ {error}")
    else:
        text = PHRASE
        print("— sautée (pas d'audio), on continue avec la phrase écrite")

    print("3. Compréhension…", end=" ", flush=True)
    started = time.monotonic()
    try:
        intent = await ai.parse_intent(text, dt.date.today(), [])
        details = ", ".join(f"{k}={v}" for k, v in intent.details.items())
        print(
            f"✓ en {time.monotonic() - started:.1f} s : {intent.kind}, {intent.category}, {details}, "
            f"date={intent.when.date}, après={intent.when.after}, manque={intent.missing or 'rien'}"
        )
    except AIError as error:
        ok = False
        print(f"✗ {error}")

    print("\nHugging Face est prêt." if ok else "\nUne étape a échoué : voir le message ci-dessus.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--garder-audio" in sys.argv)))
