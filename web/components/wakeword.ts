// Mot d'activation « Bonjour Pilote » : la page écoute en continu
// avec la reconnaissance vocale du navigateur (Chrome, Safari) et réveille Pilote quand on l'appelle.
// Si la phrase continue après le mot d'activation (« Bonjour Pilote, un train pour Lille »), la suite
// est renvoyée telle quelle : pas besoin de répéter.
// Le navigateur exige un premier geste (Espace ou toucher l'orbe) avant que Pilote puisse parler :
// l'écoute du mot d'activation démarre après ce premier geste.

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult:
    | ((event: {
        resultIndex: number;
        results: ArrayLike<
          ArrayLike<{ transcript: string }> & { isFinal: boolean }
        >;
      }) => void)
    | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

// « Bonjour Pilote » (avec ou sans virgule ; « pilot » ou « pilotes » quand la reconnaissance hésite).
const WAKE = /\bbonjour[\s,!.-]*pilot(e|es)?\b/i;

export function findWakeWord(text: string): { found: boolean; rest: string } {
  const match = WAKE.exec(text);
  if (!match) return { found: false, rest: "" };
  const rest = text
    .slice(match.index + match[0].length)
    .replace(/^[\s,!.?-]+/, "")
    .trim();
  return { found: true, rest };
}

// « OK Pilote », « stop », « attends » pendant que Pilote parle : il se tait tout de suite.
const STOP = /\b(?:(?:ok|okay|ok[ée]|o\.k\.?|au ?qu[ée])[\s,!.-]*pilot(?:e|es)?|stop|attends|attendez|tais[- ]toi|silence)\b/i;

const plainText = (text: string) =>
  text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

/**
 * Le mot pour couper a-t-il été dit ? `spoken` : ce que Pilote est en train de dire. Le micro capte sa propre
 * voix : si le mot fait partie de sa phrase (« dites stop pour… »), ce n'est pas la personne qui coupe.
 */
export function isStopWord(text: string, spoken = ""): boolean {
  const match = STOP.exec(text);
  if (!match) return false;
  const phrase = plainText(match[0]);
  return !(spoken && phrase && ` ${plainText(spoken)} `.includes(` ${phrase} `));
}

export function wakeWordSupported(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as Record<string, unknown>;
  return !!(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export class WakeWordListener {
  // Appelé avec la suite de la phrase (vide si on a seulement dit « Bonjour Pilote »)
  onWake: (rest: string) => void = () => {};
  // Appelé quand on dit « OK Pilote » pendant qu'il parle
  onStop: () => void = () => {};
  // Ce que Pilote est en train de dire : un mot pour couper qui en fait partie est de l'écho, pas la personne
  spokenText: () => string = () => "";
  // Pilote est-il en train de parler ? (on guette alors « OK Pilote », pas « Bonjour Pilote »)
  isSpeaking: () => boolean = () => false;
  private stopped = -1; // dernier résultat qui a déjà coupé Pilote
  private rec: Recognition | null = null;
  private wanted = false;
  private woken = false;

  get active() {
    return this.wanted;
  }

  start() {
    if (this.wanted || !wakeWordSupported()) return;
    this.wanted = true;
    this.launch();
  }

  // Pause pendant l'enregistrement : le micro est pris par l'enregistreur.
  stop() {
    this.wanted = false;
    this.rec?.abort();
    this.rec = null;
  }

  private launch() {
    const w = window as unknown as Record<string, new () => Recognition>;
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    const rec = new Ctor();
    rec.lang = "fr-FR";
    rec.continuous = true;
    rec.interimResults = true;
    this.woken = false;
    this.stopped = -1;
    rec.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? "";
        if (this.isSpeaking()) {
          // Pilote parle : seul « OK Pilote » compte (sa propre voix ne dit jamais ces mots)
          if (i !== this.stopped && isStopWord(text, this.spokenText())) {
            this.stopped = i;
            this.onStop();
          }
          continue;
        }
        const { found, rest } = findWakeWord(text);
        if (!found) continue;
        // On attend la fin de la phrase pour récupérer la demande qui suit le mot d'activation.
        if (!result.isFinal) {
          this.woken = true;
          continue;
        }
        this.fire(rest);
        return;
      }
    };
    rec.onerror = (event) => {
      if (
        event.error === "not-allowed" ||
        event.error === "service-not-allowed"
      )
        this.wanted = false;
    };
    rec.onend = () => {
      // La reconnaissance s'arrête d'elle-même après un silence : on la relance tant qu'on la veut.
      if (this.woken) return this.fire("");
      if (this.wanted && this.rec === rec)
        setTimeout(() => this.wanted && this.rec === rec && this.launch(), 250);
    };
    this.rec = rec;
    try {
      rec.start();
    } catch {
      this.wanted = false;
    }
  }

  private fire(rest: string) {
    this.stop();
    this.onWake(rest);
  }
}
