// L'interface comprend bien chaque exemple de message serveur du contrat.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { validate } from "../lib/contracts/validate"; // chemin relatif : vitest ne connaît pas l'alias @/
import type { ServerMessage } from "./protocol";
import { reduce, type PiloteSnapshot } from "./usePilote";

const examplesDir = join(__dirname, "../../contracts/examples/valid");
const serverExamples = readdirSync(examplesDir)
  .filter((f) => f.startsWith("ws-server-"))
  .map((f) => ({ file: f, msg: JSON.parse(readFileSync(join(examplesDir, f), "utf8")) as ServerMessage }));

const empty: PiloteSnapshot = {
  connected: true,
  sessionId: null,
  state: "listening",
  intent: null,
  options: [],
  summary: null,
  log: [],
  agentViewUrl: null,
  lastSay: "",
};

describe("reduce", () => {
  it("trouve des exemples de messages serveur", () => {
    expect(serverExamples.length).toBeGreaterThan(0);
  });

  it.each(serverExamples)("accepte $file sans erreur", ({ msg }) => {
    expect(validate("WsMessage", msg).ok).toBe(true);
    expect(() => reduce(empty, msg)).not.toThrow();
  });

  it("garde l'historique à partir des transcriptions, pas des say", () => {
    let s = reduce(empty, { type: "say", text: "Bonjour", audio: null, mime: null });
    s = reduce(s, { type: "transcript", role: "pilote", text: "Bonjour" });
    s = reduce(s, { type: "transcript", role: "user", text: "Un train pour Lille" });
    expect(s.lastSay).toBe("Bonjour");
    expect(s.log.map((e) => e.who)).toEqual(["pilote", "user"]);
  });

  it("efface la commande précédente quand une nouvelle demande commence", () => {
    const withOrder: PiloteSnapshot = {
      ...empty,
      state: "done",
      agentViewUrl: "https://example.com",
      options: serverExamples.find((e) => e.msg.type === "options")?.msg.type === "options"
        ? (serverExamples.find((e) => e.msg.type === "options")!.msg as Extract<ServerMessage, { type: "options" }>).options
        : [],
    };
    const s = reduce(withOrder, { type: "state", state: "understanding" });
    expect(s.options).toEqual([]);
    expect(s.agentViewUrl).toBeNull();
  });
});
