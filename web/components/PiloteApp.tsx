"use client";

// Interface utilisateur de Pilote : tout se fait à la voix ou au clavier, sans regarder l'écran.
//
// Raccourcis :
//   Barre d'espace (une fois ou maintenue) : parler     Entrée : oui      N : non
//   Échap : annuler (à tout moment)        R : répéter la dernière phrase

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type FormEvent,
} from "react";
import { earconForState, playEarcon, unlockAudio } from "./earcons";
import {
  BUY_STATES,
  BUSY_STATES,
  CONFIRM_STATES,
  ORDINALS,
  STATE_LABELS,
  STEPS,
  formatCents,
  type ServerMessage,
} from "./protocol";
import { PushToTalkRecorder, RELEASE_TAIL_MS } from "./recorder";
import { Speaker, listFrenchVoices, setBrowserVoice } from "./speech";
import { usePilote } from "./usePilote";

// Obligatoire (AI Act, article 50). Normalement dit par l'orchestrateur à la connexion ;
// répété ici si sa phrase d'accueil n'a pas pu être jouée.
const AI_DISCLOSURE = "Je suis Pilote, un assistant automatique.";
const KEYBOARD_HELP =
  "Appuyez une fois sur la barre d'espace, puis parlez : je réponds quand vous vous taisez. " +
  "Entrée pour dire oui, N pour dire non, Échap pour annuler à tout moment, R pour répéter.";

// "voice" : Pilote parle lui-même. "screenreader" : Pilote se tait et laisse VoiceOver lire les annonces.
// Jamais les deux à la fois, sinon les deux voix se superposent.
type VoiceMode = "voice" | "screenreader";

// Appui plus court que ça = « appuyer une fois puis parler » : Pilote écoute et s'arrête quand on se tait.
const TAP_MS = 450;
const HANDS_FREE = { silenceMs: 1600, noSpeechMs: 7000, maxMs: 30000 };

// Réglages gardés dans ce navigateur seulement (aucune donnée personnelle).
const PREFS_KEY = "pilote-prefs";
type Prefs = { rate: number; browserVoice: string | null };
const DEFAULT_PREFS: Prefs = { rate: 1.1, browserVoice: null };

function loadPrefs(): Prefs {
  try {
    const raw = window.localStorage.getItem(PREFS_KEY);
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS;
  }
}

function savePrefs(prefs: Prefs) {
  try {
    window.localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // navigation privée : les réglages valent pour cette page seulement
  }
}

// Petit store : le serveur rend les réglages par défaut, le navigateur ceux enregistrés, sans décalage.
let cachedPrefs: Prefs | null = null;
const prefListeners = new Set<() => void>();
const getPrefs = () => (cachedPrefs ??= loadPrefs());
const getServerPrefs = () => DEFAULT_PREFS;
function subscribePrefs(listener: () => void) {
  prefListeners.add(listener);
  return () => {
    prefListeners.delete(listener);
  };
}
function writePrefs(patch: Partial<Prefs>): Prefs {
  cachedPrefs = { ...getPrefs(), ...patch };
  savePrefs(cachedPrefs);
  prefListeners.forEach((listener) => listener());
  return cachedPrefs;
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="56" height="56" aria-hidden="true" focusable="false">
      <rect x="8.5" y="2.5" width="7" height="12" rx="3.5" fill="currentColor" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3.5M8.5 21.5h7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function SpeakingBars({ active }: { active: boolean }) {
  return (
    <span className={`pilote-bars ${active ? "is-active" : ""}`} aria-hidden="true">
      <i />
      <i />
      <i />
      <i />
    </span>
  );
}

export default function PiloteApp() {
  const [started, setStarted] = useState(false);
  const [recording, setRecording] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("voice");
  const [announce, setAnnounce] = useState("");
  const [micError, setMicError] = useState<string | null>(null);
  const [textInput, setTextInput] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const prefs = useSyncExternalStore(subscribePrefs, getPrefs, getServerPrefs);
  const [voices, setVoices] = useState<string[]>([]);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const speakerRef = useRef<Speaker | null>(null);
  const recorderRef = useRef<PushToTalkRecorder | null>(null);
  const voiceModeRef = useRef<VoiceMode>("voice");
  const startedRef = useRef(false);
  const pressedAtRef = useRef(0);
  const handsFreeRef = useRef(false);

  useEffect(() => {
    const speaker = new Speaker();
    speaker.onChange = setSpeaking;
    speakerRef.current = speaker;
    recorderRef.current = new PushToTalkRecorder();
    const saved = getPrefs();
    speaker.rate = saved.rate;
    setBrowserVoice(saved.browserVoice);
    // La liste des voix arrive parfois après le chargement de la page
    const refresh = () => setVoices(listFrenchVoices());
    refresh();
    const timer = setTimeout(refresh, 800);
    return () => {
      clearTimeout(timer);
      speaker.stop();
    };
  }, []);

  useEffect(() => {
    voiceModeRef.current = voiceMode;
  }, [voiceMode]);

  const updatePrefs = (patch: Partial<Prefs>) => {
    const next = writePrefs(patch);
    if (speakerRef.current) speakerRef.current.rate = next.rate;
    setBrowserVoice(next.browserVoice);
  };

  // Une phrase à dire : à voix haute (mode voix) ou via la région ARIA live (mode lecteur d'écran)
  // Une seule page Pilote parle à la fois : la dernière démarrée prévient les autres, qui se taisent.
  // Et une page cachée (onglet en arrière-plan) ne parle pas. Évite la voix en double (18/11).
  const mutedRef = useRef(false);
  const channelRef = useRef<BroadcastChannel | null>(null);
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel("pilote-voix");
    channel.onmessage = (event) => {
      if (event.data === "je-parle") {
        mutedRef.current = true;
        speakerRef.current?.stop();
      }
    };
    channelRef.current = channel;
    return () => channel.close();
  }, []);

  const tell = useCallback((text: string, audio?: string | null, mime?: string | null) => {
    if (voiceModeRef.current === "voice") {
      if (mutedRef.current || document.visibilityState !== "visible") return;
      speakerRef.current?.enqueue(text, audio, mime);
    } else setAnnounce((prev) => (prev === text ? `${text} ` : text)); // force la relecture d'un texte identique
  }, []);

  const onMessage = useCallback(
    (msg: ServerMessage) => {
      if (msg.type === "state") setBusySince(BUSY_STATES.includes(msg.state) ? Date.now() : null);
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

  const { connected, state, options, summary, lastSay, log, send } = usePilote(onMessage);
  // Pilote demande le code secret à 3 chiffres (même état que la confirmation, voir session._check_code)
  const askingCode = state === "confirm_1" && /code à 3 chiffres|bon code|votre code/i.test(lastSay);
  const awaitingConfirm = CONFIRM_STATES.includes(state) && !askingCode;
  const busy = BUSY_STATES.includes(state);
  const currentStep = STEPS.findIndex((s) => s.states.includes(state));

  // Compteur « depuis 42 s » pendant que Pilote travaille seul
  useEffect(() => {
    if (busySince === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [busySince]);
  const elapsed = busySince !== null ? Math.max(0, Math.round((now - busySince) / 1000)) : 0;

  const start = useCallback(() => {
    if (startedRef.current) return;
    unlockAudio(); // le navigateur n'autorise le son qu'après un geste de l'utilisateur
    startedRef.current = true;
    mutedRef.current = false;
    channelRef.current?.postMessage("je-parle"); // les autres pages Pilote se taisent
    setStarted(true);
    const greeting = lastSay && lastSay.includes("assistant automatique") ? lastSay : `${AI_DISCLOSURE} ${lastSay}`;
    tell(greeting.trim());
    tell(KEYBOARD_HELP);
  }, [lastSay, tell]);

  // Envoie ce qui a été enregistré (ou l'abandonne si rien n'a été dit)
  const finishTalking = useCallback(
    async (reason: "release" | "silence" | "no_speech" | "max" | "tap") => {
      const rec = recorderRef.current;
      if (!rec?.isRecording) return;
      handsFreeRef.current = false;
      setHandsFree(false);
      setRecording(false);
      if (reason === "no_speech") {
        rec.discard();
        return tell("Je n'ai rien entendu. Appuyez et parlez quand vous voulez.");
      }
      const recording = await rec.stop();
      if (!recording) return tell("C'était trop court. Appuyez une fois, puis parlez.");
      playEarcon("thinking");
      if (!send({ type: "audio", data: recording.data, mime: recording.mime })) tell("Je ne suis pas connecté à Pilote pour le moment.");
    },
    [send, tell]
  );

  // Appui (barre d'espace ou bouton)
  const startTalking = useCallback(async () => {
    // En écoute continue, un nouvel appui envoie tout de suite
    if (handsFreeRef.current) return void finishTalking("tap");
    if (recorderRef.current?.isRecording) return;
    if (mutedRef.current) {
      // On reparle depuis cette page : c'est elle qui reprend la voix
      mutedRef.current = false;
      channelRef.current?.postMessage("je-parle");
    }
    speakerRef.current?.stop(); // l'utilisateur peut couper la parole à Pilote
    setMicError(null);
    pressedAtRef.current = performance.now();
    try {
      await recorderRef.current?.start();
      setRecording(true);
      playEarcon("listening");
    } catch {
      setMicError("Le micro n'est pas accessible. Autorisez-le dans le navigateur, ou utilisez le mode texte.");
      tell("Je n'ai pas accès au micro. Vérifiez l'autorisation du navigateur, ou utilisez le champ de texte.");
    }
  }, [tell, finishTalking]);

  // Relâchement : appui court = écoute continue ; appui long = on envoie (après une petite marge)
  const stopTalking = useCallback(async () => {
    const rec = recorderRef.current;
    if (!rec?.isRecording || handsFreeRef.current) return;
    if (performance.now() - pressedAtRef.current < TAP_MS) {
      handsFreeRef.current = true;
      setHandsFree(true);
      rec.watchSilence({ ...HANDS_FREE, onStop: (reason) => void finishTalking(reason) });
      return;
    }
    setRecording(false);
    await new Promise((r) => setTimeout(r, RELEASE_TAIL_MS));
    await finishTalking("release");
  }, [finishTalking]);

  // Niveau du micro pour l'anneau du bouton
  useEffect(() => {
    if (!recording) return;
    const timer = setInterval(() => setMicLevel(recorderRef.current?.level ?? 0), 80);
    return () => {
      clearInterval(timer);
      setMicLevel(0);
    };
  }, [recording]);

  const cancel = useCallback(() => {
    speakerRef.current?.stop();
    if (recorderRef.current?.isRecording) {
      recorderRef.current.discard();
      handsFreeRef.current = false;
      setHandsFree(false);
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

  const sendText = useCallback(
    (text: string) => {
      start();
      speakerRef.current?.stop();
      if (/^\s*annul/i.test(text)) cancel();
      else send({ type: "text", text });
    },
    [start, cancel, send]
  );

  // Raccourcis clavier globaux
  useEffect(() => {
    const isTyping = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
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
    sendText(text);
    setTextInput("");
  };

  const talkLabel = !started
    ? "Démarrer Pilote"
    : handsFree
      ? "Je vous écoute… je réponds quand vous vous taisez"
      : recording
        ? "Je vous écoute… relâchez pour envoyer"
        : "Appuyez, puis parlez";

  const showOptions = state === "proposing" && options.length > 0 && !summary;
  const showSummary = !!summary && BUY_STATES.includes(state);
  const recentLog = log.slice(-8);
  const tone =
    state === "done" ? "is-done" : state === "cancelled" ? "is-cancelled" : state === "human_needed" ? "is-alert" : "";
  const statusIcon = state === "done" ? "✓" : state === "cancelled" ? "✕" : state === "human_needed" ? "!" : null;

  return (
    <main className="pilote">
      <header className="pilote-header">
        <h1>
          <span className="pilote-logo" aria-hidden="true">
            P
          </span>
          Pilote
        </h1>
        <p className={`pilote-connection ${connected ? "is-on" : "is-off"}`}>
          <span className="pilote-dot" aria-hidden="true" />
          {connected ? "Connecté" : "Connexion…"}
        </p>
      </header>

      {/* Ce qui est annoncé au lecteur d'écran (mode lecteur d'écran uniquement) */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {voiceMode === "screenreader" ? announce : ""}
      </div>

      <ol className="pilote-steps" aria-label="Étapes de la commande">
        {STEPS.map((step, i) => (
          <li
            key={step.label}
            className={i < currentStep || state === "done" ? "is-past" : i === currentStep ? "is-current" : ""}
            aria-current={i === currentStep ? "step" : undefined}
          >
            <span className="pilote-step-dot" aria-hidden="true">
              {i < currentStep || state === "done" ? "✓" : i + 1}
            </span>
            <span className="pilote-step-label">{step.label}</span>
          </li>
        ))}
      </ol>

      <section className={`pilote-status ${tone}`} aria-label="Où en est la commande">
        <div className="pilote-status-top">
          {statusIcon && (
            <span className="pilote-status-icon" aria-hidden="true">
              {statusIcon}
            </span>
          )}
          <p className="pilote-state">{STATE_LABELS[state]}</p>
          {busy && (
            <p className="pilote-elapsed" aria-hidden="true">
              <span className="pilote-spinner" />
              {elapsed >= 3 ? `${elapsed} s` : ""}
            </p>
          )}
          <SpeakingBars active={speaking} />
        </div>
        <p className="pilote-lastsay">{lastSay || "Appuyez sur le bouton, puis dites ce que vous voulez acheter."}</p>
        {lastSay && started && (
          <button type="button" className="pilote-link" onClick={repeat}>
            Répéter
          </button>
        )}
      </section>

      {awaitingConfirm && (
        <div className="pilote-confirm" role="group" aria-label="Répondre à Pilote">
          <button type="button" className="pilote-yes" onClick={() => confirm(true)}>
            Oui <kbd>Entrée</kbd>
          </button>
          <button type="button" className="pilote-no" onClick={() => confirm(false)}>
            Non <kbd>N</kbd>
          </button>
        </div>
      )}

      {askingCode && (
        <form
          className="pilote-code"
          aria-label="Code secret"
          onSubmit={(e) => {
            e.preventDefault();
            if (codeInput.length !== 3) return;
            sendText(codeInput);
            setCodeInput("");
          }}
        >
          <label htmlFor="pilote-code-input">Votre code à 3 chiffres</label>
          <div>
            <input
              id="pilote-code-input"
              type="password"
              inputMode="numeric"
              pattern="[0-9]{3}"
              maxLength={3}
              autoComplete="off"
              autoFocus
              value={codeInput}
              onChange={(e) => setCodeInput(e.target.value.replace(/\D/g, "").slice(0, 3))}
              aria-describedby="pilote-code-help"
            />
            <button type="submit" disabled={codeInput.length !== 3}>
              Valider
            </button>
          </div>
          <p id="pilote-code-help" className="pilote-muted">
            Ou dites-le à voix haute. Il n&apos;est ni affiché ni enregistré.
          </p>
        </form>
      )}

      {showOptions && (
        <section className="pilote-card" aria-label="Options proposées">
          <h2>
            Options <span className="pilote-muted">Cliquez, ou dites « la première »</span>
          </h2>
          <ol className="pilote-options">
            {options.slice(0, 3).map((o, i) => {
              const time = o.details.departure && o.details.arrival ? `${o.details.departure} → ${o.details.arrival}` : null;
              const facts = [o.details.duration, o.details.via, o.details.delivery, o.details.restaurant]
                .filter(Boolean)
                .join(" · ");
              return (
                <li key={o.id}>
                  <button type="button" className="pilote-option" onClick={() => sendText(`la ${ORDINALS[i] ?? `numéro ${i + 1}`}`)}>
                    <span className="pilote-option-rank" aria-hidden="true">
                      {i + 1}
                    </span>
                    <span className="pilote-option-body">
                      {time && <span className="pilote-option-time">{time}</span>}
                      <span className="pilote-option-title">{o.title}</span>
                      {facts && <span className="pilote-option-facts">{facts}</span>}
                      {o.rating != null && <span className="pilote-option-facts">★ {o.rating.toLocaleString("fr-FR")} / 5</span>}
                    </span>
                    <span className={`pilote-option-price ${o.price_cents === 0 ? "is-free" : ""}`}>
                      {formatCents(o.price_cents)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {showSummary && summary && (
        <section className="pilote-card pilote-summary" aria-label="Récapitulatif de la commande">
          <h2>Récapitulatif</h2>
          <ul>
            {summary.items.map((item, i) => (
              <li key={i}>
                <span>
                  {item.quantity} × {item.name}
                  {item.options.length > 0 && ` (${item.options.join(", ")})`}
                </span>
                <span>{formatCents(item.total_cents)}</span>
              </li>
            ))}
            {summary.fees.map((fee, i) => (
              <li key={`fee-${i}`} className="is-fee">
                <span>{fee.label}</span>
                <span>{formatCents(fee.amount_cents)}</span>
              </li>
            ))}
          </ul>
          <p className="pilote-total">
            <span>Total</span>
            <strong>{formatCents(summary.total_cents)}</strong>
          </p>
          {summary.when_label && <p className="pilote-muted">{summary.when_label}</p>}
          {summary.conditions && <p className="pilote-muted">{summary.conditions}</p>}
        </section>
      )}

      <div className="pilote-mic">
        <button
          type="button"
          className={`pilote-talk ${recording || handsFree ? "is-recording" : ""} ${speaking ? "is-speaking" : ""} ${started ? "" : "is-idle"}`}
          style={{ "--level": micLevel.toFixed(2) } as CSSProperties}
          aria-pressed={started ? recording || handsFree : undefined}
          aria-label={talkLabel}
          aria-describedby="pilote-help"
          onClick={() => {
            if (!started) start();
          }}
          onPointerDown={(e) => {
            if (!started) return;
            e.preventDefault();
            // Le doigt ou la souris peut glisser hors du bouton sans couper l'enregistrement
            e.currentTarget.setPointerCapture(e.pointerId);
            void startTalking();
          }}
          onPointerUp={() => void stopTalking()}
          onPointerCancel={() => void stopTalking()}
          onKeyDown={(e) => {
            // La barre d'espace est gérée globalement ; on évite le double déclenchement du bouton
            if (e.code === "Space") e.preventDefault();
          }}
          autoFocus
        >
          {recording || handsFree ? <span className="pilote-rec-dot" aria-hidden="true" /> : <MicIcon />}
        </button>
        <p className="pilote-talk-label" aria-hidden="true">
          {talkLabel}
        </p>
        <p id="pilote-help" className="pilote-help">
          <kbd>Espace</kbd> pour parler · <kbd>Échap</kbd> pour annuler
        </p>
      </div>

      <form className="pilote-text" onSubmit={submitText} aria-label="Écrire au lieu de parler">
        <label htmlFor="pilote-text-input" className="sr-only">
          Écrire au lieu de parler
        </label>
        <input
          id="pilote-text-input"
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          placeholder="Ou écrivez : un train pour Nantes demain matin"
          autoComplete="off"
        />
        <button type="submit" aria-label="Envoyer">
          Envoyer
        </button>
      </form>

      {micError && (
        <p className="pilote-alert" role="alert">
          {micError}
        </p>
      )}

      {recentLog.length > 0 && (
        <details className="pilote-panel">
          <summary>Conversation</summary>
          <ul className="pilote-log">
            {recentLog.map((entry) => (
              <li key={entry.id} className={`is-${entry.who}`}>
                <strong>{entry.who === "user" ? "Vous" : entry.who === "pilote" ? "Pilote" : "Système"}</strong>
                {entry.text}
              </li>
            ))}
          </ul>
        </details>
      )}

      <details className="pilote-panel">
        <summary>Réglages et raccourcis</summary>
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
        </fieldset>

        <div className="pilote-setting">
          <label htmlFor="pilote-rate">
            Vitesse de la voix : <strong>{prefs.rate.toLocaleString("fr-FR", { minimumFractionDigits: 1 })}×</strong>
          </label>
          <input
            id="pilote-rate"
            type="range"
            min={0.8}
            max={2}
            step={0.1}
            value={prefs.rate}
            onChange={(e) => updatePrefs({ rate: Number(e.target.value) })}
            onPointerUp={() => tell("Voici la nouvelle vitesse.")}
          />
        </div>

        <div className="pilote-setting">
          <label htmlFor="pilote-browser-voice">Voix de secours du navigateur</label>
          <select
            id="pilote-browser-voice"
            value={prefs.browserVoice ?? ""}
            onChange={(e) => updatePrefs({ browserVoice: e.target.value || null })}
          >
            <option value="">Automatique (la plus naturelle)</option>
            {voices.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <p className="pilote-muted">Utilisée seulement si la voix de Pilote ne répond pas à temps.</p>
        </div>

        <dl className="pilote-shortcuts">
          <dt>
            <kbd>Espace</kbd>
          </dt>
          <dd>Une fois puis parlez (Pilote répond quand vous vous taisez), ou maintenue pendant que vous parlez</dd>
          <dt>
            <kbd>Entrée</kbd> / <kbd>N</kbd>
          </dt>
          <dd>Oui / non quand Pilote pose une question</dd>
          <dt>
            <kbd>Échap</kbd>
          </dt>
          <dd>Annuler à tout moment</dd>
          <dt>
            <kbd>R</kbd>
          </dt>
          <dd>Répéter la dernière phrase</dd>
        </dl>

        <Link href="/spectateur" target="_blank" rel="noreferrer" className="pilote-spectator-link">
          Ouvrir l&apos;écran spectateur ↗
        </Link>
      </details>
    </main>
  );
}
