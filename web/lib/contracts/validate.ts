// Validation à l'exécution contre les schémas de contracts/ (copiés dans ./schemas par contracts:gen).
// Exemple (membre 3) :
//   const check = validate("ApprovalRequest", await req.json());
//   if (!check.ok) return Response.json({ error: check.errors }, { status: 400 });
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import approvalRequest from "./schemas/approval-request.schema.json";
import approvalStatus from "./schemas/approval-status.schema.json";
import intent from "./schemas/intent.schema.json";
import option from "./schemas/option.schema.json";
import orderSummary from "./schemas/order-summary.schema.json";
import siteCard from "./schemas/site-card.schema.json";
import wsMessage from "./schemas/ws-message.schema.json";
import type {
  ApprovalRequest,
  ApprovalStatus,
  Intent,
  Option,
  OrderSummary,
  SiteCard,
  WsMessage,
} from "./types";

const SCHEMAS = {
  ApprovalRequest: approvalRequest,
  ApprovalStatus: approvalStatus,
  Intent: intent,
  Option: option,
  OrderSummary: orderSummary,
  SiteCard: siteCard,
  WsMessage: wsMessage,
} as const;

export interface ContractTypes {
  ApprovalRequest: ApprovalRequest;
  ApprovalStatus: ApprovalStatus;
  Intent: Intent;
  Option: Option;
  OrderSummary: OrderSummary;
  SiteCard: SiteCard;
  WsMessage: WsMessage;
}

export type ContractName = keyof ContractTypes;

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
for (const schema of Object.values(SCHEMAS)) ajv.addSchema(schema);

export type ValidationResult<T> = { ok: true; value: T } | { ok: false; errors: string[] };

export function validate<N extends ContractName>(name: N, data: unknown): ValidationResult<ContractTypes[N]> {
  const check = ajv.getSchema(SCHEMAS[name].$id);
  if (!check) throw new Error(`Schéma introuvable : ${name}`);
  if (check(data)) return { ok: true, value: data as ContractTypes[N] };
  const errors = (check.errors ?? []).map((e) => `${e.instancePath || "/"} ${e.message ?? "invalide"}`);
  return { ok: false, errors };
}
