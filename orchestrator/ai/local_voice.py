"""Voix française qui tourne sur l'ordinateur de démo : Kyutai Pocket TTS (modèle Hugging Face).

Pourquoi : la voix en ligne (Kokoro via un fournisseur) répond parfois en 6 s ou par des erreurs 503,
et n'a qu'une voix française. Pocket TTS tourne sur le processeur, environ 4 fois plus vite que le
temps réel sur un Mac M1 (mesuré le 2026-11-19), sans réseau une fois le modèle téléchargé.

Les voix sont des fichiers `voices/<nom>.safetensors` : l'empreinte d'une voix, calculée une fois à
partir d'un enregistrement de la collection `kyutai/tts-voices` (voir voices/README.md pour l'origine
et la licence). Avec ces fichiers, le modèle n'a pas besoin de la fonction d'imitation de voix (dont
l'accès est restreint sur Hugging Face) : seul le modèle français de base est téléchargé.

PILOTE_VOICE=jerem (voix d'homme) active cette voix. Le paquet `pocket-tts`
est optionnel : s'il manque ou si la synthèse échoue, Pilote reprend la voix en ligne.
"""

from __future__ import annotations

import io
import logging
import threading
import wave
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

VOICES_DIR = Path(__file__).parent / "voices"
# Phrases plus longues que ça (en caractères) : jusqu'à 1000 pas de génération, sinon la fin est coupée
MAX_TOKENS = 1000


def available_voices() -> list[str]:
    return sorted(path.stem for path in VOICES_DIR.glob("*.safetensors"))


# Le modèle est partagé par toutes les voix (une voix = une petite empreinte) : changer de voix ne
# recharge pas le modèle. Une seule synthèse à la fois : il n'est pas fait pour des appels simultanés.
_LOCK = threading.Lock()
_MODEL: Any = None


def _shared_model() -> Any:
    global _MODEL
    if _MODEL is None:
        from pocket_tts import TTSModel  # import tardif : paquet optionnel et lourd (torch)

        _MODEL = TTSModel.load_model(language="french")
    return _MODEL


class LocalVoice:
    """Une voix Pocket TTS. Le modèle se charge au premier appel (quelques secondes), puis reste en
    mémoire."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.path = VOICES_DIR / f"{name}.safetensors"
        if not self.path.exists():
            raise ValueError(f"voix inconnue : {name} (disponibles : {', '.join(available_voices())})")
        self._model: Any = None
        self._state: Any = None

    def load(self) -> None:
        """Charge le modèle et la voix. Lève ImportError si le paquet pocket-tts n'est pas installé."""
        with _LOCK:
            self._load()

    def _load(self) -> None:
        if self._model is not None:
            return
        model = _shared_model()
        self._state = model.get_state_for_audio_prompt(str(self.path))
        self._model = model
        log.warning("Voix locale « %s » prête (Kyutai Pocket TTS).", self.name)

    def synthesize(self, text: str) -> bytes:
        """Audio WAV mono 16 bits de `text`. Bloquant : à appeler dans un fil à part."""
        import numpy as np

        with _LOCK:
            self._load()
            audio = self._model.generate_audio(self._state, text, max_tokens=MAX_TOKENS).numpy()
            rate = int(self._model.sample_rate)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(pcm.tobytes())
        return buffer.getvalue()
