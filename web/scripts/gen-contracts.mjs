// Génère web/lib/contracts/ à partir de contracts/schemas/ (qui font foi) :
//   - schemas/*.json : copie des schémas, pour que le build Vercel (Root Directory = web) les trouve
//   - types.ts : types TypeScript
// Ne pas éditer les fichiers générés : modifier contracts/ puis lancer `npm run contracts:gen`.
import { readFileSync, writeFileSync, readdirSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "..", "..", "contracts", "schemas");
const OUT = join(here, "..", "lib", "contracts");
const OUT_SCHEMAS = join(OUT, "schemas");

const files = readdirSync(SRC).filter((f) => f.endsWith(".schema.json")).sort();
const schemas = Object.fromEntries(files.map((f) => [f, JSON.parse(readFileSync(join(SRC, f), "utf8"))]));

// Copie des schémas.
rmSync(OUT_SCHEMAS, { recursive: true, force: true });
mkdirSync(OUT_SCHEMAS, { recursive: true });
for (const f of files) writeFileSync(join(OUT_SCHEMAS, f), JSON.stringify(schemas[f], null, 2) + "\n");

// Remplace chaque $ref "autre.schema.json" par un titre, pour que chaque type ne soit généré qu'une fois
// et que les fichiers se référencent par leur nom de type.
function inlineRefs(node) {
  if (Array.isArray(node)) return node.map(inlineRefs);
  if (node && typeof node === "object") {
    if (typeof node.$ref === "string" && schemas[node.$ref]) {
      return { tsType: schemas[node.$ref].title };
    }
    return Object.fromEntries(Object.entries(node).map(([k, v]) => [k, inlineRefs(v)]));
  }
  return node;
}

const banner =
  "/* Fichier GÉNÉRÉ par web/scripts/gen-contracts.mjs depuis contracts/schemas/. Ne pas éditer. */\n";
let out = banner;
for (const f of files) {
  const schema = inlineRefs(structuredClone(schemas[f]));
  delete schema.$id;
  const ts = await compile(schema, schema.title, {
    bannerComment: "",
    additionalProperties: false,
    declareExternallyReferenced: true,
    strictIndexSignatures: true,
    format: true,
    maxItems: -1,
  });
  out += `\n// ${f}\n${ts}`;
}
writeFileSync(join(OUT, "types.ts"), out);
console.log(`contracts: ${files.length} schémas → lib/contracts/types.ts et lib/contracts/schemas/`);
