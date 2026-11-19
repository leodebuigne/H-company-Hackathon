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

describe("le nom Topil, tel que la reconnaissance vocale l'écrit", () => {
  it("se réveille sur « Bonjour Topil » et ses variantes, et garde la demande", () => {
    for (const heard of [
      "Bonjour Topil",
      "bonjour top il",
      "Bonjour, Topile",
      "bonjour to pile",
      "Bonjour taupe il",
    ]) {
      expect(findWakeWord(heard).found).toBe(true);
    }
    expect(findWakeWord("Bonjour Topil, un train pour Lille")).toEqual({
      found: true,
      rest: "un train pour Lille",
    });
    expect(findWakeWord("bonjour tout le monde").found).toBe(false);
  });

  it("« OK Topil » le coupe, pas ses propres phrases", () => {
    expect(isStopWord("OK Topil")).toBe(true);
    expect(isStopWord("okay top il")).toBe(true);
    expect(isStopWord("Je suis Topil, un assistant automatique")).toBe(false);
  });
});
