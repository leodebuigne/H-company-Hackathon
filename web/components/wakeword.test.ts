import { describe, expect, it } from "vitest";
import { findWakeWord, isStopWord } from "./wakeword";

describe("mot d'activation « Bonjour Pilote »", () => {
  it("se réveille sur « Bonjour Pilote » et garde la demande qui suit", () => {
    expect(findWakeWord("Bonjour Pilote")).toEqual({ found: true, rest: "" });
    expect(findWakeWord("bonjour, pilote, un train pour Lille demain")).toEqual(
      {
        found: true,
        rest: "un train pour Lille demain",
      },
    );
  });
  it("ne se réveille pas sur une phrase qui cite seulement Pilote", () => {
    expect(findWakeWord("je suis Pilote, un assistant automatique").found).toBe(
      false,
    );
    expect(findWakeWord("hé pilote").found).toBe(false);
  });
});

describe("« OK Pilote » coupe Pilote", () => {
  it("reconnaît OK Pilote sous ses formes courantes", () => {
    expect(isStopWord("OK Pilote")).toBe(true);
    expect(isStopWord("okay pilote")).toBe(true);
    expect(isStopWord("o.k. pilote stop")).toBe(true);
  });
  it("ignore les phrases de Pilote", () => {
    expect(isStopWord("Je suis Pilote, un assistant automatique")).toBe(false);
    expect(isStopWord("D'accord, je m'en occupe")).toBe(false);
  });
});

describe("« stop », « attends » coupent aussi Pilote", () => {
  it("reconnaît les mots pour couper", () => {
    for (const phrase of ["stop", "Stop !", "attends", "Attendez un instant", "tais-toi", "silence", "ok pilote stop"]) {
      expect(isStopWord(phrase), phrase).toBe(true);
    }
  });

  it("ignore les phrases ordinaires, même proches", () => {
    for (const phrase of ["Un train pour Lille", "Je prends le bus pour la gare", "C'est silencieux ici", "attention"]) {
      expect(isStopWord(phrase), phrase).toBe(false);
    }
  });

  it("n'obéit pas à sa propre voix : un mot qui fait partie de la phrase en cours n'est pas la personne", () => {
    const saying = "Dites stop si vous voulez que je m'arrête, ou annule pour tout arrêter.";
    expect(isStopWord("dites stop si vous voulez", saying)).toBe(false);
    expect(isStopWord("stop", saying)).toBe(false);
  });

  it("obéit à la personne quand le mot n'est pas dans ce que Pilote est en train de dire", () => {
    const saying = "J'ai trouvé trois trains. Le premier part à quatorze heures.";
    expect(isStopWord("stop", saying)).toBe(true);
    expect(isStopWord("OK Pilote", saying)).toBe(true);
  });

  it("sans phrase en cours, tout mot pour couper compte", () => {
    expect(isStopWord("stop", "")).toBe(true);
  });
});
