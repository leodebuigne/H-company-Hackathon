"use client";

/* Orbe de Pilote : une sphère de verre claire traversée de voiles de soie bleus, cyan et lavande,
   d'après l'image de référence. Aucun grain : tout est translucide et voilé.
   - repos : les voiles flottent lentement ;
   - écoute : ils ondulent avec le niveau du micro ;
   - réflexion (l'agent travaille) : ils tournent doucement ;
   - parole : ils s'agitent et se plient au rythme d'une voix (syllabes simulées, la lecture audio
     n'expose pas son niveau).
   Dessin sur canvas, sans dépendance. Respecte « réduire les animations ». */

import { useEffect, useRef } from "react";

export type OrbMode = "idle" | "listening" | "thinking" | "speaking";

type Props = { mode: OrbMode; level?: number; size?: number };

// Voiles : rubans de soie qui traversent la sphère. angle = direction, shift = décalage du centre.
const VEILS = [
  { angle: -0.9, shift: -0.16, width: 0.3, color: "60, 165, 255", seed: 0.0 },
  { angle: 0.55, shift: 0.1, width: 0.26, color: "40, 205, 255", seed: 1.6 },
  { angle: 1.45, shift: -0.04, width: 0.22, color: "125, 135, 255", seed: 3.1 },
  { angle: -0.25, shift: 0.3, width: 0.18, color: "80, 190, 255", seed: 4.4 },
  { angle: 2.3, shift: -0.34, width: 0.2, color: "150, 150, 255", seed: 5.7 },
  { angle: 0.95, shift: 0.36, width: 0.16, color: "0, 190, 250", seed: 7.2 },
  { angle: -1.6, shift: 0.22, width: 0.17, color: "110, 170, 255", seed: 8.5 },
  { angle: 2.9, shift: 0.02, width: 0.14, color: "170, 140, 255", seed: 9.9 },
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
    let energy = 0;
    let voice = 0;
    let nextSyllable = 0;
    let flow = 0;
    let last = performance.now();
    const c = size / 2;
    const R0 = size * 0.4;

    // Un voile : ruban qui s'enroule autour de la sphère (grand cercle vu en perspective = ellipse),
    // sur une partie du tour seulement, plus large au milieu et qui se retourne comme de la soie.
    const ribbon = (v: (typeof VEILS)[number], R: number, amp: number) => {
      const rot = v.angle + flow * 0.08 * (v.seed % 2 > 1 ? 1 : -1);
      const tilt = 0.35 + 0.9 * (0.5 + 0.5 * Math.sin(flow * 0.2 + v.seed)); // inclinaison du tour
      const ux = Math.cos(rot);
      const uy = Math.sin(rot);
      const start = (VEILS.indexOf(v) / VEILS.length) * Math.PI * 2 + flow * 0.15;
      const span = Math.PI * (1.1 + v.width); // longueur du voile sur le tour
      const steps = 72;
      const top: [number, number][] = [];
      const bottom: [number, number][] = [];
      for (let i = 0; i <= steps; i++) {
        const s = i / steps;
        const th = start + s * span;
        const ripple = 1 + Math.sin(th * 3 + flow * 1.3 + v.seed) * 0.035 * amp; // le voile ondule
        const ex = Math.cos(th) * R * 0.9 * ripple;
        const ey = Math.sin(th) * R * 0.9 * Math.cos(tilt) * ripple;
        const x = c + ex * ux - ey * uy;
        const y = c + ex * uy + ey * ux;
        // largeur : nulle aux extrémités, la soie se retourne par endroits
        const twist = Math.sin(th * 1.5 + flow * 0.9 + v.seed * 1.3);
        const half = v.width * R * 1.05 * Math.sin(Math.PI * s) * (0.3 + 0.7 * Math.abs(twist));
        // direction vers l'extérieur de l'ellipse
        const len = Math.hypot(x - c, y - c) || 1;
        const nx = (x - c) / len;
        const ny = (y - c) / len;
        top.push([x + nx * half, y + ny * half]);
        bottom.push([x - nx * half, y - ny * half]);
      }
      return { top, bottom, ux, uy, ox: c, oy: c };
    };

    const trace = (pts: [number, number][], move = true) => {
      pts.forEach(([x, y], i) => (i === 0 && move ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
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
          ? 0.3 + Math.min(1, levelRef.current) * 1.4
          : m === "speaking"
            ? 0.55 + voice
            : m === "thinking"
              ? 0.5
              : 0.15;
      energy += (target - energy) * 0.12;
      flow += dt * (0.35 + energy * 2);
      const amp = 0.55 + energy * 0.9;
      const R = R0 * (1 + Math.sin(t * 1.3) * 0.006 + energy * 0.012);

      ctx.clearRect(0, 0, size, size);

      // Lueur bleue très douce autour du verre
      const aura = ctx.createRadialGradient(c, c, R * 0.95, c, c, R * 1.2);
      aura.addColorStop(0, `rgba(120, 190, 255, ${0.18 + energy * 0.1})`);
      aura.addColorStop(1, "rgba(120, 190, 255, 0)");
      ctx.fillStyle = aura;
      ctx.beginPath();
      ctx.arc(c, c, R * 1.2, 0, Math.PI * 2);
      ctx.fill();

      ctx.save();
      ctx.beginPath();
      ctx.arc(c, c, R, 0, Math.PI * 2);
      ctx.clip();

      // Verre : presque blanc au centre, bleu lumineux vers le bord
      const body = ctx.createRadialGradient(c - R * 0.15, c - R * 0.2, R * 0.05, c, c, R);
      body.addColorStop(0, "#ffffff");
      body.addColorStop(0.6, "#f2f8ff");
      body.addColorStop(0.88, "#d3e9ff");
      body.addColorStop(1, "#9ccaff");
      ctx.fillStyle = body;
      ctx.fillRect(c - R, c - R, R * 2, R * 2);

      // Cœur lavande diffus
      const heart = ctx.createRadialGradient(c, c + R * 0.05, 0, c, c, R * 0.6);
      heart.addColorStop(0, `rgba(150, 120, 255, ${0.28 + energy * 0.12})`);
      heart.addColorStop(1, "rgba(150, 120, 255, 0)");
      ctx.fillStyle = heart;
      ctx.fillRect(c - R, c - R, R * 2, R * 2);

      // Nuages de couleur en profondeur, derrière les voiles
      for (let k = 0; k < 3; k++) {
        const a = flow * (0.12 + k * 0.05) + k * 2.1;
        const x = c + Math.cos(a) * R * 0.35;
        const y = c + Math.sin(a * 1.2) * R * 0.3;
        const cloud = ctx.createRadialGradient(x, y, 0, x, y, R * 0.55);
        cloud.addColorStop(0, `rgba(${k === 1 ? "140, 120, 255" : "40, 200, 255"}, ${0.16 + energy * 0.06})`);
        cloud.addColorStop(1, "rgba(40, 200, 255, 0)");
        ctx.fillStyle = cloud;
        ctx.fillRect(c - R, c - R, R * 2, R * 2);
      }

      // Voiles de soie : voile translucide, fibres fines, pli brillant, liseré blanc lumineux
      const lerp = (p: [number, number], q: [number, number], f: number): [number, number] => [
        p[0] + (q[0] - p[0]) * f,
        p[1] + (q[1] - p[1]) * f,
      ];
      // Fumée : chaque volute est faite de filaments flous et translucides qui s'écartent et se tordent,
      // sans bord net ; un filament plus clair au cœur donne la lumière.
      for (const v of VEILS) {
        const { top, bottom } = ribbon(v, R, amp);
        const strands = 12;
        for (let k = 0; k <= strands; k++) {
          const f = k / strands;
          const core = 1 - Math.abs(f - 0.5) * 2; // 1 au milieu de la volute, 0 sur ses bords
          const pts = top.map((p, i) => {
            const q = lerp(p, bottom[i], f);
            const sN = i / (top.length - 1);
            const curl = Math.sin(sN * 9 + flow * 1.4 + v.seed + k * 0.7) * R * 0.025 * (0.5 + amp * 0.5);
            const dx = p[0] - bottom[i][0];
            const dy = p[1] - bottom[i][1];
            const len = Math.hypot(dx, dy) || 1;
            return [q[0] + (dx / len) * curl, q[1] + (dy / len) * curl] as [number, number];
          });
          ctx.beginPath();
          trace(pts);
          // la volute apparaît et s'efface à ses deux bouts
          const a0 = pts[0];
          const a1 = pts[pts.length - 1];
          const fade = ctx.createLinearGradient(a0[0], a0[1], a1[0], a1[1]);
          const alpha = (0.07 + 0.2 * core) * (1 + energy * 0.4);
          fade.addColorStop(0, `rgba(${v.color}, 0)`);
          fade.addColorStop(0.5, `rgba(${v.color}, ${alpha})`);
          fade.addColorStop(1, `rgba(${v.color}, 0)`);
          // corde trop courte (arc presque fermé) : couleur uniforme plutôt qu'un dégradé écrasé
          ctx.strokeStyle = Math.hypot(a1[0] - a0[0], a1[1] - a0[1]) > R * 0.4 ? fade : `rgba(${v.color}, ${alpha * 0.7})`;
          ctx.lineCap = "round";
          ctx.lineWidth = 2 + core * 6;
          ctx.shadowColor = `rgba(${v.color}, 0.5)`;
          ctx.shadowBlur = 22;
          ctx.stroke();
        }
        // filament de lumière au cœur de la volute
        ctx.beginPath();
        trace(top.map((p, i) => lerp(p, bottom[i], 0.45)));
        ctx.strokeStyle = `rgba(255, 255, 255, ${0.22 + energy * 0.15})`;
        ctx.lineWidth = 1;
        ctx.shadowColor = "rgba(255, 255, 255, 0.9)";
        ctx.shadowBlur = 10;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      // Bord du verre : anneau bleu lumineux à l'intérieur de la sphère
      const rim = ctx.createRadialGradient(c, c, R * 0.8, c, c, R);
      rim.addColorStop(0, "rgba(90, 170, 255, 0)");
      rim.addColorStop(0.85, "rgba(90, 170, 255, 0.18)");
      rim.addColorStop(1, "rgba(60, 150, 255, 0.55)");
      ctx.fillStyle = rim;
      ctx.fillRect(c - R, c - R, R * 2, R * 2);

      // Reflet blanc en haut à gauche
      const shine = ctx.createRadialGradient(c - R * 0.42, c - R * 0.48, 0, c - R * 0.42, c - R * 0.48, R * 0.38);
      shine.addColorStop(0, "rgba(255, 255, 255, 0.9)");
      shine.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = shine;
      ctx.fillRect(c - R, c - R, R * 2, R * 2);
      ctx.restore();

      // Croissant clair en bas à droite
      ctx.beginPath();
      ctx.arc(c, c, R * 0.93, Math.PI * 0.1, Math.PI * 0.55);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.45)";
      ctx.lineWidth = 3;
      ctx.stroke();

      // Contour fin du verre
      ctx.beginPath();
      ctx.arc(c, c, R, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(80, 165, 255, 0.6)";
      ctx.lineWidth = 1.2;
      ctx.stroke();

      if (!reduce) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  return (
    <span className="pilote-orb" style={{ width: size, height: size }} aria-hidden="true">
      <canvas ref={canvasRef} className="pilote-orb-canvas" style={{ width: size, height: size }} />
    </span>
  );
}
