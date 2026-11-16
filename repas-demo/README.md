# Miam Démo – faux site de livraison de repas pour Pilote

Site **fictif** de livraison de repas, deuxième site de test de l'agent H (le premier est `rail-demo/`, le site de train).
Restaurants, plats et prix inventés. Aucun vrai repas, aucun vrai paiement, aucune donnée envoyée à un serveur.

**Site en ligne : à déployer** (voir plus bas), puis noter l'adresse ici et dans `REPAS_DEMO_URL` de `.env.example`.

## Le parcours

1. `index.html` : liste de 6 restaurants, recherche (restaurant ou plat) et filtres par catégorie.
2. `restaurant.html?r=<id>` : menu. Certains plats ont des options obligatoires (taille, cuisson, base, épices) et facultatives (suppléments, menu), avec une quantité.
3. `panier.html` : quantités modifiables, heure de livraison (dès que possible ou créneau), pourboire, minimum de commande.
4. `paiement.html` : récapitulatif standard (articles, quantités, frais, total, livraison) et carte enregistrée fictive (Mastercard 5454). Bouton **Commander et payer** (`id="commander"`).
5. `validation.html` : simulation de la validation bancaire (authentification forte), faite par la personne, pas par l'agent.
6. `confirmation.html` : commande fictive avec référence.

Tout l'état passe dans l'URL. Le panier s'écrit `panier=platId~options~quantité|...`, par exemple `panier=bella-marg~l,fro~2|bella-tira~~1`.

## Ce qui le différencie du site de train

| | Rail Démo (train) | Miam Démo (repas) |
| --- | --- | --- |
| Choix | Un train dans une liste | Un restaurant, puis plusieurs plats |
| Options | Aucune | Obligatoires et facultatives, quantités |
| Montant | Prix du billet | Sous-total, livraison, service, pourboire |
| Temps | Date et heure de départ | Livraison dès que possible ou créneau |
| Bouton d'argent | Payer | Commander et payer |

C'est volontaire : le même agent, avec la même consigne générique, doit réussir sur les deux.

## Pièges volontaires pour l'agent

- Bandeau cookies bloquant (3 boutons).
- Pop-up promotionnelle à la première ouverture d'un menu (3 boutons).
- Options obligatoires : sans choix, le plat n'est pas ajouté et un message s'affiche.
- Minimum de commande par restaurant.

## Scénarios de test

Ajoutez `?scenario=...` à l'URL de départ (il est transmis à toutes les pages) :

| Scénario | URL de départ | Effet |
| --- | --- | --- |
| Normal | `/index.html` | Parcours classique |
| Frais qui changent | `/index.html?scenario=hausse` | Frais de livraison +2 € si plus de 60 s entre le panier et le paiement |
| Restaurant fermé | `/index.html?scenario=ferme` | Le restaurant ferme à l'étape du paiement |

## Déployer sur Vercel

Même méthode que le site de train : sur vercel.com/new, importez le dépôt `H-company-Hackathon`, branche `main`, **Root Directory `repas-demo`**, preset **Other**, aucun build, puis Deploy.
