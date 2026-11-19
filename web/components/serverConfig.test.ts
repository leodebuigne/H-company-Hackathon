import { describe, expect, it } from "vitest";

import {
  authHeaders,
  forgetPairing,
  httpUrlFor,
  isAllowedWsUrl,
  loadServerConfig,
  parsePairingHash,
  savePairing,
  takePairingFromLocation,
  wsProtocols,
  type KeyValueStore,
} from "./serverConfig";

const TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz012345";
const link = (server: string, token = TOKEN) =>
  `#server=${encodeURIComponent(server)}&token=${encodeURIComponent(token)}`;

function memoryStore(): KeyValueStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
  };
}

describe("isAllowedWsUrl", () => {
  it("accepte wss partout et ws seulement sur cette machine", () => {
    expect(isAllowedWsUrl("wss://abc.trycloudflare.com/ws")).toBe(true);
    expect(isAllowedWsUrl("ws://localhost:8000/ws")).toBe(true);
    expect(isAllowedWsUrl("ws://127.0.0.1:8000/ws")).toBe(true);
  });

  it("refuse ce qui ferait circuler le jeton en clair ou vers n'importe où", () => {
    for (const bad of [
      "ws://abc.example.com/ws",
      "http://abc.example.com/ws",
      "wss://user:mdp@abc.example.com/ws",
      "wss://abc.example.com/ws#x",
      "javascript:alert(1)",
      "pas une adresse",
      "",
    ]) {
      expect(isAllowedWsUrl(bad), bad).toBe(false);
    }
  });
});

describe("parsePairingHash", () => {
  it("lit l'adresse et le jeton du lien d'appairage", () => {
    expect(parsePairingHash(link("wss://abc.trycloudflare.com/ws"))).toEqual({
      wsUrl: "wss://abc.trycloudflare.com/ws",
      token: TOKEN,
    });
  });

  it("refuse un lien incomplet, une adresse en clair ou un jeton trop court ou aux caractères étranges", () => {
    expect(parsePairingHash("")).toBeNull();
    expect(parsePairingHash(`#token=${TOKEN}`)).toBeNull();
    expect(parsePairingHash(link("ws://abc.example.com/ws"))).toBeNull();
    expect(parsePairingHash(link("wss://abc.example.com/ws", "court"))).toBeNull();
    expect(parsePairingHash(link("wss://abc.example.com/ws", "x".repeat(20) + "<script>"))).toBeNull();
  });
});

describe("loadServerConfig", () => {
  it("garde l'adresse du build et aucun jeton tant que rien n'est appairé", () => {
    expect(loadServerConfig(memoryStore(), "ws://localhost:8000/ws")).toEqual({
      wsUrl: "ws://localhost:8000/ws",
      httpUrl: "http://localhost:8000",
      token: null,
    });
    expect(loadServerConfig(null, "ws://localhost:8000/ws").token).toBeNull();
  });

  it("utilise l'appairage enregistré, puis l'oublie sur demande", () => {
    const store = memoryStore();
    expect(savePairing(store, { wsUrl: "wss://abc.trycloudflare.com/ws", token: TOKEN })).toBe(true);
    const config = loadServerConfig(store, "ws://localhost:8000/ws");
    expect(config).toEqual({
      wsUrl: "wss://abc.trycloudflare.com/ws",
      httpUrl: "https://abc.trycloudflare.com",
      token: TOKEN,
    });
    forgetPairing(store);
    expect(loadServerConfig(store, "ws://localhost:8000/ws").token).toBeNull();
  });

  it("ignore un enregistrement abîmé ou piégé (adresse en clair ailleurs que chez soi)", () => {
    const store = memoryStore();
    store.setItem("pilote-server", "{pas du json");
    expect(loadServerConfig(store, "ws://localhost:8000/ws").token).toBeNull();
    store.setItem("pilote-server", JSON.stringify({ wsUrl: "ws://pirate.example/ws", token: TOKEN }));
    expect(loadServerConfig(store, "ws://localhost:8000/ws").wsUrl).toBe("ws://localhost:8000/ws");
  });

  it("dit quand l'appairage ne peut pas être gardé (navigation privée)", () => {
    const broken: KeyValueStore = {
      getItem: () => null,
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {},
    };
    expect(savePairing(broken, { wsUrl: "wss://abc.example.com/ws", token: TOKEN })).toBe(false);
    expect(savePairing(null, { wsUrl: "wss://abc.example.com/ws", token: TOKEN })).toBe(false);
  });
});

describe("jeton dans les échanges", () => {
  it("passe par les sous-protocoles du WebSocket et l'en-tête Authorization, jamais par l'adresse", () => {
    expect(wsProtocols(TOKEN)).toEqual(["pilote", `token.${TOKEN}`]);
    expect(wsProtocols(null)).toBeUndefined();
    expect(authHeaders(TOKEN)).toEqual({ Authorization: `Bearer ${TOKEN}` });
    expect(authHeaders(null)).toEqual({});
    expect(httpUrlFor("wss://abc.example.com/ws")).toBe("https://abc.example.com");
  });
});

describe("takePairingFromLocation", () => {
  const history = () => {
    const calls: string[] = [];
    return { calls, replaceState: (_d: unknown, _u: string, url: string) => void calls.push(url) };
  };

  it("lit le lien et l'efface de la barre d'adresse", () => {
    const h = history();
    const location = { hash: link("wss://abc.example.com/ws"), pathname: "/", search: "?x=1" };
    expect(takePairingFromLocation(location, h)?.token).toBe(TOKEN);
    expect(h.calls).toEqual(["/?x=1"]);
  });

  it("efface aussi un lien invalide, et ne touche à rien s'il n'y a pas de lien", () => {
    const bad = history();
    expect(takePairingFromLocation({ hash: "#token=court", pathname: "/", search: "" }, bad)).toBeNull();
    expect(bad.calls).toEqual(["/"]);
    const none = history();
    expect(takePairingFromLocation({ hash: "#section", pathname: "/", search: "" }, none)).toBeNull();
    expect(none.calls).toEqual([]);
  });
});
