// Enregistrement du micro pour le « maintenir pour parler ».
// Chrome enregistre en webm/opus ; Safari ne sait faire que du mp4. On choisit le premier format
// accepté et on l'envoie avec le message (champ mime, PROPOSITION de contrat).

const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export interface Recording {
  data: string; // base64
  mime: string;
  durationMs: number;
}

export class PushToTalkRecorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private startedAt = 0;

  get isRecording() {
    return this.recorder?.state === "recording";
  }

  async start(): Promise<void> {
    if (this.isRecording) return;
    if (!this.stream) {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    }
    const mimeType = PREFERRED_TYPES.find((t) => MediaRecorder.isTypeSupported(t));
    this.recorder = new MediaRecorder(this.stream, mimeType ? { mimeType } : undefined);
    this.chunks = [];
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.startedAt = performance.now();
    this.recorder.start();
  }

  /** Arrête l'enregistrement. Renvoie null si l'appui était trop court (moins de 300 ms). */
  stop(): Promise<Recording | null> {
    const recorder = this.recorder;
    if (!recorder || recorder.state !== "recording") return Promise.resolve(null);
    return new Promise((resolve) => {
      recorder.onstop = async () => {
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
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
