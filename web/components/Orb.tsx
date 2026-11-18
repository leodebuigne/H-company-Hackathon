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

      // Lueur intérieure
      const glow = ctx.createRadialGradient(c, c, base * 0.2, c, c, base * 1.25);
      glow.addColorStop(0, `rgba(79, 227, 255, ${0.05 + energy * 0.08})`);
      glow.addColorStop(0.75, `rgba(79, 227, 255, ${0.1 + energy * 0.12})`);
      glow.addColorStop(1, "rgba(79, 227, 255, 0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(c, c, base * 1.3, 0, Math.PI * 2);
      ctx.fill();

      // Anneaux qui ondulent (plusieurs couches décalées = matière lumineuse)
      const layers = [
        { color: "79, 227, 255", width: 30, alpha: 0.14, seed: 0.0, amp: 1.2, blur: 46 },
        { color: "79, 227, 255", width: 16, alpha: 0.26, seed: 1.7, amp: 1.0, blur: 30 },
        { color: "120, 236, 255", width: 7, alpha: 0.45, seed: 3.1, amp: 0.8, blur: 18 },
        { color: "79, 227, 255", width: 2.5, alpha: 0.75, seed: 4.6, amp: 1.3, blur: 10 },
      ];
      ctx.lineJoin = "round";
      for (const layer of layers) {
        ctx.beginPath();
        const steps = 120;
        for (let i = 0; i <= steps; i++) {
          const a = (i / steps) * Math.PI * 2;
          const r = base * breath + wobble(a + spin, t, layer.seed) * base * 0.13 * energy * layer.amp;
          const x = c + Math.cos(a) * r;
          const y = c + Math.sin(a) * r;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = `rgba(${layer.color}, ${layer.alpha})`;
        ctx.lineWidth = layer.width;
        ctx.shadowColor = "rgba(79, 227, 255, 0.9)";
        ctx.shadowBlur = layer.blur + energy * 20;
        ctx.stroke();
      }
      ctx.shadowBlur = 0;

      // Poussière lumineuse le long de l'anneau (grain de la pièce jointe)
      const dust = 420 + Math.round(energy * 380);
      for (let i = 0; i < dust; i++) {
        const a = Math.random() * Math.PI * 2;
        const r = base * breath + wobble(a + spin, t, 1.7) * base * 0.09 * energy + (Math.random() - 0.5) * (16 + energy * 26);
        ctx.fillStyle = `rgba(${Math.random() < 0.7 ? "79, 227, 255" : "10, 124, 255"}, ${0.15 + Math.random() * 0.55})`;
        ctx.fillRect(c + Math.cos(a) * r, c + Math.sin(a) * r, 1.6, 1.6);
      }

      if (!reduce) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  return <canvas ref={canvasRef} className="pilote-orb-canvas" style={{ width: size, height: size }} aria-hidden="true" />;
}
