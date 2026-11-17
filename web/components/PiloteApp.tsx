"use client";

// Interface utilisateur de Pilote : tout se fait à la voix ou au clavier, sans regarder l'écran.
//
// Raccourcis :
//   Barre d'espace maintenue : parler      Entrée : oui      N : non
//   Échap : annuler (à tout moment)        R : répéter la dernière phrase

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { earconForState, playEarcon, unlockAudio } from "./earcons";
import { CONFIRM_STATES, STATE_LABELS, formatCents, type ServerMessage } from "./protocol";
import { PushToTalkRecorder } from "./recorder";
import { Speaker } from "./speech";
import { usePilote } from "./usePilote";

// Obligatoire (AI Act, article 50). Normalement dit par l'orchestrateur à la connexion ;
// répété ici si sa phrase d'accueil n'a pas pu être jouée.
const AI_DISCLOSURE = "Je suis Pilote, un assistant automatique.";
const KEYBOARD_HELP =
  "Maintenez la barre d'espace pour me parler, et relâchez quand vous avez fini. " +
  "Entrée pour dire oui, N pour dire non, Échap pour annuler à tout moment, R pour répéter.";

// "voice" : Pilote parle lui-même. "screenreader" : Pilote se tait et laisse VoiceOver lire les annonces.
// Jamais les deux à la fois, sinon les deux voix se superposent.
type VoiceMode = "voice" | "screenreader";

export default function PiloteApp() {
  const [started, setStarted] = useState(false);
  const [recording, setRecording] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("voice");
  const [announce, setAnnounce] = useState("");
  const [micError, setMicError] = useState<string | null>(null);
  const [textInput, setTextInput] = useState("");

  const speakerRef = useRef<Speaker | null>(null);
  const recorderRef = useRef<PushToTalkRecorder | null>(null);
  const voiceModeRef = useRef<VoiceMode>("voice");
  const startedRef = useRef(false);

  useEffect(() => {
    const speaker = new Speaker();
    speaker.onChange = setSpeaking;
    speakerRef.current = speaker;
    recorderRef.current = new PushToTalkRecorder();
    return () => speaker.stop();
  }, []);

  useEffect(() => {
    voiceModeRef.current = voiceMode;
  }, [voiceMode]);

  // Une phrase à dire : à voix haute (mode voix) ou via la région ARIA live (mode lecteur d'écran)
  const tell = useCallback((text: string, audio?: string | null, mime?: string | null) => {
    if (voiceModeRef.current === "voice") speakerRef.current?.enqueue(text, audio, mime);
    else setAnnounce((prev) => (prev === text ? `${text} ` : text)); // force la relecture d'un texte identique
  }, []);

  const onMessage = useCallback(
    (msg: ServerMessage) => {
      // Avant le premier geste, le navigateur bloque le son : on gardera la phrase pour le démarrage.
      if (!startedRef.current) return;
      if (msg.type === "say") tell(msg.text, msg.audio, msg.mime);
      if (msg.type === "state") {
        const earcon = earconForState(msg.state);
        if (earcon) playEarcon(earcon);
      }
      if (msg.type === "error") playEarcon("error"); // l'explication arrive dans le say suivant
    },
    [tell]
  );

  const { connected, state, options, summary, lastSay, send } = usePilote(onMessage);
  const awaitingConfirm = CONFIRM_STATES.includes(state);

  const start = useCallback(() => {
    if (startedRef.current) return;
    unlockAudio(); // le navigateur n'autorise le son qu'après un geste de l'utilisateur
    startedRef.current = true;
    setStarted(true);
    const greeting = lastSay && lastSay.includes("assistant automatique") ? lastSay : `${AI_DISCLOSURE} ${lastSay}`;
    tell(greeting.trim());
    tell(KEYBOARD_HELP);
  }, [lastSay, tell]);

  const startTalking = useCallback(async () => {
    if (recorderRef.current?.isRecording) return;
    speakerRef.current?.stop(); // l'utilisateur peut couper la parole à Pilote
    setMicError(null);
    try {
      await recorderRef.current?.start();
      setRecording(true);
      playEarcon("listening");
    } catch {
      setMicError("Le micro n'est pas accessible. Autorisez-le dans le navigateur, ou utilisez le mode texte.");
      tell("Je n'ai pas accès au micro. Vérifiez l'autorisation du navigateur, ou utilisez le champ de texte.");
    }
  }, [tell]);

  const stopTalking = useCallback(async () => {
    if (!recorderRef.current?.isRecording) return;
    setRecording(false);
    const rec = await recorderRef.current.stop();
    if (!rec) return tell("C'était trop court. Maintenez la barre d'espace pendant que vous parlez.");
    if (!send({ type: "audio", data: rec.data, mime: rec.mime })) tell("Je ne suis pas connecté à Pilote pour le moment.");
  }, [send, tell]);

  const cancel = useCallback(() => {
    speakerRef.current?.stop();
    if (recorderRef.current?.isRecording) {
      void recorderRef.current.stop();
      setRecording(false);
    }
    send({ type: "cancel" });
  }, [send]);

  const confirm = useCallback(
    (value: boolean) => {
      speakerRef.current?.stop();
      send({ type: "confirm", value });
    },
    [send]
  );

  const repeat = useCallback(() => {
    if (!lastSay) return;
    speakerRef.current?.stop();
    tell(lastSay);
  }, [lastSay, tell]);

  // Raccourcis clavier globaux
  useEffect(() => {
    const isTyping = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    };
    const down = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        return cancel();
      }
      if (isTyping(e)) return;
      if (e.code === "Space") {
        e.preventDefault();
        if (e.repeat) return;
        if (!started) return start();
        void startTalking();
      } else if (!started) {
        return;
      } else if (e.key === "Enter" && awaitingConfirm) {
        e.preventDefault();
        confirm(true);
      } else if ((e.key === "n" || e.key === "N") && awaitingConfirm) {
        e.preventDefault();
        confirm(false);
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        repeat();
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space" && !isTyping(e)) {
        e.preventDefault();
        void stopTalking();
      }
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [started, awaitingConfirm, start, startTalking, stopTalking, cancel, confirm, repeat]);

  // Annonce de la perte et du retour de la connexion
  const wasConnected = useRef<boolean | null>(null);
  useEffect(() => {
    if (startedRef.current && wasConnected.current === true && !connected) {
      playEarcon("error");
      speakerRef.current?.enqueue("La connexion avec Pilote est coupée. Je réessaie.");
    }
    if (startedRef.current && wasConnected.current === false && connected) {
      speakerRef.current?.enqueue("La connexion est rétablie.");
    }
    wasConnected.current = connected;
  }, [connected]);

  const submitText = (e: FormEvent) => {
    e.preventDefault();
    const text = textInput.trim();
    if (!text) return;
    start();
    if (/^\s*annul/i.test(text)) cancel();
    else send({ type: "text", text });
    setTextInput("");
  };

  const talkLabel = !started
    ? "Démarrer Pilote"
    : recording
      ? "Je vous écoute… relâchez pour envoyer"
      : "Maintenir pour parler";

  return (
    <main className="pilote">
      <header className="pilote-header">
        <h1>Pilote</h1>
        <p className={`pilote-connection ${connected ? "is-on" : "is-off"}`}>
          {connected ? "Connecté" : "Connexion en cours…"}
        </p>
      </header>

      {/* Ce qui est annoncé au lecteur d'écran (mode lecteur d'écran uniquement) */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {voiceMode === "screenreader" ? announce : ""}
      </div>

      <section className="pilote-status" aria-label="Où en est la commande">
        <p className="pilote-state">{STATE_LABELS[state]}</p>
        <p className="pilote-lastsay">{lastSay || "Appuyez sur le bouton ou sur la barre d'espace pour commencer."}</p>
      </section>

      <button
        type="button"
        className={`pilote-talk ${recording ? "is-recording" : ""} ${speaking ? "is-speaking" : ""}`}
        aria-pressed={started ? recording : undefined}
        aria-describedby="pilote-help"
        onClick={() => {
          if (!started) start();
        }}
        onPointerDown={(e) => {
          if (!started) return;
          e.preventDefault();
          void startTalking();
        }}
        onPointerUp={() => void stopTalking()}
        onPointerLeave={() => void stopTalking()}
        onKeyDown={(e) => {
          // La barre d'espace est gérée globalement ; on évite le double déclenchement du bouton
          if (e.code === "Space") e.preventDefault();
        }}
        autoFocus
      >
        <span className="pilote-talk-icon" aria-hidden="true">{recording ? "●" : "🎙"}</span>
        <span>{talkLabel}</span>
      </button>

      <p id="pilote-help" className="pilote-help">
        Barre d&apos;espace maintenue : parler · Entrée : oui · N : non · Échap : annuler · R : répéter
      </p>

      {awaitingConfirm && (
        <div className="pilote-confirm" role="group" aria-label="Confirmer la commande">
          <button type="button" className="pilote-yes" onClick={() => confirm(true)}>
            Oui
          </button>
          <button type="button" className="pilote-no" onClick={() => confirm(false)}>
            Non
          </button>
        </div>
      )}

      {summary && (
        <section className="pilote-card" aria-label="Récapitulatif de la commande">
          <h2>Récapitulatif</h2>
          <ul>
            {summary.items.map((item, i) => (
              <li key={i}>
                {item.quantity} × {item.name}
                {item.options.length > 0 && ` (${item.options.join(", ")})`} — {formatCents(item.total_cents)}
              </li>
            ))}
            {summary.fees.map((fee, i) => (
              <li key={`fee-${i}`}>
                {fee.label} — {formatCents(fee.amount_cents)}
              </li>
            ))}
          </ul>
          <p>
            <strong>Total : {formatCents(summary.total_cents)}</strong>
            {summary.when_label && ` · ${summary.when_label}`}
          </p>
          {summary.conditions && <p>{summary.conditions}</p>}
        </section>
      )}

      {options.length > 0 && !summary && (
        <section className="pilote-card" aria-label="Options proposées">
          <h2>Options</h2>
          <ol>
            {options.slice(0, 3).map((o) => (
              <li key={o.id}>
                {o.title} — {formatCents(o.price_cents)}
              </li>
            ))}
          </ol>
        </section>
      )}

      <form className="pilote-text" onSubmit={submitText} aria-label="Mode texte de secours">
        <label htmlFor="pilote-text-input">Écrire au lieu de parler</label>
        <div>
          <input
            id="pilote-text-input"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Ex. : un train pour Lille demain après 14 h"
            autoComplete="off"
          />
          <button type="submit">Envoyer</button>
        </div>
      </form>

      {micError && (
        <p className="pilote-alert" role="alert">
          {micError}
        </p>
      )}

      <fieldset className="pilote-settings">
        <legend>Qui lit les réponses ?</legend>
        <label>
          <input type="radio" name="voice-mode" checked={voiceMode === "voice"} onChange={() => setVoiceMode("voice")} />
          La voix de Pilote
        </label>
        <label>
          <input
            type="radio"
            name="voice-mode"
            checked={voiceMode === "screenreader"}
            onChange={() => {
              speakerRef.current?.stop();
              setVoiceMode("screenreader");
            }}
          />
          Mon lecteur d&apos;écran (VoiceOver)
        </label>
        <Link href="/spectateur" target="_blank" rel="noreferrer">
          Ouvrir l&apos;écran spectateur
        </Link>
      </fieldset>
    </main>
  );
}
