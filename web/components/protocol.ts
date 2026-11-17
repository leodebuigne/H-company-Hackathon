// Messages WebSocket entre l'interface et l'orchestrateur (ws://localhost:8000/ws).
// Copie locale du contrat décrit dans le plan, en attendant contracts/README.md (membre 5).
// Les messages marqués PROPOSITION ne sont pas encore dans le contrat : à valider par le membre 5.

export type OrderState =
  | "listening"
  | "understanding"
  | "searching"
  | "proposing"
  | "cart"
  | "confirm_1"
  | "awaiting_relative"
  | "recheck"
  | "confirm_2"
  | "paying"
  | "done"
  | "cancelled"
  | "human_needed";

export interface Option {
  id: string;
  title: string;
  price_eur: number;
  rating?: number | null;
  details?: string | null;
  url?: string | null;
}

export interface OrderItem {
  title: string;
  quantity: number;
  price_eur?: number;
}

export interface OrderSummary {
  order_id: string;
  site: string;
  items: OrderItem[];
  fees_eur: number;
  total_eur: number;
  delivery?: string | null;
  refund_terms?: string | null;
  hash?: string;
}

// Interface → orchestrateur
export type ClientMessage =
  | { type: "audio"; data: string; mime?: string } // mime : PROPOSITION (Safari enregistre en mp4, pas en webm)
  | { type: "text"; text: string }
  | { type: "confirm"; value: boolean }
  | { type: "cancel" }
  | { type: "hello"; role: "user" | "spectator" }; // PROPOSITION : identifier l'écran spectateur

// Orchestrateur → interface
export type ServerMessage =
  | { type: "say"; text: string; audio?: string | null } // audio : base64 (mp3/wav) ou vide
  | { type: "state"; state: OrderState }
  | { type: "options"; options: Option[] }
  | { type: "summary"; summary: OrderSummary }
  | { type: "error"; message: string }
  | { type: "transcript"; text: string } // PROPOSITION : ce que l'utilisateur a dit, pour l'écran spectateur
  | { type: "agent_view"; url: string } // PROPOSITION : lien vers la vue en direct de l'agent H
  | { type: "human_needed"; reason: string }; // PROPOSITION : CAPTCHA, cryptogramme, connexion…

export const STATE_LABELS: Record<OrderState, string> = {
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

export const CONFIRM_STATES: OrderState[] = ["confirm_1", "confirm_2"];

export function formatEuros(value: number): string {
  return value.toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
}
