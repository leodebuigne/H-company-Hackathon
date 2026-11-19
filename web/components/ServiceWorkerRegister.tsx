"use client";

// Enregistre le service worker (public/sw.js) en production seulement.
// En développement il est retiré s'il était déjà installé : un cache ancien casserait le rechargement à chaud.

import { useEffect } from "react";

export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NODE_ENV !== "production") {
      void navigator.serviceWorker
        .getRegistrations()
        .then((registrations) => registrations.forEach((r) => void r.unregister()))
        .then(() => ("caches" in window ? caches.keys() : []))
        .then((names) => names.filter((n) => n.startsWith("pilote-")).forEach((n) => void caches.delete(n)))
        .catch(() => {});
      return;
    }
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // sans service worker, l'application marche pareil (elle ne s'ouvre simplement pas hors connexion)
    });
  }, []);
  return null;
}
