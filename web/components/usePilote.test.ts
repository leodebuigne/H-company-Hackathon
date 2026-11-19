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
  refused: false,
  sessionId: null,
  state: "listening",
  intent: null,
  options: [],
  summary: null,
  log: [],
  agentViewUrl: null,
  lastSay: "",
  question: false,
  replay: null,
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

  it("garde la demande comprise quand l'utilisateur choisit une option ou dit oui", () => {
    const example = serverExamples.find((e) => e.msg.type === "intent");
    expect(example).toBeDefined();
    const request = example!.msg as Extract<ServerMessage, { type: "intent" }>;
    let s = reduce(empty, { type: "intent", intent: { ...request.intent, kind: "new_request" } });
    s = reduce(s, { type: "intent", intent: { ...request.intent, kind: "choose", choice_index: 2 } });
    expect(s.intent?.kind).toBe("new_request");
  });
});

describe("reduce : conversation rejouée, question, options périmées", () => {
  const say = (text: string): ServerMessage => ({ type: "transcript", role: "pilote", text });
  const ready: ServerMessage = { type: "ready", session_id: "s1" };
  const listening: ServerMessage = { type: "state", state: "listening" };

  it("un écran neuf accepte la conversation rejouée, un écran qui se reconnecte l'ignore", () => {
    let fresh = reduce(empty, ready);
    fresh = reduce(fresh, say("Bonjour"));
    expect(fresh.log.map((e) => e.text)).toEqual(["Bonjour"]);

    let back = reduce({ ...fresh, replay: null }, ready);
    back = reduce(back, say("Bonjour"));
    expect(back.log).toHaveLength(1);
    back = reduce(back, listening);
    back = reduce(back, say("Nouvelle phrase"));
    expect(back.log).toHaveLength(2);
  });

  it("« on repart de zéro » (nouvel identifiant) vide la conversation affichée", () => {
    let s = reduce(empty, ready);
    s = reduce(s, say("Je cherche la CAF de Lyon."));
    s = reduce(s, { type: "ready", session_id: "s2" });
    expect(s.log).toHaveLength(0);
    s = reduce(s, say("C'est fait, on repart de zéro."));
    expect(s.log.map((e) => e.text)).toEqual(["C'est fait, on repart de zéro."]);
  });

  it("une question n'a pas d'étapes d'achat, et une recherche affinée vide les options", () => {
    const base = serverExamples.find((e) => e.msg.type === "intent")!.msg as Extract<ServerMessage, { type: "intent" }>;
    const asked = reduce(empty, { ...base, intent: { ...base.intent, kind: "question" } });
    expect(asked.question).toBe(true);
    const options = serverExamples.find((e) => e.msg.type === "options")!.msg;
    let s = reduce(reduce(empty, { type: "state", state: "proposing" }), options);
    expect(s.options.length).toBeGreaterThan(0);
    s = reduce(s, { type: "state", state: "searching" });
    expect(s.options).toEqual([]);
  });
});
