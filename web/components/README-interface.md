# Interface vocale Pilote (membre 4)

## Lancer en local

```bash
cd web
npm install
npm run mock   # faux orchestrateur sur ws://localhost:8000/ws
npm run dev    # interface sur http://localhost:3000, écran jury sur /spectateur
```

Pour viser le vrai orchestrateur : variable `NEXT_PUBLIC_ORCHESTRATOR_WS` (par défaut `ws://localhost:8000/ws`).

## Raccourcis

| Touche | Effet |
| --- | --- |
| Barre d'espace maintenue | Parler (relâcher pour envoyer) |
| Entrée | Oui (pendant une confirmation) |
| N | Non (pendant une confirmation) |
| Échap | Annuler, à tout moment, même dans le champ texte |
| R | Répéter la dernière phrase de Pilote |

Le premier appui (bouton ou barre d'espace) lance la phrase d'accueil « Je suis Pilote, un assistant automatique » : le navigateur n'autorise aucun son avant un geste de l'utilisateur.

## Fichiers

- `protocol.ts` : types des messages WebSocket (copie locale du contrat).
- `usePilote.ts` : connexion WebSocket, reconnexion automatique, état partagé.
- `PiloteApp.tsx` : interface utilisateur (bouton pour parler, oui / non, mode texte, réglage de la voix).
- `SpectatorScreen.tsx` : écran du jury (étapes, conversation, options ou récapitulatif, lien vers l'agent H).
- `recorder.ts` : enregistrement du micro (webm sur Chrome, mp4 sur Safari).
- `speech.ts` : lecture des réponses (audio fourni, sinon voix française du navigateur).
- `earcons.ts` : sons d'état (j'écoute, je réfléchis, j'attends votre proche, question, succès, erreur).
- `../mock-ws.mjs` : faux orchestrateur qui rejoue une commande de train complète.

## Choix d'accessibilité

- **Une seule voix à la fois.** Réglage « Qui lit les réponses ? » : soit la voix de Pilote, soit le lecteur d'écran (région ARIA live). Jamais les deux, sinon VoiceOver parle par-dessus Pilote.
- **Couper la parole.** Appuyer pour parler arrête immédiatement la voix de Pilote, et le micro ne capte donc pas sa propre voix.
- Contraste jaune sur noir, cibles d'au moins 72 px, focus visible, animation coupée si l'utilisateur réduit les mouvements.

## Propositions de contrat à valider (membre 5)

Ces messages sont gérés par l'interface et envoyés par le faux serveur, mais ne sont pas encore dans `contracts/` :

| Message | Sens | Pourquoi |
| --- | --- | --- |
| `{type:"transcript", text}` | orchestrateur → interface | Afficher ce que l'utilisateur a dit (écran jury) |
| `{type:"agent_view", url}` | orchestrateur → interface | Lien vers la vue en direct de l'agent H |
| `{type:"human_needed", reason}` | orchestrateur → interface | Expliquer pourquoi un humain doit intervenir (CAPTCHA, cryptogramme) |
| champ `mime` dans `{type:"audio"}` | interface → orchestrateur | Safari enregistre en mp4, pas en webm |
| `{type:"hello", role}` | interface → orchestrateur | Distinguer l'interface de l'écran jury |

Côté orchestrateur, il faut aussi **diffuser les messages à toutes les connexions** (interface + écran jury) et renvoyer l'état courant à un écran qui se connecte en cours de route.

## Reste à tester sur l'ordinateur de démo

- Le micro réel (autorisation du navigateur, qualité dans une salle bruyante).
- La voix française du navigateur (laquelle est installée, est-elle naturelle).
- VoiceOver les yeux fermés, en particulier le conflit possible avec la barre d'espace.
