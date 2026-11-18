"use client";

/* Orbe de Pilote : une seule bulle irisée (rose, cyan, bleu, violet) au cœur blanc, comme une
   conscience. Toute la masse se déforme ensemble :
   - repos : elle respire à peine ;
   - écoute : elle se déforme fortement avec le niveau du micro ;
   - réflexion (l'agent travaille) : ses couleurs tournent ;
   - parole : elle pulse et se tord au rythme d'une voix (syllabes simulées, la lecture audio n'expose
     pas son niveau).
   Dessin sur canvas, sans dépendance. Respecte « réduire les animations ». */

import { useEffect, useRef } from "react";

export type OrbMode = "idle" | "listening" | "thinking" | "speaking";

type Props = { mode: OrbMode; level?: number; size?: number };

// Taches de couleur qui glissent le long du bord de la bulle.
const TINTS = [
  { color: "255, 110, 210", angle: 3.6, speed: 0.11, reach: 0.75 }, // rose
  { color: "0, 205, 255", angle: 0.4, speed: -0.09, reach: 0.6 }, // cyan
  { color: "40, 80, 255", angle: 1.9, speed: 0.07, reach: 0.5 }, // bleu profond
  { color: "160, 90, 255", angle: 5.2, speed: -0.13, reach: 0.55 }, // violet
  { color: "255, 150, 230", angle: 2.6, speed: 0.15, reach: 0.45 }, // rose clair
  { color: "80, 220, 255", angle: 4.4, speed: 0.1, reach: 0.4 }, // cyan clair
];

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
    let energy = 0; // intensité lissée
    let voice = 0; // enveloppe de « syllabes » quand Pilote parle
    let nextSyllable = 0;
    let flow = 0; // temps propre : il accélère quand Pilote parle, écoute ou réfléchit
    let last = performance.now();
    const c = size / 2;
    const R = size * 0.33;

    // Rayon de la bulle selon l'angle : toute la masse se déforme d'un seul tenant.
    const radius = (a: number, amp: number) =>
      R *
      (1 +
        Math.sin(a * 2 + flow * 1.1) * 0.5 * amp +
        Math.sin(a * 3 - flow * 0.8 + 1.3) * 0.35 * amp +
        Math.sin(a * 5 + flow * 1.7 + 2.1) * 0.15 * amp);

    const blobPath = (amp: number, scale = 1) => {
      const steps = 96;
      ctx.beginPath();
      for (let i = 0; i <= steps; i++) {
        const a = (i / steps) * Math.PI * 2;
        const r = radius(a, amp) * scale;
        const x = c + Math.cos(a) * r;
        const y = c + Math.sin(a) * r;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
    };

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = now / 1000;
      const m = modeRef.current;

      if (m === "speaking") {
        if (t > nextSyllable) {
          voice = 0.6 + Math.random() * 0.6;
          nextSyllable = t + 0.11 + Math.random() * 0.15;
        }
        voice *= 0.88;
      } else {
        voice *= 0.85;
      }
      const target =
        m === "listening"
          ? 0.3 + Math.min(1, levelRef.current) * 1.6
          : m === "speaking"
            ? 0.5 + voice
            : m === "thinking"
              ? 0.45
              : 0.12;
      energy += (target - energy) * 0.14;
      flow += dt * (0.4 + energy * 2.2);
      const amp = 0.04 + energy * 0.14; // déformation de la masse : forte quand on parle
      const swell = 1 + Math.sin(t * 1.3) * 0.015 + energy * 0.05;

      ctx.clearRect(0, 0, size, size);
      ctx.save();
      ctx.translate(c, c);
      ctx.scale(swell, swell);
      ctx.translate(-c, -c);

      // Halo extérieur très doux (rose et cyan)
      blobPath(amp);
      ctx.shadowColor = `rgba(255, 140, 230, ${0.35 + energy * 0.2})`;
      ctx.shadowBlur = 40 + energy * 30;
      ctx.fillStyle = "rgba(255, 255, 255, 1)";
      ctx.fill();
      ctx.shadowBlur = 0;

      // Intérieur de la bulle
      ctx.save();
      blobPath(amp);
      ctx.clip();
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, size, size);

      // Taches de couleur qui glissent le long du bord
      for (const tint of TINTS) {
        const a = tint.angle + flow * tint.speed * 3;
        const r = radius(a, amp) * 0.78;
        const x = c + Math.cos(a) * r;
        const y = c + Math.sin(a) * r;
        const spot = ctx.createRadialGradient(x, y, 0, x, y, R * tint.reach);
        spot.addColorStop(0, `rgba(${tint.color}, 0.85)`);
        spot.addColorStop(0.5, `rgba(${tint.color}, 0.35)`);
        spot.addColorStop(1, `rgba(${tint.color}, 0)`);
        ctx.fillStyle = spot;
        ctx.fillRect(0, 0, size, size);
      }

      // Cœur blanc lumineux, légèrement décentré et mouvant
      const hx = c + Math.cos(flow * 0.6) * R * 0.12;
      const hy = c + Math.sin(flow * 0.5) * R * 0.1;
      const heart = ctx.createRadialGradient(hx, hy, 0, hx, hy, R * 0.75);
      heart.addColorStop(0, "rgba(255, 255, 255, 1)");
      heart.addColorStop(0.55, "rgba(255, 255, 255, 0.85)");
      heart.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = heart;
      ctx.fillRect(0, 0, size, size);
      ctx.restore();

      // Liseré irisé du bord
      blobPath(amp);
      const edge = ctx.createLinearGradient(c - R, c - R, c + R, c + R);
      edge.addColorStop(0, "rgba(0, 205, 255, 0.7)");
      edge.addColorStop(0.5, "rgba(255, 120, 220, 0.6)");
      edge.addColorStop(1, "rgba(120, 90, 255, 0.7)");
      ctx.strokeStyle = edge;
      ctx.lineWidth = 1.4;
      ctx.stroke();
      ctx.restore();

      if (!reduce) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  return <canvas ref={canvasRef} className="pilote-orb-canvas" style={{ width: size, height: size }} aria-hidden="true" />;
}
