# Pilote

Assistant vocal qui fait les achats en ligne à la place d'une personne aveugle ou malvoyante, sur de vrais sites, avec une triple vérification avant chaque paiement. Hackathon Eugenia « Build The Future » 2026, piste H Company.

Plan d'équipe : [`docs/plan-pilote.md`](docs/plan-pilote.md). Contexte pour les assistants de code : [`CLAUDE.md`](CLAUDE.md).

## Dépôt

- `contracts/` : schémas JSON partagés et README des messages WebSocket. **Font foi.**
- `orchestrator/` : Python 3.12, FastAPI, machine à états (membre 5). `orchestrator/agent_h/` : agent H (membre 1). `orchestrator/ai/` : Hugging Face (membre 2).
- `web/` : Next.js. Validation des proches (membre 3), interface vocale (membre 4).
- `docs/` : plan, décisions, sites de test, phrases de test, résultats.
- `.env.example` : variables d'environnement attendues (sans valeur).

## Démarrer

```
python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev,agent,ai]"
cp .env.example .env          # tout est factice par défaut
pytest -q

cd web && npm install -g npm@11 && npm install && npm test
```

## Lancer Pilote sur l'ordinateur de démo

```
python -m orchestrator        # orchestrateur : ws://localhost:8000/ws, santé : http://localhost:8000/health
cd web && npm run dev         # interface : http://localhost:3000, écran du jury : http://localhost:3000/spectateur
```

Passer une brique en vraie version dans `.env` : `USE_FAKE_AI=0` (Hugging Face, `HF_TOKEN`), `USE_FAKE_AGENT=0` (agent H sur les vrais sites, `HAI_API_KEY` et Chrome dédié), `USE_FAKE_APPROVALS=0` (SMS, `APPROVALS_API_URL`, `PILOTE_SHARED_SECRET`, `PILOTE_RELATIVES`). Chaque étape et chaque décision de paiement sont dans `logs/journal.jsonl`, sans audio ni texte des phrases.
