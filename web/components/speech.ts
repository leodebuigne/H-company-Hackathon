// Lecture à voix haute des messages « say », dans l'ordre, une phrase à la fois.
// Si l'orchestrateur fournit l'audio (synthèse Hugging Face), on le joue ; sinon on utilise
// la meilleure voix française du navigateur (speechSynthesis).

// Voix de secours, de la plus naturelle à la plus robotique. Les voix « Premium » / « Enhanced »
// de macOS et les voix « Natural » / « Online » d'Edge sont bien meilleures que les voix de base.
// Voix de l'ordinateur de haute qualité (Premium / Améliorée sur Mac) : toujours en tête.
const QUALITY_HINTS = ["premium", "enhanced", "améliorée", "natural", "neural"];
// Voix en ligne du navigateur (Google) : correctes, mais après les voix Premium / Améliorées.
const ONLINE_HINTS = ["google", "online"];
const PREFERRED_NAMES = ["Audrey", "Amélie", "Thomas", "Denise", "Henri", "Marie", "Google français"];

let frenchVoice: SpeechSynthesisVoice | null = null;
let chosenVoiceName: string | null = null;

// Voix fantaisie de macOS (robot, grand-mère…) : peu compréhensibles, on ne les propose pas
const NOVELTY_VOICE = /^(Eddy|Flo|Grandma|Grandpa|Reed|Rocko|Sandy|Shelley)\b/;

function frenchVoices(): SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return [];
  return window.speechSynthesis
    .getVoices()
    .filter((v) => v.lang.toLowerCase().startsWith("fr") && !NOVELTY_VOICE.test(v.name));
}

function score(v: SpeechSynthesisVoice): number {
  const name = v.name.toLowerCase();
  let s = 0;
  const q = QUALITY_HINTS.findIndex((hint) => name.includes(hint));
  if (q >= 0) s += 100 - q * 5;
  if (ONLINE_HINTS.some((hint) => name.includes(hint))) s += 20;
  const p = PREFERRED_NAMES.findIndex((n) => v.name.includes(n));
  if (p >= 0) s += 40 - p * 3;
  if (v.lang === "fr-FR") s += 10;
  if (v.localService) s += 2; // pas de coupure réseau
  return s;
}

function pickFrenchVoice(): SpeechSynthesisVoice | null {
  const voices = frenchVoices();
  if (chosenVoiceName) {
    const chosen = voices.find((v) => v.name === chosenVoiceName);
    if (chosen) return chosen;
  }
  return [...voices].sort((a, b) => score(b) - score(a))[0] ?? null;
}

if (typeof window !== "undefined" && "speechSynthesis" in window) {
  frenchVoice = pickFrenchVoice();
  window.speechSynthesis.onvoiceschanged = () => {
    frenchVoice = pickFrenchVoice();
  };
}

export function hasFrenchVoice() {
  return frenchVoice !== null;
}

/** Voix françaises du navigateur, la meilleure en premier (pour le menu des réglages). */
export function listFrenchVoices(): string[] {
  return [...frenchVoices()].sort((a, b) => score(b) - score(a)).map((v) => v.name);
}

/** null = choix automatique de la meilleure voix. */
export function setBrowserVoice(name: string | null) {
  chosenVoiceName = name;
  frenchVoice = pickFrenchVoice();
}

const hours = (h: string, m: string) => {
  const n = Number(h);
  const unit = n <= 1 ? "heure" : "heures";
  return m === "00" ? `${n} ${unit}` : `${n} ${unit} ${m}`;
};

// « h » seul est épelé par les voix de synthèse (« 14, H44 ») : on écrit « heures » en toutes lettres.
const ORDINAL_OPTIONS = ["Première", "Deuxième", "Troisième", "Quatrième", "Cinquième", "Sixième", "Septième", "Huitième"];

const SPOKEN_REPLACEMENTS: [RegExp, string | ((...m: string[]) => string)][] = [
  // « 1, TGV… » est mal lu : on dit « Première option : TGV… »
  [/(^|[:.]\s*)([1-8]),\s+/g, (_, before, n) => `${before}${ORDINAL_OPTIONS[Number(n) - 1]} option : `],
  [/\binoui\b/gi, "Inoui"],
  [/\s*(→|->|⟶)\s*/g, " vers "],
  [/\s+[·•|—–]\s+/g, ", "],
  [/\b1(?:re|ère)\b/g, "première"],
  [/\b2(?:de|nde)\b/g, "seconde"],
  [/\b(\d{1,2})\s*[:h]\s*(\d{2})\b/g, (_, h, m) => hours(h, m)],
  [/\b(\d{1,2})\s*h\b/g, (_, h) => hours(h, "00")],
  [/(\d+),00\s*(?:€|EUR\b)/g, "$1 euros"],
  [/(\d+),(\d{2})\s*(?:€|EUR\b)/g, "$1 euros $2"],
  [/(\d+)\s*(?:€|EUR\b)/g, "$1 euros"],
  [/\b(\d+)\s*min\b/g, "$1 minutes"],
  [/\s{2,}/g, " "],
];

/** Même règle que orchestrator/ai/speech_text.py : « 14:44 → 15:48 » se dit « 14 heures 44 vers 15 heures 48 ». */
export function forSpeech(text: string): string {
  return SPOKEN_REPLACEMENTS.reduce(
    (t, [pattern, replacement]) =>
      typeof replacement === "string" ? t.replace(pattern, replacement) : t.replace(pattern, replacement),
    text
  ).trim();
}

type Item = { text: string; audio?: string | null; mime?: string | null };

export class Speaker {
  private queue: Item[] = [];
  private current: HTMLAudioElement | null = null;
  private busy = false;
  // Chaque stop() ouvre une nouvelle génération : une phrase coupée ne relance jamais la file,
  // sinon deux lectures pouvaient se superposer après une interruption.
  private generation = 0;
  rate = 1;
  /** Topil a sa voix à lui : une phrase sans audio n'est pas dite par la voix du navigateur. */
  ownVoiceOnly = false;
  onChange: (speaking: boolean) => void = () => {};

  get speaking() {
    return this.busy;
  }

  /** Change à chaque stop() : une phrase préparée avant une coupure ne doit plus être dite. */
  get turn() {
    return this.generation;
  }

  enqueue(text: string, audio?: string | null, mime?: string | null) {
    this.queue.push({ text, audio, mime });
    if (!this.busy) void this.next(this.generation);
  }

  /** Coupe la parole immédiatement (l'utilisateur parle ou annule). */
  stop() {
    this.generation += 1;
    this.queue = [];
    if (this.current) {
      this.current.pause();
      this.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    this.setBusy(false);
  }

  private setBusy(v: boolean) {
    if (this.busy === v) return;
    this.busy = v;
    this.onChange(v);
  }

  private async next(generation: number) {
    if (generation !== this.generation) return;
    const item = this.queue.shift();
    if (!item) return this.setBusy(false);
    this.setBusy(true);
    try {
      if (item.audio) await this.playAudio(item.audio, item.mime);
      else if (!this.ownVoiceOnly) await this.speakWithBrowser(item.text);
    } catch {
      // un son bloqué ou une voix absente ne doit pas bloquer la file
    }
    void this.next(generation);
  }

  private playAudio(base64: string, mime?: string | null): Promise<void> {
    return new Promise((resolve) => {
      const src = base64.startsWith("data:") ? base64 : `data:${mime ?? "audio/mpeg"};base64,${base64}`;
      const audio = new Audio(src);
      audio.playbackRate = this.rate; // la hauteur de la voix est conservée par le navigateur
      this.current = audio;
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      audio.onpause = () => resolve();
      audio.play().catch(() => resolve());
    });
  }

  private speakWithBrowser(text: string): Promise<void> {
    return new Promise((resolve) => {
      if (!("speechSynthesis" in window)) return resolve();
      const u = new SpeechSynthesisUtterance(forSpeech(text));
      u.lang = "fr-FR";
      if (frenchVoice) u.voice = frenchVoice;
      u.rate = this.rate;
      u.onend = () => resolve();
      u.onerror = () => resolve();
      window.speechSynthesis.speak(u);
    });
  }
}
