# Décisions

Une entrée par décision : date, décision, raison, conséquence. Les écarts constatés avec une API externe (H, Hugging Face, Twilio, Upstash) se notent aussi ici, avec le lien vers la doc officielle lue.

## 2026-11-17 : vrais sites, faux sites en plan B (équipe, plan de Léo)

**Décision.** La démo se fait sur Uber Eats et SNCF Connect, avec une carte virtuelle éphémère à 0 € enregistrée à la main dans le compte marchand du Chrome dédié. Les deux faux sites (Rail Démo, Miam Démo) restent le plan B. Détail des conditions d'utilisation et des limites dans `docs/plan-pilote.md` et `docs/sites.md`.
**Conséquence.** Leur code a été retiré de `main` le 17/11 ; il reste récupérable dans l'historique (commit `7cc62bb`). Vérifier que leurs déploiements Vercel répondent encore avant de compter dessus.
**Fin de démo.** L'agent clique sur le bouton de paiement après la triple vérification, la banque refuse (carte à 0 €), `pay()` lit le message affiché et renvoie `refused`. La validation bancaire forte éventuelle se fait sur le téléphone du titulaire, jamais par l'agent.

## 2026-11-17 : Python 3.12 pour l'orchestrateur, l'agent H et l'IA (plan)

Le SDK Python de H se connecte directement au Chrome local en mode « votre navigateur », et une commande peut attendre plusieurs minutes un proche : un processus FastAPI qui tourne en continu sur l'ordinateur de démo. Le web reste en Next.js / TypeScript.

## 2026-11-17 : forme des contrats (membre 5)

- **Argent en centimes entiers** partout (`*_cents`), devise `EUR`. Évite les erreurs d'arrondi et rend le hash stable.
- **Tous les champs sont requis**, `null` si inconnu, aucun champ en plus. Un modèle de langage qui invente un champ est refusé à la validation.
- **`order_id` (UUID v4) est créé par l'agent au `checkout()`**, et `recheck()` le conserve. C'est la clé d'idempotence des outils H et la clé Redis de la validation.
- **Hash** : articles (nom et options normalisés), quantités et total. Implémentation unique : `orchestrator.contracts.summary_hash`.
- **URL** : `page_url`, `Option.url` et `agent_view_url` sont des chaînes qui commencent par `http(s)://`, sans validation stricte (les sites n'encodent pas toujours leur query).
- **Intent** couvre aussi les réponses courtes (« oui », « la deuxième », « annule ») avec `kind` et `choice_index`, pour que l'orchestrateur n'ait qu'un seul appel au modèle par phrase.
- **Noms de champs** : les contrats précisent la liste du plan (centimes au lieu d'euros, `when` structuré, `fees[]` détaillés). Correspondance champ par champ dans `contracts/README.md`.
- **Messages WebSocket** : ceux du plan (`audio`, `text`, `confirm`, `cancel`, `say`, `state`, `options`, `summary`, `error`) plus `ready`, `transcript`, `intent`, `approval`, `agent_view` pour l'écran spectateur.

## 2026-11-17 : variables d'environnement (membre 5)

Noms du plan, plus ceux dont l'orchestrateur a besoin. `HAI_API_KEY` confirmé : c'est le nom que lisent le SDK `hai-agents` et la CLI `hai` d'après la doc H actuelle (https://hub.hcompany.ai/computer-use-agents/authentication). Certaines pages plus anciennes de la doc parlent encore de `H_API_KEY`.
Ajouts : `USE_FAKE_AGENT`, `USE_FAKE_AI`, `USE_FAKE_APPROVALS`, `PILOTE_USER_FIRST_NAME`, `PILOTE_RELATIVES`, `APPROVAL_TIMEOUT_SECONDS(_REPAS)`, `APPROVALS_API_URL`, `VALIDATION_LINK_SECRET`, `DEMO_APPROVALS_CODE`, `NEXT_PUBLIC_ORCHESTRATOR_WS_URL`, et `RAIL_DEMO_URL` / `REPAS_DEMO_URL` pour le plan B.

## 2026-11-17 : outillage (membre 5)

- npm 10 (livré avec Node 22) plante à l'installation (`Cannot read properties of null (reading 'edgesOut')`) avec `eslint-config-next`. Utiliser npm 11 : `npm install -g npm@11`. La CI le fait.
- `web/lib/contracts/` est généré depuis `contracts/` (`npm run contracts:gen`) et copie les schémas, pour que le build Vercel (Root Directory `web`) n'ait pas besoin des fichiers hors de `web/`. La CI échoue si la copie n'est pas à jour.

## 2026-11-17 : voix Hugging Face, premières mesures (membre 2)

Mesuré avec un token fine-grained (préréglage Inference), sur la phrase « Je voudrais un train pour Lille demain après quatorze heures. ». Docs lues : https://huggingface.co/docs/inference-providers

- **Écart avec le plan : la synthèse vocale existe bien dans Inference Providers** (`hexgrad/Kokoro-82M`, `ResembleAI/chatterbox-turbo`, `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`). Kokoro répond en 1 s environ, donc sous la limite de 2 s. Il faut choisir une voix française (`voice=ff_siwis`, `lang_code=f` via `extra_body`) : la voix par défaut parle anglais et donne un audio inintelligible en français. Qwen3-TTS répond `402 Payment Required` (fournisseur together).
- **Transcription** : `openai/whisper-large-v3-turbo` avec `language=fr` répond en 0,9 s mais confond « Lille » et « l'île » ; `openai/whisper-large-v3` écrit « Lille » correctement mais met 5 s. Le turbo tient dans le budget de 3 s (transcription + intention), pas le v3.
- **Chat** : `meta-llama/Llama-3.3-70B-Instruct` (0,8 s) et `Qwen/Qwen3-30B-A3B-Instruct-2507` (0,4 s) répondent sur le routeur `https://router.huggingface.co/v1`. Comparaison complète à venir dans `docs/benchmark-llm.md`.
- **Conséquence** : la transcription doit rester robuste aux noms de villes mal reconnus (le modèle d'intention reçoit la phrase telle quelle, la liste des gares peut servir de contexte).

## 2026-11-17 : choix des modèles et de la méthode pour l'IA (membre 2)

Détail des mesures dans `docs/benchmark-llm.md` (relançable : `python -m orchestrator.ai.benchmark <modèles>`).

- **Compréhension : `meta-llama/Llama-3.3-70B-Instruct`** par défaut (20 sur 20 sur les 20 phrases, 1,3 s médian). `google/gemma-4-31B-it` fait aussi 20 sur 20 mais plus lentement. Qwen3-30B fait 13 sur 20 : il ne remplit pas `details`. Réserve : le prompt a été réglé sur ces mêmes phrases, le score est optimiste.
- **`missing` et `question` sont calculés en code, pas par le modèle.** Premier essai : 12 à 15 sur 20, presque toutes les erreurs venaient de `missing` (listes fausses ou inventées). Le modèle extrait les champs, le code applique les règles du plan (train : origine, destination, date ; repas : objet ; sinon catégorie et objet). Une seule question à la fois, plus facile à écouter.
- **`summarize_options` et `confirm_statement` sont écrites à la main** (`orchestrator/ai/speech_text.py`), sans modèle : un prix ou un article inventé au moment de la confirmation serait grave, et c'est plus rapide. FakeAI et HFAI disent exactement la même chose.
- **Villes mal transcrites** (Whisper écrit « l'île » pour Lille) : le prompt contient une liste de 40 villes de gare pour corriger.
- **Synthèse vocale : Kokoro (voix `ff_siwis`) via deepinfra, découpée en phrases courtes synthétisées en parallèle puis recollées.** La latence varie beaucoup : 1 s pour une phrase courte, 3 s ou plus pour 130 caractères, et jusqu'à 6 à 8 s à un moment de la journée. Délai de coupure 2,5 s (`PILOTE_TTS_TIMEOUT_S`) : au-delà, `speak()` renvoie `None` et l'interface prend la voix du navigateur. Le plan disait 2 s ; les phrases de Pilote sont longues, d'où 2,5 s. Format renvoyé : WAV (`orchestrator.ai.hf.SPEAK_MIME`).
- **Erreurs** : les fonctions lèvent `orchestrator.ai.AIError` avec un `code` repris de l'objet `error` des messages WebSocket (`transcription_failed`, `not_understood`, `internal`). `speak()` ne lève jamais.
- **Vision** : `Qwen/Qwen3-VL-30B-A3B-Instruct` décrit une image envoyée en data URL ; testé sur une image unie, pas encore sur de vraies captures de produits.
- **Non testé** : la reconnaissance vocale sur un vrai enregistrement du navigateur (webm de MediaRecorder) ; les essais ont utilisé du WAV synthétisé.

## À vérifier

- **Membre 1** : pendant que l'outil `request_payment_approval` attend sa réponse, l'orchestrateur appelle `recheck()` (relire la page). Vérifier dans la doc H (https://hub.hcompany.ai/agents-api/custom-tools.md) qu'on peut envoyer un message à une session dont un appel d'outil est en attente. Sinon, le recheck doit se faire autrement (par exemple dans le même outil, ou avec une seconde lecture après la réponse) : ouvrir une issue.
- **Intégration, à traiter par le membre 1 (écarts constatés à la fusion des branches partie-1, 2, 4, 5)** : `orchestrator/agent_h` ne respecte pas encore les contrats communs, il ne se branche donc pas tel quel sur l'orchestrateur.
  - `agent_h/models.py` est une copie de l'ancien plan : prix en euros à virgule (`price_eur`, `total_eur`), `Intent` avec `site` et `item`. Les contrats imposent des centimes entiers, `Intent.kind/category/object/when`, `OrderSummary.total_cents`, `page_url`, `payment_button_label`, `read_at`. À remplacer par `orchestrator.contracts`.
  - `summary_hash` d'`agent_h` n'est pas `orchestrator.contracts.summary_hash` : deux hash différents pour le même panier feraient échouer la comparaison avant paiement. Utiliser celui des contrats.
  - Écarts avec `orchestrator/ports.py` : pas de propriété `agent_view_url` ; le constructeur doit pouvoir se construire par `AgentFactory = (ApprovalCallback, NeedHumanCallback) -> ShoppingAgent` ; `NeedHumanCallback` renvoie `None` dans les ports, `"resolved"` ou `"abort"` dans `agent_h`.
  - **Sécurité du paiement** : dans `agent_h/base.py`, « sans callback, l'agent paie pendant `pay()` et la banque fait la vérification », et son README annonce qu'il n'y a pas de vérification supplémentaire côté Pilote et que la carte est la vraie. C'est l'inverse du plan (triple vérification, carte à 0 €). À trancher en équipe et à noter ici avant la démo ; par défaut, sans approbation fournie, l'agent ne devrait pas pouvoir cliquer sur le bouton de paiement.
- **Membre 3** : noms exacts des variables injectées par l'intégration Upstash de Vercel, à reporter dans `.env.example`.
