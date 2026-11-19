// Bouton du casque (AirPods, filaire, Bluetooth) : un appui = couper Pilote s'il parle, sinon lui parler.
// La Media Session API relie les boutons lecture / pause du casque et de l'écran verrouillé à la page. Elle ne
// réagit que si la page vient de jouer un son : sans lui, le bouton va à une autre application. Le
// comportement exact change d'un téléphone à l'autre : à vérifier sur l'appareil, il n'est pas garanti.

interface MediaSessionLike {
  metadata: unknown;
  setActionHandler(action: string, handler: (() => void) | null): void;
}
type NavigatorLike = { mediaSession?: MediaSessionLike };

export interface HeadsetActions {
  /** Pilote parle : le couper. Sinon : lui parler. */
  onPlayPause: () => void;
}

const ACTIONS = ["play", "pause", "stop"] as const;

/** Branche le bouton du casque. Renvoie la fonction qui le débranche (toujours appelable). */
export function registerHeadsetButton(
  actions: HeadsetActions,
  nav: NavigatorLike | undefined = typeof navigator !== "undefined" ? (navigator as NavigatorLike) : undefined,
  makeMetadata: (() => unknown) | undefined = typeof MediaMetadata !== "undefined"
    ? () => new MediaMetadata({ title: "Pilote", artist: "Assistant vocal" })
    : undefined,
): () => void {
  const session = nav?.mediaSession;
  if (!session) return () => {};
  const registered: string[] = [];
  for (const action of ACTIONS) {
    try {
      session.setActionHandler(action, actions.onPlayPause);
      registered.push(action);
    } catch {
      // action inconnue de ce navigateur : on garde les autres
    }
  }
  try {
    if (makeMetadata) session.metadata = makeMetadata();
  } catch {
    // titre non affiché : sans conséquence
  }
  return () => {
    for (const action of registered) {
      try {
        session.setActionHandler(action, null);
      } catch {
        // déjà débranché
      }
    }
  };
}
