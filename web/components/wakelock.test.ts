import { describe, expect, it, vi } from "vitest";
import { WakeLockKeeper } from "./wakelock";

function fakes(opts: { reject?: boolean; absent?: boolean } = {}) {
  const listeners: Record<string, () => void> = {};
  const sentinels: { release: ReturnType<typeof vi.fn>; fire: () => void; cb?: () => void }[] = [];
  const doc = {
    visibilityState: "visible",
    addEventListener: (t: string, l: () => void) => void (listeners[t] = l),
    removeEventListener: (t: string) => void delete listeners[t],
  };
  const nav = opts.absent
    ? {}
    : {
        wakeLock: {
          request: vi.fn(async () => {
            if (opts.reject) throw new Error("refusé");
            const s = {
              release: vi.fn(async () => {}),
              cb: undefined as undefined | (() => void),
              addEventListener: (_: string, cb: () => void) => void (s.cb = cb),
              fire: () => s.cb?.(),
            };
            sentinels.push(s);
            return s;
          }),
        },
      };
  return { doc, nav, listeners, sentinels };
}

describe("WakeLockKeeper", () => {
  it("demande le verrou et le relâche", async () => {
    const f = fakes();
    const k = new WakeLockKeeper(f.nav, f.doc);
    await k.acquire();
    expect(k.held).toBe(true);
    await k.release();
    expect(k.held).toBe(false);
    expect(f.sentinels[0].release).toHaveBeenCalled();
    expect(f.listeners.visibilitychange).toBeUndefined();
  });

  it("le redemande quand la page redevient visible après un relâchement du navigateur", async () => {
    const f = fakes();
    const k = new WakeLockKeeper(f.nav, f.doc);
    await k.acquire();
    f.sentinels[0].fire(); // le navigateur l'a retiré (page cachée)
    expect(k.held).toBe(false);
    f.listeners.visibilitychange();
    await Promise.resolve();
    await Promise.resolve();
    expect(f.sentinels).toHaveLength(2);
    expect(k.held).toBe(true);
  });

  it("repli silencieux sans l'API", async () => {
    const f = fakes({ absent: true });
    const k = new WakeLockKeeper(f.nav, f.doc);
    expect(k.supported).toBe(false);
    await expect(k.acquire()).resolves.toBeUndefined();
    expect(k.held).toBe(false);
  });

  it("repli silencieux si le navigateur refuse", async () => {
    const f = fakes({ reject: true });
    const k = new WakeLockKeeper(f.nav, f.doc);
    await expect(k.acquire()).resolves.toBeUndefined();
    expect(k.held).toBe(false);
  });
});
