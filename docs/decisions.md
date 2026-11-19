# Décisions

Une entrée par décision : date, décision, raison, conséquence. Les écarts constatés avec une API externe (H, Hugging Face, Upstash) se notent aussi ici, avec le lien vers la doc officielle lue.

## 2026-11-17 : vrais sites, faux sites en plan B (équipe, plan de Léo)

**Décision.** La démo se fait sur Uber Eats et SNCF Connect, avec une carte virtuelle éphémère à 0 € enregistrée à la main dans le compte marchand du Chrome dédié. Les deux faux sites (Rail Démo, Miam Démo) restent le plan B. Détail des conditions d'utilisation et des limites dans `docs/plan-pilote.md` et `docs/sites.md`.
**Conséquence.** Leur code a été retiré de `main` le 17/11 ; il reste récupérable dans l'historique (commit `7cc62bb`). Vérifier que leurs déploiements Vercel répondent encore avant de compter dessus.
**Fin de démo.** L'agent clique sur le bouton de paiement après la double confirmation, la banque refuse (carte à 0 €), `pay()` lit le message affiché et renvoie `refused`. La validation bancaire forte éventuelle se fait sur le téléphone du titulaire, jamais par l'agent.

## 2026-11-17 : Python 3.12 pour l'orchestrateur, l'agent H et l'IA (plan)

Le SDK Python de H se connecte directement au Chrome local en mode « votre navigateur », et une commande peut durer plusieurs minutes : un processus FastAPI qui tourne en continu sur l'ordinateur de démo. Le web reste en Next.js / TypeScript.

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
Ajouts : `USE_FAKE_AGENT`, `USE_FAKE_AI`, `NEXT_PUBLIC_ORCHESTRATOR_WS_URL`, et `RAIL_DEMO_URL` / `REPAS_DEMO_URL` pour le plan B.

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

## 2026-11-17 : fusion des branches partie-1, 2, 4, 5 (intégration)

Base : `partie-5` (contrats et squelette), puis `partie-2` (IA), `partie-4` (interface), `partie-1` (agent H).

- **`agent_h` alignée sur les contrats.** Son `models.py` était une copie de l'ancien plan (euros à virgule, `Intent.site/item`, hash différent). L'agent H lit toujours en euros, le code convertit vers `orchestrator.contracts` (centimes, `rank`, UUID `order_id` créé par `checkout()`, `read_at`, `summary_hash` officiel). Un montant illisible fait refuser, jamais deviner. `SiteCard` est le contrat (`successful_runs`, `avg_duration_s`, `avg_steps`, `useful_buttons`, `updated_at`).
- **Interface `ports.py` respectée** : `agent_view_url`, `make_agent_factory()` au format `AgentFactory`, `NeedHumanCallback` qui rend la main sans valeur.
- **Clé Redis des fiches** : `www.sncf-connect.com` et `www.ubereats.com`, comme `docs/sites.md` (l'ancien code retirait le `www.`).
- **Défaut corrigé** : quand le garde-fou refusait le paiement, l'agent lève `NeedsHuman` (faux CAPTCHA) au lieu de `PaymentDenied`.
- **CI** : installe l'extra `agent` (SDK H) ; `E501` ignoré pour les fichiers de consignes (`prompts.py`, `agent.py`, `metrics.py`).
- `orchestrator/tests/test_integration.py` fait passer une phrase dans l'IA puis dans l'agent, avec les mêmes objets des deux côtés.

## À vérifier

- **Membre 1** : pendant que l'outil `request_payment_approval` attend sa réponse, l'orchestrateur appelle `recheck()` (relire la page). Vérifier dans la doc H (https://hub.hcompany.ai/agents-api/custom-tools.md) qu'on peut envoyer un message à une session dont un appel d'outil est en attente. Sinon, le recheck doit se faire autrement (par exemple dans le même outil, ou avec une seconde lecture après la réponse) : ouvrir une issue.
- **Sécurité du paiement : à confirmer en équipe.** Le README et le code initiaux de `agent_h` disaient « pas de vérification supplémentaire côté Pilote, la carte est la vraie », ce qui contredit le plan (double confirmation, carte à 0 €) et la règle de `CLAUDE.md` (jamais de clic d'argent sans approbation). Par défaut l'agent refuse maintenant de payer sans `approval_callback` de l'orchestrateur ; payer sans passe par `PILOTE_AUTO_APPROVE=1`. Si l'équipe a bien décidé de supprimer la double confirmation, le dire ici.

## 2026-11-17 : orchestrateur (membre 5)

`python -m orchestrator` lance FastAPI sur `ws://localhost:8000/ws`. Code : `orchestrator/session.py` (machine à états), `app.py` (serveur), `config.py`.

- **Une seule session pour tous les écrans.** L'interface et l'écran du jury ouvrent chacun leur WebSocket : ils reçoivent les mêmes messages. Un écran qui arrive en cours de commande reçoit l'état, l'intention, les options, le récapitulatif et la validation en cours. La phrase d'accueil n'est dite qu'à l'écran qui se connecte, et seulement hors commande.
- **Double confirmation avant `pay()`**, puis dernier verrou dans `request_payment_approval` (même hash qu'au moment de la validation). Cela répond au point ouvert du membre 1 : `recheck()` n'est plus appelé pendant un appel d'outil en attente.
- **« Annule » marche à tout moment**, à la voix comme avec Échap : chaque message est transcrit et compris dès qu'il arrive, même pendant une recherche longue. Une autre phrase pendant une étape longue reçoit « Un instant ».
- **Information manquante** : Pilote pose la question rédigée du membre 2 (`orchestrator.ai.hf.QUESTIONS`) et complète la demande avec la réponse. Si le modèle n'extrait rien d'une réponse courte (« Paris »), la phrase remplit directement le champ demandé.
- **Délais** : chaque étape de l'agent a un délai maximum (`config.DEFAULT_STEP_TIMEOUTS`, 3 à 10 minutes car une étape peut contenir un CAPTCHA ou la validation bancaire), chaque oui ou non 3 minutes, un geste humain 10 minutes. Au-delà : rien n'est acheté et Pilote le dit.
- **Refus par défaut** : absence de réponse de la personne, prix changé, erreur de l'agent ou erreur inattendue donnent `cancelled` et « rien n'a été acheté ».
- **Journal** : `logs/journal.jsonl`, une ligne par étape (état, `order_id`, total, décision), jamais d'audio ni de texte de phrase.
- **Contrat** : `NeedHumanCallback` peut renvoyer `"resolved"` ou `"abort"` (le code du membre 1 le gérait déjà), `pay()` documenté dans `ports.py`.

## Agent H : vitesse, voix et connexion aux sites (2026-11-18)

- **Vitesse** : l'agent défini dans le code demande `reasoning_effort=low` par défaut (démo réglée en `medium` dans `.env` pour plus de fiabilité) (`PILOTE_H_REASONING_EFFORT`), ouvre le navigateur sur le site (`start_url`) et cherche 3 options (`PILOTE_MAX_OPTIONS`). Mesure sur SNCF Connect (Paris → Lyon, une recherche chacun) : 144 s avant, 85 s en `low`, 114 s en `disabled` avec de moins bons résultats.
- **Connexion par coffre-fort H** : avec `PILOTE_H_VAULT_ID` et un navigateur `cloud`, H saisit les identifiants du site à la place de l'agent, qui ne les voit jamais. La consigne demande alors de se connecter avec le coffre au lieu d'appeler `need_human` ; un code SMS ou un CAPTCHA passe toujours par un humain. **Écart avec la règle « l'agent ne tape jamais de mot de passe »** : le mot de passe est stocké chez H, pas dans le code ni dans la consigne. À valider par l'équipe ; alternative sans mot de passe stocké : un profil de navigateur H où l'on se connecte une fois soi-même.
- **Voix** : le texte lu passe par `speech_text.for_speech` (et `forSpeech` côté web) : Kokoro épelait « 14 h 44 » (« 14, H44 »), « 1, » et « inOui ». Vérifié en retranscrivant l'audio avec Whisper. Délai de synthèse 6 s et 3 essais (erreurs 503 fréquentes) avant la voix du navigateur.
- **Whisper** : pas de `prompt` de vocabulaire (mesuré : « La deuxième » devenait vide, « Non, annule » devenait « Nantes ») ; les phrases inventées sur du silence (« Sous-titres réalisés par… ») sont rejetées.
- **Chrome local sur écran Retina** : en `user_device`, Chrome affiche en densité 2 et les clics de l'agent H tombaient deux fois trop bas et trop à droite (sur SNCF Connect, « Trains » ouvrait la publicité « Ouverture des ventes »). `orchestrator/agent_h/local_chrome.py` lance le Chrome dédié avec `--force-device-scale-factor=1` (même profil que le SDK, `~/.hai/chrome-profile`), et `ShoppingAgent.start()` l'appelle avant chaque commande. Mesuré : 90 s et 3 options, compte connecté. Fiche de départ SNCF Connect (étapes, pièges) dans `site_memory.STARTER_CARDS`.
- **Connexion au compte** : le CAPTCHA SNCF bloque la connexion par coffre-fort dans le navigateur cloud. Pour la démo : Chrome local, connexion faite une fois à la main dans le Chrome dédié.
- **Agent du portail sur le Chrome local** : avec `PILOTE_H_AGENT` et `PILOTE_BROWSER_HOST=user_device`, Pilote lit la configuration de l'agent du portail H (consignes, skills, modèle, réflexion, mode de l'environnement) et la lance sur le Chrome dédié, car un agent du portail emporte son environnement cloud, où la connexion SNCF bloque sur un CAPTCHA. Mesuré : Paris → Nantes, 82 s, 3 options aux prix du compte connecté.
- **Achat validé à l'étape panier (2026-11-18)** : sur SNCF Connect, le panier d'un billet à 0 € porte directement « Valider et payer » ; l'agent a cliqué sans appeler `request_payment_approval` (billet réellement réservé). Corrigé dans les consignes (code, fiche SNCF, agent du portail : ne jamais cliquer sur un bouton qui valide l'achat hors de l'étape paiement, même à 0 €). Filet de sécurité : un `payment_result` reçu hors de `pay()` lève `UnapprovedPurchase`, et Pilote annonce à l'oral que l'achat a eu lieu (au lieu de « rien n'a été acheté »). La consigne reste une consigne : le clic n'est pas bloqué techniquement.
- **Achat direct (décision de l'équipe, 2026-11-18)** : avec `PILOTE_DIRECT_BUY=1`, choisir une option vaut ordre d'achat. Pilote dit « J'achète … », l'agent fait panier et paiement en une étape (`buy()`), puis Pilote annonce le résultat à l'oral. **Écart assumé avec la double confirmation du plan et la règle de `CLAUDE.md`** : plus de « oui » oral ni de relecture. Seul garde-fou gardé : `request_payment_approval` refuse si le total affiché dépasse le prix de l'option choisie (pas d'option ou d'assurance ajoutée). Sans la variable, le parcours complet reste celui du plan.
- **Sessions H gardées ouvertes (`idle_timeout_s`, 2026-11-18)** : sans ce réglage, une session H se termine dès que l'agent répond (doc H, `SessionRequest.idle_timeout_s`) ; en Chrome local, le SDK débranche alors le navigateur et l'étape suivante échoue, et l'agent perd sa mémoire. Pilote passe maintenant `idle_timeout_s=900` (`PILOTE_H_IDLE_TIMEOUT_S`, 0 = ancien comportement, une session par étape). Mesuré : recherche Paris → Nantes 39 s, puis « après 17 h » 42 s dans la même session, trajet et date retenus. Comparatif de modèles : holo4-35b-a3b 88 s contre 82 s pour holo4-27b sur la même recherche : le modèle n'est pas le goulot, on garde holo4-27b.
- **Commentaire en direct (2026-11-18)** : pendant la recherche et l'achat, Pilote suit le flux d'événements H (`session.changes`, actions annoncées par l'agent) et dit une phrase courte (`agent_h/narration.py`, règles fixes, sans modèle ni donnée personnelle), au plus une toutes les 6 s, hors de l'historique de conversation. Chaque commande en Chrome local ouvre aussi un onglet neuf et ferme les anciens (`local_chrome.fresh_page`) : l'agent s'accrochait sinon à l'onglet de la commande précédente, fermé en retard par H.
- **Code secret d'achat (2026-11-18)** : avec `PILOTE_PURCHASE_CODE` (3 chiffres) et l'achat direct, Pilote demande le code à l'oral avant chaque achat, même à 0 €, puis l'agent clique lui-même sur « Valider et payer ». Trois essais. Le code ne passe jamais par le modèle de langage, n'entre pas dans l'historique et s'affiche « ••• » (transcription et écran jury) ; seul le résultat (bon / mauvais) va au journal. L'interface reconnaît la demande au texte dit par Pilote (même état `confirm_1`, sans toucher au contrat) et affiche un champ masqué. Réflexion de l'agent H repassée à `low` pour la vitesse. Ce n'est pas le cryptogramme de la carte : l'agent ne le tape jamais (règle de l'équipe, et un cryptogramme ne doit jamais être enregistré).
- **Recherche rapide SNCF (2026-11-18)** : la fiche SNCF fait taper le trajet d'un coup dans « Tout rechercher » (« Paris Lyon 20 novembre 9h » + Entrée) au lieu de remplir le formulaire Trains. Mesuré sur la même recherche : 47 s, 5 actions, 70 000 tokens, contre 88 s, 12 à 17 actions et 280 000 à 350 000 tokens ; résultats justes. Le formulaire reste en repli dans la consigne (`PILOTE_SNCF_QUICK_SEARCH=0` pour le forcer). Couper le texte de la page (`PILOTE_H_PAGE_TEXT=0`) ne fait pas gagner de temps (107 s) : gardé. La lenteur n'est pas un blocage SNCF.
**Décision.** La validation d'un proche par SMS est abandonnée. Avant de payer : premier « oui », relecture de la page (même hash), deuxième « oui », puis le dernier verrou de `request_payment_approval`.
**Raisons.** La partie 3 n'existait pas, et demander l'accord d'un proche pour chaque achat d'un adulte aveugle le place sous tutelle.
**Conséquences.** `orchestrator/approvals.py` et les réglages des proches sont supprimés. Les contrats changent : les schémas `approval-*`, le message `approval`, l'état `awaiting_relative` et le code d'erreur `approval_failed` sont supprimés. L'outil H `request_payment_approval` reste (verrou avant le clic). L'écran du jury passe à 5 étapes.

## 2026-11-18 : fournisseur de la voix imposé (v1 locale)

Sans fournisseur précisé, Hugging Face a routé `hexgrad/Kokoro-82M` vers fal-ai (`fal-ai/kokoro/american-english`), qui refuse la voix `ff_siwis` (erreur 422 : voix anglaises seulement). Avec `provider="deepinfra"`, la voix française fonctionne, mais a mis 16 s ce jour-là (Hugging Face signalait un contrôle de santé raté). `PILOTE_TTS_PROVIDER` (deepinfra par défaut) règle le fournisseur. Au-delà de `PILOTE_TTS_TIMEOUT_S`, l'interface utilise la voix du navigateur. Transcription (Whisper turbo) : 1,5 s ; compréhension (Llama 3.3) : 2,3 s.

## 2026-11-18 : premier parcours complet avec le vrai agent H (v1 locale)

Commande à la voix (mode texte) sur Rail Démo, navigateur cloud H, IA Hugging Face : demande → 3 options → panier (29 €) → premier oui → relecture → deuxième oui → approbation de l'orchestrateur → clic « Payer 29,00 € » → page de validation bancaire simulée. Écarts constatés avec le SDK `hai-agents` 1.5.3, corrigés dans `orchestrator/agent_h/agent.py` :

- **Fin d'étape.** Juste après `send_message`, la session est encore « idle » et renvoie la réponse précédente. Les messages après le premier n'ont pas de `RequestStartEvent` (ce sont des `message_event`), et la réponse peut n'exister que comme appel de l'outil `answer`. L'agent lit désormais la réponse qui suit son dernier message dans les événements (`_step_answer`). Avant cette correction, la relecture reprenait la réponse du panier.
- **Objets imbriqués en texte.** L'agent envoie souvent `order_summary`, `site_notes` et le récapitulatif de `request_payment_approval` en texte JSON : acceptés et convertis. `options: null` devient une liste vide.
- **Outil de paiement.** Il était déclaré avec le contrat (centimes) mais lu au format de l'agent (euros) : tout paiement était refusé. Il est déclaré au format de l'agent, et les deux formats sont acceptés.
- **Résultat sans approbation.** Un `payment_result` annoncé sans « approved » du garde-fou n'est plus cru : refus annoncé comme « rien n'a été cliqué », et un « accepted » sans approbation devient `unknown` (« vérifiez sur le site »).
- **Validation bancaire.** Sur la page simulée de Rail Démo, l'agent attend 30 s puis renvoie `unknown`. Pour la démo, un humain valide ou refuse sur cette page ; la consigne prévoit jusqu'à 5 minutes, à régler si besoin.

## 2026-11-18 : retours du premier test au micro (v1 locale)

- **Voix en double** : plusieurs pages Pilote ouvertes parlaient en même temps. Une seule page parle désormais (la dernière démarrée prévient les autres par `BroadcastChannel`), et une page cachée se tait.
- **Heures** : « 14:57 » était lu « quatorze cinquante-sept ». `orchestrator.ai.speech_text.for_speech` réécrit chaque phrase dite : « 14 heures 57 », « départ 14 heures 14, arrivée 15 heures 16 », « Paris vers Lille », « 29 euros ».
- **Faux « prix changé »** : la relecture comparait l'empreinte, qui dépend des libellés recopiés par l'agent (jamais identiques deux fois). La relecture et le dernier verrou comparent maintenant le total au centime et les quantités (`session.same_order`). Un vrai changement de prix bloque toujours.
- **Compréhension** : « la deuxième », « le 3 », « détails du 2 », « oui », « non », « annule » sont compris sans le modèle de langage quand Pilote attend ce type de réponse (`session.quick_intent`). La même demande redite relit les options au lieu de relancer la recherche. Les options finissent par la réponse attendue (« Dites le numéro… »).
- **Progression** : pendant les étapes longues, Pilote dit ce que fait l'agent (première phrase de ses `policy_event`), au plus une phrase toutes les 10 s (la première dès qu’elle arrive).

## 2026-11-18 : Pilote ne dit que des choses compréhensibles par tout le monde (v1 locale)

- **À la source** : la consigne de l'agent H (`prompts.py`) lui demande des messages courts en français simple, sans identifiant (o1, o2), sans anglais, sans nom d'outil, dates en toutes lettres.
- **Filet de sécurité** : `readable_progress` écarte toute phrase de progression technique (adresse web, nom d'outil, code, mot anglais) ; `for_speech` réécrit dates (« 11/19/2026 » → « 19 novembre 2026 »), identifiants (« o2 » → « numéro 2 ») et jargon (« authentification forte », « DSP2 », « pop-up »).

## 2026-11-18 : premiers essais sur SNCF Connect (Chrome local, sans paiement)

- **Essai 1** (agent sans compétences, sans fiche) : 10 minutes à tâtonner (onglet « Trains » vers une page promo, menu « Voyager », chat d'aide rouvert à chaque clic), sans atteindre les résultats. Modèle utilisé : `holo4-27b`, le même que `h/web-surfer-pro`, mais sans ses compétences.
- **Corrections** : compétences `h/planning` et `h/answering` (comme `h/web-surfer-pro`), fiche de départ SNCF (`agent_h/starter_cards.py`), règle anti-boucle dans la consigne (changer de méthode après 2 échecs, demander un humain après 3 minutes).
- **Essai 2** : l'agent va droit au formulaire, le pré-remplit (Paris → Lille, 14 h), mais « Voir les prix » et le calendrier ne réagissent à aucun clic automatisé. Il demande un humain au bout de 8 minutes au lieu de boucler. Hypothèse : protection anti-robots du site qui neutralise les clics pilotés. À vérifier en cliquant à la main.

## 2026-11-18 : compétences H retirées, délais raccourcis, modèle réglable

- **Compétences `h/planning` et `h/answering` retirées** : testées seules et ensemble, elles terminent la session après la première réponse ; le message suivant (panier) provoque une erreur de l'agent. Sans compétence, l'agent enchaîne les étapes normalement.
- **Arrêt détecté tout de suite** : si l'agent termine ou plante après notre message sans répondre, l'étape échoue aussitôt au lieu d'attendre.
- **Délais raccourcis** (retour : au-delà de 5 minutes, c'est trop long) : 3 minutes au plus par étape de navigation, 6 pour le paiement (validation bancaire), 3 pour un geste humain. L'outil de vérification s'arrête à 5 minutes.
- **Modèle et réflexion réglables** : `PILOTE_H_MODEL` (vide = holo4-27b) et `PILOTE_H_REASONING` (disabled, low, medium, xhigh). Modèles accessibles avec la clé de l'équipe (`GET https://api.hcompany.ai/v1/models`, 18/11) : holo4-27b, holo4-35b-a3b, holo3-1-35b-a3b, holo3-122b-a10b (sans outils). Aucun modèle « devin » : une session avec ce nom échoue.

## 2026-11-18 : SNCF Connect fonctionne jusqu'à la page de paiement (Chrome local)

Trois causes trouvées, dans l'ordre :
1. **Chrome Retina** : en densité 2 et fenêtre de 1200 px, l'agent cliquait à côté (« Trajets via » au lieu du champ « Aller », chat d'aide). `scripts/lancer-chrome-agent.sh` lance le Chrome de l'agent en densité 1 et 1440 px : recherche en 37 s (avant : jamais).
2. **Mode « votre navigateur »** : H termine la session dès la première réponse (« destroy » envoyé au relais local, puis fin de session) ; le message de l'étape suivante n'est jamais lu. Chaque étape démarre maintenant une session courte qui reprend sur la page laissée, dans le même Chrome (`ShoppingAgent._start_step_session`).
3. **Prix à 0 €** lus par erreur (« Trajet recommandé ») : ces options sont écartées.

Résultat (sans paiement) : recherche 37 s, page de paiement 138 s (TGV INOUI 49 €), relecture 171 s.

## 2026-11-18 : billets à 0 € gardés, une correction met à jour toute la demande

- **0 € est un vrai prix** : sur SNCF Connect, un abonnement (MAX JEUNE) affiche des billets à 0 €. Le filtre qui les écartait, et celui qui ignorait « gratuit » ou un budget de 0 €, sont retirés.
- **Correction de la demande** (« j'ai dit demain après 14 h ») : l'intention est fusionnée avec la correction, redite à la personne, et l'agent reçoit la demande à jour. Avant, il recevait l'ancienne date et la correction, contradictoires, et hésitait entre 14 h et 16 h.
- **Heure** : SNCF Connect ne propose que des créneaux de 2 heures (14 h, 16 h…), et une heure déjà passée n'est pas proposée pour aujourd'hui.

## 2026-11-18 : v2 locale, travail de l'équipe et du membre 4 réunis

**Base.** Branche `fix/empty-env-defaults` (Rubens) fusionnée avec `retrait-validation-proches` (chab-algo) : sessions H gardées ouvertes (`idle_timeout_s`), recherche SNCF rapide, commentaire en direct (`narration.py`), achat direct avec code, contrats sans validation par un tiers.
**Paiement.** On garde l'achat direct avec le code secret à 3 chiffres dit à l'oral (`PILOTE_DIRECT_BUY=1`, `PILOTE_PURCHASE_CODE`). Le parcours « oui, relecture, deuxième oui » reste dans le code, utilisé seulement si `PILOTE_DIRECT_BUY` est vide.
**Reporté de `v1-locale`.** Mode question (recherche web, réponse avec la source) ; surveillant branché sur le flux d'événements de l'équipe (`agent_h/watch.py` : boucle ou étape sans action nouvelle depuis 90 s, lecture de la capture par Qwen3-VL, conseil envoyé à l'agent) ; réponses courtes comprises sans modèle (`quick_intent`) ; relecture comparant total et quantités (`same_order`) ; correction de la demande fusionnée ; filtre des phrases techniques (`readable_progress`) ; dates, identifiants et jargon réécrits dans `for_speech` ; fournisseur de la voix imposé (`PILOTE_TTS_PROVIDER`) ; une seule page qui parle ; outils de vérification `agent_h.check` et `ai.check`.
**Pris de l'équipe à la place du mien.** Une session H gardée ouverte au lieu d'une session courte par étape ; leur commentaire en direct au lieu de mes phrases de progression ; heures lues « 14 heures 14 vers 15 heures 16 » ; texte réécrit seulement au moment de la synthèse, pas dans la transcription.
**Laissé de côté.** L'annonce « votre banque demande de valider le paiement » (dépendait de mon ancienne progression).

## 2026-11-18 : fin de tâche annoncée, coupure réseau après le paiement (v2 locale)

Test à la voix sur SNCF : code bon, paiement autorisé, l'agent clique, puis une coupure avec H (`httpx.ReadTimeout` pendant `wait_for_completion`) fait tomber la commande en « erreur inattendue ». Pilote annonçait alors « rien n'a été acheté », ce qui pouvait être faux.
- **Fin de tâche** : chaque tâche terminée finit par « C'est terminé. » avant « Que puis-je faire d'autre pour vous ? ».
- **Après l'autorisation du paiement**, une erreur, un délai dépassé ou une coupure ne disent plus jamais « rien n'a été acheté » : Pilote dit qu'il ne sait pas si l'achat est passé et demande de vérifier les e-mails ou le site (`session.UNSURE`).
- **Coupure passagère avec H** : l'attente de la réponse de l'agent réessaie jusqu'à 5 fois (`NETWORK_RETRIES`) au lieu d'abandonner.
- **Sous-agents du portail** (`h/web-surfer-flash`, `h/web-scraper-pro`, `h/web-scraper-flash`, ajoutés à `pilote-shopper`) : pas recopiés sur le Chrome local par `_mirrored_spec`, donc pas encore utilisés. Ils tournent sur les navigateurs de H et portent `h/planning` et `h/answering`, qui cassaient l'enchaînement des étapes le 18/11.

## 2026-11-18 : pilote-shopper essayé en local puis dans le cloud H (sans paiement)

- **Chrome local** (agent du portail recopié, sous-agents compris) : recherche 115 s, 3 options justes (dont 0 € avec MAX JEUNE) ; panier bloqué par des coupures du lien local avec H. Aucun sous-agent appelé.
- **Navigateur cloud H** (`PILOTE_BROWSER_HOST=cloud`, agent du portail tel quel) : démarrage 2 s, recherche 76 s, page de paiement 136 s (« Valider et payer », 71 €), relecture identique 146 s. Pas de CAPTCHA jusqu'au paiement, sans être connecté : prix plein tarif (71 € au lieu de 49 € ou 0 € avec l'abonnement du compte). Aucun sous-agent appelé.
- Les sous-agents ne servent pas sur ce parcours : le modèle ne délègue pas une navigation sur une page déjà ouverte.

## 2026-11-18 : questions dans le cloud H, nouvelle interface (v2 locale, membre 4)

- **Questions** : `PILOTE_H_QUESTION_AGENT=pilote-shopper` fait répondre aux questions par l'agent du portail tel quel (navigateur cloud H, sous-agents de lecture). Les commandes restent sur le Chrome local. Mesuré : « à quelle heure ferme la gare de Lille Flandres ? », réponse sourcée en 23 s. L'agent n'a pas délégué à ses sous-agents sur cette question.
- **Interface** : fond blanc, halo bleu lumineux autour du micro (respire au repos, tourne pendant le travail de l'agent, suit le niveau du micro), conversation toujours visible en bulles bleues (personne) et grises (Pilote), indicateur « en train d'écrire », police système (SF Pro sur Mac). L'écran du jury suit le même style.

## 2026-11-18 : voix de l'ordinateur en voix principale (v2 locale, membre 4)

`PILOTE_VOICE=navigateur` : l'orchestrateur ne demande plus de synthèse à Hugging Face (Kokoro mettait de 1 à plus de 20 s ce soir-là), la page parle tout de suite avec la meilleure voix française de l'ordinateur (voix Premium ou Améliorée en priorité). Aucune autre voix française de Hugging Face Inference Providers ne parle correctement français (essais Chatterbox, Chatterbox Turbo, Sesame CSM retranscrits par Whisper). Kokoro reste disponible (`PILOTE_VOICE` vide).

## 2026-11-18 : Pilote converse avec un modèle de langage, faits vérifiés (v2 locale, membre 4)

Retour : Pilote semblait réciter des phrases toutes faites. Ses phrases de conversation sont maintenant rédigées par le modèle de langage (`PILOTE_LLM_MODEL`, Llama 3.3 70B) à partir de la situation, des faits, de la phrase écrite d'avance et de l'historique (`orchestrator/ai/conversation.py`, `Session._talk`). Il répond aux salutations, remerciements et questions sur lui, et aux questions sur les options (« lequel est le moins cher ? »).
- **Garde-fous** : chaque nombre de la réponse doit venir des faits, de la phrase d'avance ou de la phrase de la personne ; une réponse qui annonce un achat ou un paiement absent de la phrase d'avance est refusée ; délai de 4 s ; au moindre doute, la phrase écrite d'avance.
- **Restent fixes** : l'annonce « je suis une IA », la demande du code, le montant payé, les résultats de paiement et d'annulation.
- Mesuré : 1,4 à 2,1 s par réponse. `PILOTE_CONVERSATION=0` revient aux phrases écrites d'avance.

## 2026-11-18 : conversation mains libres et « Bonjour Pilote » (v2 locale, membre 4)

- **Mains libres** : après chaque réponse de Pilote qui attend quelque chose (demande, choix, oui / non, code, geste humain), la page réécoute toute seule et envoie au silence (1,4 s). Sans parole pendant 7 s, elle se tait.
- **« Bonjour Pilote »** : quand Pilote ne parle pas et n'enregistre pas, la reconnaissance vocale du navigateur (Chrome, Safari) guette « Bonjour Pilote ». La suite de la phrase (« Bonjour Pilote, un train pour Lille ») est envoyée directement. Un premier geste (Espace ou toucher l'orbe) reste nécessaire : le navigateur bloque le son et le micro sans lui.
- **Réaction immédiate** : « D'accord. », « Je m'en occupe. »… dès qu'on a fini de parler (nouvelle demande ou choix seulement).
- **Modèle des réponses** : Qwen3-30B-A3B essayé, plus lent ce soir (plus de 4 s, donc phrase d'avance) ; Llama 3.3 70B gardé (1,5 à 1,7 s). Les nombres doivent être écrits en chiffres : un nombre en lettres échapperait à la vérification et fait reprendre la phrase d'avance.

## 2026-11-18 : code dit à voix haute, « OK Pilote », écoute automatique limitée (v2 locale, membre 4)

- **Code** : Pilote demande le code à voix haute ; le champ à taper n'apparaît que si on choisit « Je préfère le taper au clavier ».
- **« OK Pilote »** : pendant que Pilote parle, la reconnaissance vocale du navigateur guette « OK Pilote » ; il se tait aussitôt et écoute. Seule cette phrase compte pendant qu'il parle (sa propre voix ne la dit jamais).
- **Écoute automatique** : une seule fois par phrase de Pilote, et seulement si elle attend une réponse (choix, oui / non, code, ou question finissant par « ? »). Plus d'écoute automatique après la fin d'une commande ni après une écoute restée sans parole : il faut dire « Bonjour Pilote » ou appuyer. Avant, une écoute sans parole relançait aussitôt une nouvelle écoute.

## 2026-11-18 : questions mal comprises, mots inventés (v2 locale, membre 4)

Retour du test : « Tu pourrais regarder combien de temps je mets pour aller Merci. » La destination n'a pas été entendue, Pilote a lancé une recherche web sur une question incomplète (20 s), a oublié le fil quand la personne a précisé, est passé au tutoiement, et a lu une « source » technique.
- **Mots inventés par Whisper** : le son « je vous écoute » démarrait en même temps que le micro, et son écho était enregistré ; Whisper « transcrivait » la cloche. Le son est maintenant joué avant l'ouverture du micro (380 ms d'écart) et raccourci. L'écoute attend 2 s de silence (au lieu de 1,4 s) avant d'envoyer, pour laisser une petite pause (« pour aller… à Lyon »).
- **Question préparée avant la recherche** (`conversation.prepare_question`, 0,5 à 1,3 s) : le modèle complète la question avec la conversation, ou demande la précision qui manque (« Pour aller où ? ») au lieu de lancer une recherche. La réponse suivante est reliée à la question en attente.
- **Vouvoiement** imposé (réponses de Pilote et consigne de l'agent pour les questions). Une « source » qui décrit un échec (« demande incomplète ») n'est plus lue.

## 2026-11-19 : consigne de l'agent élargie à toutes les démarches (v2 locale, membre 4)

La consigne était tournée vers SNCF et l'achat d'un train. Elle couvre maintenant achat, réservation, recherche et comparaison sur n'importe quel site ; sans site imposé, l'agent va directement sur le site le plus connu en France pour la tâche (SNCF Connect, Uber Eats, Amazon / Fnac / Darty, Doctolib, TheFork, Booking), sinon passe par un moteur de recherche. Ajouts : méthode pour lire une page (repérer la recherche du site, fermer les fenêtres gênantes, vérifier après chaque action, changer de méthode après 2 échecs), refus des options et assurances ajoutées, étapes panier et achat sans vocabulaire ferroviaire. Côté code : texte de la page envoyé avec la capture (`PILOTE_H_PAGE_TEXT=0` pour couper).
Essai réel (Chrome local, agent du code, aucun site imposé, « casque Bluetooth Sony WH-1000XM5 ») : Amazon choisi, cookies fermés, 3 offres avec prix et livraison en 55 s, rien dans le panier. L'agent du portail `pilote-shopper` garde l'ancienne consigne tant qu'il n'est pas mis à jour.

## 2026-11-19 : Pilote opérationnel pour toutes les démarches (v2 locale, membre 4, avec accord pour toucher les autres parties)

- **Contrat** (membre 5, à relire) : nouvelle catégorie `reservation` (table, hôtel, rendez-vous, spectacle) dans `intent.schema.json`, `contracts.py` et les types web générés. Clés de `details` : place, people, kind.
- **Compréhension** (membre 2) : consigne générale (acheter, réserver, chercher), définitions des catégories, informations obligatoires d'une réservation (objet et date), questions de relance générales (« Pour quel jour ? », « Qu'est-ce qu'il vous faut exactement ? »). Essai : « une table pour deux ce soir à Lyon, italien » → reservation ; « rendez-vous chez un dentiste à Paris » → reservation ; « écouteurs à moins de 50 € » → boutique, budget 5000.
- **Orchestrateur** (membre 5) : la demande redite gère la réservation.
- **Agent** (membre 1) : texte de la page aussi pour l'agent du portail recopié ; `pilote-shopper` mis à jour sur H avec la nouvelle consigne (sous-agents gardés).
- **Sites** : sans site configuré (boutique, réservation), l'agent choisit le site le plus connu. `PILOTE_SITE_REPAS` vidé dans `.env` : les repas vont sur le vrai Uber Eats (connexion à faire dans le Chrome de l'agent).

## 2026-11-19 : Pilote demande ce qui manque pour bien choisir (v2 locale, membre 4)

Retour : pour un vêtement, Pilote ne demandait pas la taille. En plus des informations obligatoires par catégorie, `complete_intent` demande maintenant (une question à la fois) :
- **par règle** : la taille d'un vêtement, la pointure de chaussures, le nombre de personnes puis l'heure pour une table au restaurant ;
- **par le modèle** (champ `needs` de sa réponse, hors contrat) : la seule information indispensable restante (modèle de téléphone pour une coque, imprimante pour des cartouches…), jamais une question de confort.
Essai réel : pull → taille ; baskets → pointure ; coque → modèle de téléphone ; cartouches → imprimante ; t-shirt taille M → rien ; table japonaise → nombre de personnes ; livre précis → rien.
- **Mémoire des sites et speedrun (2026-11-19)** : la fiche donnée à l'agent garde toujours les étapes de départ écrites à la main (le speedrun SNCF « Tout rechercher ») ; la mémoire n'y ajoute que ses pièges, ses boutons et ses statistiques (`card_for_order`). Avant, dès qu'un premier achat avait été enregistré, la fiche apprise remplaçait le speedrun pour toutes les commandes suivantes, et le fichier `data/site-cards.json` le gardait après redémarrage. La mémoire est maintenant enregistrée à chaque fin de commande, achetée ou non (échec, blocage, annulation), avec la raison du blocage comme piège : une commande ratée sert à la suivante. Seul un achat accepté compte dans `successful_runs`. On garde les 12 pièges et boutons les plus récents.
- **Speedrun SNCF corrigé et commandes plus rapides (2026-11-19)** : sur SNCF Connect, Entrée ne lance plus rien dans « Tout rechercher » et les suggestions sont des adresses ; l'agent repartait alors sur le formulaire Trains et reconfirmait tout (71 à 89 s, 12 actions). La fiche fait maintenant cliquer directement sur « Rechercher » après avoir tapé le trajet, sans reconfirmer : 53 s, 6 actions, mesuré sur Paris → Lyon. L'adresse `/home/search?userInput=…` ouverte directement ne marche pas (retour à l'accueil). Les consignes de l'agent du portail (onglet « Trains ») passent désormais après la fiche du site (`prompts.with_card_priority`). Autres gains : Chrome et la session H s'ouvrent pendant que Pilote redit la demande, et l'agent sélectionne l'option pendant « J'achète … ». Le journal dit pourquoi et où chaque commande s'arrête (`code`, `state_before`, `step`, `seconds`, jamais la phrase dite). Les réservations sans site fixe ne rangent plus leur mémoire sous un nom vide (refusé par le contrat) : elle va au site où l'agent a fini.
- **Tournée de tests réels et corrections (2026-11-19)** : parcours complets rejoués sans achat (question, train, affinage, repas, réservation, mauvais code, coupure du serveur, téléphone). Corrigé : heures et classes mal dites (« 7 heures52 », « 2e classe », « 20/11 »), détails d'option en double, « répète les options » compris, heure inventée quand aucune n'est dite, heure exacte d'une réservation dans `details.time`, source d'une réponse dite simplement. Vitesse : options lues telles quelles (2,6 s après leur arrivée au lieu de 5 à 8 s), une seule question pour départ, arrivée et jour, Chrome ouvert au démarrage, affinage sur la page de résultats (43 s au lieu de 57 s). Voix : le service Hugging Face (Kokoro via deepinfra) répond parfois en 6 s ou par des erreurs 503 ; une requête lente est doublée, et après deux phrases de suite sans voix le navigateur parle seul pendant 45 s. Interface : conversation et champ de texte visibles à l'écran, états justes, commentaire en direct affiché, cibles tactiles de 44 px ; écran du jury avec date en clair et conversation rejouée. Démo : `python -m orchestrator.check` (tout vérifier avant de commencer, sans rien acheter) et `PILOTE_PLAN_B=1` (faux sites de l'équipe, recherche mesurée à 40 s).
- **Lien direct vers les résultats SNCF (2026-11-19)** : le bouton « Rechercher » de SNCF Connect passe par l'assistant du site, qui met 30 à 40 s à afficher les trains ; l'agent ne pouvait qu'attendre (recherche mesurée à 79 s). Pilote ouvre maintenant lui-même `https://www.sncf-connect.com/home/search?userInput=Paris+Nantes+20+novembre+10h` dans le Chrome dédié dès le début (`site_memory.direct_search_url`), pendant qu'il redit la demande ; l'agent n'a plus qu'à lire. Mesuré : options 34 s et 37 s après la phrase (Paris → Nantes, Paris → Lyon). En Chrome local, la session H démarre sans `start_url` (elle continue depuis la page ouverte) : avec `start_url`, la fenêtre se fermait pendant le chargement (« target window already closed »). `PILOTE_SNCF_QUICK_SEARCH=0` revient au formulaire Trains. Le code secret d'achat reste disponible (`PILOTE_PURCHASE_CODE`) mais n'est plus utilisé en démo : la reconnaissance vocale du code a échoué trois fois de suite en essai réel.
- **Toujours un « oui » avant d'acheter (2026-11-19)** : sans code secret, l'achat direct demande « J'achète bien … ? » pour toute option, y compris un billet à 0 € (avant, un billet gratuit s'achetait sur le seul choix de l'option). Vérifié en vrai : billet gratuit choisi, « non » répondu, rien acheté.

## 2026-11-18 : carte dictée quand le site n'en a pas d'enregistrée

- À la page de paiement, si aucune carte enregistrée n'est utilisable, l'agent appelle l'outil `request_card`. Pilote fait dicter à voix haute le numéro, la date d'expiration et le cryptogramme (saisie masquée « ••• » : ni modèle de langage, ni historique, ni journal), relit les 4 derniers chiffres, puis demande : « Voulez-vous enregistrer cette carte sur <site> ? ». Le nom du titulaire n'est demandé que si le site le réclame.
- L'agent clique dans chaque champ et appelle `fill_card_field` : Pilote tape la valeur dans le Chrome local (port 9222), l'agent H ne reçoit jamais les chiffres. Il coche ou décoche la case d'enregistrement du site selon la réponse (`card_saved_on_site`), ou ne paie pas si le site impose l'enregistrement alors que la personne a dit non.
- Pilote ne garde jamais la carte : effacée à la fin de `buy()`, `pay()` et `cancel()` ; jamais dans la mémoire des sites ni ailleurs. Seul le site la garde, et seulement si la personne l'a demandé.
- Limites : seulement avec le Chrome local ; dictés, les chiffres passent par la transcription Hugging Face et sont entendus autour ; ce que la page affiche ensuite reste visible sur les captures de l'agent. Non testé en paiement réel.

## 2026-11-18 : mémoire des chemins, avec réessais espacés

- `orchestrator/agent_h/path_memory.py`, fichier local `~/.pilote/memoire-sites.json` (droits 600), gardé d'une visite et d'un redémarrage à l'autre. Une astuce par chemin ou piège, avec réussites, échecs et échecs de suite.
- Apprentissage : après une étape réussie (options trouvées, récapitulatif lu, paiement tenté), l'agent résume le chemin suivi en 1 à 3 astuces et les pièges évités (`new_tips`) ; pour chaque astuce de la mémoire essayée, il dit si elle a marché (`tips_feedback`).
- Jugée inutile et mise de côté après 3 échecs de suite (une réussite remet le compteur à zéro). Pas de réessai programmé (décision du 2026-11-18) : une astuce écartée n'est proposée que « si tu es bloqué », quand aucun autre chemin ne marche. Si elle marche alors, la réussite est enregistrée et elle revient en service.
- Données personnelles : refus des textes avec e-mail, adresse, nombre de 2 chiffres ou plus (prix, date, heure, carte), montant ; les valeurs de la commande (villes, plat) sont remplacées par <ville de départ>, <ville d'arrivée>, <plat>.
- Mesuré : 3 visites SNCF, 4 astuces apprises ; 2e visite 13 décisions au lieu de 18, astuces confirmées. Limite vue : les chemins du guide écrit à la main (ex. recherche rapide « Tout rechercher ») ne sont pas suivis par la mémoire, donc pas réessayés : la 1re visite a vu la recherche rapide échouer et la mémoire a appris à passer par le formulaire.

## 2026-11-18 : recherche rapide généralisée, achats en boutique

- La « recherche rapide » de SNCF Connect (tout taper d'un coup dans « Tout rechercher ») devient une règle de la consigne pour tous les sites : barre de recherche principale, texte de recherche tapé d'un coup, puis les critères avec les filtres du site. Le budget n'est jamais tapé (une barre prend « 3000 » pour un mot du produit) : filtre de prix ou tri « Prix croissant », et aucune option au-dessus du budget.
- Pilote calcule le texte de recherche (`shops.search_query`) : l'objet et ses critères, sans budget ni nom de boutique ; pour un train « <départ> <arrivée> <jour> <mois> <heure> ».
- Catégorie « boutique » : la boutique nommée par la personne (« sur Amazon », « chez Fnac », Leroy Merlin, Ikea, Darty…), sinon Amazon.fr (`PILOTE_SITE_BOUTIQUE` pour changer). Sur Amazon, l'agent arrive directement sur les résultats (`/s?k=`).
- Mesuré : « abat-jour style moderne, budget 3000 € » sur Amazon, 3 options dans le budget en 33 s et 4 actions.

## 2026-11-18 : comparaison entre boutiques

- Achat en boutique sans boutique nommée (et sans `PILOTE_SITE_BOUTIQUE`) : Pilote compare jusqu'à 3 boutiques adaptées au type de produit (`shops.CATALOG` : canapé → Maisons du Monde, Conforama, Ikea ; casque → Fnac, Darty, Boulanger ; vélo → Decathlon… ; sinon Cdiscount, La Redoute, Fnac). Amazon ou Fnac seulement s'ils sont nommés ou adaptés.
- Les recherches tournent en parallèle, une session H par boutique, en navigateur cloud (pas besoin d'être connecté pour chercher) ; au plus 3 à la fois (offre gratuite H), 2 options par boutique, mêlées (la meilleure de chaque boutique d'abord), titre suivi du nom de la boutique. Une boutique bloquée, lente (240 s) ou sans résultat est ignorée.
- Après le choix, l'achat se fait dans le Chrome local (comptes connectés) : nouvelle session sur la boutique choisie, l'agent retrouve le produit par la barre de recherche et vérifie le prix.
- Poltronesofà retiré : site vitrine, pas de prix ni de vente en ligne (« Visitez nos magasins »).
- Réponses de l'agent plus tolérantes : détails de produit libres (couleur, places…) acceptés au lieu de rejeter toute la boutique.
- Mesuré : canapé d'angle gris, budget 1500 €, 6 options de 3 boutiques en 86 s. Achat après comparaison non testé en réel.

## 2026-11-18 : acheter sur n'importe quel site, plus de comparaison

- Décision : Pilote n'est pas un comparateur. La personne fait sa recherche ailleurs (un assistant, un ami) et demande d'acheter sur le site de son choix. La comparaison entre boutiques et Amazon par défaut sont retirés.
- Le site est pris dans la demande (`shops.resolve_site`) : un lien (produit ou site, tapé dans le champ de texte : ouvert tel quel, l'agent propose ce produit-là), une adresse (« maisonsdumonde.com »), une boutique courante (Ikea, Zalando, Vinted…), ou n'importe quel autre nom après « sur » / « chez ». Pour un nom inconnu, l'agent part d'une recherche Bing et ouvre le site officiel (pas une annonce, une place de marché ni un comparateur) ; s'il ne vend pas en ligne, il s'arrête et le dit.
- Sans site donné (hors train et repas, qui gardent SNCF Connect et Uber Eats), Pilote demande : « Sur quel site voulez-vous l'acheter ? ». `PILOTE_SITE_BOUTIQUE` impose un site si besoin.
- La recherche rapide reste valable sur tous les sites (texte tapé d'un coup, budget par les filtres).
- Mesuré : « un pull marinière sur le site de Petit Bateau » (site inconnu) : site officiel trouvé, 3 options en 69 s et 10 actions.


## 2026-11-19 — Le chemin d'achat est retenu même sans achat

- En achat direct, l'agent va d'abord jusqu'au bouton de paiement ; le code à 3 chiffres (ou le « oui » sans code)
  est demandé à ce moment-là, sur le total réellement affiché, via request_payment_approval.
- Dès que l'agent a atteint ce bouton (récapitulatif lisible envoyé), l'étape d'achat compte comme réussie pour la
  mémoire des chemins : si la personne dit non ou se trompe de code, rien n'est payé mais le chemin est appris.
- Un panier plus cher que l'option choisie est toujours refusé, sans poser la question.

## 2026-11-19 — Total plus cher que le prix annoncé : on explique, la personne décide

- Achat direct : si le total au bouton de paiement diffère du prix annoncé (frais de livraison, de service…),
  Pilote dit le détail (« le produit à 5 euros, comme annoncé, frais de livraison : 99 centimes, frais de
  service : 5 euros 49 ») puis demande le code (ou un oui). Avant, l'achat était refusé d'office.
- Le plafond de l'agent (PILOTE_MAX_TOTAL_EUR) s'applique toujours, avant toute question.

## 2026-11-19 : fusion de `version-2` et `pilote-V72`

- **Base** : `version-2` (interface, conversation, questions sur le web, réservations, mémoire des sites) + les 9 commits de `pilote-V72` (carte dictée à voix haute, mémoire des chemins de l'agent, achat sur n'importe quel site, explication des frais). Les deux partaient de `fix/empty-env-defaults` ; 29 zones de conflit résolues à la main.
- **Site d'achat** : les deux branches avaient chacune sa règle. Règle retenue : un site donné par la personne (lien, adresse, nom) passe d'abord ; sinon le site par défaut (train, repas ; faux sites si `PILOTE_PLAN_B=1`) ; **réservation** (restaurant, rendez-vous) sans site : l'agent choisit lui-même (Google Maps), `site_for` renvoie `""` ; **boutique** sans site : Pilote demande « Sur quel site voulez-vous l'acheter ? » (pas d'Amazon par défaut, décision de `pilote-V72`).
- **Achat direct** : le code ou le oui est demandé au bouton de paiement, sur le total réellement affiché (`pilote-V72`), avec le détail des frais si le total diffère du prix annoncé. La phrase d'avant dit « Je prépare l'achat… Je vous demanderai votre code juste avant de payer », car « J'achète » serait faux à ce moment.
- **Deux mémoires** coexistent : la fiche de site (`site_memory`, `version-2`) et la mémoire des chemins (`path_memory`, `pilote-V72`, `PILOTE_MEMORY`). À rapprocher plus tard.

## 2026-11-19 : pilote-Vmax, fusion de `version-2` à jour et `pilote-V72`

- Base : la fusion de l'équipe (`95cccc0`, version-2 + pilote-V72), plus les 2 derniers commits de `version-2` (lien direct vers les résultats SNCF, toujours un oui avant d'acheter).
- Achat direct : le code ou le oui reste demandé au bouton de paiement, sur le total réellement affiché (`pilote-V72`), et il est maintenant demandé **même pour un billet gratuit** (« J'achète bien …, gratuit ? ») : règle de `version-2`, appliquée au moment où l'agent est sur le bouton.
- Page d'arrivée : le lien direct SNCF (`direct_search_url`) passe d'abord, sinon la page de résultats d'Amazon ou d'Uber Eats, ou le lien donné par la personne (`start_url_for`).

## 2026-11-19 : pilote-Vmax, heures des trains et panier propre

- **Heures des trains** : les options ne disaient plus les heures depuis la fusion (l'agent les mettait dans `details.departure` / `arrival`, plus dans le nom). `options_summary` ajoute maintenant « départ à 14 heures 44, arrivée à 15 heures 48 » depuis les détails, sauf si le nom les contient déjà.
- **Panier propre** : consigne de l'agent, le panier ne doit contenir que l'option choisie, dans la quantité demandée ; il retire les restes d'une commande précédente (un autre billet, un 2e Big Mac).
- **Filet de sécurité** (achat direct, au bouton de paiement) : si les articles coûtent plus que l'option, Pilote nomme ce qui est en trop (nom, heure, prix) et demande « Je le retire du panier ? ». Oui → réponse `fix_cart` à l'agent, qui nettoie et redemande l'accord. Non → le total complet est expliqué et la personne décide. Une seule tentative de nettoyage ; si l'agent n'y arrive pas, Pilote le dit.
- Vérification de la fusion : la suite de tests de `pilote-V72` a été rejouée sur `pilote-Vmax` ; à part les heures, les écarts sont des changements voulus (validation par un proche retirée, nouvelles phrases).
