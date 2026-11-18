"use client";

/* Orbe de Pilote : une sphère de verre traversée de voiles de lumière bleue et violette, comme une
   conscience qui respire.
   - repos : les voiles flottent lentement ;
   - écoute : ils suivent le niveau du micro ;
   - réflexion (l'agent travaille) : ils tournent ;
   - parole : ils ondulent au rythme d'une voix (syllabes simulées, la lecture audio n'expose pas son niveau).
   Dessin sur canvas, sans dépendance. Respecte « réduire les animations ». */

import { useEffect, useRef } from "react";

export type OrbMode = "idle" | "listening" | "thinking" | "speaking";

type Props = { mode: OrbMode; level?: number; size?: number };

// Voiles : chacun est une forme souple qui dérive dans la sphère, avec sa couleur et sa phase.
const VEILS = [
  { from: "rgba(0, 190, 255, 0.50)", to: "rgba(120, 220, 255, 0.06)", seed: 0.0, scale: 0.8, offset: 0.16, stretch: 0.62 },
  { from: "rgba(135, 105, 255, 0.45)", to: "rgba(90, 160, 255, 0.06)", seed: 2.1, scale: 0.6, offset: 0.2, stretch: 0.9 },
  { from: "rgba(40, 130, 255, 0.42)", to: "rgba(160, 230, 255, 0.05)", seed: 4.3, scale: 0.7, offset: 0.22, stretch: 0.55 },
  { from: "rgba(90, 225, 255, 0.50)", to: "rgba(170, 140, 255, 0.10)", seed: 6.0, scale: 0.42, offset: 0.14, stretch: 1.0 },
]

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
    let flow = 0; // temps propre des voiles : il accélère quand Pilote parle ou réfléchit
    let last = performance.now();
    const c = size / 2;
    const R = size * 0.36;

    // Contour d'un voile : cercle déformé par plusieurs sinus, décentré, qui tourne lentement.
    const veil = (seed: number, scale: number, offset: number, stretch: number, amp: number) => {
      const cx = c + Math.cos(flow * 0.5 + seed) * R * offset;
      const cy = c + Math.sin(flow * 0.43 + seed * 1.3) * R * offset;
      const r0 = R * scale;
      const steps = 64;
      ctx.beginPath();
      for (let i = 0; i <= steps; i++) {
        const a = (i / steps) * Math.PI * 2;
        const d =
          Math.sin(a * 2 + flow * 0.9 + seed) * 0.22 +
          Math.sin(a * 3 - flow * 0.7 + seed * 1.7) * 0.14 * amp +
          Math.sin(a * 5 + flow * 1.3 + seed * 2.3) * 0.06 * amp;
        const r = r0 * (1 + d);
        const x = cx + Math.cos(a + flow * 0.15) * r;
        const y = cy + Math.sin(a + flow * 0.15) * r * stretch;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      return { cx, cy, r0 };
    };

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = now / 1000;
      const m = modeRef.current;

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
        m === "listening"
          ? 0.3 + Math.min(1, levelRef.current) * 1.2
          : m === "speaking"
            ? 0.45 + voice
            : m === "thinking"
              ? 0.55
              : 0.15;
      energy += (target - energy) * 0.1;
      flow += dt * (0.35 + energy * 1.6);
      const breath = 1 + Math.sin(t * 1.4) * 0.012 + energy * 0.015;

      ctx.clearRect(0, 0, size, size);
      const r = R * breath;

      // Lueur douce autour de la sphère
      const aura = ctx.createRadialGradient(c, c, r * 0.9, c, c, r * 1.35);
      aura.addColorStop(0, `rgba(90, 200, 255, ${0.14 + energy * 0.14})`);
      aura.addColorStop(1, "rgba(90, 200, 255, 0)");
      ctx.fillStyle = aura;
      ctx.beginPath();
      ctx.arc(c, c, r * 1.35, 0, Math.PI * 2);
      ctx.fill();

      // Intérieur de la sphère (verre clair)
      ctx.save();
      ctx.beginPath();
      ctx.arc(c, c, r, 0, Math.PI * 2);
      ctx.clip();
      const body = ctx.createRadialGradient(c - r * 0.2, c - r * 0.25, r * 0.1, c, c, r);
      body.addColorStop(0, "rgba(255, 255, 255, 1)");
      body.addColorStop(0.75, "rgba(246, 250, 255, 1)");
      body.addColorStop(1, "rgba(225, 240, 255, 1)");
      ctx.fillStyle = body;
      ctx.fillRect(c - r, c - r, r * 2, r * 2);

      // Voiles de lumière : remplissage translucide et liseré clair, comme de la soie
      const amp = 0.6 + energy * 0.9;
      for (const v of VEILS) {
        const shape = veil(v.seed, v.scale, v.offset, v.stretch, amp);
        const fill = ctx.createLinearGradient(
          shape.cx - shape.r0,
          shape.cy - shape.r0,
          shape.cx + shape.r0,
          shape.cy + shape.r0,
        );
        fill.addColorStop(0, v.from);
        fill.addColorStop(1, v.to);
        ctx.fillStyle = fill;
        ctx.shadowColor = "rgba(90, 150, 255, 0.35)";
        ctx.shadowBlur = 18;
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = `rgba(255, 255, 255, ${0.55 + energy * 0.2})`;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }

      // Bord du verre : lumière bleue qui s'intensifie vers l'extérieur
      const rim = ctx.createRadialGradient(c, c, r * 0.72, c, c, r);
      rim.addColorStop(0, "rgba(80, 200, 255, 0)");
      rim.addColorStop(1, `rgba(60, 190, 255, ${0.28 + energy * 0.15})`);
      ctx.fillStyle = rim;
      ctx.fillRect(c - r, c - r, r * 2, r * 2);

      // Reflet en haut à gauche
      const shine = ctx.createRadialGradient(c - r * 0.38, c - r * 0.45, 0, c - r * 0.38, c - r * 0.45, r * 0.45);
      shine.addColorStop(0, "rgba(255, 255, 255, 0.85)");
      shine.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = shine;
      ctx.fillRect(c - r, c - r, r * 2, r * 2);
      ctx.restore();

      // Contour fin du verre
      ctx.beginPath();
      ctx.arc(c, c, r, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(90, 200, 255, 0.5)";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      if (!reduce) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  return <canvas ref={canvasRef} className="pilote-orb-canvas" style={{ width: size, height: size }} aria-hidden="true" />;
}
