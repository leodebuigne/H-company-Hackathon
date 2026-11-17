# Contrats Pilote

Les fichiers de ce dossier font foi. Si votre code et un contrat ne disent pas la même chose, c'est votre code qui a tort.

**Changer un contrat :** ouvrez une issue GitHub qui explique le besoin. Le membre 5 tranche et fait la modification dans une PR. Personne d'autre ne modifie `contracts/`, `orchestrator/contracts.py` ni `orchestrator/ports.py`.

## Contenu

| Fichier | Contrat | Qui produit | Qui consomme |
| --- | --- | --- | --- |
| `schemas/intent.schema.json` | `Intent` | IA (`parse_intent`) | orchestrateur, agent H |
| `schemas/option.schema.json` | `Option` | agent H (`search`, `refine`) | orchestrateur, IA, interface |
| `schemas/order-summary.schema.json` | `OrderSummary` | agent H (`checkout`, `recheck`) | orchestrateur, IA, validation, interface |
| `schemas/approval-request.schema.json` | `ApprovalRequest` | orchestrateur | `POST /api/approvals` |
| `schemas/approval-status.schema.json` | `ApprovalStatus` | `/api/approvals` | orchestrateur, interface |
| `schemas/site-card.schema.json` | `SiteCard` | agent H (Redis `site:{domaine}`) | agent H |
| `schemas/ws-message.schema.json` | messages WebSocket | interface et orchestrateur | les deux |
| `examples/valid/*.json` | exemples à copier | | tests |
| `examples/invalid/*.json` | exemples qui doivent être refusés | | tests |

Traductions :
- Python : `orchestrator/contracts.py` (modèles pydantic) et `orchestrator/ports.py` (interfaces des briques).
- TypeScript : `web/lib/contracts/types.ts`, généré par `npm run contracts:gen` dans `web/`. Ne pas l'éditer à la main.

Les tests (`orchestrator/tests/test_contracts.py` et `web/lib/contracts/contracts.test.ts`) vérifient en CI que les exemples valides passent, que les invalides sont refusés, et que Python et TypeScript suivent les schémas.

## Règles communes

- **Argent en centimes entiers** (`price_cents`, `total_cents`, `amount_cents`). Jamais de nombre à virgule. 14,50 € = `1450`. Devise toujours `"EUR"`.
- **Tous les champs sont présents.** Une valeur inconnue vaut `null` (ou `[]`, `{}`), elle n'est jamais omise. Aucun champ en plus n'est accepté.
- **Dates** en ISO 8601 avec fuseau (`2026-11-17T19:02:11+01:00`), jours en `AAAA-MM-JJ`, heures en `HH:MM`.
- **Aucune donnée de santé ou de handicap**, nulle part. Aucun numéro de carte, cryptogramme ni mot de passe.
- `SiteCard` ne contient aucune donnée personnelle ni contenu de commande.

## Hash du récapitulatif

Sert à détecter qu'un prix ou un panier a changé entre la validation du proche et le paiement. Calcul (implémentation de référence : `orchestrator.contracts.summary_hash`, à utiliser telle quelle) :

1. Normaliser chaque libellé : décomposition Unicode NFKD, suppression des accents, minuscules, tout caractère hors `a-z0-9` remplacé par une espace, espaces fusionnées, bords supprimés. « Crème  Brûlée ! » → `creme brulee`.
2. Pour chaque article : `[nom normalisé, liste triée des options normalisées, quantité]`.
3. Trier la liste des articles.
4. Sérialiser `{"items": [...], "total_cents": total}` en JSON compact (`separators=(",", ":")`, clés triées, ASCII).
5. SHA-256 en hexadécimal minuscule.

L'ordre des articles, la casse et les accents ne changent pas le hash. Une quantité, une option, un article ou un total différent le change.

## Messages WebSocket

Adresse : `ws://localhost:8000/ws`. Chaque message est un objet JSON avec un champ `type`. Le schéma complet est `schemas/ws-message.schema.json`, un exemple par type est dans `examples/valid/ws-*.json`.

### Interface → orchestrateur

| type | Champs | Quand |
| --- | --- | --- |
| `audio` | `data` (base64), `mime` | Bouton ou espace relâché. Un message = un enregistrement complet. |
| `text` | `text` | Mode texte de secours. Traité exactement comme une transcription. |
| `cancel` | | Échap ou « annule ». Accepté dans tous les états. |

### Orchestrateur → interface

| type | Champs | Quand |
| --- | --- | --- |
| `ready` | `session_id` | Juste après la connexion. |
| `state` | `state` | À chaque changement d'état. L'interface joue le son de l'état. |
| `say` | `text`, `audio` (base64 ou `null`), `mime` | Phrase à dire. Si `audio` est `null`, `speechSynthesis` en fr-FR. |
| `transcript` | `role` (`user` ou `pilote`), `text` | Pour l'écran spectateur. |
| `intent` | `intent` | Intent compris, pour l'écran spectateur. |
| `options` | `options` (8 max) | Après `search()` ou `refine()`. |
| `summary` | `summary` | Après `checkout()` et après `recheck()`. |
| `approval` | `status` | À chaque changement du statut de validation du proche. |
| `agent_view` | `agent_view_url` | Dès que la vue en direct de l'agent H est connue. |
| `error` | `code`, `message` | Erreur. Toujours suivie d'un `say` qui l'explique. |

### États

| État | Sens | Son conseillé |
| --- | --- | --- |
| `listening` | Pilote attend que la personne parle | j'écoute |
| `understanding` | transcription et compréhension | je réfléchis |
| `searching` | l'agent H cherche sur le site | je réfléchis |
| `proposing` | les options sont lues, Pilote attend un choix | j'écoute |
| `cart` | l'agent remplit le panier et va jusqu'au paiement | je réfléchis |
| `confirm_1` | récapitulatif lu, Pilote attend le premier « oui » | j'écoute |
| `awaiting_relative` | SMS envoyé, on attend le proche | j'attends votre proche |
| `recheck` | l'agent relit la page de paiement | je réfléchis |
| `confirm_2` | rien n'a changé, Pilote attend le deuxième « oui » | j'écoute |
| `paying` | l'agent clique sur le bouton de paiement | je réfléchis |
| `done` | parcours terminé (résultat annoncé par un `say`) | succès |
| `cancelled` | annulé par la personne, un refus ou une erreur | erreur |
| `human_needed` | CAPTCHA, cryptogramme ou connexion : un humain doit intervenir | erreur |

### Parcours type

```
→ (connexion)
← ready, state listening, say « Je suis Pilote, un assistant automatique. Que voulez-vous commander ? »
→ audio
← state understanding, transcript user, intent
← say « Vous partez de quelle gare ? », state listening        (si intent.missing n'est pas vide)
→ audio
← state searching, agent_view, options, say (résumé), state proposing
→ audio « la deuxième »
← state cart, summary, say (affirmation du récapitulatif), state confirm_1
→ audio « oui »
← state awaiting_relative, approval (pending) ... approval (approved)
← state recheck, summary, state confirm_2, say « Léa a validé. Rien n'a changé. Je paie ? »
→ audio « oui »
← state paying, say « La banque a refusé le paiement. »  (ou accepté), state done
```

À tout moment : `→ cancel` donne `← state cancelled` et un `say`, puis `state listening` pour une nouvelle demande.

## Interfaces Python des briques

Dans `orchestrator/ports.py` :
- `ShoppingAgent` (membre 1) : `start`, `search`, `refine`, `choose`, `checkout`, `recheck`, `pay`, `cancel`, propriété `agent_view_url`. Construit avec deux callbacks : `request_payment_approval(summary) -> "approved" | "denied"` et `need_human(reason)`.
- `AI` (membre 2) : `transcribe`, `parse_intent`, `summarize_options`, `confirm_statement`, `describe_product`, `speak`. Toutes asynchrones.
- `Approvals` : client de l'API de validation (membre 3), écrit par le membre 5.
