"use client";

// Connexion à l'orchestrateur et état partagé de l'interface (utilisateur ou spectateur).

import { useCallback, useEffect, useRef, useState } from "react";
import type { ClientMessage, Option, OrderState, OrderSummary, ServerMessage } from "./protocol";

export const ORCHESTRATOR_URL = process.env.NEXT_PUBLIC_ORCHESTRATOR_WS ?? "ws://localhost:8000/ws";

export type LogEntry = { id: number; who: "pilote" | "user" | "system"; text: string; at: number };

export interface PiloteSnapshot {
  connected: boolean;
  state: OrderState;
  options: Option[];
  summary: OrderSummary | null;
  log: LogEntry[];
  agentViewUrl: string | null;
  humanReason: string | null;
  lastSay: string;
}

const INITIAL: PiloteSnapshot = {
  connected: false,
  state: "listening",
  options: [],
  summary: null,
  log: [],
  agentViewUrl: null,
  humanReason: null,
  lastSay: "",
};

let logId = 0;

export function usePilote(role: "user" | "spectator", onMessage?: (msg: ServerMessage) => void) {
  const [snap, setSnap] = useState<PiloteSnapshot>(INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const ws = new WebSocket(ORCHESTRATOR_URL);
      wsRef.current = ws;
      ws.onopen = () => {
        setSnap((s) => ({ ...s, connected: true }));
        ws.send(JSON.stringify({ type: "hello", role } satisfies ClientMessage));
      };
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
  }, [role]);

  const send = useCallback((msg: ClientMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    // Ce que dit ou tape l'utilisateur revient par le message "transcript", pour que
    // l'interface et l'écran spectateur affichent le même historique.
    ws.send(JSON.stringify(msg));
    return true;
  }, []);

  return { ...snap, send };
}

function entry(who: LogEntry["who"], text: string): LogEntry {
  return { id: ++logId, who, text, at: Date.now() };
}

function reduce(s: PiloteSnapshot, msg: ServerMessage): PiloteSnapshot {
  switch (msg.type) {
    case "say":
      return { ...s, lastSay: msg.text, log: [...s.log, entry("pilote", msg.text)] };
    case "state": {
      const fresh = msg.state === "understanding" && ["done", "cancelled", "listening"].includes(s.state);
      return {
        ...s,
        state: msg.state,
        humanReason: msg.state === "human_needed" ? s.humanReason : null,
        ...(fresh ? { options: [], summary: null, agentViewUrl: null } : {}),
      };
    }
    case "options":
      return { ...s, options: msg.options };
    case "summary":
      return { ...s, summary: msg.summary };
    case "error":
      return { ...s, log: [...s.log, entry("system", `Erreur : ${msg.message}`)] };
    case "transcript":
      return { ...s, log: [...s.log, entry("user", msg.text)] };
    case "agent_view":
      return { ...s, agentViewUrl: msg.url };
    case "human_needed":
      return { ...s, humanReason: msg.reason, log: [...s.log, entry("system", `Intervention humaine : ${msg.reason}`)] };
  }
}
