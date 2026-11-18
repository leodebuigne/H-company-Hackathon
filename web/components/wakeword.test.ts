import { describe, expect, it } from "vitest";
import { findWakeWord } from "./wakeword";

describe("mot d'activation « Bonjour Pilote »", () => {
  it("se réveille sur « Bonjour Pilote » et garde la demande qui suit", () => {
    expect(findWakeWord("Bonjour Pilote")).toEqual({ found: true, rest: "" });
    expect(findWakeWord("bonjour, pilote, un train pour Lille demain")).toEqual({
      found: true,
      rest: "un train pour Lille demain",
    });
  });
  it("ne se réveille pas sur une phrase qui cite seulement Pilote", () => {
    expect(findWakeWord("je suis Pilote, un assistant automatique").found).toBe(false);
    expect(findWakeWord("hé pilote").found).toBe(false);
  });
});
