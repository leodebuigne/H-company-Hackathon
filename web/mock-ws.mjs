// Faux orchestrateur Pilote : rejoue une commande de train complète, au format du contrat
// (contracts/README.md). Chaque message envoyé ou reçu est vérifié contre le schéma
// ws-message : une erreur de format s'affiche dans le terminal.
//
// Lancer : npm run mock   (écoute sur ws://localhost:8000/ws)
//
// Pilotage en mode texte (champ de secours) :
//   - n'importe quelle phrase    → nouvelle commande
//   - « le deuxième » / « 2 »    → choisit l'option 2 (sinon la 1)
//   - « oui » / « non »          → confirme ou refuse (comme Entrée / N)
//   - « annule »                 → annule à tout moment (comme Échap)
//   - phrase contenant « captcha » → simule un blocage qui demande un humain
// Un message audio est traité comme la réponse la plus probable à l'étape en cours.

import { randomUUID } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { WebSocketServer } from "ws";

// ───── Vérification contre le contrat ─────
const schemaDir = join(dirname(fileURLToPath(import.meta.url)), "lib/contracts/schemas");
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
let wsSchemaId;
for (const file of readdirSync(schemaDir).filter((f) => f.endsWith(".json"))) {
  const schema = JSON.parse(readFileSync(join(schemaDir, file), "utf8"));
  ajv.addSchema(schema);
  if (file === "ws-message.schema.json") wsSchemaId = schema.$id;
}
const checkWs = ajv.getSchema(wsSchemaId);
/** Vérifie un message ; renvoie false (et l'affiche) s'il est hors contrat. */
const report = (dir, msg) => {
  if (checkWs(msg)) return true;
  const first = checkWs.errors.find((e) => e.keyword !== "const" && e.keyword !== "oneOf") ?? checkWs.errors[0];
  console.error(`✗ message ${dir} hors contrat (type « ${msg?.type} ») : ${first.instancePath || "/"} ${first.message}`);
  return false;
};

// ───── Données de démonstration ─────
const PORT = Number(process.env.MOCK_WS_PORT ?? 8000);
const SITE = "h-company-hackathon-rail-demo.vercel.app";
const now = () => new Date().toISOString();
const fakeHash = () => randomUUID().replace(/-/g, "").repeat(2);

const option = (rank, departure, arrival, via, price_cents, conditions) => ({
  id: `opt-${rank}`,
  rank,
  title: `Train de ${departure.replace(":", " h ")}, ${via}`,
  price_cents,
  currency: "EUR",
  rating: null,
  description: null,
  conditions,
  details: { departure, arrival, via },
  url: null,
});

const OPTIONS = [
  option(1, "14:12", "15:15", "direct", 4200, "Échangeable et remboursable sans frais"),
  option(2, "14:27", "15:31", "direct", 4300, "Échangeable et remboursable (frais de 5 €)"),
  option(3, "15:10", "16:18", "direct", 2500, "Ni échangeable ni remboursable"),
  option(4, "14:31", "17:02", "une correspondance à Arras", 3150, null),
];

const INTENT = (text) => ({
  kind: "new_request",
  text,
  category: "train",
  object: "billet de train",
  quantity: 1,
  when: { date: new Date(Date.now() + 86400000).toISOString().slice(0, 10), after: "14:00", before: null, asap: false },
  budget_cents: null,
  details: { origin: "Paris", destination: "Lille" },
  constraints: [],
  choice_index: null,
  missing: [],
  question: null,
});

const euros = (cents) => (cents / 100).toLocaleString("fr-FR", { minimumFractionDigits: cents % 100 ? 2 : 0 }) + " euros";

// ───── Session (partagée par l'interface et l'écran jury) ─────
let state = "listening";
let options = [];
let summary = null;
let agentView = null;
let run = 0; // incrémenté à chaque annulation : les étapes d'un ancien parcours s'arrêtent

const wss = new WebSocketServer({ port: PORT, path: "/ws" });

const broadcast = (msg) => {
  report("envoyé", msg);
  const data = JSON.stringify(msg);
  for (const client of wss.clients) if (client.readyState === 1) client.send(data);
};
const setState = (s) => {
  state = s;
  broadcast({ type: "state", state: s });
};
const say = (text) => {
  broadcast({ type: "say", text, audio: null, mime: null });
  broadcast({ type: "transcript", role: "pilote", text });
};
const heard = (text) => broadcast({ type: "transcript", role: "user", text });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function step(myRun, ms, fn) {
  await wait(ms);
  if (myRun !== run) throw new Error("annulé");
  fn();
}

function cancel() {
  run++;
  summary = null;
  setState("cancelled");
  say("Commande annulée. Rien n'a été payé.");
  setTimeout(() => state === "cancelled" && setState("listening"), 800);
}

async function newOrder(text) {
  const myRun = ++run;
  options = [];
  summary = null;
  agentView = null;
  const phrase = text || "Je voudrais un train pour Lille demain après 14 h";
  setState("understanding");
  heard(phrase);
  await step(myRun, 900, () => broadcast({ type: "intent", intent: INTENT(phrase) }));
  await step(myRun, 400, () => {
    say("D'accord, je cherche un train de Paris à Lille demain après 14 heures.");
    setState("searching");
    agentView = "https://example.com/vue-agent-h-demo";
    broadcast({ type: "agent_view", agent_view_url: agentView });
  });
  if (/captcha/i.test(phrase)) {
    await step(myRun, 2500, () => {
      setState("human_needed");
      say("Le site me demande une vérification anti-robot. Un humain doit intervenir. Je mets la commande en pause.");
    });
    return;
  }
  await step(myRun, 2500, () => say("Je cherche toujours, le site est un peu lent."));
  await step(myRun, 2500, () => {
    options = OPTIONS;
    broadcast({ type: "options", options });
    say(
      `J'ai trouvé ${OPTIONS.length} trains. Les trois premiers : ` +
        OPTIONS.slice(0, 3)
          .map((o) => `${o.rank}, ${o.details.departure.replace(":", " heures ")}, ${o.details.via}, ${euros(o.price_cents)}.`)
          .join(" ") +
        " Lequel voulez-vous ?"
    );
    setState("proposing");
  });
}

async function chooseOption(text) {
  const myRun = run;
  const n = /deux|2|second/i.test(text) ? 1 : /trois|3/i.test(text) ? 2 : 0;
  const choice = options[n] ?? OPTIONS[0];
  heard(text || ["Le premier.", "Le deuxième.", "Le troisième."][n]);
  setState("cart");
  await step(myRun, 1500, () => {
    summary = {
      order_id: randomUUID(),
      site: SITE,
      page_url: `https://${SITE}/paiement.html`,
      items: [{ name: `Paris → Lille, ${choice.title}`, quantity: 1, unit_price_cents: choice.price_cents, total_cents: choice.price_cents, options: ["2de classe"] }],
      fees: [],
      total_cents: choice.price_cents,
      currency: "EUR",
      when_label: `Demain, départ ${choice.details.departure.replace(":", " h ")}, arrivée ${choice.details.arrival.replace(":", " h ")}`,
      conditions: choice.conditions,
      payment_button_label: "Payer",
      hash: fakeHash(),
      read_at: now(),
    };
    broadcast({ type: "summary", summary });
    say(
      `J'ai mis dans le panier le ${choice.title}, pour ${euros(choice.price_cents)}, sans frais. ` +
        (choice.conditions ? `${choice.conditions}. ` : "") +
        "Dites oui pour demander la validation à votre proche, ou non pour annuler."
    );
    setState("confirm_1");
  });
}

const approval = (status, extra = {}) => ({
  type: "approval",
  status: {
    order_id: summary.order_id,
    status,
    current_relative: status === "pending" ? 1 : null,
    relatives_count: 2,
    decided_by: null,
    decided_at: null,
    expires_at: status === "pending" ? new Date(Date.now() + 300000).toISOString() : null,
    updated_at: now(),
    ...extra,
  },
});

async function afterConfirm1() {
  const myRun = run;
  setState("awaiting_relative");
  broadcast(approval("pending"));
  say("J'ai envoyé la demande à Léa par SMS. J'attends sa réponse.");
  await step(myRun, 6000, () => broadcast(approval("approved", { decided_by: "Léa", decided_at: now() })));
  await step(myRun, 300, () => setState("recheck"));
  await step(myRun, 1800, () => {
    summary = { ...summary, read_at: now() };
    broadcast({ type: "summary", summary });
    say(`Léa a validé. J'ai relu la page de paiement : rien n'a changé, le total est de ${euros(summary.total_cents)}. Je paie ?`);
    setState("confirm_2");
  });
}

async function pay() {
  const myRun = run;
  setState("paying");
  say("Je lance le paiement.");
  await step(myRun, 2500, () => {
    say("La banque a refusé le paiement, car la carte de démonstration est vide. Tout le parcours a fonctionné, et aucun argent n'est parti.");
    setState("done");
  });
}

const isYes = (t) => /\b(oui|ok|d'accord|vas-y|valide)\b/i.test(t);
const isNo = (t) => /\b(non|stop)\b/i.test(t);

async function handle(msg) {
  if (msg.type === "cancel") return cancel();

  const text = msg.type === "text" ? msg.text.trim() : "";
  const isAudio = msg.type === "audio";
  if (isAudio) console.log(`  audio reçu : ${Math.round((msg.data.length * 0.75) / 1024)} Ko, ${msg.mime}`);
  if (/annul/i.test(text)) {
    heard(text);
    return cancel();
  }

  if (state === "confirm_1" || state === "confirm_2") {
    const yes = msg.type === "confirm" ? msg.value : isAudio ? true : isYes(text) ? true : isNo(text) ? false : null;
    if (yes === null) {
      heard(text);
      return say("Je n'ai pas compris. Dites oui ou non.");
    }
    if (msg.type !== "confirm") heard(text || "Oui.");
    if (!yes) return cancel();
    return state === "confirm_1" ? afterConfirm1() : pay();
  }

  if (msg.type === "confirm") {
    if (state === "proposing") return chooseOption(msg.value ? "le premier" : "");
    return; // rien à confirmer pour l'instant
  }

  if (state === "proposing") return chooseOption(text);
  if (["listening", "done", "cancelled", "human_needed"].includes(state)) return newOrder(text);
  say("Un instant, je n'ai pas fini l'étape en cours.");
}

wss.on("connection", (ws) => {
  const send = (msg) => {
    report("envoyé", msg);
    ws.send(JSON.stringify(msg));
  };
  send({ type: "ready", session_id: randomUUID() });
  send({ type: "state", state });
  if (state === "listening") {
    send({ type: "say", text: "Je suis Pilote, un assistant automatique. Que voulez-vous commander ?", audio: null, mime: null });
  }
  // Remet à jour un écran qui se connecte en cours de route
  if (options.length) send({ type: "options", options });
  if (summary) send({ type: "summary", summary });
  if (agentView) send({ type: "agent_view", agent_view_url: agentView });

  ws.on("message", (raw) => {
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return console.error("✗ message reçu illisible");
    }
    if (!report("reçu", msg)) return; // ignoré, comme le fera le vrai orchestrateur
    console.log("←", msg.type, msg.type === "audio" ? "" : JSON.stringify(msg));
    handle(msg).catch((e) => {
      if (e.message !== "annulé") console.error(e);
    });
  });
});

console.log(`Faux orchestrateur Pilote prêt sur ws://localhost:${PORT}/ws (messages vérifiés contre le contrat)`);
