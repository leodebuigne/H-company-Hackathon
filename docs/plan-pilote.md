# Pilote – Benchmark, solution et plan d'équipe

17 novembre 2026 · Léo

> Version Markdown du doc en ligne : https://claude.ai/artifact/A7ue2eRWdthFZCMSHD8m7h (les deux schémas, architecture et calendrier, ne sont visibles que dans le doc en ligne).

## En bref

Pilote est un assistant vocal qui fait les achats en ligne à la place d'une personne aveugle ou malvoyante, sur de vrais sites, avec une triple vérification avant chaque paiement. Le projet repose sur l'agent de navigation de H Company et sur les modèles de Hugging Face (voix, compréhension, vision).

Ce qui change par rapport au premier plan : plus de faux sites. La démo se fait sur de vrais sites marchands avec une carte virtuelle éphémère à 0 €. Le paiement est refusé par la banque, ce qui prouve que tout le parcours fonctionne sans dépenser d'argent.

Ce doc contient, dans l'ordre : le benchmark des concurrents, notre solution, les règles pour tester en réel, l'architecture, le calendrier, puis un prompt prêt à l'emploi pour chacun des 5 membres de l'équipe.

## Benchmark des concurrents

Aucun produit trouvé ne fait ce que fait Pilote : un agent vocal qui achète sur n'importe quel site à la place d'une personne aveugle, en français, avec une vérification avant paiement. Les acteurs se rangent en deux camps : les outils d'accessibilité décrivent mais n'agissent pas, et les agents d'achat agissent mais sont pensés pour des personnes qui voient l'écran.

| Acteur | Ce qu'il fait | Ce qui lui manque pour notre usage |
| --- | --- | --- |
| [Be My Eyes](https://www.bemyeyes.com/?p=21193598) | Bénévoles en vidéo, IA qui décrit les images, portail d'achat accessible avec InnoSearch | Le portail n'existe qu'aux États-Unis, au Canada, au Royaume-Uni et en Australie ; la page ne dit pas si l'IA achète sur les sites |
| [Envision Ally](https://apps.apple.com/us/app/ally-accessible-ai-assistant/id6476980907) | Assistant vocal (lit, décrit, répond), lunettes connectées, français inclus, 9 $/mois | N'agit pas sur les sites, n'achète rien |
| Perplexity (Comet, achat intégré) | Agent d'achat pour abonnés américains depuis novembre 2024 ([Modern Retail](https://www.modernretail.co/technology/why-the-ai-shopping-agent-wars-will-heat-up-in-2026/)) | Interface visuelle, pas de parcours vocal ni de garde-fous pour un utilisateur qui ne voit pas ; poursuivi par Amazon |
| Amazon (Buy for Me) | Achète sur des sites tiers sans quitter l'app Amazon ([Modern Retail](https://www.modernretail.co/technology/why-the-ai-shopping-agent-wars-will-heat-up-in-2026/)) | Fermé sur l'écosystème Amazon, bloque les agents extérieurs sur son propre site |
| OpenAI (achat dans ChatGPT) | Achat chez des partenaires (Target, Instacart, DoorDash) ([Modern Retail](https://www.modernretail.co/technology/why-the-ai-shopping-agent-wars-will-heat-up-in-2026/)) | Limité aux marchands partenaires ; une source secondaire dit que ce paiement intégré a été réduit en 2026 (non vérifié) |
| Google (achat dans AI Mode et Gemini) | Paiement intégré annoncé en 2026, d'abord aux États-Unis (sources secondaires, page officielle non consultée) | Marchands compatibles uniquement, pas pensé pour l'accessibilité |

**Ce que dit la recherche.** Une étude CHI 2026 a fait acheter 12 personnes aveugles coréennes avec un agent vocal piloté en coulisses ([résumé](https://a11ybob.com/writing/reviews/69e63e5f5570d11947cedf8f)). Résultats directement utiles pour nous : au plus 3 options annoncées à la fois, nom-prix-note d'abord, des confirmations formulées comme des affirmations, et une forte peur des erreurs de l'IA au moment du paiement. Le paiement réel avait été exclu de l'étude : c'est exactement le trou que Pilote comble.

**Contexte à citer au jury.** Visa et Mastercard construisent des moyens de paiement dédiés aux agents (Visa Intelligent Commerce, Mastercard Agent Pay) d'après plusieurs articles. Ce ne sont pas des concurrents mais l'infrastructure de demain, que Pilote pourra brancher plus tard.

**Risque principal.** Be My Eyes a la notoriété, un million d'utilisateurs et déjà un volet achat. Notre avance tient à l'action de bout en bout en Europe et en français, et à la sécurité du paiement.

## Notre solution

Pilote permet à une personne aveugle de dire « commande-moi une pizza margherita pour 20 h » et d'obtenir la commande, sur le vrai site du marchand, sans jamais voir l'écran ni dicter sa carte. Six choses le distinguent des concurrents ci-dessus.

1. **Il agit, il ne décrit pas.** L'agent de H Company navigue, remplit et va jusqu'au paiement, là où Be My Eyes et Envision s'arrêtent à la description.
2. **N'importe quel site, sans partenariat.** Les agents d'Amazon, OpenAI ou Google ne marchent qu'avec leurs marchands partenaires. Pilote travaille sur le site tel qu'il est, grâce au « computer use ».
3. **Une conversation pensée pour l'oreille.** Au plus 3 options annoncées à la fois, nom, prix et note d'abord, détails sur demande, confirmations sous forme d'affirmations (« J'ai mis dans le panier une margherita à 11,50 € »). Ce sont les recommandations de l'étude CHI 2026.
4. **Un paiement qu'on ne peut pas déclencher par erreur.** L'agent s'arrête toujours avant le bouton qui engage de l'argent. Il faut un « oui » oral, la validation d'un proche par SMS, puis un deuxième « oui » après relecture de la page. La carte est enregistrée à l'avance sur le compte marchand : personne ne la dicte ni ne la lit.
5. **Un agent qui « écoute » ce qu'il voit.** Une description orale des produits (couleur, aspect, avis résumés) grâce aux modèles de vision de Hugging Face, ce qu'aucun agent d'achat grand public ne fait pour un utilisateur qui ne voit pas.
6. **Une mémoire des sites.** Après chaque commande, Pilote garde une fiche du site (étapes, pièges, bandeaux cookies). La fois suivante, il va plus vite. Aucune donnée personnelle dans la fiche.

**Ce qu'on montre au jury.** Une commande complète à la voix sur un vrai site, la validation SMS d'un proche en direct, puis le paiement refusé par la banque grâce à la carte éphémère à 0 €. Le refus prouve que l'argent serait vraiment parti si la carte avait été approvisionnée.

**Modèle économique à pitcher.** Abonnement pour les particuliers, et licence pour les associations et les mutuelles qui accompagnent les personnes aveugles. Plus tard, branchement sur les paiements dédiés aux agents de Visa et Mastercard.

## Tester en réel avec des cartes éphémères

On peut tester sur de vrais sites à condition de choisir les sites avec soin et de laisser trois gestes à un humain : la création du compte, le CAPTCHA et la validation bancaire. Le reste du parcours est fait par l'agent.

**Les deux sites retenus : Uber Eats et SNCF Connect.**

- **Ce que disent leurs conditions d'utilisation.** Aucune des deux n'autorise expressément un agent IA, et toutes deux interdisent les robots dans certains cas :
  - [Uber](https://www.uber.com/legal/terms/fr), article 11 c : interdit de lancer un programme ou un script pour récupérer ou extraire des données. Article 7.3 : le compte est personnel, on ne peut pas autoriser un tiers à l'utiliser. Article 16 : Uber peut fermer le compte en cas de manquement.
  - [SNCF Connect](https://www.sncf-connect.com/popup/conditions-generales-de-vente-et-utilisation), article 17.1 : interdit le scraping et les robots qui extraient ou reproduisent des éléments du site, y compris les offres, sans accord écrit. Seul l'usage privé et non commercial d'une petite partie du site est autorisé.
- **Ce que ça veut dire pour le hackathon.** Quelques commandes isolées, lancées par le titulaire du compte, restent une zone grise et non une autorisation. Le risque réaliste : le compte bloqué ou la commande refusée par le site. On utilise donc des comptes de l'équipe dont la perte n'est pas grave, jamais un compte principal.
- **Ce que ça veut dire pour le pitch.** Ne pas dire que Pilote est autorisé sur ces sites. Dire que le produit commercial passera par des accords ou par les interfaces prévues pour les partenaires.
- **Limites d'usage :** une commande à la fois, déclenchée par une personne, aucune collecte de données en masse, 2 tentatives de paiement par site et par jour au maximum.
- **Points à vérifier à la main le jour 1 :**
  - Uber Eats : la connexion demande un code par SMS ou email, à faire par un humain dans le Chrome dédié. Vérifier que la session reste connectée, que la carte s'enregistre à 0 € et qu'une adresse de livraison est déjà renseignée.
  - SNCF Connect : vérifier si la carte peut être enregistrée sur le compte, si le cryptogramme est redemandé, et si une protection anti-robots ou un CAPTCHA apparaît quand l'agent navigue.
  - Sur les deux : faire une commande complète à la main avec la carte à 0 € pour voir à quelle étape le refus arrive.

**Mode de navigation H : « votre navigateur ».** L'agent pilote un Chrome dédié sur l'ordinateur de démo, avec son propre profil ([doc H](https://hub.hcompany.ai/agents-api/your-browser.md)). On s'y connecte à la main sur chaque site et on enregistre la carte dans le compte marchand. Ainsi l'agent ne voit ni mot de passe ni numéro de carte. Le coffre-fort de H ne gère pas les cartes bancaires : seulement identifiants, mots de passe, codes 2FA et clés API ([doc H](https://hub.hcompany.ai/agents-api/vaults/overview.md)).

**Pièges de la carte éphémère à 0 €.**

- Certains sites font une vérification de 0 ou 1 € quand on enregistre la carte. Si l'enregistrement échoue, mettre 1 € sur la carte le temps de l'enregistrer, puis la vider. À tester le jour 1.
- Des refus répétés peuvent faire bloquer le compte marchand pour suspicion de fraude. Limite proposée : 2 tentatives de paiement par site et par jour, et un compte de secours.
- Si le site redemande le cryptogramme pour une carte enregistrée, l'agent ne le tape jamais : il passe la main à un humain. Préférer les sites qui ne le redemandent pas.
- La validation bancaire forte (DSP2) se fait sur le téléphone du titulaire, jamais par l'agent.

**Règles pour l'agent.**

- Jamais de CAPTCHA résolu par l'agent : il met la session en pause et annonce qu'un humain doit intervenir.
- Jamais de création de compte ni de saisie de mot de passe par l'agent.
- Pas de boucles automatiques : une commande à la fois, déclenchée par une personne.
- Les règles juridiques du premier plan restent valables : annonce « Je suis Pilote, un assistant automatique », audio supprimé après transcription, aucune donnée de handicap enregistrée.

**Plan B.** L'équipe teste désormais sur Uber Eats et SNCF Connect, mais les deux faux sites (train et repas) restent en ligne, sans coût, comme repli si un site bloque l'agent ou le compte le jour de la démo. Enregistrer aussi une vidéo complète du parcours réel la veille.

## Architecture et contrat commun

Un seul dépôt GitHub, quatre briques indépendantes qui ne se parlent qu'à travers le contrat ci-dessous. Si chacun respecte le contrat, le merge final se fait sans conflit.

_(Schéma de l'architecture : voir le doc en ligne.)_

L'orchestrateur reçoit la voix, demande la compréhension à Hugging Face, pilote l'agent H, et attend la validation du proche avant d'autoriser le clic de paiement.

**Choix techniques (et pourquoi).**

- **Orchestrateur en Python (FastAPI)**, lancé sur l'ordinateur de démo. Le SDK Python de H se connecte tout seul au Chrome local, le SDK TypeScript demande une étape de plus ([doc H](https://hub.hcompany.ai/agents-api/your-browser.md)). Et une commande peut attendre plusieurs minutes un proche : un processus qui tourne en continu est plus sûr qu'une fonction serverless.
- **Interface et pages de validation en Next.js.** L'interface vocale tourne sur l'ordinateur de démo. Les pages Valider / Refuser envoyées par SMS sont déployées sur Vercel, car le proche doit les ouvrir depuis son téléphone.
- **Redis hébergé (Upstash, via Vercel)** pour partager l'état des validations et les fiches de sites entre Vercel et l'orchestrateur.
- **Hugging Face Inference Providers** pour la voix, le langage et la vision, avec un seul `HF_TOKEN` ([doc HF](https://huggingface.co/docs/inference-providers/index)).

**Arborescence du dépôt.**

```
pilote/
  contracts/            # schémas JSON partagés (membre 5, jour 1 matin)
  orchestrator/         # Python, FastAPI, machine à états (membre 5)
    agent_h/            # sessions H, consignes, fiches de sites (membre 1)
    ai/                 # voix, compréhension, résumés, vision (membre 2)
  web/                  # Next.js : interface vocale + pages de validation (membres 3 et 4)
  docs/                 # décisions, sites testés, résultats des tests
  .env.example
```

**Les objets échangés** (fichiers JSON Schema dans `contracts/`, noms de champs en anglais pour le code) :

| Objet | Champs | Produit par | Lu par |
| --- | --- | --- | --- |
| `Intent` | `site`, `item`, `constraints[]`, `date`, `budget_max_eur`, `missing[]` | ai (membre 2) | orchestrateur, agent H |
| `Option` | `id`, `title`, `price_eur`, `rating`, `details`, `url` | agent H (membre 1) | ai (résumé oral), interface |
| `OrderSummary` | `order_id`, `site`, `items[]`, `fees_eur`, `total_eur`, `delivery`, `refund_terms`, `hash` | agent H (membre 1) | validation, interface |
| `ApprovalRequest` | `order_id`, `summary`, `relatives[]`, `timeout_s` | orchestrateur | validation (membre 3) |
| `ApprovalStatus` | `order_id`, `state` (`pending`, `approved`, `denied`, `expired`), `by`, `at` | validation (membre 3) | orchestrateur |
| `SiteCard` | `domain`, `steps[]`, `pitfalls[]`, `avg_seconds`, `runs` | agent H (membre 1) | agent H |

**Machine à états d'une commande** (seul l'orchestrateur la fait avancer) : `listening` → `understanding` → `searching` → `proposing` → `cart` → `confirm_1` → `awaiting_relative` → `recheck` → `confirm_2` → `paying` → `done`. Sorties possibles à tout moment : `cancelled`, `human_needed` (CAPTCHA, cryptogramme, erreur).

**Messages WebSocket entre interface et orchestrateur** (`ws://localhost:8000/ws`) :

- Interface → orchestrateur : `{type:"audio", data}` (webm en base64), `{type:"text", text}` (mode texte de secours), `{type:"confirm", value}`, `{type:"cancel"}`.
- Orchestrateur → interface : `{type:"say", text, audio}`, `{type:"state", state}`, `{type:"options", options}`, `{type:"summary", summary}`, `{type:"error", message}`.

**API de validation (sur Vercel)**, protégée par un secret partagé côté orchestrateur :

- `POST /api/approvals` crée la demande et envoie le SMS au proche n° 1.
- `GET /api/approvals/{order_id}` renvoie l'`ApprovalStatus` (l'orchestrateur interroge toutes les 2 secondes).
- `/v/{token}` : page Valider / Refuser, lien signé, à usage unique, valable 5 minutes.

**L'arrêt avant paiement.** La documentation de H ne décrit pas de réglage « bloquer tel bouton » ([doc H](https://hub.hcompany.ai/agents-api/custom-tools.md)). On passe donc par un outil personnalisé : la consigne oblige l'agent à appeler `request_payment_approval(summary)` avant tout clic qui engage de l'argent. Notre fonction ne répond qu'après la triple vérification, avec `approved` ou `denied`. Un second outil, `need_human(reason)`, sert pour les CAPTCHA et le cryptogramme.

**Variables d'environnement** (dans `.env.example`, sans valeur) : `HAI_API_KEY` (nom utilisé dans la doc H, à confirmer), `HF_TOKEN`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `PILOTE_SHARED_SECRET`, `PUBLIC_VALIDATION_URL`.

## Ordre de travail

Les contrats sont figés le jour 1 à 11 h, et le parcours complet à la voix doit finir par un paiement refusé le jour 3 au soir. Le jour 4 ne sert qu'au second site, aux tests et à la démo.

| Membre | Jour 1 | Jour 2 | Jour 3 | Jour 4 |
| --- | --- | --- | --- | --- |
| 1 Agent H | Test de H, agent factice | Recherche, panier sur le site 1 | Arrêt avant paiement, mémoire des sites | Site 2, 5 essais par site |
| 2 IA HF | IA factice, Whisper testé | Intent, résumés, benchmark LLM | Vision produits, synthèse vocale | Réglages fins, slide benchmark |
| 3 Validation | Version factice, Redis branché | SMS, liens signés, page Valider | Cascade des proches, 6 scénarios testés | Plan B démo, journal |
| 4 Interface | Faux serveur WS, bouton parler | Sons, lecture, mode texte | Écran du jury, test VoiceOver | Finitions, test yeux fermés |
| 5 Intégration | Contrats à 11 h, sites et carte | Orchestrateur, intégration texte | Triple vérification, intégration voix | 20 tests, vidéo, pitch |
| **Jalon** | Contrats figés (11 h) | Parcours texte jusqu'au panier | **Parcours voix complet, paiement refusé** | Démo, plan B prêt |

Chaque jalon se vérifie en fin de journée, en équipe. S'il n'est pas atteint, le lendemain matin commence par lui, avant toute nouvelle fonctionnalité.

## Répartition : 5 membres, 5 parties

Chaque membre possède un dossier et n'écrit nulle part ailleurs. Chacun livre d'abord une version factice de sa brique (même interface, données inventées) pour que les autres puissent avancer sans l'attendre.

| Membre | Partie | Dossier | Version factice livrée | Vraie version prête |
| --- | --- | --- | --- | --- |
| 1 | Agent H : navigation, panier, arrêt avant paiement, mémoire des sites | `orchestrator/agent_h/` | J1 soir (`FakeShoppingAgent`) | J3 midi sur le site 1 |
| 2 | IA Hugging Face : voix, compréhension, résumés, description des produits | `orchestrator/ai/` | J1 soir (`FakeAI`) | J2 soir |
| 3 | Validation des proches : SMS, liens signés, pages Valider / Refuser | `web/app/api/`, `web/app/v/`, `web/lib/approvals/` | J1 soir (statut toujours « approuvé ») | J3 midi |
| 4 | Interface vocale accessible + écran spectateur pour le jury | `web/app/(pilote)/`, `web/components/` | J1 soir (faux serveur WebSocket) | J2 soir |
| 5 (toi) | Contrats, orchestrateur, intégration, sites réels, démo et pitch | `contracts/`, `orchestrator/` (hors sous-dossiers ci-dessus), `docs/` | Contrats J1 à 11 h | Intégration complète J3 soir |

Répartition proposée par défaut : à ajuster selon les compétences de chacun. Le membre 1 doit être à l'aise en Python, les membres 3 et 4 en TypeScript et React.

## Prompts pour chaque membre

Chaque membre colle dans son assistant de code (Claude Code ou autre) le contexte commun, puis son prompt. Les prompts sont écrits pour être suivis dans l'ordre et s'arrêter sur une définition claire de « fini ».

### Contexte commun (à coller en tête de chaque prompt)

```text
Tu travailles sur Pilote, un projet de hackathon d'une équipe de 5 personnes.
Pilote est un assistant vocal en français qui fait des achats en ligne à la place d'une personne aveugle, sur de vrais sites marchands. Il utilise l'agent "computer use" de H Company (navigation) et des modèles Hugging Face (voix, langage, vision).
Avant chaque paiement : un "oui" oral, la validation d'un proche par SMS, une relecture de la page, puis un deuxième "oui". La démo paie avec une carte virtuelle à 0 € : le paiement doit être refusé par la banque, ce qui prouve que le parcours marche.

Dépôt : monorepo pilote/
  contracts/              schémas JSON partagés + README des messages WebSocket
  orchestrator/           Python 3.12, FastAPI, machine à états
  orchestrator/agent_h/   agent H Company
  orchestrator/ai/        modèles Hugging Face
  web/                    Next.js : interface vocale + pages de validation (Vercel)
  docs/                   décisions, résultats de tests

Contrat : les fichiers de contracts/ font foi (Intent, Option, OrderSummary, ApprovalRequest, ApprovalStatus, SiteCard, messages WebSocket). Ne modifie jamais un contrat seul : ouvre une issue GitHub, le membre 5 tranche.

Règles absolues :
- N'écris que dans les dossiers de ta partie.
- Aucune clé dans le code : lis les variables d'environnement et ajoute leur nom, sans valeur, à .env.example.
- L'agent ne tape jamais de numéro de carte, de cryptogramme ni de mot de passe, ne résout jamais de CAPTCHA, ne crée jamais de compte, et ne clique jamais sur un bouton qui engage de l'argent sans approbation.
- Aucune donnée de santé ou de handicap stockée. L'audio est supprimé dès qu'il est transcrit.
- Si une API externe ne se comporte pas comme décrit ici, lis la documentation officielle au lieu de deviner (H : https://hub.hcompany.ai/llms.txt, Hugging Face : https://huggingface.co/docs/inference-providers) et note l'écart dans docs/decisions.md.
- Travaille sur ta branche, en petits commits, avec des tests à côté du code. Pose-moi une question dès qu'une décision n'est pas couverte par ce prompt.
```

### Membre 1 — Agent H

```text
Ta partie : orchestrator/agent_h/ (Python 3.12). Branche : feat/agent-h.
Objectif : à partir d'un Intent, trouver des options sur un vrai site, remplir le panier, aller jusqu'à la page de paiement et s'arrêter pour demander l'approbation.

Étapes, dans l'ordre :
1. Installe le SDK : pip install "hai-agents[cli,browser]". Écris smoke.py qui lance une session avec l'agent h/web-surfer-flash sur une tâche simple, puis la même tâche en mode "votre navigateur" (environnement host user_device, Chrome dédié sur le port 9222, profil ~/.hai/chrome-profile). Doc : https://hub.hcompany.ai/agents-api/your-browser.md
2. Livre tout de suite FakeShoppingAgent : même interface que ci-dessous, données inventées, délais réalistes. Les autres en dépendent dès le jour 1.
3. Écris la classe ShoppingAgent (async) :
   - start(intent: Intent, site_card: SiteCard | None) -> None : ouvre la session avec la consigne générique + la fiche du site.
   - search() -> list[Option] : 8 options maximum, sortie structurée (doc : https://hub.hcompany.ai/agents-api/structured-output.md).
   - refine(message: str) -> list[Option] : affiner sans tout relancer (envoi de message dans la session).
   - choose(option_id) puis checkout() -> OrderSummary : panier, puis page de paiement, sans cliquer sur le bouton final.
   - recheck() -> OrderSummary : relit la page de paiement et renvoie le récapitulatif actuel (son hash permet de détecter un prix qui a changé).
   - pay() -> "refused" | "accepted" | "unknown" : clique sur le bouton de paiement après approbation et lit le résultat affiché.
   - cancel() : annule la session.
4. Consigne générique en français, identique pour tous les sites : "Trouve ce que l'utilisateur demande, renvoie les options, et avant TOUT clic qui engage de l'argent (Payer, Commander, Acheter, Valider la commande), appelle l'outil request_payment_approval avec le récapitulatif et attends sa réponse. Si tu rencontres un CAPTCHA, un cryptogramme demandé ou une connexion nécessaire, appelle need_human et ne fais rien d'autre."
5. Déclare deux outils personnalisés (doc : https://hub.hcompany.ai/agents-api/custom-tools.md) :
   - request_payment_approval(summary) : appelle un callback async fourni par l'orchestrateur, qui ne répond qu'après la triple vérification ("approved" ou "denied").
   - need_human(reason) : appelle un callback de l'orchestrateur et met la session en pause.
   Les outils peuvent être appelés plusieurs fois pour la même action : rends-les idempotents (clé = order_id).
6. Hash du récapitulatif : articles + quantités + total, normalisés.
7. Mémoire des sites : après une commande menée jusqu'au paiement, écris une SiteCard dans Redis (clé site:{domaine}) : étapes suivies, pièges rencontrés, durée. Aucune donnée personnelle (ni nom, ni adresse, ni contenu de commande).
8. Mesure le temps et le nombre d'étapes de chaque commande, dans docs/results-agent.md.

Sites de test : les 2 sites réels choisis par l'équipe (voir docs/sites.md, rempli par le membre 5). Le compte est déjà connecté et la carte déjà enregistrée dans le Chrome dédié : tu n'as jamais à les saisir.

Fini quand : sur chacun des 2 sites, 5 commandes d'affilée partent d'un Intent, proposent des options, remplissent le panier et s'arrêtent sur request_payment_approval sans jamais cliquer sur le bouton final tout seul, et au moins 4 sur 5 réussissent.
```

### Membre 2 — IA Hugging Face

```text
Ta partie : orchestrator/ai/ (Python 3.12). Branche : feat/ai.
Objectif : tout ce qui touche à la voix, au langage et à la vision passe par Hugging Face, avec un seul HF_TOKEN (client : huggingface_hub.InferenceClient ; routeur compatible OpenAI pour le chat : https://router.huggingface.co/v1).

Étapes, dans l'ordre :
1. Livre tout de suite FakeAI : mêmes fonctions que ci-dessous, réponses inventées.
2. transcribe(audio: bytes) -> str : reconnaissance vocale française avec un modèle Whisper servi par Inference Providers (vérifie quel modèle et quel fournisseur sont disponibles avec "hf models ls --warm"). Supprime l'audio dès la transcription.
3. parse_intent(text, today, history) -> Intent : un modèle de langage ouvert, sortie JSON validée par pydantic contre contracts/. Envoie toujours la date du jour. S'il manque une information, remplis missing[] et propose la question à poser, sans deviner.
4. summarize_options(options) -> str : 3 options au maximum, nom, prix et note d'abord, moins de 20 secondes à l'oral (environ 50 mots). Termine en proposant les détails sur demande.
5. confirm_statement(summary: OrderSummary) -> str : confirmation sous forme d'affirmation ("J'ai mis dans le panier une margherita à 11,50 euros, total 14 euros livraison comprise"), avec la mention échangeable ou remboursable si le site l'indique.
6. describe_product(image, question) -> str : un modèle vision-langage décrit couleur, aspect, et résume les avis à partir d'une capture d'écran ou de l'image du produit.
7. speak(text) -> bytes | None : synthèse vocale française. Attention : la liste des tâches d'Inference Providers ne contient pas la synthèse vocale. Évalue, dans cet ordre, un Space Hugging Face appelé avec gradio_client, puis un Inference Endpoint dédié si le budget le permet. Si rien n'est assez rapide (plus de 2 secondes), renvoie None : l'interface utilisera la voix du navigateur. Note ton choix dans docs/decisions.md.
8. Benchmark : compare 2 ou 3 modèles de langage sur les 20 phrases de test (docs/test-phrases.md) : bonnes réponses, temps de réponse, coût. Tableau dans docs/benchmark-llm.md : il servira de slide pour le jury.

Fini quand : les 20 phrases donnent le bon Intent dans au moins 18 cas, chaque résumé dure moins de 20 secondes à l'oral, et transcribe + parse_intent répondent en moins de 3 secondes au total.
```

### Membre 3 — Validation des proches

```text
Ta partie : web/app/api/approvals/, web/app/v/, web/lib/approvals/ (Next.js, TypeScript, déployé sur Vercel). Branche : feat/validation.
Objectif : quand l'orchestrateur demande une validation, un proche reçoit un SMS, ouvre un lien, valide ou refuse ; sans réponse, on passe au proche suivant ; par défaut, on refuse.

Étapes, dans l'ordre :
1. Livre tout de suite une version factice : POST /api/approvals renvoie un statut "approved" après 5 secondes, sans SMS.
2. Stockage : Redis Upstash (intégration Vercel), clés approval:{order_id} et token:{token}.
3. POST /api/approvals (en-tête Authorization: Bearer PILOTE_SHARED_SECRET) : reçoit un ApprovalRequest, crée un jeton signé HMAC, à usage unique, valable 5 minutes, et envoie au proche n° 1 un SMS court : prénom de l'utilisateur, site, total, lien.
4. GET /api/approvals/{order_id} (même en-tête) : renvoie l'ApprovalStatus. Pas de minuteur en serverless : c'est cet appel, répété toutes les 2 secondes par l'orchestrateur, qui détecte qu'un délai est dépassé et envoie le SMS au proche suivant. Après le dernier proche : "expired".
5. Page /v/{token} : lisible au lecteur d'écran, deux gros boutons Valider et Refuser, le récapitulatif (site, articles, total), rien d'autre (pas d'historique). Un jeton déjà utilisé ou expiré affiche "Lien expiré" et ne change rien.
6. SMS : Twilio par défaut (variables TWILIO_*). En compte d'essai, seuls les numéros vérifiés reçoivent les SMS : enregistre ceux de l'équipe. Vérifie le coût d'un SMS vers la France et l'expéditeur affiché.
7. Plan B : page /demo/approvals (protégée par un code) qui liste les demandes en attente avec Valider / Refuser, si le SMS n'arrive pas pendant la démo.
8. Journal : order_id, heure, qui a décidé, conservé 30 jours, sans contenu audio.
9. Important : la protection de déploiement Vercel doit être désactivée pour ce projet, sinon les proches tombent sur une page de connexion Vercel.

Fini quand : les 6 scénarios passent (proche 1 valide, proche 1 refuse, cascade vers le proche 2, personne ne répond, lien réutilisé, lien expiré), testés avec de vrais téléphones.
```

### Membre 4 — Interface vocale accessible

```text
Ta partie : web/app/(pilote)/ et web/components/ (Next.js, TypeScript). Branche : feat/interface. L'interface tourne sur l'ordinateur de démo et parle à l'orchestrateur sur ws://localhost:8000/ws.
Objectif : une personne aveugle utilise Pilote de bout en bout sans jamais regarder l'écran ; le jury, lui, voit ce qui se passe.

Étapes, dans l'ordre :
1. Écris web/mock-ws.mjs : un faux serveur WebSocket qui rejoue un parcours complet (say, state, options, summary) selon contracts/README.md. Tu développes contre lui jusqu'à l'intégration.
2. Parler : un seul gros bouton et la barre d'espace maintenue pour parler (MediaRecorder, webm), envoyé en {type:"audio"}.
3. Écouter : joue l'audio des messages "say" ; si audio est vide, utilise speechSynthesis en fr-FR.
4. Sons courts pour chaque état : j'écoute, je réfléchis, j'attends votre proche, succès, erreur. L'utilisateur doit savoir où il en est sans voir.
5. Première phrase de chaque session : "Je suis Pilote, un assistant automatique."
6. Mode texte de secours : un champ de saisie qui envoie {type:"text"}.
7. Accessibilité : régions ARIA live, focus géré, tout au clavier, contraste suffisant, rien qui ne soit que visuel. Teste avec VoiceOver (Mac) les yeux fermés.
8. Écran spectateur pour le jury (à droite ou sur un second écran) : état de la commande, transcription, options, récapitulatif, et le lien vers la vue en direct de l'agent H (agent_view_url) quand l'orchestrateur l'envoie.
9. À tout moment, dire "annule" ou appuyer sur Échap envoie {type:"cancel"}.

Fini quand : 2 personnes de l'équipe font un parcours complet sur le faux serveur, les yeux fermés, sans aide, et l'écran spectateur est lisible depuis le fond d'une salle.
```

### Membre 5 — Contrats, orchestrateur, intégration (toi)

```text
Ta partie : contracts/, orchestrator/ (hors agent_h/ et ai/), docs/, la configuration du dépôt. Branche : feat/orchestrator ; les contrats passent par une PR à toi seul.
Objectif : que les 4 briques s'assemblent en un parcours complet, et que la démo soit prête.

Étapes, dans l'ordre :
1. Jour 1, avant 11 h : squelette du dépôt (arborescence, .env.example, .gitignore, CODEOWNERS, protection de la branche main), contracts/ avec les 6 schémas JSON et le README des messages WebSocket, tests d'intégration continue (lint + tests Python et TypeScript). Merge et préviens l'équipe : plus personne ne change un contrat sans toi.
2. Jour 1 : docs/sites.md. Choisis 2 sites réels avec l'équipe, lis leurs conditions d'utilisation, crée les comptes à la main dans le Chrome dédié, enregistre la carte éphémère, et teste un paiement refusé à la main. Note ce qui se passe (vérification à l'enregistrement, cryptogramme redemandé, CAPTCHA).
3. Orchestrateur FastAPI : route WebSocket /ws, machine à états (listening, understanding, searching, proposing, cart, confirm_1, awaiting_relative, recheck, confirm_2, paying, done, cancelled, human_needed). Branche les versions factices des 4 briques, puis les vraies une par une grâce à des variables USE_FAKE_AGENT, USE_FAKE_AI, USE_FAKE_APPROVALS.
4. Le callback request_payment_approval : premier "oui" oral (confirm_1), appel POST /api/approvals, attente du statut, recheck() de l'agent, comparaison du hash, deuxième "oui" (confirm_2), puis renvoie "approved" : l'agent clique, et pay() lit le résultat affiché. Le moindre écart de prix, refus, délai ou erreur donne "denied", annoncé à l'oral.
5. Annulation possible à tout moment, et un délai maximum par étape. Journal des étapes sans audio.
6. Jalons d'intégration : J2 soir, parcours complet en mode texte jusqu'au panier ; J3 soir, parcours complet à la voix avec SMS et paiement refusé sur le site 1.
7. Jour 4 : site 2, 20 tests complets, vidéo de secours, script de démo minuté, pitch.

Fini quand : 5 parcours complets à la voix d'affilée se terminent par un paiement refusé par la banque, sans qu'aucun humain touche le clavier en dehors des gestes prévus (validation du proche, validation bancaire).
```

## Règles GitHub

Le merge final se passe bien si les contrats sont figés tôt et si on fusionne un peu chaque jour, pas tout le dernier soir.

- **Un dépôt neuf** `pilote`, créé par le membre 5 le jour 1 au matin. Branche `main` protégée : pas de push direct, une relecture obligatoire.
- **Une branche par membre** : `feat/agent-h`, `feat/ai`, `feat/validation`, `feat/interface`, `feat/orchestrator`.
- **Fichier CODEOWNERS** : chaque dossier a son propriétaire, `contracts/` appartient au membre 5. GitHub demande automatiquement la bonne relecture.
- **Petites PR, fusionnées tous les jours à 18 h.** Les tests d'intégration continue doivent passer avant la fusion.
- **Les versions factices d'abord.** Tant qu'une brique réelle n'est pas prête, l'orchestrateur utilise sa version factice : personne n'attend personne.
- **Aucune clé dans le dépôt.** Vérifier avant chaque push ; activer la détection de secrets de GitHub.
- **Les décisions dans `docs/decisions.md`** : une ligne par décision (date, quoi, pourquoi). C'est ce que l'assistant de code de chacun relira.

## Questions ouvertes à trancher en équipe

Ce plan suppose un hackathon de 4 jours avec démo le jour 4, comme le premier plan. Les questions ci-dessous changent le plan si la réponse est différente.

- [ ] Durée exacte du hackathon et heure de la démo ?
- [ ] Uber Eats et SNCF Connect retenus : quels comptes de l'équipe sacrifie-t-on s'ils sont bloqués ?
- [ ] Quelle banque pour la carte virtuelle éphémère, et peut-on l'enregistrer chez le marchand à 0 € ?
- [ ] Les sites choisis redemandent-ils le cryptogramme pour une carte enregistrée ?
- [ ] Fournisseur de SMS (Twilio par défaut) et budget accepté ?
- [ ] Qui prend quelle partie, selon les compétences de chacun ?
- [ ] Quelle synthèse vocale française via Hugging Face, puisque Inference Providers ne propose pas cette tâche ?
- [ ] Nom exact de la variable de clé H (`HAI_API_KEY` dans la doc) et plan H : le plan gratuit permet 3 sessions simultanées et 60 millions de jetons par mois ([doc H](https://hub.hcompany.ai/agents-api/plans-and-limits.md)), a priori suffisant.
- [ ] Désactiver la protection de déploiement Vercel sur les 2 faux sites, sinon l'agent ne peut pas les ouvrir en plan B.
- [ ] Qui présente la démo, et qui joue le proche qui reçoit le SMS ?

## Sources

Pages consultées le 17 novembre 2026.

- [Documentation H, index](https://hub.hcompany.ai/llms.txt), [SDK](https://hub.hcompany.ai/computer-use-agents/sdks.md), [votre navigateur](https://hub.hcompany.ai/agents-api/your-browser.md), [approbations](https://hub.hcompany.ai/agents-api/sessions/tool-approvals.md), [outils personnalisés](https://hub.hcompany.ai/agents-api/custom-tools.md), [coffre-fort](https://hub.hcompany.ai/agents-api/vaults/overview.md), [suivre une session](https://hub.hcompany.ai/agents-api/observe-and-steer.md), [plans et limites](https://hub.hcompany.ai/agents-api/plans-and-limits.md)
- [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers/index), [liste des tâches](https://huggingface.co/docs/inference-providers/tasks/index)
- [Be My Eyes et InnoSearch](https://www.bemyeyes.com/?p=21193598), [Envision Ally](https://apps.apple.com/us/app/ally-accessible-ai-assistant/id6476980907), [Modern Retail sur les agents d'achat](https://www.modernretail.co/technology/why-the-ai-shopping-agent-wars-will-heat-up-in-2026/), [résumé de l'étude CHI 2026](https://a11ybob.com/writing/reviews/69e63e5f5570d11947cedf8f)
- Non consultées directement (résultats de recherche seulement) : les annonces de Google, Visa et Mastercard et la règle d'eBay sur les agents. À vérifier avant de les citer au jury.
