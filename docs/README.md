# Documentation

Le projet s'appelle Topil à l'écran et à la voix, Pilote dans le code et dans les anciens documents (voir le [README](../README.md)).

## Pour comprendre le projet

| Document | Contenu | Statut |
|---|---|---|
| [`fiche-projet.md`](fiche-projet.md) | Le projet en une page : problème, solution, stack, architecture, garde-fous, mesures, limites | À jour (19/11), brouillon du checkpoint 3 |
| [`decisions.md`](decisions.md) | Une entrée par décision : date, décision, raison, conséquence. Les écarts avec une API externe s'y notent aussi | Vivant : on ajoute en bas |
| [`../contracts/README.md`](../contracts/README.md) | Les messages WebSocket entre l'interface et l'orchestrateur | Fait foi |
| [`plan-pilote.md`](plan-pilote.md) | Plan d'équipe du 17/11 : benchmark des concurrents, solution, répartition en 5 parties, prompts par membre | **Historique** : certains choix ont changé depuis, `decisions.md` prévaut |

## Pour tester et mesurer

| Document | Contenu |
|---|---|
| [`sites.md`](sites.md) | Sites de test (SNCF Connect, Uber Eats), règles d'usage, journal des tentatives de paiement, plan B |
| [`results-agent.md`](results-agent.md) | Une ligne par commande de l'agent H, ajoutée automatiquement par `orchestrator/agent_h/metrics.py` (ne pas éditer à la main) |
| [`test-phrases.md`](test-phrases.md), [`test-phrases.json`](test-phrases.json) | 20 phrases pour vérifier la compréhension (même contenu en deux formats) |
| [`benchmark-llm.md`](benchmark-llm.md) | Comparaison des modèles de langage sur ces 20 phrases |

## Pour le pitch

| Document | Contenu |
|---|---|
| [`script-video.md`](script-video.md) | Script de la vidéo de démo de 5 minutes, mot pour mot, aligné sur le diaporama |
| [`pitch-deck/`](pitch-deck/README.md) | Sources du diaporama (11 diapositives) |

## Documentation près du code

- [`orchestrator/agent_h/README.md`](../orchestrator/agent_h/README.md) : l'agent H, son installation et son utilisation.
- [`orchestrator/ai/README.md`](../orchestrator/ai/README.md) : les modèles Hugging Face.
- [`orchestrator/ai/voices/README.md`](../orchestrator/ai/voices/README.md) : les voix locales et leur licence.
- [`web/components/README-interface.md`](../web/components/README-interface.md) : l'interface vocale (raccourcis, fichiers, accessibilité).
