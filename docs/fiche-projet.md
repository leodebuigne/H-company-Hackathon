# Topil : fiche projet

> Topil, c'est « pilote » en verlan. Le dépôt, les fichiers et les réglages (`PILOTE_…`) gardent l'ancien nom.

> Fiche du 19 novembre 2026, pour le checkpoint 3 (vendredi 20 novembre avant 11 h). Seul le lien de
> la vidéo de démo reste à ajouter, entre crochets.

**Internet, à portée de voix.** Topil est un assistant vocal en français qui fait les démarches en
ligne à la place d'une personne aveugle ou malvoyante : on lui parle, il agit sur les vrais sites, il
dit ce qu'il fait, et il n'achète jamais sans accord.

- **Équipe 3 :** Antonin Fonteneau, Léo Debuigne, Victor Smiernow, Benjamin Chabanis, Rubens Le Scao
- **Dépôt :** https://github.com/leodebuigne/H-company-Hackathon (branche `main`)
- **Prototype :** il tourne sur l'ordinateur de démo (voir « Comment tester ») ; [lien vers la vidéo de démo]
- **Pitch deck :** https://claude.ai/artifact/ATsZ6Zf7pMjkcq15bpcaLP (sources dans [`docs/pitch-deck/`](pitch-deck/README.md))

## Le problème

Acheter un billet de train en ligne sans voir l'écran reste un parcours d'obstacles : une dizaine
d'écrans, des bandeaux publicitaires, des menus qui s'ouvrent, des boutons sans nom. Un lecteur d'écran
lit tout dans l'ordre, sans dire ce qui compte. Pendant nos essais, une seule recherche de train sur
SNCF Connect demandait 12 à 17 clics.

L'Europe compte plus de 30 millions de personnes aveugles ou malvoyantes (estimation de l'Union
européenne des aveugles, pour l'Europe géographique). Depuis le 28 juin 2025, la
directive européenne 2019/882 impose l'accessibilité au e-commerce, au transport et à la banque.

## La solution

Une phrase suffit : « Un train de Paris pour Nantes demain matin. »

1. **Vous demandez.** S'il manque le jour ou la ville, Topil pose une seule question.
2. **Topil cherche.** Il ouvre le site, commente ce qu'il fait et lit trois options, avec les heures et
   les prix.
3. **Vous décidez.** « La première. » Topil redit le billet et le prix, attend votre oui, achète, puis
   annonce le résultat.

Topil sait faire : les billets de train (SNCF Connect), les repas (Uber Eats), les réservations de
restaurant (TheFork), et répondre à une question en cherchant sur le web.

## La stack

| Brique | Rôle | Technologie |
|---|---|---|
| Écouter | La voix devient du texte | Whisper large-v3-turbo, via Hugging Face |
| Comprendre | La phrase devient une demande (trajet, jour, heure) | Llama 3.3 70B, via Hugging Face |
| Agir | Clique et lit sur les vrais sites | Agent Holo de H Company, dans un vrai Chrome |
| Voir | Lit une capture quand l'agent est bloqué | Qwen3-VL, via Hugging Face |
| Répondre | Dit la réponse à voix haute | Kyutai Pocket TTS (voix « Jerem »), sur l'ordinateur ; Kokoro en ligne si le paquet voix n'est pas installé |
| Orchestrer | Enchaîne les étapes et applique les garde-fous | Python 3.12, FastAPI, machine à états |
| Interface | Micro, conversation, écran du jury | Next.js, reliée par WebSocket |

## L'architecture

```
 voix ──► Whisper ──► Llama 3.3 ──► Orchestrateur ──► Agent Holo (H Company) ──► vrai site
                                         │   ▲                 dans un vrai Chrome
                                         ▼   │
 haut-parleur ◄── Kyutai (voix) ◄── phrases à dire, commentaire en direct
```

- `contracts/` : schémas JSON partagés et messages WebSocket (font foi).
- `orchestrator/` : la machine à états (`session.py`), l'agent H (`agent_h/`), les modèles (`ai/`).
- `web/` : l'interface vocale et l'écran du jury (`/spectateur`).
- `docs/decisions.md` : chaque choix technique, avec sa mesure.

Deux idées qui font la vitesse :

- **Topil ouvre lui-même la page des résultats** pendant qu'il redit la demande (lien direct SNCF) ;
  l'agent n'a plus qu'à lire.
- **Mémoire des sites** : ce que l'agent apprend d'un site (pièges, boutons utiles) sert à la commande
  suivante, même quand la précédente a échoué.

## Les garde-fous

- **Toujours un oui avant d'acheter**, même pour un billet gratuit.
- **Prix plafonné** : si le total affiché dépasse le prix annoncé, le paiement est refusé avant le clic.
- **Rien de secret** : l'agent ne tape ni mot de passe ni cryptogramme, et ne résout aucun CAPTCHA.
- **Jamais de faux semblant** : Topil annonce qu'il est un assistant automatique, et dit toujours si
  l'achat a eu lieu ou non.

## Ce que nous avons mesuré

Mesures du 19 novembre 2026, sur les vrais sites, sur un Mac M1, sans achat.

| Parcours | Durée |
|---|---|
| Train : de la phrase aux trois options (SNCF Connect) | 34 à 37 s |
| Question avec recherche sur le web | 30 s |
| Repas (Uber Eats), avec la mémoire du site | 73 s |
| Réservation de restaurant (TheFork) | 85 s |
| Dire une phrase courte (voix locale) | 0,5 s |

La première version demandait 4 à 7 minutes pour une commande.

## Comment tester

Il faut Python 3.12, Node avec npm 11, Google Chrome, une clé H Company (`HAI_API_KEY`) et une clé
Hugging Face (`HF_TOKEN`).

```bash
git clone https://github.com/leodebuigne/H-company-Hackathon.git && cd H-company-Hackathon
python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev,agent,ai,voix]"
cp .env.example .env        # puis renseigner HAI_API_KEY et HF_TOKEN
(cd web && npm install)
```

**Essai sans clé ni vrai site** (tout est simulé) : dans `.env`, mettre `USE_FAKE_AGENT=1` et
`USE_FAKE_AI=1`.

**Essai réel** : dans `.env`, mettre `USE_FAKE_AGENT=0`, `USE_FAKE_AI=0`, `PILOTE_DIRECT_BUY=1` et
`PILOTE_VOICE=jerem`. Lancer une fois Topil, puis se connecter à la main au compte SNCF dans la fenêtre
Chrome qu'il ouvre (la connexion est gardée ensuite).

```bash
python -m orchestrator            # dans un premier terminal
(cd web && npm run dev)           # dans un second terminal
python -m orchestrator.check      # vérifie tout avant une démo, sans rien acheter
```

Ouvrir http://localhost:3000 dans un seul onglet, appuyer sur Espace, puis dire par exemple :

- « À quelle heure ferme la tour Eiffel ce soir ? » (aucun achat)
- « Un train de Paris pour Nantes demain matin », puis « les détails de la deuxième », puis « non » à la
  question d'achat.

Attention : avec un vrai compte, répondre « oui » à « J'achète bien … ? » achète réellement le billet.
En cas de blocage du site pendant une démo, `PILOTE_PLAN_B=1` fait passer train et repas par les faux
sites de l'équipe.

Vérifier le code : `ruff check . && ruff format --check . && pytest -q`, puis dans `web/` :
`npm run contracts:check && npm run lint && npm run typecheck && npm test`.

## Limites connues

- La voix locale demande une installation lourde (`.[voix]`, qui installe torch). Sans elle, Topil garde
  la voix en ligne, qui a eu des pannes le 19 novembre.
- Le vrai micro et le mot de réveil « Bonjour Topil » ont été peu testés dans la dernière tournée.
- Topil n'a pas encore été essayé par des personnes aveugles.
