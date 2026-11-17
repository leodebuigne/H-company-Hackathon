# H-company-Hackathon : Pilote

Projet Pilote, hackathon Eugenia 2026 (piste H Company) : un assistant vocal qui commande sur n'importe quel site marchand (train, repas, boutique), pensé d'abord pour les personnes aveugles, avec une triple vérification avant tout paiement (utilisateur, proche de confiance par SMS, utilisateur).

## Adresses utiles

| Quoi | Adresse |
| --- | --- |
| Faux site de train (Rail Démo) | https://h-company-hackathon-rail-demo.vercel.app |
| Scénario « prix qui change » | https://h-company-hackathon-rail-demo.vercel.app/?scenario=hausse |
| Scénario « train complet » | https://h-company-hackathon-rail-demo.vercel.app/?scenario=complet |
| Faux site de repas (Miam Démo) | https://h-company-hackathon-repas-demo.vercel.app |
| Scénario « frais qui changent » | https://h-company-hackathon-repas-demo.vercel.app/?scenario=hausse |
| Scénario « restaurant fermé » | https://h-company-hackathon-repas-demo.vercel.app/?scenario=ferme |

Les mêmes adresses sont dans `.env.example` (variables `RAIL_DEMO_URL` et `REPAS_DEMO_URL`) pour le code de l'application.

## Contenu du dépôt

- `rail-demo/` : faux site de train **Rail Démo** (bleu), déployé sur Vercel (projet `h-company-hackathon-rail-demo`, Root Directory `rail-demo`, preset Other). Détails dans `rail-demo/README.md`.
- `repas-demo/` : faux site de livraison de repas **Miam Démo** (orange), déployé sur Vercel (projet `h-company-hackathon-repas-demo`, Root Directory `repas-demo`, preset Other). Détails dans `repas-demo/README.md`.

Chaque faux site a son dossier et son propre projet Vercel : ils restent indépendants, et l'application Pilote (à venir) aura aussi le sien.
- `contracts/` : schémas JSON partagés et README des messages WebSocket. **Font foi.**
- `orchestrator/` : Python 3.12, FastAPI, machine à états (membre 5). `orchestrator/agent_h/` : agent H (membre 1). `orchestrator/ai/` : modèles Hugging Face (membre 2).
- `web/` : Next.js. Validation des proches (membre 3), interface vocale (membre 4).
- `docs/` : décisions, sites de test, phrases de test, résultats.
- `.env.example` : variables d'environnement attendues (sans aucune vraie clé).
- `CLAUDE.md` : contexte du projet pour les assistants de code.

## Démarrer

```
python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
pytest -q

cd web && npm install -g npm@11 && npm install && npm test
```

## Avancement

- [x] Étape 1 : faux site de train en ligne
- [x] Étape 1 bis : faux site de livraison de repas en ligne
- [ ] Étape 2 : agent H générique (même code pour tous les sites)
- [ ] Étape 3 : comprendre et résumer avec Hugging Face
- [ ] Étape 4 : la voix
- [ ] Étape 5 : triple vérification et SMS
- [ ] Étape 6 : mémoire des sites
- [ ] Étape 7 : finitions, tests et pitch
