# IA Hugging Face (membre 2)

Interface : `AI` dans `orchestrator/ports.py` (fonctions asynchrones). Contrats : `orchestrator/contracts.py`.

| Fichier | Rôle |
| --- | --- |
| `fake.py` | `FakeAI` : réponses inventées, sans réseau (USE_FAKE_AI=1) |
| `hf.py` | `HFAI` : vraie IA, un seul `HF_TOKEN` |
| `speech_text.py` | phrases dites (options, confirmation), écrites à la main |
| `benchmark.py` | compare des modèles sur `docs/test-phrases.json` |

```python
from orchestrator.ai import build_ai  # FakeAI ou HFAI selon USE_FAKE_AI

ai = build_ai()
```

Erreurs : `AIError` avec `code` (`transcription_failed`, `not_understood`, `internal`), à renvoyer dans le message WebSocket `error`. `speak()` renvoie du WAV (`SPEAK_MIME`) ou `None` si c'est trop lent.

Réglages : variables `PILOTE_*` de `.env.example`. Mesures et choix : `docs/decisions.md` et `docs/benchmark-llm.md`.

```bash
.venv/bin/pytest orchestrator/ai                                            # sans réseau
.venv/bin/python -m orchestrator.ai.benchmark meta-llama/Llama-3.3-70B-Instruct   # avec HF_TOKEN
```
