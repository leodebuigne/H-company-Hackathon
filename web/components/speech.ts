// Lecture à voix haute des messages « say », dans l'ordre, une phrase à la fois.
// Si l'orchestrateur fournit l'audio (synthèse Hugging Face), on le joue ; sinon on utilise
// la voix française du navigateur (speechSynthesis).

const PREFERRED_VOICES = ["Amélie", "Thomas", "Audrey", "Google français", "Microsoft Denise", "Marie"];

let frenchVoice: SpeechSynthesisVoice | null = null;

function pickFrenchVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("fr"));
  for (const name of PREFERRED_VOICES) {
    const v = voices.find((voice) => voice.name.includes(name));
    if (v) return v;
  }
  return voices.find((v) => v.lang === "fr-FR") ?? voices[0] ?? null;
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

type Item = { text: string; audio?: string | null; mime?: string | null };

export class Speaker {
  private queue: Item[] = [];
  private current: HTMLAudioElement | null = null;
  private busy = false;
  rate = 1;
  onChange: (speaking: boolean) => void = () => {};

  get speaking() {
    return this.busy;
  }

  enqueue(text: string, audio?: string | null, mime?: string | null) {
    this.queue.push({ text, audio, mime });
    if (!this.busy) void this.next();
  }

  /** Coupe la parole immédiatement (l'utilisateur parle ou annule). */
  stop() {
    this.queue = [];
    if (this.current) {
      this.current.pause();
      this.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    this.setBusy(false);
  }

  private setBusy(v: boolean) {
    this.busy = v;
    this.onChange(v);
  }

  private async next() {
    const item = this.queue.shift();
    if (!item) return this.setBusy(false);
    this.setBusy(true);
    try {
      if (item.audio) await this.playAudio(item.audio, item.mime);
      else await this.speakWithBrowser(item.text);
    } catch {
      // un son bloqué ou une voix absente ne doit pas bloquer la file
    }
    if (this.busy) void this.next();
  }

  private playAudio(base64: string, mime?: string | null): Promise<void> {
    return new Promise((resolve) => {
      const src = base64.startsWith("data:") ? base64 : `data:${mime ?? "audio/mpeg"};base64,${base64}`;
      const audio = new Audio(src);
      this.current = audio;
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      audio.play().catch(() => resolve());
    });
  }

  private speakWithBrowser(text: string): Promise<void> {
    return new Promise((resolve) => {
      if (!("speechSynthesis" in window)) return resolve();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "fr-FR";
      if (frenchVoice) u.voice = frenchVoice;
      u.rate = this.rate;
      u.onend = () => resolve();
      u.onerror = () => resolve();
      window.speechSynthesis.speak(u);
    });
  }
}
