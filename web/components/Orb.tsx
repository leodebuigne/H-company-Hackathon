"use client";

/* Orbe de Pilote : un halo bleu vivant, comme une conscience qui respire.
   - repos : respire lentement ;
   - écoute : se déforme avec le niveau du micro ;
   - réflexion (l'agent travaille) : tourne et scintille ;
   - parole : ondule au rythme d'une voix (syllabes simulées, la lecture audio n'expose pas son niveau).
   Dessin sur canvas, sans dépendance. Respecte « réduire les animations ». */

import { useEffect, useRef } from "react";

export type OrbMode = "idle" | "listening" | "thinking" | "speaking";

type Props = { mode: OrbMode; level?: number; size?: number };

// Bruit doux et périodique sur le cercle : somme de sinus aux phases qui dérivent dans le temps.
function wobble(angle: number, t: number, seed: number) {
  return (
    Math.sin(angle * 3 + t * 1.3 + seed) * 0.5 +
    Math.sin(angle * 5 - t * 1.9 + seed * 2.1) * 0.3 +
    Math.sin(angle * 8 + t * 2.7 + seed * 3.7) * 0.2
  );
}

export default function Orb({ mode, level = 0, size = 320 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const modeRef = useRef(mode);
  const levelRef = useRef(level);
  useEffect(() => {
    modeRef.current = mode;
    levelRef.current = level;
  }, [mode, level]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    let raf = 0;
    let energy = 0; // amplitude lissée de la déformation
    let spin = 0;
    let voice = 0; // enveloppe de « syllabes » quand Pilote parle
    let nextSyllable = 0;
    const start = performance.now();
    const c = size / 2;
    const base = size * 0.27;

    const draw = (now: number) => {
      const t = (now - start) / 1000;
      const m = modeRef.current;

      // Cible d'énergie selon l'état
      if (m === "speaking") {
        if (t > nextSyllable) {
          voice = 0.55 + Math.random() * 0.45;
          nextSyllable = t + 0.12 + Math.random() * 0.16;
        }
        voice *= 0.9;
      } else {
        voice *= 0.85;
      }
      const target =
        m === "listening" ? 0.25 + Math.min(1, levelRef.current) * 1.2 : m === "speaking" ? 0.35 + voice : m === "thinking" ? 0.35 : 0.14;
      energy += (target - energy) * 0.12;
      spin += m === "thinking" ? 0.035 : 0.006;
      const breath = 1 + Math.sin(t * 1.6) * 0.02;

      ctx.clearRect(0, 0, size, size);

      // Anneau de la photo : bande cyan large, centre blanc, bord extérieur granuleux, aucun trait net.
      const ring = base * breath * (1 + energy * 0.04);
      const band = size * 0.045 * (1 + energy * 0.35);

      // 1. Bande de lumière douce : se fond vers le centre blanc, plus franche vers l'extérieur
      const light = ctx.createRadialGradient(c, c, ring - band * 1.4, c, c, ring + band * 0.8);
      light.addColorStop(0, "rgba(79, 227, 255, 0)");
      light.addColorStop(0.5, `rgba(79, 227, 255, ${0.12 + energy * 0.1})`);
      light.addColorStop(0.82, `rgba(79, 227, 255, ${0.7 + energy * 0.2})`);
      light.addColorStop(1, "rgba(79, 227, 255, 0)");
      ctx.fillStyle = light;
      ctx.beginPath();
      ctx.arc(c, c, ring + band * 0.7, 0, Math.PI * 2);
      ctx.fill();

      // 2. Grain : points cyan serrés sur le bord extérieur, qui ondulent avec la voix
      const dust = 2200 + Math.round(energy * 900);
      for (let i = 0; i < dust; i++) {
        const a = Math.random() * Math.PI * 2;
        const depth = Math.pow(Math.random(), 1.8); // 0 = bord extérieur, 1 = vers l'intérieur
        const r = ring + band * 0.7 - depth * band * 1.2 + wobble(a + spin, t, 1.7) * base * 0.06 * energy;
        ctx.fillStyle = `rgba(${Math.random() < 0.85 ? "79, 227, 255" : "40, 200, 245"}, ${(1 - depth) * (0.35 + Math.random() * 0.5)})`;
        ctx.fillRect(c + Math.cos(a) * r, c + Math.sin(a) * r, 1.3, 1.3);
      }

      if (!reduce) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  return <canvas ref={canvasRef} className="pilote-orb-canvas" style={{ width: size, height: size }} aria-hidden="true" />;
}
