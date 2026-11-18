// Enregistrement du micro. Deux façons de parler :
//   - maintenir (barre d'espace ou bouton) : on enregistre tant que c'est appuyé ;
//   - appui court : on écoute en continu et on s'arrête tout seul quand la personne se tait.
// Chrome enregistre en webm/opus ; Safari ne sait faire que du mp4. On choisit le premier format
// accepté et on l'envoie avec le message (champ mime, PROPOSITION de contrat).

const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

/** On continue d'enregistrer un instant après le relâchement : sinon la fin du dernier mot est coupée. */
export const RELEASE_TAIL_MS = 400;

export interface Recording {
  data: string; // base64
  mime: string;
  durationMs: number;
}

export interface SilenceWatch {
  /** Silence après la parole avant de s'arrêter (une hésitation « euh… » ne coupe pas). */
  silenceMs: number;
  /** Aucune parole entendue pendant ce délai : on abandonne. */
  noSpeechMs: number;
  /** Durée maximale d'une phrase. */
  maxMs: number;
  onStop: (reason: "silence" | "no_speech" | "max") => void;
}

export class PushToTalkRecorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private startedAt = 0;
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private watchTimer: ReturnType<typeof setInterval> | null = null;
  private meterTimer: ReturnType<typeof setInterval> | null = null;
  /** Vrai si de la parole a été entendue pendant cet enregistrement. */
  heardSpeech = false;
  /** Niveau du micro de 0 à 1, pour l'animation de l'interface. */
  level = 0;

  get isRecording() {
    return this.recorder?.state === "recording";
  }

  async start(): Promise<void> {
    if (this.isRecording) return;
    if (!this.stream) {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    }
    const mimeType = PREFERRED_TYPES.find((t) => MediaRecorder.isTypeSupported(t));
    this.recorder = new MediaRecorder(this.stream, mimeType ? { mimeType, audioBitsPerSecond: 64000 } : undefined);
    this.chunks = [];
    this.heardSpeech = false;
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.startedAt = performance.now();
    this.recorder.start();
    this.startMeter();
  }

  /** Écoute continue : appelle onStop quand la personne s'est tue (ou n'a rien dit). */
  watchSilence(watch: SilenceWatch) {
    this.stopWatch();
    let lastVoice = performance.now();
    const started = lastVoice;
    this.watchTimer = setInterval(() => {
      const now = performance.now();
      if (this.level > SPEECH_LEVEL) {
        this.heardSpeech = true;
        lastVoice = now;
      }
      if (now - started > watch.maxMs) return this.fire(watch, "max");
      if (!this.heardSpeech && now - started > watch.noSpeechMs) return this.fire(watch, "no_speech");
      if (this.heardSpeech && now - lastVoice > watch.silenceMs) return this.fire(watch, "silence");
    }, 50);
  }

  private fire(watch: SilenceWatch, reason: "silence" | "no_speech" | "max") {
    this.stopWatch();
    watch.onStop(reason);
  }

  private stopWatch() {
    if (this.watchTimer) clearInterval(this.watchTimer);
    this.watchTimer = null;
  }

  /** Arrête l'enregistrement. Renvoie null si c'était trop court (moins de 300 ms) ou vide. */
  stop(): Promise<Recording | null> {
    this.stopWatch();
    const recorder = this.recorder;
    if (!recorder || recorder.state !== "recording") return Promise.resolve(null);
    return new Promise((resolve) => {
      recorder.onstop = async () => {
        this.stopMeter();
        const durationMs = performance.now() - this.startedAt;
        const mime = recorder.mimeType || "audio/webm";
        const blob = new Blob(this.chunks, { type: mime });
        this.chunks = [];
        if (durationMs < 300 || blob.size === 0) return resolve(null);
        resolve({ data: await blobToBase64(blob), mime, durationMs });
      };
      recorder.stop();
    });
  }

  /** Abandonne l'enregistrement sans rien envoyer. */
  discard() {
    this.stopWatch();
    const recorder = this.recorder;
    if (recorder && recorder.state === "recording") {
      recorder.onstop = () => this.stopMeter();
      recorder.stop();
    }
    this.chunks = [];
  }

  // Niveau du micro (RMS), mesuré pendant l'enregistrement seulement
  private startMeter() {
    if (!this.stream || typeof AudioContext === "undefined") return;
    try {
      this.audioCtx ??= new AudioContext();
      void this.audioCtx.resume();
      const source = this.audioCtx.createMediaStreamSource(this.stream);
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 1024;
      source.connect(this.analyser);
      const buf = new Float32Array(this.analyser.fftSize);
      // setInterval plutôt que requestAnimationFrame : continue même si l'onglet passe en arrière-plan
      this.meterTimer = setInterval(() => {
        if (!this.analyser) return;
        this.analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += v * v;
        this.level = Math.min(1, Math.sqrt(sum / buf.length) * 8);
      }, 40);
    } catch {
      this.analyser = null; // pas de mesure : l'écoute continue s'arrêtera au délai maximal
    }
  }

  private stopMeter() {
    if (this.meterTimer) clearInterval(this.meterTimer);
    this.meterTimer = null;
    this.analyser?.disconnect();
    this.analyser = null;
    this.level = 0;
  }
}

/** Seuil de parole sur le niveau 0..1 (le bruit de fond d'une pièce calme reste en dessous). */
const SPEECH_LEVEL = 0.12;

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
