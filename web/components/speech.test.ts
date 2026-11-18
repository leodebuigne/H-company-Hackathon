import { describe, expect, it } from "vitest";
import { forSpeech } from "./speech";

// Même règle que orchestrator/ai/speech_text.py (test_for_speech_reads_times_prices_and_arrows_aloud)
describe("forSpeech", () => {
  it.each([
    ["TGV 14:44 → 15:48", "TGV 14 heures 44 vers 15 heures 48"],
    ["TGV INOUI 14 h 12 → 15 h 15", "TGV Inoui 14 heures 12 vers 15 heures 15"],
    ["Durée 1h56, avant 20 h", "Durée 1 heure 56, avant 20 heures"],
    ["2de classe dès 115 €, 1re classe", "seconde classe dès 115 euros, première classe"],
    ["Direct — 42,00 €", "Direct, 42 euros"],
    ["J'ai trouvé : 1, TGV inOui. 2, TER", "J'ai trouvé : Première option : TGV Inoui. Deuxième option : TER"],
    ["Livraison 19h30 · 3,50 € de frais", "Livraison 19 heures 30, 3 euros 50 de frais"],
    ["Départ à 10:00, 45 min", "Départ à 10 heures, 45 minutes"],
  ])("%s", (shown, spoken) => {
    expect(forSpeech(shown)).toBe(spoken);
  });
});
