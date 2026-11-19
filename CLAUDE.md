# Pilote : contexte pour les assistants de code

Plan complet de l'équipe (benchmark, architecture, répartition, prompts par membre) : `docs/plan-pilote.md`.

## Le projet

Pilote est un assistant vocal en français qui fait des achats en ligne à la place d'une personne aveugle, sur de vrais sites marchands (Uber Eats et SNCF Connect pour le hackathon). Il utilise l'agent "computer use" de H Company (navigation) et des modèles Hugging Face (voix, langage, vision).

Avant chaque paiement : un "oui" oral, une relecture de la page, puis un deuxième "oui". La démo paie avec une carte virtuelle à 0 € : le paiement doit être refusé par la banque, ce qui prouve que le parcours marche.

## Dépôt

```
contracts/              schémas JSON partagés + README des messages WebSocket (font foi)
orchestrator/           Python 3.12, FastAPI, machine à états (membre 5)
orchestrator/agent_h/   agent H Company (membre 1)
orchestrator/ai/        modèles Hugging Face (membre 2)
web/                    Next.js : interface vocale (membre 4)
docs/                   décisions, sites, phrases de test, résultats
```

Traductions des contrats : `orchestrator/contracts.py` (pydantic), `orchestrator/ports.py` (interfaces des briques), `web/lib/contracts/` (généré par `npm run contracts:gen`, ne pas éditer). Argent en centimes entiers. Tous les champs sont présents (`null` si inconnu).

## Règles absolues

- Ne modifie jamais un contrat seul : ouvre une issue GitHub, le membre 5 tranche.
- N'écris que dans les dossiers de ta partie (voir `.github/CODEOWNERS`).
- Aucune clé dans le code : lis les variables d'environnement et ajoute leur nom, sans valeur, à `.env.example`.
- L'agent ne tape jamais de mot de passe, ne résout jamais de CAPTCHA, ne crée jamais de compte, et ne clique jamais sur un bouton qui engage de l'argent sans approbation. Une carte dictée à voix haute est permise : c'est Pilote qui la tape dans la page (`orchestrator/agent_h/card.py`), l'agent H ne la voit pas.
- Une commande à la fois, déclenchée par une personne. 2 tentatives de paiement par site et par jour au maximum. Aucune collecte de données en masse.
- Aucune donnée de santé ou de handicap stockée. L'audio est supprimé dès qu'il est transcrit.
- Pilote annonce à l'oral qu'il est une IA : « Je suis Pilote, un assistant automatique ».
- Si une API externe ne se comporte pas comme décrit, lis la documentation officielle au lieu de deviner (H : https://hub.hcompany.ai/llms.txt, Hugging Face : https://huggingface.co/docs/inference-providers) et note l'écart dans `docs/decisions.md`.
- Travaille sur ta branche, en petits commits, avec des tests à côté du code.

## Vérifier avant de pousser

- Racine : `ruff check . && ruff format --check . && pytest -q`
- `web/` (npm 11) : `npm run contracts:check && npm run lint && npm run typecheck && npm test`
