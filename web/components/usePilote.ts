"use client";

// Connexion à l'orchestrateur et état partagé de l'interface (utilisateur ou écran jury).

import { useCallback, useEffect, useRef, useState } from "react";
import { getServerConfig, wsProtocols } from "./serverConfig";
import type { ClientMessage, Intent, Option, OrderSummary, ServerMessage, State } from "./protocol";

export const ORCHESTRATOR_URL = process.env.NEXT_PUBLIC_ORCHESTRATOR_WS_URL ?? "ws://localhost:8000/ws";
export const ORCHESTRATOR_HTTP = ORCHESTRATOR_URL.replace(/^ws/, "http").replace(/\/ws\/?$/, "");

export type LogEntry = { id: number; who: "pilote" | "user" | "system"; text: string };

export interface PiloteSnapshot {
  connected: boolean;
  /** Le serveur a refusé cet appareil (jeton faux ou page inconnue) : inutile de réessayer. */
  refused: boolean;
  sessionId: string | null;
  state: State;
  intent: Intent | null;
  options: Option[];
  summary: OrderSummary | null;
  log: LogEntry[];
  agentViewUrl: string | null;
  lastSay: string;
  /** La demande en cours est une simple question (pas d'achat) : pas d'étapes Choix / Achat. */
  question: boolean;
  /** Entre « ready » et le premier « state », le serveur rejoue la conversation récente. */
  replay: "accept" | "skip" | null;
}

const INITIAL: PiloteSnapshot = {
  connected: false,
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

let logId = 0;
const entry = (who: LogEntry["who"], text: string): LogEntry => ({ id: ++logId, who, text });

export function reduce(s: PiloteSnapshot, msg: ServerMessage): PiloteSnapshot {
  switch (msg.type) {
    case "ready":
      // Nouvelle conversation (« on repart de zéro », ou orchestrateur relancé) : nouvel
      // identifiant, l'écran vide ce qu'il affichait.
      if (s.sessionId !== null && msg.session_id !== s.sessionId) {
        return {
          ...s,
          sessionId: msg.session_id,
          log: [],
          intent: null,
          options: [],
          summary: null,
          agentViewUrl: null,
          question: false,
          replay: "accept",
        };
      }
      // Un écran neuf (conversation vide) accepte la conversation rejouée ; un écran qui se
      // reconnecte l'a déjà : il l'ignore pour ne pas afficher les phrases en double.
      return { ...s, sessionId: msg.session_id, replay: s.log.length === 0 ? "accept" : "skip" };
    case "say":
      // L'historique vient des messages transcript (role pilote), pour ne pas doubler les phrases.
      return { ...s, lastSay: msg.text };
    case "state": {
      // Une nouvelle demande efface la commande précédente
      const fresh = msg.state === "understanding" && ["done", "cancelled", "listening"].includes(s.state);
      return {
        ...s,
        state: msg.state,
        replay: null,
        ...(fresh ? { intent: null, options: [], summary: null, agentViewUrl: null, question: false } : {}),
        // Nouvelle recherche (demande affinée) : les anciennes options ne sont plus valables
        ...(msg.state === "searching" && s.state === "proposing" ? { options: [] } : {}),
      };
    }
    case "transcript":
      if (s.replay === "skip") return s;
      return { ...s, log: [...s.log, entry(msg.role, msg.text)] };
    case "intent":
      // L'écran du jury montre la demande ; « la deuxième » ou « oui » ne la remplacent pas.
      if (msg.intent.kind === "question") return { ...s, question: true };
      return ["new_request", "refine"].includes(msg.intent.kind)
        ? { ...s, intent: msg.intent, question: false }
        : s;
    case "options":
      return { ...s, options: msg.options };
    case "summary":
      return { ...s, summary: msg.summary };
    case "agent_view":
      return { ...s, agentViewUrl: msg.agent_view_url };
    case "error":
      return { ...s, log: [...s.log, entry("system", msg.message)] };
  }
}

export function usePilote(onMessage?: (msg: ServerMessage) => void) {
  const [snap, setSnap] = useState<PiloteSnapshot>(INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const server = getServerConfig(); // relu à chaque tentative : un appairage vient peut-être d'être fait
      const ws = new WebSocket(server.wsUrl, wsProtocols(server.token));
      wsRef.current = ws;
      ws.onopen = () => setSnap((s) => ({ ...s, connected: true, refused: false }));
      ws.onclose = (event) => {
        // 4401 jeton faux, 4403 page inconnue : réessayer ne sert à rien. 4429 : trop d'essais, on attend.
        const refused = event.code === 4401 || event.code === 4403;
        setSnap((s) => ({ ...s, connected: false, refused }));
        if (stopped || refused) return;
        retry = setTimeout(connect, event.code === 4429 ? 60000 : 2000);
      };
      ws.onmessage = (event) => {
        let msg: ServerMessage;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;
        }
        setSnap((s) => reduce(s, msg));
        onMessageRef.current?.(msg);
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, []);

  // Ce que dit ou tape l'utilisateur revient par le message transcript (role user).
  const send = useCallback((msg: ClientMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(msg));
    return true;
  }, []);

  return { ...snap, send };
}
