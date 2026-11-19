// Le service worker ne met jamais en cache le WebSocket, l'audio, ni autre chose que l'enveloppe de l'application.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import vm from "node:vm";
import { describe, expect, it } from "vitest";

const source = readFileSync(join(__dirname, "../public/sw.js"), "utf8");
const ORIGIN = "https://pilote.example";

type Listener = (event: unknown) => void;

function loadWorker() {
  const listeners: Record<string, Listener> = {};
  const cached: string[] = [];
  const cache = {
    add: async (path: string) => void cached.push(path),
    put: async (req: { url: string }) => void cached.push(req.url),
  };
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, fn: Listener) => void (listeners[type] = fn),
    skipWaiting: async () => {},
    clients: { claim: async () => {} },
  };
  const context = {
    self,
    caches: { open: async () => cache, keys: async () => [], match: async () => undefined, delete: async () => true },
    fetch: async (req: { url: string }) => ({ ok: true, clone: () => ({}), url: req.url }),
    Response: class {},
    URL,
  };
  vm.runInNewContext(source, context);
  return { listeners, cached, context };
}

const request = (url: string, init: Partial<{ method: string; destination: string; mode: string; headers: Record<string, string> }> = {}) => ({
  url,
  method: init.method ?? "GET",
  destination: init.destination ?? "",
  mode: init.mode ?? "cors",
  headers: { get: (name: string) => init.headers?.[name.toLowerCase()] ?? null },
});

/** Renvoie true si le service worker a pris la requête en charge (respondWith appelé). */
function handled(req: ReturnType<typeof request>) {
  const { listeners } = loadWorker();
  let responded = false;
  listeners.fetch({ request: req, respondWith: () => void (responded = true) });
  return responded;
}

describe("service worker", () => {
  it("prend en charge la page et les fichiers de l'application", () => {
    expect(handled(request(`${ORIGIN}/`, { mode: "navigate" }))).toBe(true);
    expect(handled(request(`${ORIGIN}/spectateur`, { mode: "navigate" }))).toBe(true);
    expect(handled(request(`${ORIGIN}/_next/static/chunks/app.js`, { destination: "script" }))).toBe(true);
    expect(handled(request(`${ORIGIN}/icons/icon-192.png`, { destination: "image" }))).toBe(true);
    expect(handled(request(`${ORIGIN}/manifest.webmanifest`))).toBe(true);
  });

  it("ne touche jamais à l'audio", () => {
    expect(handled(request(`${ORIGIN}/voix.mp3`))).toBe(false);
    expect(handled(request(`${ORIGIN}/tts/phrase.wav`))).toBe(false);
    expect(handled(request(`${ORIGIN}/x`, { destination: "audio" }))).toBe(false);
    expect(handled(request(`${ORIGIN}/x`, { headers: { accept: "audio/mpeg" } }))).toBe(false);
    expect(handled(request(`${ORIGIN}/_next/static/media/son.webm`))).toBe(false);
    expect(handled(request(`${ORIGIN}/x`, { headers: { range: "bytes=0-" } }))).toBe(false);
    expect(handled(request("data:audio/wav;base64,AAAA"))).toBe(false);
  });

  it("ne touche jamais au WebSocket ni à une autre origine", () => {
    expect(handled(request("ws://localhost:8000/ws?uid=abc"))).toBe(false);
    expect(handled(request("wss://orchestrator.example/ws"))).toBe(false);
    expect(handled(request("http://localhost:8000/health"))).toBe(false);
    expect(handled(request("https://cdn.example/lib.js"))).toBe(false);
  });

  it("ne touche pas aux requêtes qui ne sont pas des GET ni à l'API", () => {
    expect(handled(request(`${ORIGIN}/`, { method: "POST", mode: "navigate" }))).toBe(false);
    expect(handled(request(`${ORIGIN}/api/anything`))).toBe(false);
  });

  it("ne met en cache que l'enveloppe à l'installation", async () => {
    const { listeners, cached } = loadWorker();
    let done: Promise<unknown> = Promise.resolve();
    listeners.install({ waitUntil: (p: Promise<unknown>) => void (done = p) });
    await done;
    expect(cached.length).toBeGreaterThan(0);
    for (const path of cached) expect(path).toMatch(/^\/($|manifest\.webmanifest|icons\/)/);
    expect(cached.some((p) => /\.(mp3|wav|ogg|webm|m4a)$/.test(p))).toBe(false);
  });
});
