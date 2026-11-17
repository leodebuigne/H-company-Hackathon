# Décisions

Une entrée par décision : date, décision, raison, conséquence. Les écarts constatés avec une API externe (H, Hugging Face, Twilio, Upstash) se notent aussi ici, avec le lien vers la doc officielle lue.

## 2026-11-17 : faux sites uniquement (membre 5)

**Décision.** L'agent n'agit que sur Rail Démo et Miam Démo, jamais sur un vrai site marchand.
**Raison.** Le prompt d'équipe parlait de 2 vrais sites avec une carte virtuelle à 0 €. Le CLAUDE.md du dépôt l'interdit (« jamais sur SNCF Connect, Uber Eats ou Amazon »). Les faux sites évitent les conditions d'utilisation, les CAPTCHA, la création de comptes et rendent la démo reproductible.
**Conséquence.** Pas de carte éphémère. Après le clic sur Payer, les faux sites affichent une page de validation bancaire simulée (`validation.html`) avec « Refuser » et « Confirmer le paiement ». Un humain de l'équipe clique « Refuser » (geste prévu, comme la validation bancaire réelle). `pay()` lit le message affiché : « Paiement refusé » donne `refused`, la page de confirmation donne `accepted`, sinon `unknown`. L'agent ne clique jamais sur ces deux boutons.

## 2026-11-17 : Python 3.12 pour l'orchestrateur et l'agent H (membre 5)

**Décision.** Orchestrateur, agent H et IA en Python (SDK `hai-agents`). Le web reste en Next.js / TypeScript.
**Raison.** Le CLAUDE.md citait `hai-agents-ts` « de préférence », le prompt d'équipe prévoit Python. Un seul langage côté serveur évite de dupliquer les contrats.
**Conséquence.** CLAUDE.md mis à jour.

## 2026-11-17 : forme des contrats (membre 5)

- **Argent en centimes entiers** partout (`*_cents`), devise `EUR`. Évite les erreurs d'arrondi et rend le hash stable.
- **Tous les champs sont requis**, `null` si inconnu, aucun champ en plus. Un modèle de langage qui invente un champ est refusé à la validation.
- **`order_id` (UUID v4) est créé par l'agent au `checkout()`**, et `recheck()` le conserve. C'est la clé d'idempotence des outils H et la clé Redis de la validation.
- **Hash** : articles (nom et options normalisés), quantités et total. Implémentation unique : `orchestrator.contracts.summary_hash`.
- **URL** : `page_url` et `agent_view_url` sont des chaînes qui commencent par `http(s)://`, sans validation stricte. Les faux sites mettent des `|` non encodés dans leurs adresses.
- **Intent** couvre aussi les réponses courtes (« oui », « la deuxième », « annule ») avec `kind` et `choice_index`, pour que l'orchestrateur n'ait qu'un seul appel au modèle par phrase.
- **Messages WebSocket** : en plus de `say`, `state`, `options`, `summary`, ajout de `ready`, `transcript`, `intent`, `approval`, `agent_view`, `error` pour l'écran spectateur.

## 2026-11-17 : variables d'environnement (membre 5)

`SMS_API_KEY` et `SMS_SENDER` remplacés par `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`. Ajout de `PILOTE_SHARED_SECRET`, `USE_FAKE_*`, `APPROVALS_API_URL`, `PILOTE_RELATIVES`, `APPROVAL_TIMEOUT_SECONDS(_REPAS)`, `DEMO_APPROVALS_CODE`, `UPSTASH_REDIS_REST_*`, `NEXT_PUBLIC_ORCHESTRATOR_WS_URL`. `VALIDATION_LINK_SECRET` garde son nom.
Délai par proche : 30 s en démo (CLAUDE.md), réglable, 300 s maximum (prompt).

## 2026-11-17 : outillage (membre 5)

- npm 10 (livré avec Node 22) plante à l'installation (`Cannot read properties of null (reading 'edgesOut')`) avec `eslint-config-next`. Utiliser npm 11 : `npm install -g npm@11`. La CI le fait.
- `web/lib/contracts/` est généré depuis `contracts/` (`npm run contracts:gen`) et copie les schémas, pour que le build Vercel (Root Directory `web`) n'ait pas besoin des fichiers hors de `web/`. La CI échoue si la copie n'est pas à jour.

## À vérifier

- **Membre 1** : pendant que l'outil `request_payment_approval` attend sa réponse, l'orchestrateur appelle `recheck()` (relire la page). Vérifier dans la doc H (https://hub.hcompany.ai/agents-api/custom-tools.md) qu'on peut envoyer un message à une session dont un appel d'outil est en attente. Sinon, le recheck doit se faire autrement (par exemple dans le même outil, ou avec une seconde lecture après la réponse) : ouvrir une issue.
- **Membre 3** : noms exacts des variables injectées par l'intégration Upstash de Vercel, à reporter dans `.env.example`.
