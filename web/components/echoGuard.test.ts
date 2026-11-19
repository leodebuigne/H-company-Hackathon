import { describe, expect, it } from "vitest";

import { OverlapTracker, overlapField } from "./echoGuard";

describe("OverlapTracker", () => {
  it("ne signale rien quand Pilote se tait pendant tout l'enregistrement", () => {
    const tracker = new OverlapTracker();
    tracker.begin(false);
    expect(tracker.overlapped).toBe(false);
    expect(overlapField(tracker)).toEqual({});
  });

  it("signale un enregistrement ouvert pendant que Pilote parle", () => {
    const tracker = new OverlapTracker();
    tracker.begin(true);
    expect(overlapField(tracker)).toEqual({ overlapped: true });
  });

  it("signale un enregistrement pendant lequel Pilote se met à parler", () => {
    const tracker = new OverlapTracker();
    tracker.begin(false);
    tracker.pilotStartedSpeaking();
    expect(overlapField(tracker)).toEqual({ overlapped: true });
  });

  it("repart de zéro à chaque nouvel enregistrement", () => {
    const tracker = new OverlapTracker();
    tracker.begin(true);
    tracker.begin(false);
    expect(tracker.overlapped).toBe(false);
  });
});
