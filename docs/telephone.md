# Utiliser Pilote depuis un iPhone

Le téléphone sert de micro et de haut-parleur. **Le serveur reste sur le Mac** : c'est lui qui pilote le Chrome
connecté à vos comptes. Vercel héberge seulement l'interface (https, ce que l'iPhone exige pour le micro).
Vercel ne peut pas héberger le serveur : il garde des WebSocket ouverts et lance des tâches de plusieurs
minutes (à vérifier dans la documentation de Vercel).

```
iPhone ── https ──> interface (Vercel)
iPhone ── wss ────> tunnel ──> serveur Pilote (le Mac) ──> Chrome
```

## Ce qui est vérifié, et ce qui ne l'est pas

Vérifié par des tests et par un essai réseau local : le jeton, l'origine, le refus d'un appareil non appairé, le
lien d'appairage, le manifeste et les icônes servis par l'interface. **Pas vérifié** : le tunnel, le
déploiement sur Vercel, et tout ce qui se passe sur un vrai iPhone (micro conservé, écran maintenu allumé,
bouton du casque, installation sur l'écran d'accueil). Essayez dans cet ordre et corrigez ce qui ne marche pas.

## 1. Le serveur, sur le Mac

Dans `.env` (le jeton est tiré au hasard s'il manque ; sinon au moins 24 caractères) :

```bash
PILOTE_HOST=0.0.0.0          # joignable par le tunnel : un jeton devient obligatoire
PILOTE_TOKEN=                # facultatif ; vide = tiré au hasard et affiché au démarrage
PILOTE_ALLOWED_ORIGINS=https://votre-interface.vercel.app
PILOTE_WEB_URL=https://votre-interface.vercel.app
PILOTE_PUBLIC_WS_URL=wss://adresse-du-tunnel.example/ws
```

Avec `PILOTE_HOST=127.0.0.1` (le défaut), rien ne change : aucun jeton, seul le Mac y accède.

## 2. Le tunnel

Un tunnel https qui accepte les WebSocket, par exemple Cloudflare Tunnel ou Tailscale Funnel (à vérifier) :

```bash
cloudflared tunnel --url http://localhost:8000
```

Il affiche une adresse en `https://…`. Mettez la même en `wss://…/ws` dans `PILOTE_PUBLIC_WS_URL`.

## 3. L'interface sur Vercel

Déployez le dossier `web/` (Root Directory = `web`). Aucune variable n'est nécessaire : l'adresse du serveur et le
jeton viennent du lien d'appairage, pas du build.

## 4. Appairer le téléphone

Au démarrage, le serveur affiche un lien d'appairage (une seule fois) :

```
https://votre-interface.vercel.app/#server=wss%3A%2F%2F…&token=…
```

Ouvrez-le sur l'iPhone. Tout ce qui suit le `#` reste dans le navigateur : ni Vercel ni le tunnel ne le voient. La
page demande « Connecter Pilote au serveur … ? » : vérifiez l'adresse avant d'accepter, un lien piégé enverrait
votre voix ailleurs. Puis « Partager > Sur l'écran d'accueil ».

## Si ça ne marche pas

- **« Ce téléphone n'est pas appairé »** : le jeton est faux ou la page n'est pas dans `PILOTE_ALLOWED_ORIGINS`.
  Rouvrez le lien d'appairage du serveur.
- **Trop d'essais ratés** : après 10 jetons faux en une minute, le serveur refuse d'emblée pendant une minute.
- **Le micro est redemandé à chaque ouverture** : réglez Réglages > Safari > Micro sur « Autoriser ».
