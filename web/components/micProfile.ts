// Sensibilité du micro : trois profils et un étalonnage du bruit de fond.
// Le seuil de parole était fixe (0,12). Une voix basse passait sous le seuil, une pièce bruyante le dépassait.
// Le profil « normal » garde 0,12 : sans réglage, rien ne change.

export type MicProfile = "whisper" | "normal" | "noisy";

export const MIC_PROFILES: MicProfile[] = ["whisper", "normal", "noisy"];

export const MIC_PROFILE_LABELS: Record<MicProfile, string> = {
  whisper: "Je parle doucement",
  normal: "Normal",
  noisy: "Pièce bruyante",
};

/** Niveau (0 à 1, même échelle que `PushToTalkRecorder.level`) au-dessus duquel on entend de la parole. */
const BASE_LEVEL: Record<MicProfile, number> = { whisper: 0.05, normal: 0.12, noisy: 0.2 };
export const MAX_SPEECH_LEVEL = 0.5;
/** Au-delà de ce bruit de fond, parler près du micro ou mettre un casque vaut mieux qu'un réglage. */
export const LOUD_NOISE_FLOOR = 0.15;

/** Bruit de fond : le 90e centile des niveaux mesurés pendant que la personne ne dit rien. */
export function noiseFloor(samples: number[]): number {
  if (samples.length === 0) return 0;
  const sorted = [...samples].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil(0.9 * sorted.length) - 1);
  return Math.max(0, sorted[index]);
}

/** Seuil de parole : celui du profil, relevé si le bruit de fond mesuré le rattrape. */
export function speechLevelFor(profile: MicProfile, floor = 0): number {
  return Math.min(MAX_SPEECH_LEVEL, Math.max(BASE_LEVEL[profile], floor * 2.5 + 0.02));
}

/** Réglages du micro : dans une pièce bruyante, le gain automatique gonflerait le bruit autant que la voix. */
export function audioConstraints(profile: MicProfile): MediaTrackConstraints {
  return {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: profile !== "noisy",
    channelCount: 1,
  };
}

/** Phrase à dire après l'étalonnage. */
export function describeCalibration(floor: number): string {
  if (floor >= LOUD_NOISE_FLOOR) {
    return "Il y a beaucoup de bruit autour de vous. Parlez près du micro, ou mettez un casque : je vous entendrai mieux.";
  }
  if (floor >= 0.06) {
    return "Micro réglé. Il y a un peu de bruit de fond : j'ai relevé la sensibilité en conséquence.";
  }
  return "Micro réglé. La pièce est calme, je vous entends bien.";
}

export function isMicProfile(value: unknown): value is MicProfile {
  return typeof value === "string" && (MIC_PROFILES as string[]).includes(value);
}
