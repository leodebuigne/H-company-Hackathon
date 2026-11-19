import { describe, expect, it } from "vitest";

import {
  LOUD_NOISE_FLOOR,
  MAX_SPEECH_LEVEL,
  audioConstraints,
  describeCalibration,
  isMicProfile,
  noiseFloor,
  speechLevelFor,
} from "./micProfile";

describe("speechLevelFor", () => {
  it("le profil normal garde l'ancien seuil fixe : sans réglage, rien ne change", () => {
    expect(speechLevelFor("normal")).toBe(0.12);
    expect(speechLevelFor("normal", 0)).toBe(0.12);
  });

  it("une voix basse a un seuil plus bas, une pièce bruyante un seuil plus haut", () => {
    expect(speechLevelFor("whisper")).toBeLessThan(speechLevelFor("normal"));
    expect(speechLevelFor("normal")).toBeLessThan(speechLevelFor("noisy"));
  });

  it("relève le seuil quand le bruit de fond mesuré le rattrape, jamais au-dessus du plafond", () => {
    expect(speechLevelFor("whisper", 0.1)).toBeCloseTo(0.27, 5);
    expect(speechLevelFor("normal", 0.05)).toBe(0.145);
    expect(speechLevelFor("noisy", 5)).toBe(MAX_SPEECH_LEVEL);
  });

  it("ne baisse jamais le seuil en dessous du profil à cause d'un bruit de fond très faible", () => {
    for (const profile of ["whisper", "normal", "noisy"] as const) {
      expect(speechLevelFor(profile, 0.001)).toBe(speechLevelFor(profile, 0));
    }
  });
});

describe("noiseFloor", () => {
  it("vaut 0 sans mesure", () => {
    expect(noiseFloor([])).toBe(0);
  });

  it("prend le 90e centile : un claquement isolé ne fausse pas le réglage", () => {
    const quiet = Array(18).fill(0.02);
    expect(noiseFloor([...quiet, 0.02, 0.9])).toBe(0.02);
  });

  it("suit un bruit de fond régulier", () => {
    // rang le plus proche : le 9e des 10 niveaux classés
    expect(noiseFloor([0.1, 0.12, 0.11, 0.1, 0.13, 0.1, 0.12, 0.11, 0.1, 0.12])).toBeCloseTo(0.12, 5);
  });
});

describe("audioConstraints", () => {
  it("coupe le gain automatique seulement dans une pièce bruyante", () => {
    expect(audioConstraints("noisy").autoGainControl).toBe(false);
    expect(audioConstraints("whisper").autoGainControl).toBe(true);
    expect(audioConstraints("normal").autoGainControl).toBe(true);
  });

  it("garde l'annulation d'écho et la réduction de bruit dans tous les profils", () => {
    for (const profile of ["whisper", "normal", "noisy"] as const) {
      expect(audioConstraints(profile)).toMatchObject({ echoCancellation: true, noiseSuppression: true });
    }
  });
});

describe("describeCalibration", () => {
  it("dit la vérité sur la pièce", () => {
    expect(describeCalibration(0.01)).toContain("calme");
    expect(describeCalibration(0.08)).toContain("un peu de bruit");
    expect(describeCalibration(LOUD_NOISE_FLOOR)).toContain("casque");
  });
});

describe("isMicProfile", () => {
  it("n'accepte que les trois profils connus (un réglage enregistré peut être périmé)", () => {
    expect(isMicProfile("whisper")).toBe(true);
    expect(isMicProfile("loud")).toBe(false);
    expect(isMicProfile(undefined)).toBe(false);
  });
});
