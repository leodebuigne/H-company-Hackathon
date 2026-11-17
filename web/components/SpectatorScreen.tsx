"use client";

// Écran spectateur pour le jury : lisible depuis le fond de la salle.
// Il ne fait que regarder : il n'envoie aucune commande et ne parle pas.

import { useEffect, useRef } from "react";
import { STATE_LABELS, formatCents, type ApprovalStatus, type Intent, type State } from "./protocol";
import { usePilote } from "./usePilote";

const STEPS: { states: State[]; label: string }[] = [
  { states: ["listening", "understanding"], label: "Écoute" },
  { states: ["searching", "proposing"], label: "Recherche" },
  { states: ["cart", "confirm_1"], label: "Panier · 1er oui" },
  { states: ["awaiting_relative"], label: "Validation du proche" },
  { states: ["recheck", "confirm_2"], label: "Relecture · 2e oui" },
  { states: ["paying", "done"], label: "Paiement" },
];

/** « billet de train · Paris → Lille · 2026-11-18 après 14:00 » */
function describeIntent(intent: Intent): string {
  const parts: string[] = [];
  if (intent.object) parts.push(intent.quantity ? `${intent.quantity} × ${intent.object}` : intent.object);
  const { origin, destination } = intent.details;
  if (origin || destination) parts.push(`${origin ?? "?"} → ${destination ?? "?"}`);
  const w = intent.when;
  const when = [w.date, w.after && `après ${w.after}`, w.before && `avant ${w.before}`, w.asap && "au plus vite"]
    .filter(Boolean)
    .join(" ");
  if (when) parts.push(when);
  if (intent.budget_cents != null) parts.push(`budget ${formatCents(intent.budget_cents)}`);
  parts.push(...intent.constraints);
  return parts.join(" · ") || intent.text;
}

function describeApproval(a: ApprovalStatus): { text: string; cls: string } {
  switch (a.status) {
    case "pending":
      return { text: `En attente du proche ${a.current_relative ?? "?"} sur ${a.relatives_count}`, cls: "is-pending" };
    case "approved":
      return { text: `Validé par ${a.decided_by ?? "un proche"}`, cls: "is-approved" };
    case "denied":
      return { text: `Refusé par ${a.decided_by ?? "un proche"}`, cls: "is-denied" };
    case "expired":
      return { text: "Aucun proche n'a répondu à temps", cls: "is-denied" };
  }
}

export default function SpectatorScreen() {
  const { connected, state, intent, options, summary, approval, log, agentViewUrl, lastSay } = usePilote();
  const current = STEPS.findIndex((s) => s.states.includes(state));
  const logBox = useRef<HTMLElement>(null);

  // Fait défiler la conversation seule, sans déplacer le reste de l'écran
  useEffect(() => {
    const box = logBox.current;
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [log.length]);

  const banner =
    state === "done"
      ? { cls: "is-done", text: lastSay || "Parcours terminé" }
      : state === "cancelled"
        ? { cls: "is-cancelled", text: "Commande annulée — rien n'a été payé" }
        : state === "human_needed"
          ? { cls: "is-human", text: `Un humain doit intervenir${lastSay ? ` : ${lastSay}` : ""}` }
          : null;

  const approvalInfo = approval ? describeApproval(approval) : null;

  return (
    <main className="spectator">
      <header className="spectator-header">
        <h1>
          Pilote <span>· vue jury</span>
        </h1>
        <p className={`pilote-connection ${connected ? "is-on" : "is-off"}`}>
          {connected ? "En direct" : "Connexion en cours…"}
        </p>
      </header>

      <ol className="spectator-steps" aria-label="Étapes de la commande">
        {STEPS.map((step, i) => (
          <li
            key={step.label}
            className={i < current ? "is-past" : i === current ? "is-current" : ""}
            aria-current={i === current ? "step" : undefined}
          >
            {step.label}
          </li>
        ))}
      </ol>

      <p className="spectator-state">{STATE_LABELS[state]}</p>
      {banner && <p className={`spectator-banner ${banner.cls}`}>{banner.text}</p>}
      {intent && <p className="spectator-intent">Compris : {describeIntent(intent)}</p>}

      <div className="spectator-grid">
        <section ref={logBox} className="spectator-panel spectator-log" aria-label="Conversation">
          <h2>Conversation</h2>
          {log.length === 0 && <p className="muted">En attente de la première demande…</p>}
          {log.slice(-12).map((e) => (
            <p key={e.id} className={`bubble bubble-${e.who}`}>
              <strong>{e.who === "user" ? "Utilisateur" : e.who === "pilote" ? "Pilote" : "Erreur"}</strong>
              {e.text}
            </p>
          ))}
        </section>

        <div className="spectator-side">
          {summary ? (
            <section className="spectator-panel" aria-label="Récapitulatif">
              <h2>Récapitulatif · {summary.site}</h2>
              <ul className="spectator-items">
                {summary.items.map((item, i) => (
                  <li key={i}>
                    {item.quantity} × {item.name}
                  </li>
                ))}
              </ul>
              <p className="spectator-total">{formatCents(summary.total_cents)}</p>
              <p className="muted">
                {summary.fees.length > 0
                  ? summary.fees.map((f) => `${f.label} ${formatCents(f.amount_cents)}`).join(" · ")
                  : "Sans frais"}
                {summary.conditions ? ` · ${summary.conditions}` : ""}
              </p>
            </section>
          ) : (
            <section className="spectator-panel" aria-label="Options">
              <h2>Options trouvées</h2>
              {options.length === 0 && <p className="muted">Aucune pour l&apos;instant</p>}
              <ol className="spectator-options">
                {options.slice(0, 3).map((o) => (
                  <li key={o.id}>
                    <span>{o.title}</span>
                    <strong>{formatCents(o.price_cents)}</strong>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {approvalInfo && (
            <section className="spectator-panel" aria-label="Validation du proche">
              <h2>Validation du proche</h2>
              <p className={`spectator-approval ${approvalInfo.cls}`}>{approvalInfo.text}</p>
            </section>
          )}

          <section className="spectator-panel" aria-label="Vue de l'agent H">
            <h2>Agent H en direct</h2>
            {agentViewUrl ? (
              <a className="spectator-agent" href={agentViewUrl} target="_blank" rel="noreferrer">
                Ouvrir la vue en direct de l&apos;agent ↗
              </a>
            ) : (
              <p className="muted">Le lien apparaît quand l&apos;agent démarre</p>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
