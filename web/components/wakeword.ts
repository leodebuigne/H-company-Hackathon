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
// Le nom est « Topil » (« pilote » en verlan). La reconnaissance vocale l'écrit de plusieurs façons :
// « topil », « top il », « to pile », « taupe il »… L'ancien nom « Pilote » réveille aussi l'assistant.
const NAME = String.raw`(?:topi(?:l|le|lle|ls)|top[\s-]?(?:il|ile|ils|hill)|taupe?[\s-]?il|to[\s-]?pil(?:e|es)?|pilot(?:e|es)?)`;
const WAKE = new RegExp(String.raw`\bbonjour[\s,!.-]*${NAME}\b`, "i");

export function findWakeWord(text: string): { found: boolean; rest: string } {
  const match = WAKE.exec(text);
  if (!match) return { found: false, rest: "" };
  const rest = text
    .slice(match.index + match[0].length)
    .replace(/^[\s,!.?-]+/, "")
    .trim();
  return { found: true, rest };
}

// « OK Pilote » pendant que Pilote parle : il se tait tout de suite.
const STOP = new RegExp(
  String.raw`\b(ok|okay|ok[ée]|o\.k\.?|au ?qu[ée])[\s,!.-]*${NAME}\b`,
  "i",
);

export function isStopWord(text: string): boolean {
  return STOP.test(text);
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
          if (i !== this.stopped && isStopWord(text)) {
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
