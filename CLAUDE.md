# Pilote : contexte pour les assistants de code

## Le projet

Hackathon Eugenia 2026, piste H Company. Pilote est un assistant vocal pour les personnes aveugles : la personne dit ce qu'elle veut (« un train pour Lille demain après 14 h »), l'agent H navigue sur le site, résume les options à l'oral, puis réserve.

Stack : H Company (API Agent, SDK `hai-agents-ts` de préférence), Hugging Face (reconnaissance vocale, modèle de langage pour comprendre et résumer, synthèse vocale), Vercel (Next.js, workflow de validation, crédit de 30 $).

## Adresses

- Faux site de train : https://h-company-hackathon-rail-demo.vercel.app (variable `RAIL_DEMO_URL` dans `.env.example`)
- Scénarios de test : ajouter `?scenario=hausse` (prix +8 € après 60 s entre récapitulatif et paiement) ou `?scenario=complet` à l'URL.
- Code du faux site : `rail-demo/`. Le bouton de paiement a l'id `payer` sur `paiement.html`.

## Parcours de validation (à respecter)

1. L'agent lit le récapitulatif tiré de la page du site ; l'utilisateur dit « oui ».
2. Identifiant de commande unique ; SMS au proche n° 1 avec un lien signé, à usage unique, valable 5 min (30 s en démo). Sans réponse : proche n° 2 puis n° 3.
3. Si un proche valide : l'agent relit la page ; si rien n'a changé, l'utilisateur redit « oui ».
4. Seulement alors, approuver l'action « Payer » dans H. La validation bancaire (`validation.html`) est faite par la personne.

Refus, absence de réponse ou erreur = aucun paiement.

## Règles à ne jamais casser

- Agir uniquement sur le faux site, jamais sur SNCF Connect ou Uber Eats.
- Ne jamais lire, dicter ni stocker un numéro de carte ou un cryptogramme. Aucun mot de passe en clair.
- Aucun champ sur le handicap ou la santé. Supprimer l'audio après transcription.
- L'agent annonce à l'oral qu'il est une IA (« Je suis Pilote, un assistant automatique »).
- Le proche peut seulement valider ou refuser, jamais acheter ni modifier.
- Aucune clé API dans le dépôt : tout passe par les variables d'environnement.
