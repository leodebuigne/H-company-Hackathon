# Phrases de test

20 phrases pour vérifier `parse_intent` et comparer les modèles de langage (membre 2, `docs/benchmark-llm.md`). Même contenu en JSON pour automatiser : `docs/test-phrases.json`.

Objectif : au moins 18 bonnes réponses sur 20.

## Règles du test

- **Date du jour envoyée au modèle : mercredi 18 novembre 2026** (`today = 2026-11-18`). Demain = jeudi 19, vendredi = 20.
- `history` vide, sauf phrases 14 à 19 : l'historique contient la phrase 1 (avec la gare de départ Paris) et la réponse de Pilote qui propose 3 trains.
- Informations indispensables (sinon elles vont dans `missing`) : train → `details.origin`, `details.destination`, `when.date` ; repas → `object` ; type d'achat inconnu → `category` et `object`. L'heure n'est jamais indispensable.
- Une réponse est **bonne** si la sortie passe la validation du schéma `Intent` **et** si tous les champs listés ci-dessous sont exacts. Les champs non listés sont libres.
- « contient » : comparaison sans majuscules ni accents, sur un morceau de mot (ex. `object` contient « margherita »).
- `missing` listé `[]` : doit être vide. `missing` avec des valeurs : doit contenir exactement ces chemins (ordre libre).
- Conventions de temps attendues du modèle : « matin » = avant 12:00, « après-midi » = après 12:00, « ce soir » = après 18:00 aujourd'hui, « midi » = 12:00, « avant 20 h » pour un repas = livraison avant 20:00 aujourd'hui, « le plus vite possible » = `asap: true`.
- Argent en centimes : 60 euros = 6000.

## Phrases

| # | Phrase | Attendu |
| --- | --- | --- |
| 1 | Je voudrais un train pour Lille demain après 14 h | `kind` = `"new_request"` ; `category` = `"train"` ; `when.date` = `"2026-11-19"` ; `when.after` = `"14:00"` ; `details.destination` = `"Lille"` ; `missing` = `["details.origin"]` |
| 2 | Un aller Paris Lyon vendredi matin, pas plus de 60 euros | `kind` = `"new_request"` ; `category` = `"train"` ; `when.date` = `"2026-11-20"` ; `when.before` = `"12:00"` ; `budget_cents` = `6000` ; `details.origin` = `"Paris"` ; `details.destination` = `"Lyon"` ; `missing` = `[]` |
| 3 | Deux billets de Bordeaux à Toulouse le 24 novembre à partir de 18 h | `kind` = `"new_request"` ; `category` = `"train"` ; `quantity` = `2` ; `when.date` = `"2026-11-24"` ; `when.after` = `"18:00"` ; `details.origin` = `"Bordeaux"` ; `details.destination` = `"Toulouse"` ; `missing` = `[]` |
| 4 | Je dois aller à Marseille | `kind` = `"new_request"` ; `category` = `"train"` ; `details.destination` = `"Marseille"` ; `missing` = `["details.origin", "when.date"]` |
| 5 | Un train direct Paris Nantes ce soir | `kind` = `"new_request"` ; `category` = `"train"` ; `when.date` = `"2026-11-18"` ; `when.after` = `"18:00"` ; `details.origin` = `"Paris"` ; `details.destination` = `"Nantes"` ; `constraints` contient « direct » ; `missing` = `[]` |
| 6 | Paris Strasbourg demain en première classe, avec un billet échangeable | `kind` = `"new_request"` ; `category` = `"train"` ; `when.date` = `"2026-11-19"` ; `details.origin` = `"Paris"` ; `details.destination` = `"Strasbourg"` ; `details.class` contient « premi » ; `constraints` contient « changeable » ; `missing` = `[]` |
| 7 | euh un train euh pour Lyon demain matin depuis Paris | `kind` = `"new_request"` ; `category` = `"train"` ; `when.date` = `"2026-11-19"` ; `when.before` = `"12:00"` ; `details.origin` = `"Paris"` ; `details.destination` = `"Lyon"` ; `missing` = `[]` |
| 8 | Une pizza margherita grande taille livrée avant 20 h | `kind` = `"new_request"` ; `category` = `"repas"` ; `object` contient « margherita » ; `details.size` contient « grand » ; `when.date` = `"2026-11-18"` ; `when.before` = `"20:00"` ; `missing` = `[]` |
| 9 | Commande-moi des sushis le plus vite possible | `kind` = `"new_request"` ; `category` = `"repas"` ; `object` contient « sushi » ; `when.asap` = `true` ; `missing` = `[]` |
| 10 | Deux smash classic et des frites chez Smash Corner | `kind` = `"new_request"` ; `category` = `"repas"` ; `object` contient « smash classic » ; `details.restaurant` = `"Smash Corner"` ; `missing` = `[]` |
| 11 | J'ai faim, je veux un truc thaï pour moins de 15 euros | `kind` = `"new_request"` ; `category` = `"repas"` ; `details.cuisine` contient « tha » ; `budget_cents` = `1500` ; `missing` = `[]` |
| 12 | Un poké saumon pour 19 h 30 | `kind` = `"new_request"` ; `category` = `"repas"` ; `object` contient « pok » ; `when.date` = `"2026-11-18"` ; `when.before` = `"19:30"` ; `missing` = `[]` |
| 13 | Je veux acheter un truc | `kind` = `"new_request"` ; `category` = `null` ; `object` = `null` ; `missing` contient « object » ; `question` non nulle |
| 14 | La deuxième | `kind` = `"choose"` ; `choice_index` = `2` |
| 15 | Donne-moi plus de détails sur la troisième | `kind` = `"details"` ; `choice_index` = `3` |
| 16 | Plutôt un train plus tôt, avant midi | `kind` = `"refine"` ; `when.before` = `"12:00"` |
| 17 | Oui, c'est bon | `kind` = `"confirm"` |
| 18 | Non, pas celle-là | `kind` = `"deny"` |
| 19 | Annule tout | `kind` = `"cancel"` |
| 20 | Quel temps fera-t-il demain ? | `kind` = `"question"` (recherche sans achat) |
