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
  type State,
} from "./protocol";
import { OverlapTracker, overlapMime } from "./echoGuard";
import { registerHeadsetButton } from "./mediaSession";
import { WakeLockKeeper } from "./wakelock";
import {
  MIC_PROFILES,
  MIC_PROFILE_LABELS,
  describeCalibration,
  isMicProfile,
  type MicProfile,
} from "./micProfile";
import { PushToTalkRecorder, RELEASE_TAIL_MS } from "./recorder";
import { Speaker, listFrenchVoices, setBrowserVoice } from "./speech";
import {
  authHeaders,
  browserStorage,
  getServerConfig,
  savePairing,
  takePairingFromLocation,
} from "./serverConfig";
import { usePilote } from "./usePilote";
import Orb, { type OrbMode } from "./Orb";
import { WakeWordListener, wakeWordSupported } from "./wakeword";

// Obligatoire (AI Act, article 50). Normalement dit par l'orchestrateur à la connexion ;
// répété ici si sa phrase d'accueil n'a pas pu être jouée.
const AI_DISCLOSURE = "Je suis Pilote, un assistant automatique.";

// "voice" : Pilote parle lui-même. "screenreader" : Pilote se tait et laisse VoiceOver lire les annonces.
// Jamais les deux à la fois, sinon les deux voix se superposent.
type VoiceMode = "voice" | "screenreader";

// Appui plus court que ça = « appuyer une fois puis parler » : Pilote écoute et s'arrête quand on se tait.
const VOICE_LABELS: Record<string, string> = {
  jerem: "Jerem (homme)",
};
const TAP_MS = 450;
// Deux appuis sur espace à moins de ce délai = « tais-toi » : Pilote arrête de parler, rien n'est envoyé.
const DOUBLE_SPACE_MS = 450;
// 2 s de silence avant d'envoyer : on laisse le temps d'une petite pause (« pour aller… à Lyon »).
const HANDS_FREE = { silenceMs: 2000, noSpeechMs: 7000, maxMs: 30000 };
// Pause entre le son « je vous écoute » et l'ouverture du micro
const EARCON_GAP_MS = 380;

// États où Pilote attend une réponse : il réécoute tout seul après avoir parlé (conversation mains libres).
const AUTO_LISTEN_STATES: State[] = [
  "listening",
  "proposing",
  "confirm_1",
  "confirm_2",
  "human_needed",
];

// Réaction immédiate quand on a fini de parler, le temps que Pilote comprenne et réponde.
const ACKS = [
  "D'accord.",
  "Entendu.",
  "Très bien, je regarde.",
  "Je m'en occupe.",
  "Voyons cela.",
];

// Réglages gardés dans ce navigateur seulement (aucune donnée personnelle).
const PREFS_KEY = "pilote-prefs";
type Prefs = { rate: number; browserVoice: string | null; micProfile: MicProfile; noiseFloor: number };
// 1,2× : vitesse retenue à l'écoute pour la voix Jerem (2026-11-19)
const DEFAULT_PREFS: Prefs = { rate: 1.2, browserVoice: null, micProfile: "normal", noiseFloor: 0 };

function loadPrefs(): Prefs {
  try {
    const raw = window.localStorage.getItem(PREFS_KEY);
    if (!raw) return DEFAULT_PREFS;
    const stored = { ...DEFAULT_PREFS, ...JSON.parse(raw) };
    // Un réglage enregistré par une ancienne version peut être absent ou périmé : on le remplace
    const floor = Number(stored.noiseFloor);
    return {
      ...stored,
      micProfile: isMicProfile(stored.micProfile) ? stored.micProfile : "normal",
      noiseFloor: Number.isFinite(floor) ? Math.min(1, Math.max(0, floor)) : 0,
    };
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

export default function PiloteApp() {
  const [started, setStarted] = useState(false);
  const [recording, setRecording] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("voice");
  // Voix de Pilote au choix (Jerem…) : la liste vient de l'orchestrateur, vide s'il n'en a pas
  const [piloteVoices, setPiloteVoices] = useState<{
    current: string | null;
    available: string[];
  }>({
    current: null,
    available: [],
  });
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [announce, setAnnounce] = useState("");
  const [micError, setMicError] = useState<string | null>(null);
  const [textInput, setTextInput] = useState("");
  const prefs = useSyncExternalStore(subscribePrefs, getPrefs, getServerPrefs);
  const [voices, setVoices] = useState<string[]>([]);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const speakerRef = useRef<Speaker | null>(null);
  const recorderRef = useRef<PushToTalkRecorder | null>(null);
  const voiceModeRef = useRef<VoiceMode>("voice");
  const startedRef = useRef(false);
  const pressedAtRef = useRef(0);
  const lastSpaceRef = useRef(0);
  const hushGenRef = useRef(0); // augmente à chaque « Stop » : périme un micro en train de s'ouvrir
  const handsFreeRef = useRef(false);
  const autoListenRef = useRef(false); // écoute lancée par Pilote (pas par un appui) : silence = rien à dire
  const awaitingReplyRef = useRef(false); // on a parlé, la réponse de Pilote n'est pas encore arrivée
  const wakeRef = useRef<WakeWordListener | null>(null);
  const sayCountRef = useRef(0); // numéro de la dernière phrase de Pilote
  const autoForRef = useRef(-1); // phrase après laquelle on a déjà réécouté (une seule fois)
  const overlapRef = useRef(new OverlapTracker()); // la voix de Pilote a-t-elle chevauché l'enregistrement ?
  const endedRef = useRef(true); // conversation terminée : on attend « Bonjour Pilote » ou un appui

  useEffect(() => {
    const speaker = new Speaker();
    speaker.onChange = (isSpeaking) => {
      setSpeaking(isSpeaking);
      // Pilote se met à parler micro ouvert : l'enregistrement est marqué, le serveur se méfiera
      if (isSpeaking && recorderRef.current?.isRecording) overlapRef.current.pilotStartedSpeaking();
    };
    speakerRef.current = speaker;
    recorderRef.current = new PushToTalkRecorder();
    const saved = getPrefs();
    speaker.rate = saved.rate;
    recorderRef.current.setProfile(saved.micProfile, saved.noiseFloor);
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
    recorderRef.current?.setProfile(next.micProfile, next.noiseFloor);
    setBrowserVoice(next.browserVoice);
  };

  // Mesure le bruit de fond puis règle le seuil de parole. Pilote se tait d'abord : sa voix fausserait la mesure.
  const calibrateMic = async () => {
    const rec = recorderRef.current;
    if (!rec || rec.isRecording) return;
    speakerRef.current?.stop();
    tell("Ne dites rien pendant deux secondes, je mesure le bruit autour de vous.");
    for (let i = 0; i < 60 && speakerRef.current?.speaking; i += 1) await new Promise((r) => setTimeout(r, 100));
    await new Promise((r) => setTimeout(r, 400)); // la fin de la phrase ne doit pas entrer dans la mesure
    try {
      const floor = await rec.calibrate(1500);
      updatePrefs({ noiseFloor: floor });
      tell(describeCalibration(floor));
    } catch {
      tell("Je n'ai pas pu mesurer : le micro n'est pas accessible. Autorisez-le dans le navigateur.");
    }
  };

  // Une phrase à dire : à voix haute (mode voix) ou via la région ARIA live (mode lecteur d'écran)
  // Une seule page Pilote parle à la fois : la dernière démarrée prévient les autres, qui se taisent.
  // Évite la voix en double (18/11). Une page en arrière-plan continue de parler : on regarde souvent
  // l'écran du jury pendant la recherche, et c'est justement là que Pilote décrit ce que fait l'agent.
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

  const tell = useCallback(
    (text: string, audio?: string | null, mime?: string | null) => {
      if (voiceModeRef.current === "voice") {
        if (mutedRef.current) return;
        speakerRef.current?.enqueue(text, audio, mime);
      } else setAnnounce((prev) => (prev === text ? `${text} ` : text)); // force la relecture d'un texte identique
    },
    [],
  );

  const onMessage = useCallback(
    (msg: ServerMessage) => {
      if (msg.type === "state")
        setBusySince(BUSY_STATES.includes(msg.state) ? Date.now() : null);
      // Avant le premier geste, le navigateur bloque le son : on gardera la phrase pour le démarrage.
      if (!startedRef.current) return;
      if (msg.type === "say") {
        awaitingReplyRef.current = false;
        sayCountRef.current += 1;
        tell(msg.text, msg.audio, msg.mime);
      }
      if (msg.type === "state") {
        // Commande finie ou annulée : la conversation s'arrête, Pilote ne réécoute plus tout seul
        if (msg.state === "done" || msg.state === "cancelled")
          endedRef.current = true;
        const earcon = earconForState(msg.state);
        if (earcon) playEarcon(earcon);
      }
      if (msg.type === "error") playEarcon("error"); // l'explication arrive dans le say suivant
    },
    [tell],
  );

  const { connected, refused, state, options, summary, lastSay, log, question, send } =
    usePilote(onMessage);

  // Lien d'appairage (« …/#server=…&token=… ») : l'adresse du serveur et le jeton sont gardés ici, puis le #
  // est effacé de la barre d'adresse. Un lien piégé enverrait votre voix à un autre serveur : on dit où.
  useEffect(() => {
    const pairing = takePairingFromLocation(window.location, window.history);
    if (!pairing) return;
    const host = new URL(pairing.wsUrl).host;
    if (!window.confirm(`Connecter Pilote au serveur ${host} ?`)) return;
    if (savePairing(browserStorage(), pairing)) window.location.reload();
    else window.alert("Impossible de garder l'appairage : désactivez la navigation privée et recommencez.");
  }, []);

  useEffect(() => {
    if (refused)
      tell(
        "Ce téléphone n'est pas appairé à Pilote. Ouvrez à nouveau le lien d'appairage affiché sur l'ordinateur.",
      );
  }, [refused, tell]);
  const chooseVoice = async (name: string) => {
    setVoiceBusy(true);
    try {
      const server = getServerConfig();
      const response = await fetch(`${server.httpUrl}/voice`, {
        method: "POST",
        headers: { "content-type": "application/json", ...authHeaders(server.token) },
        body: JSON.stringify({ name }),
      });
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      setPiloteVoices({ current: data.current, available: data.available });
      // On entend tout de suite la nouvelle voix
      speakerRef.current?.stop();
      if (voiceModeRef.current === "voice")
        speakerRef.current?.enqueue(data.text, data.sample, data.mime);
    } catch {
      tell("Je n'ai pas pu changer de voix.");
    } finally {
      setVoiceBusy(false);
    }
  };

  // Voix proposées par l'orchestrateur (relues à chaque connexion : il a pu redémarrer)
  useEffect(() => {
    if (!connected) return;
    let cancelled = false;
    const server = getServerConfig();
    fetch(`${server.httpUrl}/voice`, { headers: authHeaders(server.token) })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && !cancelled)
          setPiloteVoices({
            current: data.current,
            available: data.available ?? [],
          });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [connected]);
  const awaitingConfirm = CONFIRM_STATES.includes(state);
  const busy = BUSY_STATES.includes(state);
  const currentStep = STEPS.findIndex((s) => s.states.includes(state));

  // Compteur « depuis 42 s » pendant que Pilote travaille seul
  useEffect(() => {
    if (busySince === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [busySince]);
  const elapsed =
    busySince !== null ? Math.max(0, Math.round((now - busySince) / 1000)) : 0;

  const start = useCallback(() => {
    if (startedRef.current) return;
    unlockAudio(); // le navigateur n'autorise le son qu'après un geste de l'utilisateur
    startedRef.current = true;
    mutedRef.current = false;
    channelRef.current?.postMessage("je-parle"); // les autres pages Pilote se taisent
    setStarted(true);
    const greeting =
      lastSay && lastSay.includes("assistant automatique")
        ? lastSay
        : `${AI_DISCLOSURE} ${lastSay}`;
    tell(greeting.trim());
    // L'accueil finit par « Comment allez-vous ? » : Pilote écoute la réponse une fois
    endedRef.current = false;
  }, [lastSay, tell]);

  // Réaction immédiate pendant que Pilote comprend : seulement pour une nouvelle demande ou un choix,
  // jamais pendant un oui / non ou la saisie du code.
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const acknowledge = useCallback(() => {
    if (!["listening", "proposing"].includes(stateRef.current)) return;
    tell(ACKS[Math.floor(Math.random() * ACKS.length)]);
  }, [tell]);

  // Envoie ce qui a été enregistré (ou l'abandonne si rien n'a été dit)
  const finishTalking = useCallback(
    async (reason: "release" | "silence" | "no_speech" | "max" | "tap") => {
      const rec = recorderRef.current;
      if (!rec?.isRecording) return;
      handsFreeRef.current = false;
      setHandsFree(false);
      setRecording(false);
      const auto = autoListenRef.current;
      autoListenRef.current = false;
      if (reason === "no_speech") {
        rec.discard();
        // Écoute automatique sans réponse : Pilote se tait et attend « Bonjour Pilote ».
        if (auto) return;
        return tell(
          "Je n'ai rien entendu. Appuyez et parlez quand vous voulez.",
        );
      }
      const recording = await rec.stop();
      if (!recording)
        return tell("C'était trop court. Appuyez une fois, puis parlez.");
      playEarcon("thinking");
      awaitingReplyRef.current = true;
      if (
        !send({
          type: "audio",
          data: recording.data,
          mime: overlapMime(recording.mime, overlapRef.current),
        })
      ) {
        awaitingReplyRef.current = false;
        tell("Je ne suis pas connecté à Pilote pour le moment.");
      } else acknowledge();
    },
    [send, tell, acknowledge],
  );

  // Appui (barre d'espace ou bouton)
  const startTalking = useCallback(async () => {
    endedRef.current = false; // on parle à Pilote : la conversation reprend
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
    const gen = hushGenRef.current;
    try {
      // Le son d'abord, le micro ensuite : sinon la cloche est enregistrée et Whisper invente des mots
      playEarcon("listening");
      await new Promise((r) => setTimeout(r, EARCON_GAP_MS));
      if (gen !== hushGenRef.current) return; // « Stop » pendant la cloche : on n'ouvre pas le micro
      await recorderRef.current?.start();
      overlapRef.current.begin(speakerRef.current?.speaking ?? false);
      if (gen !== hushGenRef.current) return recorderRef.current?.discard(); // « Stop » pendant l'ouverture
      setRecording(true);
    } catch {
      if (gen !== hushGenRef.current) return;
      setMicError(
        "Le micro n'est pas accessible. Autorisez-le dans le navigateur, ou utilisez le mode texte.",
      );
      tell(
        "Je n'ai pas accès au micro. Vérifiez l'autorisation du navigateur, ou utilisez le champ de texte.",
      );
    }
  }, [tell, finishTalking]);

  // Relâchement : appui court = écoute continue ; appui long = on envoie (après une petite marge)
  const stopTalking = useCallback(async () => {
    const rec = recorderRef.current;
    if (!rec?.isRecording || handsFreeRef.current) return;
    if (performance.now() - pressedAtRef.current < TAP_MS) {
      handsFreeRef.current = true;
      setHandsFree(true);
      rec.watchSilence({
        ...HANDS_FREE,
        onStop: (reason) => void finishTalking(reason),
      });
      return;
    }
    setRecording(false);
    await new Promise((r) => setTimeout(r, RELEASE_TAIL_MS));
    await finishTalking("release");
  }, [finishTalking]);

  // Écoute mains libres lancée par Pilote ou par « Bonjour Pilote » : on parle, Pilote répond au silence.
  const listenHandsFree = useCallback(
    async (auto: boolean, immediate = false) => {
      const rec = recorderRef.current;
      if (!rec || rec.isRecording || mutedRef.current) return;
      wakeRef.current?.stop();
      if (!immediate) {
        playEarcon("listening"); // avant le micro : la cloche ne doit pas être enregistrée
        await new Promise((r) => setTimeout(r, EARCON_GAP_MS));
      }
      try {
        await rec.start();
        overlapRef.current.begin(speakerRef.current?.speaking ?? false);
      } catch {
        return;
      }
      autoListenRef.current = auto;
      handsFreeRef.current = true;
      setHandsFree(true);
      setRecording(true);
      rec.watchSilence({
        ...HANDS_FREE,
        onStop: (reason) => void finishTalking(reason),
      });
    },
    [finishTalking],
  );

  // Conversation : Pilote réécoute tout seul UNE fois après une phrase qui attend une réponse
  // (un choix, un oui / non, le code, ou une question qui finit par « ? »). Pas après la fin d'une
  // commande : il faut alors dire « Bonjour Pilote » ou appuyer.
  useEffect(() => {
    if (!started || speaking || recording || voiceMode !== "voice") return;
    if (
      endedRef.current ||
      awaitingReplyRef.current ||
      autoForRef.current === sayCountRef.current
    )
      return;
    const asks =
      state !== "listening"
        ? AUTO_LISTEN_STATES.includes(state)
        : lastSay.trim().endsWith("?");
    if (!asks) return;
    const timer = setTimeout(() => {
      if (speakerRef.current?.speaking || recorderRef.current?.isRecording)
        return;
      autoForRef.current = sayCountRef.current;
      void listenHandsFree(true);
    }, 350);
    return () => clearTimeout(timer);
  }, [
    started,
    speaking,
    recording,
    state,
    lastSay,
    voiceMode,
    listenHandsFree,
  ]);

  // « Bonjour Pilote » pour le réveiller, « OK Pilote » pour le couper : écoute hors enregistrement.
  useEffect(() => {
    const wake = (wakeRef.current ??= new WakeWordListener());
    wake.isSpeaking = () => !!speakerRef.current?.speaking;
    wake.spokenText = () => speakerRef.current?.sayingText ?? "";
    wake.onStop = () => {
      // « OK Pilote », « stop » : il se tait et écoute ce qu'on veut lui dire. Le micro s'ouvre tout de suite,
      // sans cloche : la personne continue de parler, la cloche et son délai couperaient le début de sa phrase.
      speakerRef.current?.stop();
      endedRef.current = false;
      void listenHandsFree(false, true);
    };
    wake.onWake = (rest) => {
      endedRef.current = false;
      if (rest.split(/\s+/).filter(Boolean).length >= 2) {
        // « Bonjour Pilote, un train pour Lille » : la demande est déjà là
        playEarcon("thinking");
        awaitingReplyRef.current = true;
        speakerRef.current?.stop();
        send({ type: "text", text: rest });
        acknowledge();
      } else void listenHandsFree(false);
    };
    if (started && !recording && voiceMode === "voice") wake.start();
    else wake.stop();
  }, [started, recording, voiceMode, listenHandsFree, send, acknowledge]);
  useEffect(() => () => wakeRef.current?.stop(), []);

  // Niveau du micro pour l'anneau du bouton
  useEffect(() => {
    if (!recording) return;
    const timer = setInterval(
      () => setMicLevel(recorderRef.current?.level ?? 0),
      80,
    );
    return () => {
      clearInterval(timer);
      setMicLevel(0);
    };
  }, [recording]);

  // Fait taire Pilote tout de suite (bouton Stop ou deux fois espace), sans annuler la commande
  const hush = useCallback(() => {
    hushGenRef.current += 1;
    speakerRef.current?.stop();
    if (recorderRef.current?.isRecording) {
      recorderRef.current.discard();
      handsFreeRef.current = false;
      setHandsFree(false);
      setRecording(false);
    }
  }, []);

  // Session en cours : l'écran reste allumé (sinon le téléphone se verrouille et coupe le micro), et le bouton
  // du casque coupe Pilote ou lui donne la parole.
  const wakeLockRef = useRef<WakeLockKeeper | null>(null);
  useEffect(() => {
    if (!started) return;
    const keeper = (wakeLockRef.current ??= new WakeLockKeeper());
    void keeper.acquire();
    const unplug = registerHeadsetButton({
      onPlayPause: () => {
        if (speakerRef.current?.speaking) hush();
        else void listenHandsFree(false, true);
      },
    });
    return () => {
      unplug();
      void keeper.release();
    };
  }, [started, hush, listenHandsFree]);

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
    [send],
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
      else {
        awaitingReplyRef.current = true;
        endedRef.current = false;
        send({ type: "text", text });
      }
    },
    [start, cancel, send],
  );

  // Raccourcis clavier globaux
  useEffect(() => {
    const isTyping = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      return (
        !!el &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.tagName === "SELECT" ||
          el.isContentEditable)
      );
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
        const now = performance.now();
        const double = now - lastSpaceRef.current < DOUBLE_SPACE_MS;
        lastSpaceRef.current = double ? 0 : now;
        if (double) return hush();
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
  }, [
    started,
    awaitingConfirm,
    start,
    startTalking,
    stopTalking,
    cancel,
    hush,
    confirm,
    repeat,
  ]);

  // Annonce de la perte et du retour de la connexion
  const wasConnected = useRef<boolean | null>(null);
  useEffect(() => {
    if (startedRef.current && wasConnected.current === true && !connected) {
      playEarcon("error");
      speakerRef.current?.enqueue(
        "La connexion avec Pilote est coupée. Je réessaie.",
      );
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
  const hasAside = awaitingConfirm || showOptions || showSummary;
  const recentLog = log.slice(-8);
  const tone =
    state === "done"
      ? "is-done"
      : state === "cancelled"
        ? "is-cancelled"
        : state === "human_needed"
          ? "is-alert"
          : "";
  const listening = recording || handsFree;
  const haloClass = listening
    ? "is-listening"
    : speaking
      ? "is-speaking"
      : busy
        ? "is-busy"
        : started
          ? ""
          : "is-idle";
  // Une fois démarré, l'orbe rétrécit : la conversation et le champ de texte tiennent à l'écran
  const orbSize = started ? 220 : 360;
  // Ce que l'écran annonce : jamais « J'écoute » avant d'avoir démarré ni quand la connexion est coupée
  const stateLabel = !connected
    ? "Connexion perdue, je réessaie…"
    : !started
      ? "Prêt"
      : question && state === "searching"
        ? "Je cherche la réponse"
        : STATE_LABELS[state];
  // Commentaire en direct (« Je lance la recherche ») : dit à l'oral mais absent de la conversation,
  // on l'affiche dans la bulle d'attente à la place des trois points.
  const lastPilote = [...log].reverse().find((e) => e.who === "pilote")?.text;
  // Seulement une phrase arrivée pendant le travail en cours (pas la phrase d'avant, comme l'accueil)
  const [sayBeforeWork, setSayBeforeWork] = useState("");
  if (!busy && sayBeforeWork !== lastSay) setSayBeforeWork(lastSay);
  const liveNote =
    busy && lastSay && lastSay !== lastPilote && lastSay !== sayBeforeWork
      ? lastSay
      : "";
  const threadRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const box = threadRef.current;
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [log.length, liveNote, busy]);
  const orbMode: OrbMode = listening
    ? "listening"
    : speaking
      ? "speaking"
      : busy
        ? "thinking"
        : "idle";

  return (
    <main className={`pilote ${started ? "is-started" : ""}`}>
      <div className="pilote-backdrop" aria-hidden="true">
        <span />
        <span />
      </div>

      <header className="pilote-header">
        <p className={`pilote-connection ${connected ? "is-on" : "is-off"}`}>
          <span className="pilote-dot" aria-hidden="true" />
          {connected ? "En ligne" : "Connexion…"}
        </p>
        <h1 className="pilote-title">
          Pilote<span aria-hidden="true">.</span>
        </h1>
        <p className="pilote-tagline">
          Internet, à portée de voix. Pour que chacun puisse faire ses démarches
          en toute autonomie.
        </p>
      </header>

      {/* Ce qui est annoncé au lecteur d'écran (mode lecteur d'écran uniquement) */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {voiceMode === "screenreader" ? announce : ""}
      </div>

      <div className={`pilote-layout ${hasAside ? "has-aside" : ""}`}>
        <div className="pilote-main">
          <section
            className={`pilote-hero ${tone}`}
            aria-label="Où en est la commande"
          >
            <div className={`pilote-halo ${haloClass}`}>
              <button
                type="button"
                className={`pilote-talk ${listening ? "is-recording" : ""}`}
                aria-pressed={started ? listening : undefined}
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
                <Orb mode={orbMode} level={micLevel} size={orbSize} />
              </button>
            </div>
            <p className="pilote-state">
              {stateLabel}
              {connected && busy && elapsed >= 3 && (
                <span className="pilote-elapsed"> · {elapsed} s</span>
              )}
            </p>
            <p className="pilote-talk-label" aria-hidden="true">
              {talkLabel}
            </p>
            {started && (speaking || lastSay) && (
              <div className="pilote-actions">
                {speaking && (
                  <button
                    type="button"
                    className="pilote-stop"
                    onClick={hush}
                    aria-label="Faire taire Pilote"
                  >
                    <span aria-hidden="true">■</span> Stop
                  </button>
                )}
                {lastSay && !speaking && (
                  <button
                    type="button"
                    className="pilote-repeat"
                    onClick={repeat}
                  >
                    Répéter
                  </button>
                )}
              </div>
            )}
            <p id="pilote-help" className="pilote-help">
              {started && wakeWordSupported() && <>Dites « Bonjour Pilote »</>}
              <span className="pilote-keys">
                {started && wakeWordSupported() && " · "}
                <kbd>Espace</kbd> pour parler · <kbd>Espace</kbd> ×2 pour faire
                taire · <kbd>Échap</kbd> pour annuler
              </span>
            </p>
          </section>

          {/* Une simple question n'a ni choix ni achat : pas d'étapes */}
          <ol
            className="pilote-steps"
            aria-label="Étapes de la commande"
            hidden={question}
          >
            {STEPS.map((step, i) => (
              <li
                key={step.label}
                className={
                  i < currentStep || state === "done"
                    ? "is-past"
                    : i === currentStep
                      ? "is-current"
                      : ""
                }
                aria-current={i === currentStep ? "step" : undefined}
              >
                <span className="pilote-step-dot" aria-hidden="true" />
                <span className="pilote-step-label">{step.label}</span>
              </li>
            ))}
          </ol>

          <section
            ref={threadRef}
            className="pilote-thread"
            aria-label="Conversation"
          >
            {recentLog.length === 0 && (
              <p className="pilote-bubble is-pilote">
                {lastSay ||
                  "Bonjour, je suis Pilote. Dites-moi ce que vous voulez acheter, ou posez-moi une question."}
              </p>
            )}
            {recentLog.map((entry) => (
              <p key={entry.id} className={`pilote-bubble is-${entry.who}`}>
                <span className="sr-only">
                  {entry.who === "user"
                    ? "Vous : "
                    : entry.who === "pilote"
                      ? "Pilote : "
                      : "Système : "}
                </span>
                {entry.text}
              </p>
            ))}
            {busy &&
              (liveNote ? (
                <p
                  className="pilote-bubble is-pilote is-live"
                  aria-hidden="true"
                >
                  {liveNote}
                </p>
              ) : (
                <p
                  className="pilote-bubble is-pilote is-typing"
                  aria-hidden="true"
                >
                  <i />
                  <i />
                  <i />
                </p>
              ))}
          </section>

          <form
            className="pilote-text"
            onSubmit={submitText}
            aria-label="Écrire au lieu de parler"
          >
            <label htmlFor="pilote-text-input" className="sr-only">
              Écrire au lieu de parler
            </label>
            <input
              id="pilote-text-input"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              placeholder="Écrire à Pilote…"
              autoComplete="off"
            />
            <button
              type="submit"
              aria-label="Envoyer"
              disabled={!textInput.trim()}
            >
              <svg
                viewBox="0 0 24 24"
                width="18"
                height="18"
                aria-hidden="true"
                focusable="false"
              >
                <path
                  d="M12 19V5M6 11l6-6 6 6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </form>

          {micError && (
            <p className="pilote-alert" role="alert">
              {micError}
            </p>
          )}
        </div>
        {hasAside && (
          <aside className="pilote-aside" aria-label="Propositions de Pilote">
            {awaitingConfirm && (
              <div
                className="pilote-confirm"
                role="group"
                aria-label="Répondre à Pilote"
              >
                <button
                  type="button"
                  className="pilote-yes"
                  onClick={() => confirm(true)}
                >
                  Oui <kbd>Entrée</kbd>
                </button>
                <button
                  type="button"
                  className="pilote-no"
                  onClick={() => confirm(false)}
                >
                  Non <kbd>N</kbd>
                </button>
              </div>
            )}

            {showOptions && (
              <section className="pilote-card" aria-label="Options proposées">
                <h2>
                  Options{" "}
                  <span className="pilote-muted">
                    Touchez, ou dites « la première »
                  </span>
                </h2>
                <ol className="pilote-options">
                  {options.slice(0, 3).map((o, i) => {
                    const time =
                      o.details.departure && o.details.arrival
                        ? `${o.details.departure} → ${o.details.arrival}`
                        : null;
                    const facts = [
                      o.details.duration,
                      o.details.via,
                      o.details.delivery,
                      o.details.restaurant,
                      o.details.cuisine,
                      o.details.address,
                      o.details.slots && `Disponible à ${o.details.slots}`,
                      o.details.avg_price &&
                        `Prix moyen ${o.details.avg_price}`,
                    ]
                      .filter(Boolean)
                      .join(" · ");
                    return (
                      <li key={o.id}>
                        <button
                          type="button"
                          className="pilote-option"
                          onClick={() =>
                            sendText(`la ${ORDINALS[i] ?? `numéro ${i + 1}`}`)
                          }
                        >
                          <span
                            className="pilote-option-rank"
                            aria-hidden="true"
                          >
                            {i + 1}
                          </span>
                          <span className="pilote-option-body">
                            {time && (
                              <span className="pilote-option-time">{time}</span>
                            )}
                            <span className="pilote-option-title">
                              {o.title}
                            </span>
                            {facts && (
                              <span className="pilote-option-facts">
                                {facts}
                              </span>
                            )}
                            {o.rating != null && (
                              <span className="pilote-option-facts">
                                ★ {o.rating.toLocaleString("fr-FR")} / 5
                              </span>
                            )}
                          </span>
                          <span
                            className={`pilote-option-price ${o.price_cents === 0 ? "is-free" : ""}`}
                          >
                            {o.price_cents === 0
                              ? "Gratuit"
                              : formatCents(o.price_cents)}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </section>
            )}

            {showSummary && summary && (
              <section
                className="pilote-card pilote-summary"
                aria-label="Récapitulatif de la commande"
              >
                <h2>Récapitulatif</h2>
                <ul>
                  {summary.items.map((item, i) => (
                    <li key={i}>
                      <span>
                        {item.quantity} × {item.name}
                        {item.options.length > 0 &&
                          ` (${item.options.join(", ")})`}
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
                {summary.when_label && (
                  <p className="pilote-muted">{summary.when_label}</p>
                )}
                {summary.conditions && (
                  <p className="pilote-muted">{summary.conditions}</p>
                )}
              </section>
            )}
          </aside>
        )}
      </div>

      <details className="pilote-panel">
        <summary>Réglages et raccourcis</summary>
        <fieldset className="pilote-settings">
          <legend>Qui lit les réponses ?</legend>
          <label>
            <input
              type="radio"
              name="voice-mode"
              checked={voiceMode === "voice"}
              onChange={() => setVoiceMode("voice")}
            />
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

        {piloteVoices.available.length > 1 && (
          <fieldset className="pilote-settings" disabled={voiceBusy}>
            <legend>Voix de Pilote</legend>
            {piloteVoices.available.map((name) => (
              <label key={name}>
                <input
                  type="radio"
                  name="pilote-voice"
                  checked={piloteVoices.current === name}
                  onChange={() => void chooseVoice(name)}
                />
                {VOICE_LABELS[name] ??
                  name.charAt(0).toUpperCase() + name.slice(1)}
              </label>
            ))}
          </fieldset>
        )}

        <div className="pilote-setting">
          <label htmlFor="pilote-rate">
            Vitesse de la voix :{" "}
            <strong>
              {prefs.rate.toLocaleString("fr-FR", { minimumFractionDigits: 1 })}
              ×
            </strong>
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
          <label htmlFor="pilote-mic-profile">Sensibilité du micro</label>
          <select
            id="pilote-mic-profile"
            value={prefs.micProfile}
            onChange={(e) => updatePrefs({ micProfile: e.target.value as MicProfile })}
          >
            {MIC_PROFILES.map((profile) => (
              <option key={profile} value={profile}>
                {MIC_PROFILE_LABELS[profile]}
              </option>
            ))}
          </select>
          <button type="button" className="pilote-link" onClick={() => void calibrateMic()}>
            Régler le micro maintenant
          </button>
          <p className="pilote-muted">
            « Je parle doucement » entend une voix basse. « Pièce bruyante » ignore mieux le bruit autour.
          </p>
        </div>

        <div className="pilote-setting">
          <label htmlFor="pilote-browser-voice">
            Voix de secours du navigateur
          </label>
          <select
            id="pilote-browser-voice"
            value={prefs.browserVoice ?? ""}
            onChange={(e) =>
              updatePrefs({ browserVoice: e.target.value || null })
            }
          >
            <option value="">Automatique (la plus naturelle)</option>
            {voices.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <p className="pilote-muted">
            Utilisée seulement si la voix de Pilote ne répond pas à temps.
          </p>
        </div>

        <dl className="pilote-shortcuts">
          <dt>
            <kbd>Espace</kbd>
          </dt>
          <dd>
            Une fois puis parlez (Pilote répond quand vous vous taisez), ou
            maintenue pendant que vous parlez
          </dd>
          <dt>
            <kbd>Espace</kbd> ×2
          </dt>
          <dd>Faire taire Pilote quand il parle (la commande continue)</dd>
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

        <Link
          href="/spectateur"
          target="_blank"
          rel="noreferrer"
          className="pilote-spectator-link"
        >
          Ouvrir l&apos;écran spectateur ↗
        </Link>
      </details>
    </main>
  );
}
