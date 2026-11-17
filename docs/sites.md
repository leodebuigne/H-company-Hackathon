# Sites de test

Les deux seuls sites sur lesquels l'agent a le droit d'agir. Ils sont fictifs : aucun vrai billet, aucun vrai repas, aucun vrai paiement. Pourquoi des faux sites : voir `decisions.md`.

Pas de compte à créer ni de carte à saisir : chaque site affiche une carte enregistrée fictive. L'agent n'a donc jamais à taper de numéro de carte, de cryptogramme ou de mot de passe.

## Site 1 : Rail Démo (train)

- Adresse : https://h-company-hackathon-rail-demo.vercel.app (`RAIL_DEMO_URL`)
- Domaine (clé `site:{domaine}`) : `h-company-hackathon-rail-demo.vercel.app`
- Code : `rail-demo/`

| Étape | Page | Ce que l'agent fait |
| --- | --- | --- |
| 1 | `index.html` | Fermer le bandeau cookies, saisir départ, arrivée, date, heure, rechercher |
| 2 | `resultats.html` | Lire jusqu'à 8 trains (horaires, durée, correspondance, prix, conditions), puis « Choisir ce train » |
| 3 | `recap.html` | Cocher « J'accepte les conditions de vente », continuer |
| 4 | `paiement.html` | Lire le récapitulatif. **S'arrêter avant « Payer » (`id="payer"`) et appeler `request_payment_approval`** |
| 5 | `validation.html` | Validation bancaire simulée : **un humain** clique « Refuser » ou « Confirmer le paiement » |
| 6 | `confirmation.html` | Réservation fictive avec référence |

Gares : Paris, Lille, Lyon, Marseille, Bordeaux, Nantes, Strasbourg, Rennes, Toulouse, Nice, Montpellier. Même recherche = mêmes trains.

Pièges : bandeau cookies à trois boutons qui se ressemblent ; deux boutons par train (« Voir le détail » et « Choisir ce train ») ; case des conditions de vente obligatoire.

| Scénario | Ajouter à l'URL | Effet attendu dans Pilote |
| --- | --- | --- |
| Normal | rien | parcours complet |
| Prix qui change | `?scenario=hausse` | +8 € si plus de 60 s entre récapitulatif et paiement : le hash change au `recheck()`, Pilote annule et le dit |
| Train complet | `?scenario=complet` | le train devient complet au paiement : Pilote annule et le dit |

## Site 2 : Miam Démo (livraison de repas)

- Adresse : https://h-company-hackathon-repas-demo.vercel.app (`REPAS_DEMO_URL`)
- Domaine : `h-company-hackathon-repas-demo.vercel.app`
- Code : `repas-demo/`

| Étape | Page | Ce que l'agent fait |
| --- | --- | --- |
| 1 | `index.html` | Fermer le bandeau cookies, chercher un restaurant ou un plat, filtrer par catégorie |
| 2 | `restaurant.html?r=<id>` | Fermer la pop-up promo, choisir les plats, remplir les options obligatoires, quantité |
| 3 | `panier.html` | Vérifier quantités, heure de livraison (dès que possible ou créneau), pourboire, minimum de commande |
| 4 | `paiement.html` | Lire le récapitulatif (articles, frais, total). **S'arrêter avant « Commander et payer » (`id="commander"`)** |
| 5 | `validation.html` | Validation bancaire simulée, faite par un humain |
| 6 | `confirmation.html` | Commande fictive avec référence |

Restaurants : Bella Notte (pizza), Smash Corner (burger), Sakura Box et Bangkok Street (asiatique), Verde Bowl (healthy), La Petite Douceur (desserts).

Pièges : bandeau cookies à trois boutons ; pop-up promo à la première ouverture d'un menu ; options obligatoires (sans choix, le plat n'est pas ajouté) ; minimum de commande par restaurant.

| Scénario | Ajouter à l'URL | Effet attendu dans Pilote |
| --- | --- | --- |
| Normal | rien | parcours complet |
| Frais qui changent | `?scenario=hausse` | livraison +2 € si plus de 60 s entre panier et paiement : hash différent, Pilote annule |
| Restaurant fermé | `?scenario=ferme` | fermeture au paiement : Pilote annule et le dit |

## Fin du parcours en démo

Après la triple vérification, l'agent clique sur le bouton de paiement. La page de validation bancaire s'affiche. Un membre de l'équipe clique **« Refuser »** (c'est le geste « validation bancaire » prévu). Le site affiche « Paiement refusé », `pay()` renvoie `refused` et Pilote dit que la banque a refusé le paiement. C'est la preuve que tout le parcours fonctionne sans dépenser d'argent.
