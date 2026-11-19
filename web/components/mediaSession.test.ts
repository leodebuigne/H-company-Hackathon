import { describe, expect, it, vi } from "vitest";

import { registerHeadsetButton } from "./mediaSession";

function fakeSession(unsupported: string[] = []) {
  const handlers = new Map<string, (() => void) | null>();
  return {
    handlers,
    metadata: null as unknown,
    setActionHandler(action: string, handler: (() => void) | null) {
      if (unsupported.includes(action)) throw new TypeError(`action inconnue : ${action}`);
      handlers.set(action, handler);
    },
  };
}

describe("registerHeadsetButton", () => {
  it("relie lecture, pause et stop du casque à la même action", () => {
    const session = fakeSession();
    const onPlayPause = vi.fn();
    registerHeadsetButton({ onPlayPause }, { mediaSession: session }, () => ({ title: "Pilote" }));
    for (const action of ["play", "pause", "stop"]) session.handlers.get(action)?.();
    expect(onPlayPause).toHaveBeenCalledTimes(3);
    expect(session.metadata).toEqual({ title: "Pilote" });
  });

  it("débranche les boutons quand on s'en va", () => {
    const session = fakeSession();
    const off = registerHeadsetButton({ onPlayPause: vi.fn() }, { mediaSession: session }, undefined);
    off();
    expect([...session.handlers.values()]).toEqual([null, null, null]);
  });

  it("garde les actions que le navigateur connaît quand il en refuse une", () => {
    const session = fakeSession(["stop"]);
    const onPlayPause = vi.fn();
    const off = registerHeadsetButton({ onPlayPause }, { mediaSession: session }, undefined);
    session.handlers.get("play")?.();
    expect(onPlayPause).toHaveBeenCalledOnce();
    expect(session.handlers.has("stop")).toBe(false);
    expect(off).not.toThrow();
  });

  it("ne fait rien, sans erreur, quand le navigateur n'a pas de Media Session", () => {
    const off = registerHeadsetButton({ onPlayPause: vi.fn() }, {}, undefined);
    expect(off).not.toThrow();
    expect(() => registerHeadsetButton({ onPlayPause: vi.fn() }, undefined, undefined)()).not.toThrow();
  });
});
