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
  cart: "Je prépare l'achat",
  confirm_1: "Confirmation",
  awaiting_relative: "J'attends la validation du proche",
  recheck: "Je relis la page de paiement",
  confirm_2: "Deuxième confirmation",
  paying: "Achat en cours",
  done: "C'est fait",
  cancelled: "Commande annulée",
  human_needed: "Un humain doit intervenir",
};

/** États où Entrée (oui) et N (non) sont acceptés par l'orchestrateur. */
export const CONFIRM_STATES: State[] = ["confirm_1", "confirm_2"];

/** 1450 → « 14,50 € », 1400 → « 14 € », 0 → « 0 € » */
export function formatCents(cents: number): string {
  const whole = cents % 100 === 0;
  return (cents / 100).toLocaleString("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: whole ? 0 : 2,
  });
}

/** Étapes du parcours, dans l'ordre (barre de progression de l'interface et de l'écran jury).
 *  Valable pour l'achat direct comme pour le parcours complet : tout ce qui suit le choix est « Achat ». */
export const STEPS: { states: State[]; label: string }[] = [
  { states: ["listening", "understanding"], label: "Demande" },
  { states: ["searching"], label: "Recherche" },
  { states: ["proposing"], label: "Choix" },
  { states: ["cart", "confirm_1", "awaiting_relative", "recheck", "confirm_2", "paying"], label: "Achat" },
  { states: ["done"], label: "Terminé" },
];

/** États où une commande est en train d'être achetée (après le choix). */
export const BUY_STATES: State[] = ["cart", "confirm_1", "awaiting_relative", "recheck", "confirm_2", "paying"];

/** États où Pilote travaille seul : on affiche depuis combien de temps. */
export const BUSY_STATES: State[] = ["understanding", "searching", "cart", "recheck", "paying"];

/** 1 → « première », pour choisir une option comme on le dirait à l'oral. */
export const ORDINALS = ["première", "deuxième", "troisième", "quatrième", "cinquième", "sixième", "septième", "huitième"];
