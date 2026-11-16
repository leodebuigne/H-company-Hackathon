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
- `.env.example` : variables d'environnement attendues par l'application Pilote (sans aucune vraie clé).
- `CLAUDE.md` : contexte du projet pour les assistants de code.

## Avancement

- [x] Étape 1 : faux site de train en ligne
- [x] Étape 1 bis : faux site de livraison de repas en ligne
- [ ] Étape 2 : agent H générique (même code pour tous les sites)
- [ ] Étape 3 : comprendre et résumer avec Hugging Face
- [ ] Étape 4 : la voix
- [ ] Étape 5 : triple vérification et SMS
- [ ] Étape 6 : mémoire des sites
- [ ] Étape 7 : finitions, tests et pitch
