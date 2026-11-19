// Service worker de Pilote : met en cache l'enveloppe de l'application (page, scripts, styles,
// icônes) pour qu'elle s'ouvre vite et s'installe sur l'écran d'accueil.
//
// Ce qu'il ne fait JAMAIS :
//  - toucher au WebSocket (un service worker n'intercepte de toute façon pas les WebSocket) ;
//  - mettre de l'audio en cache (voix de Pilote, enregistrements) ni aucune requête qui n'est pas GET ;
//  - mettre en cache autre chose que les fichiers de la même origine listés ci-dessous.
// Sans réseau, l'application s'ouvre mais ne peut pas parler à Pilote : l'interface le dit à voix haute.

const CACHE = "pilote-shell-v1";
const SHELL = ["/", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon.svg"];
const AUDIO_PATH = /\.(mp3|wav|ogg|oga|webm|m4a|aac|flac|opus|mp4)$/i;

const OFFLINE_PAGE =
  '<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
  "<title>Pilote hors connexion</title>" +
  '<body style="font-family:system-ui,sans-serif;background:#ffffff;color:#10131a;padding:24px;font-size:1.3rem;line-height:1.5">' +
  "<h1>Pilote est hors connexion</h1><p>Vérifiez votre connexion à Internet, puis rouvrez Pilote.</p></body></html>";

/** Que faire d'une requête : "network" (ne pas y toucher), "shell" (page), "static" (fichier de l'application). */
function classify(request, selfOrigin) {
  if (request.method !== "GET") return "network";
  let url;
  try {
    url = new URL(request.url);
  } catch {
    return "network";
  }
  if (url.origin !== selfOrigin) return "network"; // jamais d'autre origine (serveur d'audio, WebSocket sur un autre hôte)
  if (url.protocol !== "http:" && url.protocol !== "https:") return "network";
  const accept = request.headers && request.headers.get ? request.headers.get("accept") || "" : "";
  if (request.destination === "audio" || request.destination === "video" || /^(audio|video)\//.test(accept)) return "network";
  if (AUDIO_PATH.test(url.pathname) || url.pathname.startsWith("/api/")) return "network";
  if (request.headers && request.headers.get && request.headers.get("range")) return "network"; // lecture partielle d'un média
  if (request.mode === "navigate") return "shell";
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/") || url.pathname === "/manifest.webmanifest") {
    return "static";
  }
  return "network";
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => Promise.all(SHELL.map((path) => cache.add(path).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((n) => n.startsWith("pilote-") && n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const kind = classify(event.request, self.location.origin);
  if (kind === "network") return; // le navigateur gère seul

  if (kind === "shell") {
    // Réseau d'abord (toujours la dernière version), cache si le réseau manque
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            void caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() =>
          caches
            .match(event.request)
            .then((hit) => hit || caches.match("/"))
            .then((hit) => hit || new Response(OFFLINE_PAGE, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }))
        )
    );
    return;
  }

  // Fichiers de l'application (noms uniques par version) : cache d'abord
  event.respondWith(
    caches.match(event.request).then(
      (hit) =>
        hit ||
        fetch(event.request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            void caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
    )
  );
});
