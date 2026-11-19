# Topil : script de la vidéo de démo (5 minutes)

> Checkpoint 3, vendredi 20 novembre avant 11 h. Aligné sur le pitch deck de 11 diapositives. Les durées
> de la démo viennent des mesures du 19 novembre ; l'étape d'achat n'a pas été rechronométrée depuis.

## Le déroulé en un coup d'œil

| Temps | Durée | Diapositive | Qui parle |
|---|---|---|---|
| 0:00 | 8 s | 1. Couverture | Narrateur |
| 0:08 | 25 s | 2. Le problème | Narrateur |
| 0:33 | 22 s | 3. La solution | Narrateur |
| 0:55 | 15 s | 4. Face aux autres | Narrateur |
| 1:10 | 2 min 20 | 5. Démo : carton de 3 s, puis l'app et le Chrome côte à côte | Utilisateur et Topil |
| 3:30 | 20 s | 6. Business model | Narrateur |
| 3:50 | 18 s | 7. Go-to-market | Narrateur |
| 4:08 | 20 s | 8. Architecture technique | Narrateur |
| 4:28 | 15 s | 9. Limites et feuille de route | Narrateur |
| 4:43 | 10 s | 10. Coût de run | Narrateur |
| 4:53 | 7 s | 11. Équipe et lien du code | Narrateur |

Total : 5 min 00. Le texte hors démo fait environ 2 min 40 : il faut le dire sans traîner, ou raccourcir
les diapositives 6 à 10 si une prise déborde.

## Le texte, mot pour mot

### 0:00 — 1. Couverture (8 s)

> « Voici Topil. Un assistant vocal qui fait les démarches en ligne à la place d'une personne aveugle. »

### 0:08 — 2. Le problème (25 s)

> « En France, 1,7 million de personnes sont déficientes visuelles, dont 207 000 aveugles ou malvoyantes
> profondes. Pour elles, acheter un billet de train en ligne reste un parcours d'obstacles : une dizaine
> d'écrans, des bandeaux publicitaires, des boutons sans nom. Nous avons compté douze à dix-sept clics
> pour une seule recherche. Et depuis juin 2025, la loi impose l'accessibilité au e-commerce et au
> transport. »

Source du chiffre : DREES, enquête de 2005.

### 0:33 — 3. La solution (22 s)

> « Avec Topil, vous parlez, et il fait la démarche, sur le vrai site. Vous demandez en une phrase. Topil
> cherche, dit ce qu'il fait, et lit trois options au plus. Vous décidez : il redit l'achat et le prix,
> attend votre oui, puis achète. Jamais sans accord. Il faut un agent qui voit l'écran : ces sites n'ont
> pas d'API ouverte. »

### 0:55 — 4. Face aux autres (15 s)

> « Aujourd'hui, les outils d'accessibilité décrivent l'écran mais n'agissent pas. Les agents d'achat
> agissent, mais pour des gens qui voient, et chez leurs marchands partenaires. Nous n'en avons trouvé
> aucun qui fasse les trois : décrire, agir et acheter, à la voix, en français. »

### 1:10 — 5. La démo (2 min 20 après montage)

Carton de 3 secondes sur la diapositive 5, puis écran partagé en deux : à gauche l'app Topil
(http://localhost:3000), à droite la fenêtre Chrome où l'agent travaille. On entend la vraie voix de
l'utilisateur et la voix de Topil. Pas de narrateur pendant la démo, sauf les deux cartons indiqués.

| Étape | Ce qui se passe | Durée réelle | Dans la vidéo |
|---|---|---|---|
| 1 | L'utilisateur dit : « Bonjour Topil. Un train de Paris pour Nantes demain matin. » | 5 s | 5 s |
| 2 | Topil redit la demande ; à droite, la page des résultats SNCF s'ouvre toute seule | 8 s | 8 s |
| 3 | La page est lue ; Topil commente (« Je parcours les résultats ») | 25 s | 10 s, accéléré, carton « accéléré × 3 » |
| 4 | Topil lit les trois options, avec les heures et les prix | 17 s | 17 s |
| 5 | L'utilisateur : « Donne-moi les détails de la deuxième. » Topil répond | 12 s | 12 s |
| 6 | L'utilisateur : « Je prends la première. » | 3 s | 3 s |
| 7 | Topil : « J'achète bien … ? » L'utilisateur : « Oui. » | 8 s | 8 s |
| 8 | L'agent choisit le tarif, passe les étapes, arrive au paiement | 60 à 90 s | 25 s, accéléré, carton « accéléré × 3 » |
| 9 | Topil annonce le résultat : « C'est acheté : … » | 8 s | 8 s |
| 10 | Bonus : « À quelle heure ferme la tour Eiffel ce soir ? », réponse de Topil | 30 s | 20 s, attente coupée |

Total réel : environ 3 min à 3 min 30. Total monté : environ 2 min, plus 20 s de marge. Si la marge
manque, retirer l'étape 10 : la démo tient alors en 1 min 40.

**Décision de l'équipe (19 novembre) : la vidéo montre un achat réel.** L'étape 8 achète donc un vrai
billet sur le compte de démo :

- Choisir, à l'étape 6, une option à **0 €** (billet gratuit du compte). Ne jamais prendre une option
  payante pendant la prise : la carte enregistrée serait débitée.
- Si aucune des trois options n'est à 0 €, dire « annule » et refaire la recherche avec une autre heure ou
  un autre jour.
- Une seule prise avec achat. Les essais à blanc se font en répondant « Non » à l'étape 7.
- Annuler le billet sur le compte SNCF juste après l'enregistrement, et vérifier qu'il n'en reste pas
  d'autres (deux billets ont déjà été achetés pendant les essais du 18 novembre).

### 3:30 — 6. Business model (20 s)

> « Qui paie ? D'abord la personne : un abonnement à 9,90 euros par mois, après cinq démarches offertes.
> Ensuite les associations et les mutuelles, qui équipent leurs adhérents avec une licence. Et plus tard,
> Topil se branchera sur les paiements que Visa et Mastercard préparent pour les agents. »

Les prix sont des hypothèses, et le prix de la licence n'est pas fixé : ne pas l'improviser à l'oral.

### 3:50 — 7. Go-to-market (18 s)

> « Pour démarrer : vingt testeurs aveugles, sur un seul parcours, le billet de train. Ensuite, les
> associations, qui équipent et forment déjà ce public. Puis les secteurs soumis à l'obligation
> d'accessibilité : transport, e-commerce, banque. »

Les associations nommées sur la diapositive sont des cibles, pas des partenaires : ne pas dire « avec ».

### 4:08 — 8. Architecture technique (20 s)

> « Sous le capot, quatre briques. Whisper écoute. Llama comprend la demande. L'agent Holo de H Company
> clique, remplit et achète dans un vrai Chrome, sur le compte de la personne. Et une voix française
> répond. Trois de ces modèles viennent de Hugging Face. Un orchestrateur enchaîne le tout et tient les
> garde-fous. »

### 4:28 — 9. Limites et feuille de route (15 s)

> « Ce qui ne marche pas encore : Topil tourne sur un seul ordinateur, et il n'a pas été essayé par des
> personnes aveugles. C'est la suite : vingt utilisateurs dans un mois, dix sites dans trois mois, une
> application mobile dans six. »

### 4:43 — 10. Coût de run (10 s)

> « Une recherche coûte trois centimes de dollar à faire tourner, une commande complète environ dix.
> L'hébergement n'est pas encore compté. »

Le trois centimes est mesuré ; le dix centimes est une estimation.

### 4:53 — 11. Équipe et lien du code (7 s)

> « Topil : Internet, à portée de voix. Le code est sur GitHub. Merci. »

## Avant d'enregistrer

1. Lancer `python -m orchestrator.check` : tout doit être vert, compte SNCF connecté compris.
2. Vérifier que `PILOTE_VOICE=jerem` est dans `.env` et que la voix sort bien à l'accueil.
3. Ouvrir **un seul** onglet sur http://localhost:3000, sinon deux voix se superposent.
4. Régler la vitesse de la voix à 1,2× dans les réglages.
5. Placer l'app à gauche et le Chrome de l'agent à droite, à la même hauteur.
6. Couper les notifications du Mac et fermer les autres applications (8 Go de mémoire).
7. Essayer « Bonjour Topil » au vrai micro. S'il n'est pas reconnu, appuyer sur Espace pour parler.
8. Faire un essai complet à blanc, en répondant « Non » à la question d'achat.
9. Choisir une date de train qui propose un billet à 0 € : la vidéo montre un achat réel.

## Si ça se passe mal pendant la prise

- **Topil comprend mal la phrase** : dire « annule », attendre « Que puis-je faire d'autre », recommencer.
- **L'agent tourne en rond ou le site bloque** : couper, mettre `PILOTE_PLAN_B=1` dans `.env`, relancer
  l'orchestrateur. La démo passe par le faux site de train de l'équipe (recherche mesurée à 40 s). Le dire
  à l'écran par un carton : « site de démonstration ».
- **La voix ne sort pas** : Topil reprend seul la voix en ligne, puis celle du navigateur. Refaire la
  prise plutôt que garder un changement de voix au milieu.
- **Deux voix en même temps** : un deuxième onglet est ouvert. Le fermer.

## Après l'enregistrement

- Annuler le billet acheté sur le compte de démo, et vérifier qu'il n'en reste pas d'autres.
- Vérifier la durée finale : 5 minutes au plus.
- Ajouter le lien de la vidéo dans `docs/fiche-projet.md`.
