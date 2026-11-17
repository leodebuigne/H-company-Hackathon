"use client";

// Écran spectateur pour le jury : lisible depuis le fond de la salle.
// Il ne fait que regarder : il n'envoie aucune commande et ne parle pas.

import { useEffect, useRef } from "react";
import { STATE_LABELS, formatEuros, type OrderState } from "./protocol";
import { usePilote } from "./usePilote";

const STEPS: { states: OrderState[]; label: string }[] = [
  { states: ["listening", "understanding"], label: "Écoute" },
  { states: ["searching", "proposing"], label: "Recherche" },
  { states: ["cart", "confirm_1"], label: "Panier · 1er oui" },
  { states: ["awaiting_relative"], label: "Validation du proche" },
  { states: ["recheck", "confirm_2"], label: "Relecture · 2e oui" },
  { states: ["paying", "done"], label: "Paiement" },
];

export default function SpectatorScreen() {
  const { connected, state, options, summary, log, agentViewUrl, humanReason } = usePilote("spectator");
  const current = STEPS.findIndex((s) => s.states.includes(state));
  const logBox = useRef<HTMLElement>(null);

  // Fait défiler la conversation seule, sans déplacer le reste de l'écran
  useEffect(() => {
    const box = logBox.current;
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [log.length]);

  const banner =
    state === "done"
      ? { cls: "is-done", text: "Parcours terminé — paiement refusé par la banque (carte de démo à 0 €)" }
      : state === "cancelled"
        ? { cls: "is-cancelled", text: "Commande annulée — rien n'a été payé" }
        : state === "human_needed"
          ? { cls: "is-human", text: `Intervention humaine : ${humanReason ?? "en attente"}` }
          : null;

  return (
    <main className="spectator">
      <header className="spectator-header">
        <h1>Pilote <span>· vue jury</span></h1>
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

      <div className="spectator-grid">
        <section ref={logBox} className="spectator-panel spectator-log" aria-label="Conversation">
          <h2>Conversation</h2>
          {log.length === 0 && <p className="muted">En attente de la première demande…</p>}
          {log.slice(-12).map((e) => (
            <p key={e.id} className={`bubble bubble-${e.who}`}>
              <strong>{e.who === "user" ? "Utilisateur" : e.who === "pilote" ? "Pilote" : "Système"}</strong>
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
                    {item.quantity} × {item.title}
                  </li>
                ))}
              </ul>
              <p className="spectator-total">{formatEuros(summary.total_eur)}</p>
              <p className="muted">
                dont frais {formatEuros(summary.fees_eur)}
                {summary.refund_terms ? ` · ${summary.refund_terms}` : ""}
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
                    <strong>{formatEuros(o.price_eur)}</strong>
                  </li>
                ))}
              </ol>
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
