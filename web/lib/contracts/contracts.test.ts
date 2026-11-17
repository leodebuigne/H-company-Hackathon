import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { validate, type ContractName } from "./validate";

const EXAMPLES = join(__dirname, "..", "..", "..", "contracts", "examples");

const PREFIXES: [string, ContractName][] = [
  ["approval-request-", "ApprovalRequest"],
  ["approval-status-", "ApprovalStatus"],
  ["order-summary-", "OrderSummary"],
  ["site-card-", "SiteCard"],
  ["intent-", "Intent"],
  ["option-", "Option"],
  ["ws-", "WsMessage"],
];

function contractFor(file: string): ContractName {
  const found = PREFIXES.find(([prefix]) => file.startsWith(prefix));
  if (!found) throw new Error(`Préfixe inconnu : ${file}`);
  return found[1];
}

function load(dir: string) {
  return readdirSync(join(EXAMPLES, dir))
    .filter((f) => f.endsWith(".json"))
    .map((f) => [f, JSON.parse(readFileSync(join(EXAMPLES, dir, f), "utf8"))] as const);
}

describe("exemples valides", () => {
  it.each(load("valid"))("%s", (file, data) => {
    const result = validate(contractFor(file), data);
    expect(result.ok ? [] : result.errors).toEqual([]);
  });
});

describe("exemples invalides", () => {
  it.each(load("invalid"))("%s est refusé", (file, data) => {
    expect(validate(contractFor(file), data).ok).toBe(false);
  });
});
