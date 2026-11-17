// Messages WebSocket entre l'interface et l'orchestrateur (ws://localhost:8000/ws).
// Les types viennent du contrat officiel (web/lib/contracts, généré depuis contracts/) :
// ce fichier n'ajoute que des aides d'affichage, jamais de champ.

import type {
  ClientAudio,
  ClientCancel,
  ClientConfirm,
  ClientText,
  ServerAgentView,
  ServerApproval,
  ServerError,
  ServerIntent,
  ServerOptions,
  ServerReady,
  ServerSay,
  ServerState,
  ServerSummary,
  ServerTranscript,
  State,
} from "@/lib/contracts";

export type { ApprovalStatus, Intent, Option, OrderSummary, State } from "@/lib/contracts";

/** Interface → orchestrateur (confirm compris : Entrée / N au clavier). */
export type ClientMessage = ClientAudio | ClientText | ClientConfirm | ClientCancel;

/** Orchestrateur → interface. */
export type ServerMessage =
  | ServerReady
  | ServerState
  | ServerSay
  | ServerTranscript
  | ServerIntent
  | ServerOptions
  | ServerSummary
  | ServerApproval
  | ServerAgentView
  | ServerError;

export const STATE_LABELS: Record<State, string> = {
  listening: "J'écoute",
  understanding: "Je comprends la demande",
  searching: "Je cherche sur le site",
  proposing: "Je propose des options",
  cart: "Je remplis le panier",
  confirm_1: "Première confirmation",
  awaiting_relative: "J'attends la validation du proche",
  recheck: "Je relis la page de paiement",
  confirm_2: "Deuxième confirmation",
  paying: "Paiement en cours",
  done: "Terminé",
  cancelled: "Commande annulée",
  human_needed: "Un humain doit intervenir",
};

/** États où Entrée (oui) et N (non) sont acceptés par l'orchestrateur. */
export const CONFIRM_STATES: State[] = ["confirm_1", "confirm_2"];

/** 1450 → « 14,50 € » */
export function formatCents(cents: number): string {
  return (cents / 100).toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
}
