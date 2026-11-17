# Interface vocale Pilote (membre 4)

## Lancer en local

```bash
cd web
npm install
npm run mock   # faux orchestrateur sur ws://localhost:8000/ws, messages vérifiés contre le contrat
npm run dev    # interface sur http://localhost:3000, écran jury sur /spectateur
```

Pour viser le vrai orchestrateur, arrêter `npm run mock` : l'adresse est la même. Une autre adresse se règle avec `NEXT_PUBLIC_ORCHESTRATOR_WS`.

## Raccourcis

| Touche | Effet |
| --- | --- |
| Barre d'espace maintenue | Parler (relâcher pour envoyer) |
| Entrée | Oui (en `confirm_1` et `confirm_2`) |
| N | Non (en `confirm_1` et `confirm_2`) |
| Échap | Annuler, à tout moment, même dans le champ texte |
| R | Répéter la dernière phrase de Pilote |

Le navigateur bloque tout son avant un geste de l'utilisateur. La phrase d'accueil envoyée par l'orchestrateur à la connexion est donc gardée et dite au premier appui, précédée de « Je suis Pilote, un assistant automatique » si elle ne le contient pas.

## Fichiers

- `protocol.ts` : réexporte les types de `@/lib/contracts` (aucun champ ajouté) et les libellés d'état.
- `usePilote.ts` : connexion WebSocket, reconnexion automatique, état partagé (`reduce`, testé dans `usePilote.test.ts`).
- `PiloteApp.tsx` : interface utilisateur (bouton pour parler, oui / non, mode texte, réglage de la voix).
- `SpectatorScreen.tsx` : écran du jury (étapes, intention comprise, conversation, options ou récapitulatif, validation du proche, lien vers l'agent H).
- `recorder.ts` : enregistrement du micro (webm/opus sur Chrome, mp4 sur Safari), envoyé avec son `mime`.
- `speech.ts` : lecture des `say` (audio fourni avec son `mime`, sinon voix française du navigateur).
- `earcons.ts` : sons d'état (j'écoute, je réfléchis, j'attends votre proche, question, succès, erreur).
- `../mock-ws.mjs` : faux orchestrateur qui rejoue une commande de train ; il ignore et signale tout message hors contrat.

## Choix d'accessibilité

- **Une seule voix à la fois.** Réglage « Qui lit les réponses ? » : soit la voix de Pilote, soit le lecteur d'écran (région ARIA live). Jamais les deux, sinon VoiceOver parle par-dessus Pilote.
- **Couper la parole.** Appuyer pour parler arrête immédiatement la voix de Pilote, et le micro ne capte donc pas sa propre voix.
- L'historique de l'écran jury vient uniquement des messages `transcript` (rôles `user` et `pilote`), pour ne pas doubler les phrases.
- Contraste jaune sur noir, cibles d'au moins 72 px, focus visible, animation coupée si l'utilisateur réduit les mouvements.

## Points à remonter au membre 5

- `web/lib/contracts/index.ts` : `ClientMessage` n'inclut pas `ClientConfirm`, donc `ServerMessage` (`Exclude<WsMessage, ClientMessage>`) contient `confirm` à tort. L'interface définit ses propres unions dans `protocol.ts` en attendant.
- Aucun message ne donne la raison d'un `human_needed` : l'interface s'appuie sur le `say` qui suit.
- `web/package.json` : ajout de `ws` et `@types/ws` (dev) et du script `mock`, nécessaires au faux orchestrateur.

## Reste à tester sur l'ordinateur de démo

- Le micro réel (autorisation du navigateur, qualité dans une salle bruyante).
- La voix française du navigateur (laquelle est installée, est-elle naturelle).
- VoiceOver les yeux fermés, en particulier le conflit possible avec la barre d'espace.
