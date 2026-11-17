// Sons courts qui disent à l'utilisateur où en est la commande, sans regarder l'écran.
// Générés avec Web Audio (aucun fichier à charger). Le navigateur exige un premier geste
// de l'utilisateur avant de jouer un son : appeler unlockAudio() au premier appui.

import type { OrderState } from "./protocol";

export type Earcon = "listening" | "thinking" | "waiting" | "question" | "success" | "error";

let ctx: AudioContext | null = null;

export function unlockAudio() {
  if (typeof window === "undefined") return;
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") void ctx.resume();
}

function tone(freq: number, start: number, duration: number, volume = 0.18, type: OscillatorType = "sine") {
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  const t = ctx.currentTime + start;
  gain.gain.setValueAtTime(0, t);
  gain.gain.linearRampToValueAtTime(volume, t + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + duration);
  osc.connect(gain).connect(ctx.destination);
  osc.start(t);
  osc.stop(t + duration + 0.05);
}

const PATTERNS: Record<Earcon, () => void> = {
  // Deux notes montantes, brèves : « je vous écoute »
  listening: () => { tone(660, 0, 0.09); tone(990, 0.09, 0.12); },
  // Deux notes graves et douces : « je réfléchis / je travaille »
  thinking: () => { tone(392, 0, 0.12, 0.12, "triangle"); tone(392, 0.2, 0.12, 0.12, "triangle"); },
  // Trois pulsations lentes : « j'attends votre proche »
  waiting: () => { [0, 0.45, 0.9].forEach((s) => tone(523, s, 0.18, 0.12)); },
  // Note qui monte, comme une question : « à vous de répondre »
  question: () => { tone(587, 0, 0.12); tone(784, 0.14, 0.22); },
  // Petit accord majeur : « c'est fait »
  success: () => { tone(523, 0, 0.15); tone(659, 0.12, 0.15); tone(784, 0.24, 0.3); },
  // Deux notes descendantes : « problème ou annulation »
  error: () => { tone(440, 0, 0.18, 0.18, "square"); tone(294, 0.2, 0.3, 0.18, "square"); },
};

export function playEarcon(name: Earcon) {
  if (!ctx) return;
  PATTERNS[name]();
}

export function earconForState(state: OrderState): Earcon | null {
  switch (state) {
    case "listening":
      return null; // le son « j'écoute » est joué quand on appuie pour parler
    case "understanding":
    case "searching":
    case "cart":
    case "recheck":
    case "paying":
      return "thinking";
    case "proposing":
    case "confirm_1":
    case "confirm_2":
      return "question";
    case "awaiting_relative":
      return "waiting";
    case "done":
      return "success";
    case "cancelled":
    case "human_needed":
      return "error";
  }
}
