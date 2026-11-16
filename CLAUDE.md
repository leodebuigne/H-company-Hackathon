# Pilote : contexte pour les assistants de code

## Le projet

Hackathon Eugenia 2026, piste H Company. Pilote est un assistant vocal, pensé d'abord pour les personnes aveugles : la personne dit ce qu'elle veut (« un train pour Lille demain après 14 h », « une pizza livrée avant 20 h »), l'agent H navigue sur le site, résume les options à l'oral, puis commande.

Objectif : fonctionner sur n'importe quel site marchand (train, livraison de repas, boutique en ligne) avec la même triple vérification. Pour le hackathon : 2 faux sites (train, puis repas), et le même code d'agent pour les deux.

Stack : H Company (API Agent, SDK `hai-agents-ts` de préférence), Hugging Face (reconnaissance vocale, modèle de langage pour comprendre et résumer, synthèse vocale), Vercel (Next.js, workflow de validation, crédit de 30 $).

## Adresses

- Faux site de train : https://h-company-hackathon-rail-demo.vercel.app (variable `RAIL_DEMO_URL` dans `.env.example`)
- Scénarios de test : ajouter `?scenario=hausse` (prix +8 € après 60 s entre récapitulatif et paiement) ou `?scenario=complet` à l'URL.
- Code du faux site de train : `rail-demo/`. Le bouton de paiement a l'id `payer` sur `paiement.html`.
- Faux site de repas Miam Démo : https://h-company-hackathon-repas-demo.vercel.app (variable `REPAS_DEMO_URL`), code dans `repas-demo/`. Bouton `commander` sur `paiement.html`. Scénarios `?scenario=hausse` (frais de livraison +2 € après 60 s) et `?scenario=ferme`.

## Agent générique et mémoire des sites

- Une seule consigne générique pour tous les sites, complétée par la demande et la fiche du site. Aucun code propre à un site.
- Toute action qui engage de l'argent (Payer, Commander, Acheter, Valider la commande) est soumise à approbation, sur tous les sites.
- Compréhension commune : chaque demande devient {site, objet, contraintes, date, budget}. Récapitulatif standard : articles, quantités, frais, total, date ou heure de livraison.
- Mémoire des sites : après chaque commande réussie, enregistrer une fiche par site (étapes suivies, boutons utiles, pièges, temps) et l'ajouter à la consigne à la visite suivante. Le modèle n'est pas réentraîné. Stockage simple sur Vercel (Blob ou clé-valeur).

## Parcours de validation (à respecter)

1. L'agent lit le récapitulatif tiré de la page du site ; l'utilisateur dit « oui ».
2. Identifiant de commande unique (site, articles, total) ; SMS au proche n° 1 avec un lien signé, à usage unique, valable 5 min (30 s en démo). Sans réponse : proche n° 2 puis n° 3. Délai réglable par type d'achat (plus court pour un repas).
3. Si un proche valide : l'agent relit la page ; si rien n'a changé, l'utilisateur redit « oui ».
4. Seulement alors, approuver l'action « Payer » dans H. La validation bancaire (`validation.html`) est faite par la personne.

Refus, absence de réponse ou erreur = aucun paiement.

## Règles à ne jamais casser

- Agir uniquement sur les faux sites, jamais sur SNCF Connect, Uber Eats ou Amazon.
- Ne jamais lire, dicter ni stocker un numéro de carte ou un cryptogramme. Aucun mot de passe en clair.
- Aucun champ sur le handicap ou la santé. Supprimer l'audio après transcription.
- La fiche d'un site ne contient aucune donnée personnelle (ni nom, ni adresse, ni contenu de commande).
- L'agent annonce à l'oral qu'il est une IA (« Je suis Pilote, un assistant automatique »).
- Le proche peut seulement valider ou refuser, jamais acheter ni modifier.
- Aucune clé API dans le dépôt : tout passe par les variables d'environnement.
