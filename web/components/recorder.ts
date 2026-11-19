// Enregistrement du micro. Deux façons de parler :
//   - maintenir (barre d'espace ou bouton) : on enregistre tant que c'est appuyé ;
//   - appui court : on écoute en continu et on s'arrête tout seul quand la personne se tait.
// Chrome enregistre en webm/opus ; Safari ne sait faire que du mp4. On choisit le premier format
// accepté et on l'envoie avec le message (champ mime, PROPOSITION de contrat).

import { audioConstraints, noiseFloor, speechLevelFor, type MicProfile } from "./micProfile";

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
  /** Niveau au-dessus duquel on entend de la parole : fixé par le profil et le bruit de fond mesuré. */
  speechLevel = speechLevelFor("normal");
  private profile: MicProfile = "normal";

  /** Choisit la sensibilité. `floor` : le bruit de fond mesuré par `calibrate` (0 si jamais mesuré). */
  setProfile(profile: MicProfile, floor = 0) {
    const agcChanged = audioConstraints(profile).autoGainControl !== audioConstraints(this.profile).autoGainControl;
    this.profile = profile;
    this.speechLevel = speechLevelFor(profile, floor);
    // Le gain automatique se règle à l'ouverture du micro : on le rouvrira au prochain enregistrement
    if (agcChanged && !this.isRecording) this.releaseStream();
  }

  private releaseStream() {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  /** Mesure le bruit de fond pendant `ms` : la personne ne dit rien, et Pilote non plus (sinon sa voix fausse la mesure). */
  async calibrate(ms = 1500): Promise<number> {
    if (this.isRecording || typeof AudioContext === "undefined") return 0;
    this.stream ??= await navigator.mediaDevices.getUserMedia({ audio: audioConstraints(this.profile) });
    this.audioCtx ??= new AudioContext();
    await this.audioCtx.resume();
    const source = this.audioCtx.createMediaStreamSource(this.stream);
    const analyser = this.audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const samples: number[] = [];
    await new Promise<void>((resolve) => {
      const timer = setInterval(() => {
        analyser.getFloatTimeDomainData(buf);
        samples.push(rmsLevel(buf));
      }, 50);
      setTimeout(() => {
        clearInterval(timer);
        resolve();
      }, ms);
    });
    source.disconnect();
    analyser.disconnect();
    return noiseFloor(samples);
  }

  get isRecording() {
    return this.recorder?.state === "recording";
  }

  async start(): Promise<void> {
    if (this.isRecording) return;
    if (!this.stream) {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints(this.profile) });
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
      if (this.level > this.speechLevel) {
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
        this.level = rmsLevel(buf);
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

/** Niveau 0..1 d'un bloc de son (RMS), la mesure commune du seuil de parole et de l'étalonnage. */
function rmsLevel(buf: Float32Array): number {
  let sum = 0;
  for (const v of buf) sum += v * v;
  return Math.min(1, Math.sqrt(sum / buf.length) * 8);
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
