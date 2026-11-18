// Sons courts qui disent à l'utilisateur où en est la commande, sans regarder l'écran.
// Générés avec Web Audio (aucun fichier à charger). Le navigateur exige un premier geste
// de l'utilisateur avant de jouer un son : appeler unlockAudio() au premier appui.

import type { State } from "./protocol";

export type Earcon = "listening" | "thinking" | "question" | "success" | "error";

let ctx: AudioContext | null = null;
let bus: AudioNode | null = null; // sortie commune : filtre doux + légère réverbération

export function unlockAudio() {
  if (typeof window === "undefined") return;
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") void ctx.resume();
}

// Chaîne de sortie : filtre passe-bas (son feutré) et écho court très discret (espace, élégance).
function output(): AudioNode | null {
  if (!ctx) return null;
  if (bus) return bus;
  const input = ctx.createGain();
  const soft = ctx.createBiquadFilter();
  soft.type = "lowpass";
  soft.frequency.value = 5200;
  input.connect(soft).connect(ctx.destination);
  const delay = ctx.createDelay(1);
  delay.delayTime.value = 0.16;
  const feedback = ctx.createGain();
  feedback.gain.value = 0.28;
  const tail = ctx.createBiquadFilter();
  tail.type = "lowpass";
  tail.frequency.value = 2600;
  const wet = ctx.createGain();
  wet.gain.value = 0.22;
  input.connect(delay);
  delay.connect(tail).connect(feedback).connect(delay);
  tail.connect(wet).connect(ctx.destination);
  bus = input;
  return bus;
}

// Note de cloche de verre : fondamentale pure et deux harmoniques légères, attaque douce,
// extinction longue. Volume bas : un signal discret, jamais agressif.
function bell(freq: number, start: number, duration: number, volume = 0.2) {
  const out = output();
  if (!ctx || !out) return;
  const t = ctx.currentTime + start;
  const partials: [number, number][] = [
    [1, 1],
    [2, 0.18],
    [3.01, 0.05],
  ];
  for (const [ratio, level] of partials) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq * ratio;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(volume * level, t + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + duration / ratio);
    osc.connect(gain).connect(out);
    osc.start(t);
    osc.stop(t + duration + 0.05);
  }
}

// Notes (Hz) : gamme de ré majeur, aiguë et claire
const D5 = 587.33;
const FS5 = 739.99;
const A5 = 880;
const B5 = 987.77;
const D6 = 1174.66;
const FS6 = 1479.98;

const PATTERNS: Record<Earcon, () => void> = {
  // « je vous écoute » : deux notes qui s'élèvent, comme une respiration qui s'ouvre
  listening: () => {
    bell(A5, 0, 0.7, 0.21);
    bell(D6, 0.085, 0.9, 0.18);
  },
  // « c'est envoyé, je réfléchis » : la même phrase qui redescend, plus discrète
  thinking: () => {
    bell(D6, 0, 0.5, 0.13);
    bell(A5, 0.08, 0.7, 0.12);
  },
  // « à vous de répondre » : une seule note claire qui reste suspendue
  question: () => bell(B5, 0, 1.1, 0.17),
  // « c'est fait » : petit arpège majeur qui scintille
  success: () => {
    bell(D6, 0, 1.0, 0.16);
    bell(FS6, 0.09, 1.0, 0.13);
    bell(A5 * 2, 0.18, 1.4, 0.12);
  },
  // « annulé ou problème » : deux notes douces qui descendent, sans dureté
  error: () => {
    bell(FS5, 0, 0.8, 0.18);
    bell(D5, 0.14, 1.1, 0.17);
  },
};

export function playEarcon(name: Earcon) {
  if (!ctx) return;
  PATTERNS[name]();
}

export function earconForState(state: State): Earcon | null {
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
    case "done":
      return "success";
    case "cancelled":
    case "human_needed":
      return "error";
  }
}
