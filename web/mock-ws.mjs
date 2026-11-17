// Faux orchestrateur Pilote : rejoue un parcours complet de commande de train.
// Lancer : npm run mock   (écoute sur ws://localhost:8000/ws)
//
// Il suit le contrat du plan (say, state, options, summary, error) et envoie aussi
// les messages PROPOSITION (transcript, agent_view, human_needed) décrits dans components/protocol.ts.
// Tous les écrans connectés (interface + spectateur) reçoivent les mêmes messages.
//
// Pilotage en mode texte (champ de secours) :
//   - n'importe quelle phrase  → nouvelle commande
//   - "le deuxième" / "2"      → choisit l'option 2 (sinon la 1)
//   - "oui" / "non"            → confirme ou refuse
//   - "annule"                 → annule à tout moment
//   - phrase contenant "captcha" → simule un blocage qui demande un humain
// Un message audio est traité comme la réponse la plus probable à l'étape en cours.

import { WebSocketServer } from "ws";

const PORT = Number(process.env.MOCK_WS_PORT ?? 8000);
const wss = new WebSocketServer({ port: PORT, path: "/ws" });

const OPTIONS = [
  { id: "t1", title: "TGV INOUI 14 h 12, direct, arrivée 15 h 15", price_eur: 42, rating: null, details: "Direct, 1 h 03, voiture 12 calme possible", url: null },
  { id: "t2", title: "TGV INOUI 14 h 46, direct, arrivée 15 h 49", price_eur: 37, rating: null, details: "Direct, 1 h 03", url: null },
  { id: "t3", title: "OUIGO 15 h 10, direct, arrivée 16 h 18", price_eur: 25, rating: null, details: "Direct, 1 h 08, bagage cabine seulement", url: null },
  { id: "t4", title: "TER 14 h 31, une correspondance, arrivée 17 h 02", price_eur: 31.5, rating: null, details: "Correspondance à Arras", url: null },
];

let state = "listening";
let options = [];
let summary = null;
let agentView = null;
let run = 0; // incrémenté à chaque annulation : les étapes en attente d'un ancien parcours s'arrêtent

const broadcast = (msg) => {
  const data = JSON.stringify(msg);
  for (const client of wss.clients) if (client.readyState === 1) client.send(data);
};
const setState = (s) => { state = s; broadcast({ type: "state", state: s }); };
const say = (text) => broadcast({ type: "say", text, audio: null });
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
}

async function newOrder(text) {
  const myRun = ++run;
  options = [];
  summary = null;
  agentView = null;
  broadcast({ type: "transcript", text: text || "Un train pour Lille demain après 14 heures." });
  setState("understanding");
  await step(myRun, 900, () => say("D'accord, je cherche un train de Paris à Lille demain après 14 heures."));
  await step(myRun, 600, () => {
    setState("searching");
    agentView = "https://example.com/vue-agent-h-demo";
    broadcast({ type: "agent_view", url: agentView });
  });
  if (/captcha/i.test(text)) {
    await step(myRun, 2500, () => {
      setState("human_needed");
      broadcast({ type: "human_needed", reason: "Le site affiche une vérification anti-robot." });
      say("Le site me demande une vérification anti-robot. Un humain doit intervenir. Je mets la commande en pause.");
    });
    return;
  }
  await step(myRun, 2500, () => say("Je cherche toujours, le site est un peu lent."));
  await step(myRun, 2500, () => {
    options = OPTIONS;
    broadcast({ type: "options", options });
    setState("proposing");
    say(
      "J'ai trouvé 4 trains. Les trois premiers : " +
        "un, 14 heures 12, direct, 42 euros. " +
        "Deux, 14 heures 46, direct, 37 euros. " +
        "Trois, 15 heures 10, Ouigo, 25 euros. " +
        "Lequel voulez-vous ? Vous pouvez aussi demander les détails."
    );
  });
}

async function chooseOption(text) {
  const myRun = run;
  const n = /deux|2|second/i.test(text) ? 1 : /trois|3/i.test(text) ? 2 : 0;
  const choice = options[n] ?? OPTIONS[0];
  broadcast({ type: "transcript", text: text || `Le ${["premier", "deuxième", "troisième"][n]}.` });
  setState("cart");
  await step(myRun, 1500, () => {
    summary = {
      order_id: `demo-${Date.now()}`,
      site: "SNCF Connect (démo)",
      items: [{ title: choice.title, quantity: 1, price_eur: choice.price_eur }],
      fees_eur: 0,
      total_eur: choice.price_eur,
      delivery: "E-billet dans l'application",
      refund_terms: "Échangeable et remboursable sans frais jusqu'à 3 jours avant le départ",
      hash: "abc123",
    };
    broadcast({ type: "summary", summary });
    setState("confirm_1");
    say(
      `J'ai mis dans le panier le ${choice.title}, pour ${String(choice.price_eur).replace(".", ",")} euros, sans frais. ` +
        "Le billet est échangeable et remboursable jusqu'à 3 jours avant le départ. " +
        "Dites oui pour demander la validation à votre proche, ou non pour annuler."
    );
  });
}

async function afterConfirm1() {
  const myRun = run;
  setState("awaiting_relative");
  say("J'ai envoyé la demande à Camille par SMS. J'attends sa réponse.");
  await step(myRun, 6000, () => say("Camille a validé."));
  await step(myRun, 500, () => setState("recheck"));
  await step(myRun, 1800, () => {
    setState("confirm_2");
    say(`J'ai relu la page de paiement : rien n'a changé, le total est de ${String(summary.total_eur).replace(".", ",")} euros. Dites oui pour payer.`);
  });
}

async function pay() {
  const myRun = run;
  setState("paying");
  say("Je lance le paiement.");
  await step(myRun, 2500, () => {
    setState("done");
    say("La banque a refusé le paiement, car la carte de démonstration est vide. Tout le parcours a fonctionné, et aucun argent n'est parti.");
  });
}

const isYes = (t) => /\b(oui|ok|d'accord|vas-y|valide)\b/i.test(t);
const isNo = (t) => /\b(non|stop)\b/i.test(t);

async function handle(msg) {
  if (msg.type === "hello") return;
  if (msg.type === "cancel") return cancel();

  const text = msg.type === "text" ? msg.text.trim() : "";
  const isAudio = msg.type === "audio";
  if (/annul/i.test(text)) return cancel();

  if (isAudio) console.log(`audio reçu : ${Math.round((msg.data?.length ?? 0) * 0.75 / 1024)} Ko, format ${msg.mime ?? "non précisé"}`);

  // Réponse oui / non
  if (state === "confirm_1" || state === "confirm_2") {
    const yes = msg.type === "confirm" ? msg.value : isAudio ? true : isYes(text) ? true : isNo(text) ? false : null;
    if (yes === null) return say("Je n'ai pas compris. Dites oui ou non.");
    if (text) broadcast({ type: "transcript", text });
    if (isAudio) broadcast({ type: "transcript", text: "Oui." });
    if (!yes) return cancel();
    return state === "confirm_1" ? afterConfirm1() : pay();
  }

  if (msg.type === "confirm") return; // rien à confirmer pour l'instant

  if (state === "proposing") return chooseOption(text);

  if (["listening", "done", "cancelled", "human_needed"].includes(state)) return newOrder(text);

  say("Un instant, je n'ai pas fini l'étape en cours.");
}

wss.on("connection", (ws) => {
  // Remet l'écran qui se connecte à jour
  ws.send(JSON.stringify({ type: "state", state }));
  if (options.length) ws.send(JSON.stringify({ type: "options", options }));
  if (summary) ws.send(JSON.stringify({ type: "summary", summary }));
  if (agentView) ws.send(JSON.stringify({ type: "agent_view", url: agentView }));

  ws.on("message", (raw) => {
    let msg;
    try { msg = JSON.parse(raw.toString()); } catch { return; }
    console.log("←", msg.type, msg.type === "audio" ? "" : JSON.stringify(msg));
    handle(msg).catch((e) => { if (e.message !== "annulé") console.error(e); });
  });
});

console.log(`Faux orchestrateur Pilote prêt sur ws://localhost:${PORT}/ws`);
