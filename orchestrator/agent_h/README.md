# orchestrator/agent_h — Agent H Company (membre 1)

L'agent qui navigue sur Uber Eats et SNCF Connect : recherche, panier, page de paiement, puis paiement. Il parle les contrats communs (`orchestrator/contracts.py`) et respecte l'interface `ShoppingAgent` de `orchestrator/ports.py` : l'orchestrateur le construit avec `make_agent_factory()`. La validation bancaire (DSP2) reste faite par le titulaire dans son application.

**Tout est réel par défaut.** `make_agent()` renvoie `ShoppingAgent`, qui agit sur les vrais sites avec la carte enregistrée dans le compte marchand : un paiement `accepted` est une vraie commande, débitée. `FakeShoppingAgent` ne sert qu'aux tests automatiques et au développement sans clé H, et seulement si on la demande (`USE_FAKE_AGENT=1`). Elle n'est jamais utilisée pour la démo.

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
from orchestrator.agent_h import make_agent_factory

make_agent = make_agent_factory()  # vrai agent H ; USE_FAKE_AGENT=1 pour la version factice
agent = make_agent(approval_callback, need_human_callback)  # AgentFactory de ports.py

await agent.start(intent)  # orchestrator.contracts.Intent ; le site se déduit de intent.category
options = await agent.search()  # list[contracts.Option], 8 au maximum
await agent.choose(options[0].id)
summary = await agent.checkout()  # contracts.OrderSummary ; rien n'est cliqué ; crée l'order_id (UUID)
# ... pay() déclenche approval_callback(summary) : triple vérification de l'orchestrateur ...
result = await agent.pay()  # "refused", "accepted" ou "unknown"
```

L'agent H lit les pages en euros (`models.py`, plus fiable pour un modèle) ; le code convertit vers les contrats : centimes entiers, `rank`, `order_id`, `read_at` et le hash officiel `orchestrator.contracts.summary_hash`. Une option sans prix lisible est écartée, un total ou un prix de ligne illisible fait lever `AgentError` : on ne devine jamais un montant. La catégorie d'achat donne le site (`train` : SNCF Connect, `repas` : Uber Eats) ; le plan B se règle avec `PILOTE_SITE_TRAIN` et `PILOTE_SITE_REPAS`.

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

L'agent ne paie jamais de lui-même. Il doit appeler l'outil `request_payment_approval` avant tout clic qui engage de l'argent, et cet outil répond `denied` dans tous ces cas :

- hors de l'étape `pay()` (recherche, panier, relecture) ;
- total au-dessus de `PILOTE_MAX_TOTAL_EUR` (999 € par défaut) ou récapitulatif illisible ;
- l'`approval_callback` de l'orchestrateur répond autre chose que `approved`, lève une erreur ou dépasse son délai ;
- **aucun `approval_callback` n'est fourni**, sauf choix explicite (`auto_approve=True` ou `PILOTE_AUTO_APPROVE=1`, réservé aux essais réels en solo).

Quand le garde-fou refuse pendant `pay()`, l'agent lève `PaymentDenied` (rien n'a été cliqué), pas `NeedsHuman`. Le prix lu est converti puis hashé : si le prix change entre deux appels, la décision est reprise depuis le début.

L'outil `need_human` sert pour les CAPTCHA, le cryptogramme et les pages de connexion. Il appelle `need_human_callback` (qui rend la main quand l'humain a fini, comme dans `ports.py`) ; sans callback ou en cas d'erreur, il répond `abort`. La validation dans l'application bancaire n'est pas un cas `need_human` : l'agent attend qu'elle soit faite.

## Réglages

| Variable | Rôle |
| --- | --- |
| `HAI_API_KEY` | Clé H, lue par le SDK |
| `PILOTE_H_AGENT` | Nom d'un agent créé sur la plateforme H (ex. `pilote-shopper`). Vide : agent défini dans le code, consigne de `prompts.py` |
| `PILOTE_BROWSER_HOST` | `user_device` (Chrome dédié de l'ordinateur de démo, défaut) ou `cloud` |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Mémoire des sites ; sans elles, mémoire en RAM |
| `PILOTE_MAX_TOTAL_EUR` | Plafond d'un paiement réel, en euros (999 par défaut) |
| `PILOTE_AUTO_APPROVE` | `1` : payer sans `approval_callback` (essais réels en solo). Absent : refus |
| `PILOTE_SITE_TRAIN`, `PILOTE_SITE_REPAS` | Site visé par catégorie, pour le plan B (adresses des faux sites) |
| `USE_FAKE_AGENT` | `1` pour la version factice (tests, développement sans clé). Jamais pour la démo |
| `PILOTE_FAKE_SPEED` | Vitesse de `FakeShoppingAgent` (0 = instantané) |

Chaque commande ajoute une ligne à `docs/results-agent.md` (durée, étapes H, résultat du paiement).

## À vérifier avec la vraie clé

- L'enchaînement des étapes dans une même session (message envoyé à une session au repos) n'a pas encore été testé contre H.
- Que l'agent attend bien la validation dans l'application bancaire au lieu de s'arrêter : c'est l'étape la plus fragile du parcours réel.
