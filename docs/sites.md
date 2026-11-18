# Sites de test

Choix de l'équipe : **Uber Eats** (repas) et **SNCF Connect** (train), avec une carte virtuelle éphémère à 0 €. Les faux sites restent le plan B. Analyse complète des conditions d'utilisation : `docs/plan-pilote.md`, section « Tester en réel avec des cartes éphémères ».

## Règles d'usage (à respecter par tout le monde)

- Comptes de l'équipe dont la perte n'est pas grave, jamais un compte principal. Un compte de secours par site.
- Création du compte, connexion (code SMS ou email), CAPTCHA et validation bancaire : **toujours faits par un humain**, dans le Chrome dédié (profil `~/.hai/chrome-profile`, port 9222).
- Une commande à la fois, déclenchée par une personne. Aucune collecte de données en masse.
- **2 tentatives de paiement par site et par jour au maximum**, pour ne pas faire bloquer le compte pour suspicion de fraude. Noter chaque tentative dans le journal ci-dessous.
- Au pitch : ne jamais dire que Pilote est autorisé sur ces sites. Le produit commercial passera par des accords ou les interfaces partenaires.

## Site 1 : SNCF Connect (train)

- Adresse : https://www.sncf-connect.com
- Domaine (clé Redis `site:{domaine}`) : `www.sncf-connect.com`
- Conditions d'utilisation : article 17.1, scraping et robots interdits sans accord écrit. Zone grise pour quelques commandes isolées du titulaire.

Vérifications à faire à la main le jour 1 (remplir avec ce qui s'est réellement passé) :

| Point | Résultat | Date, qui |
| --- | --- | --- |
| Compte créé et connecté dans le Chrome dédié, session qui reste ouverte | | |
| Carte à 0 € enregistrée sur le compte (vérification à 0 ou 1 € ?) | | |
| Cryptogramme redemandé au paiement avec la carte enregistrée ? | | |
| CAPTCHA ou protection anti-robots quand l'agent navigue ? | | |
| Commande complète à la main : étape et message du refus bancaire | | |
| Libellé exact du bouton qui engage l'argent | | |

## Site 2 : Uber Eats (repas)

- Adresse : https://www.ubereats.com/fr
- Domaine : `www.ubereats.com`
- Conditions d'utilisation : article 11 c (pas de script pour extraire des données), 7.3 (compte personnel), 16 (fermeture possible du compte).

| Point | Résultat | Date, qui |
| --- | --- | --- |
| Connexion par code SMS ou email faite par un humain, session qui reste ouverte | | |
| Adresse de livraison déjà renseignée | | |
| Carte à 0 € enregistrée sur le compte (vérification à 0 ou 1 € ?) | | |
| Cryptogramme redemandé au paiement ? | | |
| CAPTCHA ou protection anti-robots quand l'agent navigue ? | | |
| Commande complète à la main : étape et message du refus bancaire | | |
| Libellé exact du bouton qui engage l'argent | | |

Si l'enregistrement de la carte échoue à 0 € : mettre 1 € le temps de l'enregistrer, puis la vider. Si un site redemande le cryptogramme, l'agent appelle `need_human` et ne le tape jamais.

## Journal des tentatives de paiement

| Date | Site | Qui | Résultat (refusé, accepté, autre) | Remarque |
| --- | --- | --- | --- | --- |
| | | | | |

## Plan B : faux sites

À utiliser si un vrai site bloque l'agent ou le compte le jour de la démo. Rien n'est dépensé, aucune carte n'est nécessaire.

| Site | Adresse | Bouton d'argent | Scénarios (`?scenario=`) |
| --- | --- | --- | --- |
| Rail Démo (train) | https://h-company-hackathon-rail-demo.vercel.app (`RAIL_DEMO_URL`) | « Payer » (`id="payer"`) | `hausse` : +8 € après 60 s, `complet` : train complet au paiement |
| Miam Démo (repas) | https://h-company-hackathon-repas-demo.vercel.app (`REPAS_DEMO_URL`) | « Commander et payer » (`id="commander"`) | `hausse` : livraison +2 € après 60 s, `ferme` : restaurant fermé au paiement |

Le scénario `hausse` sert aussi à montrer au jury que Pilote annule quand le prix change entre la première confirmation et le paiement (le hash du récapitulatif change au `recheck()`).

Après le clic sur le bouton d'argent, ces sites affichent une validation bancaire simulée avec « Refuser » et « Confirmer le paiement » : un membre de l'équipe clique « Refuser », jamais l'agent.

Leur code a été retiré de `main` le 17/11. Il reste dans l'historique : `git show 7cc62bb:rail-demo/README.md`. À vérifier avant la démo : que les deux adresses répondent encore.
