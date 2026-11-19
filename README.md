# Topil

Assistant vocal en français qui fait les achats en ligne (train, repas) à la place d'une personne aveugle ou malvoyante, sur de vrais sites, avec un « oui » explicite avant chaque paiement. Hackathon Eugenia « Build The Future » 2026, piste H Company.

> **Nom.** Topil, c'est « pilote » en verlan : c'est le nom que la personne voit et entend. Le dépôt, les dossiers, les fichiers (`PiloteApp.tsx`…) et les variables (`PILOTE_…`) gardent l'ancien nom, Pilote.

## Comment ça marche

1. La personne parle (Espace, ou le bouton). Hugging Face transcrit (Whisper) et comprend la demande (modèle de langage).
2. Topil pose les questions qui manquent, puis l'agent H Company (« computer use ») cherche sur le vrai site (SNCF Connect, Uber Eats) dans un Chrome dédié et propose des options.
3. Après le choix : relecture du récapitulatif, puis « oui » avant de payer. La démo paie avec une carte virtuelle à 0 € : la banque refuse, ce qui prouve que le parcours marche.
4. Les réponses sont dites par une voix française qui tourne sur l'ordinateur (Kyutai Pocket TTS, voix Jerem), et affichées à l'écran.

Garde-fous : l'agent ne tape ni numéro de carte ni mot de passe, ne résout aucun CAPTCHA, ne crée aucun compte ; une commande à la fois ; audio supprimé dès qu'il est transcrit ; Topil dit qu'il est un assistant automatique. Règles complètes : [`CLAUDE.md`](CLAUDE.md).

## Le dépôt

```
contracts/              schémas JSON partagés + README des messages WebSocket (font foi)
orchestrator/           Python 3.12, FastAPI : machine à états, journal, vérification de démo
orchestrator/agent_h/   agent H Company : navigation sur les sites, paiement
orchestrator/ai/        Hugging Face : voix → texte, compréhension, vision, texte → voix (dont voix locale)
web/                    Next.js : interface vocale, écran du jury (/spectateur)
docs/                   plan, décisions, sites de test, résultats, pitch (voir docs/README.md)
.env.example            variables d'environnement attendues, sans valeur
```

## Installer

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,agent,ai]"     # ajouter ",voix" pour la voix locale Kyutai (installe torch, lourd)
cp .env.example .env                 # tout est factice par défaut : rien ne sort, rien n'est acheté
pytest -q

cd web && npm install -g npm@11 && npm install && npm test
```

## Lancer

```bash
python -m orchestrator          # orchestrateur : ws://localhost:8000/ws, santé : http://localhost:8000/health
cd web && npm run dev           # interface : http://localhost:3000, écran du jury : http://localhost:3000/spectateur
```

Passer une brique en vraie version, dans `.env` :

| Réglage | Effet |
|---|---|
| `USE_FAKE_AI=0` | Hugging Face pour de vrai (`HF_TOKEN`) |
| `USE_FAKE_AGENT=0` | agent H sur les vrais sites (`HAI_API_KEY`, Chrome dédié connecté au site). **Un paiement accepté est une vraie commande** |
| `PILOTE_VOICE=jerem` | voix locale Kyutai (`pip install -e ".[voix]"`) |

Avant une démo : `python -m orchestrator.check` vérifie les clés, l'agent H, la compréhension, la voix, le Chrome dédié et le compte SNCF. Il n'achète rien. Chaque étape et chaque décision de paiement sont dans `logs/journal.jsonl`, sans audio ni texte des phrases.

Sans micro ni clé : `cd web && npm run mock` lance un faux orchestrateur qui rejoue une commande de train.

## Documentation

L'index est dans [`docs/README.md`](docs/README.md). À lire en premier :

- [`docs/fiche-projet.md`](docs/fiche-projet.md) : le projet en une page (problème, solution, stack, garde-fous, mesures, limites).
- [`docs/decisions.md`](docs/decisions.md) : toutes les décisions, avec leur date et leur raison ; les plus récentes sont en bas.
- [`contracts/README.md`](contracts/README.md) : les messages WebSocket entre l'interface et l'orchestrateur.

## Vérifier avant de pousser

```bash
ruff check . && ruff format --check . && pytest -q                                   # racine
cd web && npm run contracts:check && npm run lint && npm run typecheck && npm test   # web (npm 11)
```

La même chose tourne sur GitHub à chaque pull request (`.github/workflows/ci.yml`).
