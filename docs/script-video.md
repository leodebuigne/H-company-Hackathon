# Topil : script de la vidéo de démo (5 minutes)

> Brouillon du 19 novembre 2026 pour le checkpoint 3 (vendredi avant 11 h). Les durées de la démo viennent
> des mesures du 19 novembre ; l'étape d'achat n'a pas été rechronométrée depuis le lien direct SNCF.

## Le déroulé en un coup d'œil

| Temps | Durée | À l'écran | Qui parle |
|---|---|---|---|
| 0:00 | 10 s | Diapositive 1, couverture | Narrateur |
| 0:10 | 30 s | Diapositive 2, le problème | Narrateur |
| 0:40 | 25 s | Diapositive 3, la solution | Narrateur |
| 1:05 | 2 min 40 | Démo : l'app Topil et le Chrome côte à côte | Utilisateur et Topil |
| 3:45 | 30 s | Diapositive 5, comment ça marche | Narrateur |
| 4:15 | 20 s | Diapositive 6, les garde-fous | Narrateur |
| 4:35 | 15 s | Diapositive 7, les mesures | Narrateur |
| 4:50 | 10 s | Diapositive 8, la suite | Narrateur |

Total : 5 min 00. La diapositive 4 (« Démo en direct ») sert de carton d'ouverture à la démo, 3 secondes.

## Le texte, mot pour mot

### 0:00 — Couverture (10 s)

> « Voici Topil. Un assistant vocal qui fait les démarches en ligne à la place d'une personne aveugle. »

### 0:10 — Le problème (30 s)

> « Acheter un billet de train en ligne, quand on ne voit pas l'écran, c'est un parcours d'obstacles. Une
> dizaine d'écrans, des bandeaux publicitaires, des boutons sans nom. Pendant nos essais, une seule
> recherche sur SNCF Connect demandait douze à dix-sept clics. Un lecteur d'écran lit tout, dans l'ordre,
> sans dire ce qui compte. Alors qu'une phrase devrait suffire. »

> « En France, 1,7 million de personnes sont déficientes visuelles, dont 207 000 aveugles ou malvoyantes
> profondes. » (DREES, enquête de 2005.)

### 0:40 — La solution (25 s)

> « Avec Topil, on parle, et il fait la démarche. Vous demandez : une phrase. Topil cherche sur le vrai
> site, il dit ce qu'il fait, et il lit trois options. Vous décidez : il redit le billet et le prix,
> attend votre oui, puis achète. Regardez. »

### 1:05 — La démo (2 min 40 après montage)

Écran partagé en deux : à gauche l'app Topil (http://localhost:3000), à droite la fenêtre Chrome où
l'agent travaille. On entend la vraie voix de l'utilisateur et la voix de Topil. Pas de narrateur
pendant la démo, sauf les deux cartons indiqués.

| Étape | Ce qui se passe | Durée réelle | Dans la vidéo |
|---|---|---|---|
| 1 | L'utilisateur dit : « Bonjour Topil. Un train de Paris pour Nantes demain matin. » | 5 s | 5 s |
| 2 | Topil redit la demande ; à droite, la page des résultats SNCF s'ouvre toute seule | 8 s | 8 s |
| 3 | L'agent lit la page ; Topil commente (« Je parcours les résultats ») | 25 s | 10 s, accéléré, carton « accéléré × 3 » |
| 4 | Topil lit les trois options, avec les heures et les prix | 17 s | 17 s |
| 5 | L'utilisateur : « Donne-moi les détails de la deuxième. » Topil répond | 12 s | 12 s |
| 6 | L'utilisateur : « Je prends la première. » | 3 s | 3 s |
| 7 | Topil : « J'achète bien … ? » L'utilisateur : « Oui. » | 8 s | 8 s |
| 8 | L'agent choisit le tarif, passe les étapes, arrive au paiement | 60 à 90 s | 25 s, accéléré, carton « accéléré × 3 » |
| 9 | Topil annonce le résultat : « C'est acheté : … » | 8 s | 8 s |
| 10 | Bonus : « À quelle heure ferme la tour Eiffel ce soir ? », réponse de Topil | 30 s | 20 s, attente coupée |

Total réel : environ 3 min à 3 min 30. Total monté : environ 2 min, plus 40 s de marge pour respirer entre
les étapes. Si la marge manque, retirer l'étape 10.

**Décision de l'équipe (19 novembre) : la vidéo montre un achat réel.** L'étape 8 achète donc un vrai
billet sur le compte de démo :

- Choisir, à l'étape 6, une option à **0 €** (billet gratuit du compte). Ne jamais prendre une option
  payante pendant la prise : la carte enregistrée serait débitée.
- Si aucune des trois options n'est à 0 €, dire « annule » et refaire la recherche avec une autre heure ou
  un autre jour.
- Une seule prise avec achat. Les essais à blanc se font en répondant « Non » à l'étape 7.
- Annuler le billet sur le compte SNCF juste après l'enregistrement, et vérifier qu'il n'en reste pas
  d'autres (deux billets ont déjà été achetés pendant les essais du 18 novembre).

### 3:45 — Comment ça marche (30 s)

> « Sous le capot, quatre briques. Whisper transforme la voix en texte. Llama comprend la demande : le
> trajet, le jour, l'heure. L'agent Holo de H Company clique et lit dans un vrai Chrome, sur le compte de
> la personne. Et une voix française de Kyutai répond, directement sur l'ordinateur, sans réseau. Whisper,
> Llama et Kyutai sont des modèles Hugging Face. Un orchestrateur enchaîne le tout. »

### 4:15 — Les garde-fous (20 s)

> « Un agent qui achète doit savoir s'arrêter. Topil demande toujours un oui, même pour un billet
> gratuit. Si le total dépasse le prix annoncé, le paiement est refusé avant le clic. Il ne tape jamais de
> mot de passe ni de cryptogramme. Et il dit toujours qu'il est un assistant automatique. »

### 4:35 — Les mesures (15 s)

> « Sur les vrais sites : trente-cinq secondes de la phrase aux trois options. Trente secondes pour
> répondre à une question. La première version demandait quatre à sept minutes. »

### 4:50 — La suite (10 s)

> « La suite : des essais avec des personnes aveugles, et d'autres démarches. Topil : Internet, à portée
> de voix. »

## Avant d'enregistrer

1. Lancer `python -m orchestrator.check` : tout doit être vert, compte SNCF connecté compris.
2. Vérifier que `PILOTE_VOICE=jerem` est dans `.env` et que la voix sort bien à l'accueil.
3. Ouvrir **un seul** onglet sur http://localhost:3000, sinon deux voix se superposent.
4. Régler la vitesse de la voix à 1,2× dans les réglages.
5. Placer l'app à gauche et le Chrome de l'agent à droite, à la même hauteur.
6. Couper les notifications du Mac et fermer les autres applications (8 Go de mémoire).
7. Faire un essai complet à blanc, en répondant « Non » à la question d'achat.
8. Choisir une date de train qui propose un billet à 0 € : la vidéo montre un achat réel.

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
