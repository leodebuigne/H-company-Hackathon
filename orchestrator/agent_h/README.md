# orchestrator/agent_h — Agent H Company (membre 1)

L'agent qui navigue sur Uber Eats et SNCF Connect : recherche, panier, page de paiement, puis paiement. La vérification du paiement est celle de la banque : le titulaire valide dans son application bancaire (DSP2). Il n'y a pas de vérification supplémentaire côté Pilote.

**Tout est réel par défaut.** `make_agent()` renvoie `ShoppingAgent`, qui agit sur les vrais sites avec la vraie carte enregistrée dans le compte marchand : un paiement `accepted` est une vraie commande, débitée. `FakeShoppingAgent` ne sert qu'aux tests automatiques et au développement sans clé H, et seulement si on la demande (`USE_FAKE_AGENT=1`). Elle n'est jamais utilisée pour la démo.

## Installer et tester

Depuis la racine du dépôt :

```bash
python3 -m venv .venv && .venv/bin/pip install -r orchestrator/agent_h/requirements.txt
cd orchestrator/agent_h && ../../.venv/bin/python -m pytest -q   # tests sans réseau
```

Test de fumée avec la vraie clé H (navigateur cloud, puis Chrome local) :

```bash
export HAI_API_KEY=...   # ou : .venv/bin/holo login
.venv/bin/python -m orchestrator.agent_h.smoke
```

## Utiliser depuis l'orchestrateur

```python
from orchestrator.agent_h import make_agent, Intent

agent = make_agent()  # vrai agent H ; USE_FAKE_AGENT=1 pour la version factice
await agent.start(Intent(site="ubereats.com", item="une pizza margherita"))
options = await agent.search()  # 8 options max
await agent.choose(options[0].id)
summary = await agent.checkout()  # page de paiement, rien n'est cliqué
# ... l'utilisateur confirme qu'il veut payer ...
result = await agent.pay()  # clic, puis validation dans l'application bancaire
# "accepted" = vraie commande payée
```

| Méthode | Ce qu'elle fait |
| --- | --- |
| `start(intent, site_card=None)` | Ouvre la session H avec la consigne, la fiche du site (lue dans Redis si absente) et la demande |
| `search()` / `refine(texte)` | Renvoie au plus 8 `Option` |
| `choose(option_id)` puis `checkout()` | Panier puis page de paiement ; renvoie l'`OrderSummary` avec son `hash` |
| `recheck()` | Relit la page de paiement sans cliquer (facultatif) |
| `pay()` | Clique sur le bouton de paiement, attend jusqu'à 5 minutes la validation dans l'application bancaire, renvoie `"refused"`, `"accepted"` ou `"unknown"` ; lève `PaymentDenied` si le paiement n'a pas été tenté (plafond, total illisible) |
| `cancel()` | Annule la session |

Erreurs : `NeedsHuman` (CAPTCHA, cryptogramme, connexion), `PaymentDenied`, `AgentError`.

## Le garde-fou de paiement

La validation du paiement est faite par la banque, dans l'application du titulaire. Pilote garde seulement un garde-fou technique, pour que l'agent ne paie jamais de lui-même :

- l'agent doit appeler l'outil `request_payment_approval` avant tout clic qui engage de l'argent ;
- l'outil répond `denied` en dehors de l'étape `pay()` (recherche, panier, relecture) ;
- il répond aussi `denied` si le total dépasse `PILOTE_MAX_TOTAL_EUR` (999 € par défaut) ou s'il est illisible ;
- sinon il répond `approved`. Si l'orchestrateur fournit un `approval_callback`, c'est lui qui décide.

L'outil `need_human` sert pour les CAPTCHA, le cryptogramme et les pages de connexion. Il appelle `need_human_callback` ; sans callback, il répond `abort`. La validation dans l'application bancaire n'est pas un cas `need_human` : l'agent attend simplement qu'elle soit faite.

## Réglages

| Variable | Rôle |
| --- | --- |
| `HAI_API_KEY` | Clé H, lue par le SDK |
| `PILOTE_H_AGENT` | Nom d'un agent créé sur la plateforme H (ex. `pilote-shopper`). Vide : agent défini dans le code, consigne de `prompts.py` |
| `PILOTE_BROWSER_HOST` | `user_device` (Chrome dédié de l'ordinateur de démo, défaut) ou `cloud` |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Mémoire des sites ; sans elles, mémoire en RAM |
| `PILOTE_MAX_TOTAL_EUR` | Plafond d'un paiement réel, en euros (999 par défaut) |
| `USE_FAKE_AGENT` | `1` pour la version factice (tests, développement sans clé). Jamais pour la démo |
| `PILOTE_FAKE_SPEED` | Vitesse de `FakeShoppingAgent` (0 = instantané) |

Chaque commande ajoute une ligne à `docs/results-agent.md` (durée, étapes H, résultat du paiement).

## À vérifier avec la vraie clé

- `models.py` copie le contrat en attendant `contracts/` (membre 5) : à aligner dès sa publication.
- L'enchaînement des étapes dans une même session (message envoyé à une session au repos) n'a pas encore été testé contre H.
- Que l'agent attend bien la validation dans l'application bancaire au lieu de s'arrêter : c'est l'étape la plus fragile du parcours réel.
