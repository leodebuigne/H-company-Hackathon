import { describe, expect, it } from "vitest";

import { OverlapTracker, overlapMime } from "./echoGuard";

describe("OverlapTracker", () => {
  it("ne signale rien quand Pilote se tait pendant tout l'enregistrement", () => {
    const tracker = new OverlapTracker();
    tracker.begin(false);
    expect(tracker.overlapped).toBe(false);
    expect(overlapMime("audio/webm;codecs=opus", tracker)).toBe("audio/webm;codecs=opus");
  });

  it("signale un enregistrement ouvert pendant que Pilote parle", () => {
    const tracker = new OverlapTracker();
    tracker.begin(true);
    expect(overlapMime("audio/webm;codecs=opus", tracker)).toBe("audio/webm;codecs=opus;overlapped=1");
  });

  it("signale un enregistrement pendant lequel Pilote se met à parler", () => {
    const tracker = new OverlapTracker();
    tracker.begin(false);
    tracker.pilotStartedSpeaking();
    expect(overlapMime("audio/webm;codecs=opus", tracker)).toBe("audio/webm;codecs=opus;overlapped=1");
  });

  it("repart de zéro à chaque nouvel enregistrement", () => {
    const tracker = new OverlapTracker();
    tracker.begin(true);
    tracker.begin(false);
    expect(tracker.overlapped).toBe(false);
  });
});
