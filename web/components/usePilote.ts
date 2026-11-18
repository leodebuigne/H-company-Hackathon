"use client";

// Connexion à l'orchestrateur et état partagé de l'interface (utilisateur ou écran jury).

import { useCallback, useEffect, useRef, useState } from "react";
import type { ClientMessage, Intent, Option, OrderSummary, ServerMessage, State } from "./protocol";

export const ORCHESTRATOR_URL = process.env.NEXT_PUBLIC_ORCHESTRATOR_WS_URL ?? "ws://localhost:8000/ws";

export type LogEntry = { id: number; who: "pilote" | "user" | "system"; text: string };

export interface PiloteSnapshot {
  connected: boolean;
  sessionId: string | null;
  state: State;
  intent: Intent | null;
  options: Option[];
  summary: OrderSummary | null;
  log: LogEntry[];
  agentViewUrl: string | null;
  lastSay: string;
}

const INITIAL: PiloteSnapshot = {
  connected: false,
  sessionId: null,
  state: "listening",
  intent: null,
  options: [],
  summary: null,
  log: [],
  agentViewUrl: null,
  lastSay: "",
};

let logId = 0;
const entry = (who: LogEntry["who"], text: string): LogEntry => ({ id: ++logId, who, text });

export function reduce(s: PiloteSnapshot, msg: ServerMessage): PiloteSnapshot {
  switch (msg.type) {
    case "ready":
      return { ...s, sessionId: msg.session_id };
    case "say":
      // L'historique vient des messages transcript (role pilote), pour ne pas doubler les phrases.
      return { ...s, lastSay: msg.text };
    case "state": {
      // Une nouvelle demande efface la commande précédente
      const fresh = msg.state === "understanding" && ["done", "cancelled", "listening"].includes(s.state);
      return {
        ...s,
        state: msg.state,
        ...(fresh ? { intent: null, options: [], summary: null, agentViewUrl: null } : {}),
      };
    }
    case "transcript":
      return { ...s, log: [...s.log, entry(msg.role, msg.text)] };
    case "intent":
      return { ...s, intent: msg.intent };
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
      const ws = new WebSocket(ORCHESTRATOR_URL);
      wsRef.current = ws;
      ws.onopen = () => setSnap((s) => ({ ...s, connected: true }));
      ws.onclose = () => {
        setSnap((s) => ({ ...s, connected: false }));
        if (!stopped) retry = setTimeout(connect, 2000);
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
