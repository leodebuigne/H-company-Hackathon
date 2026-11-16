# Rail Démo – faux site de train pour Pilote

Site **fictif** de réservation de trains, utilisé par l'agent H pendant le hackathon.
Aucun vrai billet, aucun vrai paiement, aucune donnée envoyée à un serveur.

## Les pages

1. `index.html` : recherche (gare de départ, arrivée, date, heure).
2. `resultats.html` : 8 trains maximum à partir de l'heure demandée (horaires, durée, correspondance, prix, conditions).
3. `recap.html` : récapitulatif + case « J'accepte les conditions de vente » obligatoire.
4. `paiement.html` : carte enregistrée fictive (Visa 4242) + bouton **Payer**.
5. `validation.html` : simulation de la validation bancaire (authentification forte). C'est la personne, pas l'agent, qui confirme.
6. `confirmation.html` : réservation fictive avec référence.

Les trains sont générés à partir de la recherche : la même recherche donne toujours les mêmes trains. Tout l'état passe dans l'URL.

Pièges volontaires pour montrer la précision de l'agent H : un bandeau cookies bloquant avec trois boutons qui se ressemblent, et deux boutons par train (« Voir le détail » et « Choisir ce train »).

## Scénarios de test

Ajoutez `?scenario=...` à l'URL de départ (il est transmis à toutes les pages) :

| Scénario | URL de départ | Effet |
| --- | --- | --- |
| Normal | `/index.html` | Parcours classique |
| Prix qui change | `/index.html?scenario=hausse` | +8 € si plus de 60 s passent entre le récapitulatif et le paiement |
| Train complet | `/index.html?scenario=complet` | Le train devient complet à l'étape du paiement |

## Déployer sur Vercel (aucun build nécessaire)

**Option A – depuis GitHub**
1. Créez un dépôt GitHub et mettez-y ces fichiers (à la racine).
2. Sur vercel.com : Add New → Project → importez le dépôt.
3. Framework Preset : **Other**. Laissez Build Command et Output Directory vides.
4. Deploy. Vous obtenez une adresse du type `https://rail-demo-xxx.vercel.app`.

**Option B – en ligne de commande**
```
npm i -g vercel
cd rail-demo
vercel        # puis « vercel --prod » pour la version finale
```

Pour tester en local sans rien installer : ouvrez `index.html` dans le navigateur.

## Brancher l'agent H

- Donnez à l'agent l'URL Vercel de `index.html`.
- Le clic sur **Payer** (`paiement.html`, lien `id="payer"`) doit être une action soumise à approbation côté agent H : l'agent s'arrête avant, le workflow Pilote attend les validations (utilisateur, proche, utilisateur), puis approuve.
- La page `validation.html` représente l'étape bancaire : en démo, un membre de l'équipe clique « Confirmer le paiement » à la place de l'utilisateur.
