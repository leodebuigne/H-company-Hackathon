"use client";

/* Orbe de Pilote : une sphère de verre claire remplie de fumée bleue, cyan et lavande.
   La fumée est calculée sur la carte graphique (WebGL) : un bruit fractal déformé par lui-même
   (domain warping), qui tourbillonne surtout près du bord de la sphère.
   - repos : la fumée dérive lentement ;
   - écoute : elle s'agite avec le niveau du micro ;
   - réflexion (l'agent travaille) : elle tourne ;
   - parole : elle tourbillonne et s'épaissit au rythme d'une voix (syllabes simulées, la lecture
     audio n'expose pas son niveau).
   Sans WebGL : une sphère dégradée fixe. Respecte « réduire les animations ». */

import { useEffect, useRef } from "react";

export type OrbMode = "idle" | "listening" | "thinking" | "speaking";

type Props = { mode: OrbMode; level?: number; size?: number };

const VERTEX = `
attribute vec2 pos;
void main() { gl_Position = vec4(pos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision highp float;
uniform vec2 res;
uniform float time;   // temps propre : accélère quand Pilote parle
uniform float energy; // 0 au repos, ~1.5 quand on parle

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 4; i++) { v += a * noise(p); p = m * p; a *= 0.5; }
  return v;
}

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * res) / (0.5 * res.y);
  uv.y = -uv.y;
  float R = 0.8;
  float r = length(uv);

  // Lueur bleue douce autour de la sphère
  float aura = smoothstep(R + 0.22, R, r) * (0.22 + 0.12 * energy);
  if (r > R) {
    gl_FragColor = vec4(vec3(0.55, 0.78, 1.0) * aura, aura); // couleur prémultipliée
    return;
  }

  // Coordonnées « enroulées » : la fumée tourne autour du centre, plus vite près du bord
  float ang = atan(uv.y, uv.x);
  float swirl = time * 0.15 + (r / R) * (1.2 + energy * 0.8);
  vec2 p = vec2(cos(ang + swirl), sin(ang + swirl)) * r * 1.3;

  // Fumée : bruit fractal déformé deux fois par lui-même
  float warp = 2.2 + energy * 1.2;
  vec2 q = vec2(fbm(p + vec2(0.0, time * 0.10)), fbm(p + vec2(5.2, 1.3) - time * 0.08));
  vec2 w = vec2(fbm(p + warp * q + vec2(1.7, 9.2) + time * 0.12), fbm(p + warp * q + vec2(8.3, 2.8) - time * 0.10));
  float f = fbm(p + warp * w);

  // Plus dense près du bord (la fumée s'enroule autour), légère au centre
  float ring = smoothstep(0.15, 0.85, r / R);
  float density = smoothstep(0.32 - 0.05 * energy, 0.8, f) * (0.3 + 0.7 * ring);
  density = clamp(density * (1.15 + 0.35 * energy), 0.0, 1.0);

  // Couleurs : cyan, bleu, lavande selon les volutes
  vec3 cyan = vec3(0.18, 0.76, 1.0);
  vec3 blue = vec3(0.24, 0.45, 1.0);
  vec3 lavender = vec3(0.66, 0.56, 1.0);
  vec3 smoke = mix(cyan, blue, smoothstep(0.3, 0.8, w.x));
  smoke = mix(smoke, lavender, smoothstep(0.45, 0.9, q.y) * 0.8);

  // Verre : blanc au centre, bleu lumineux vers le bord
  vec3 glass = mix(vec3(1.0), vec3(0.86, 0.93, 1.0), smoothstep(0.2, 0.95, r / R));
  vec3 col = mix(glass, smoke, density * 0.9);
  // liseré clair des volutes (la lumière accroche les bords de la fumée)
  // reflet doux sur les volutes les plus épaisses
  col += vec3(0.12) * smoothstep(0.7, 0.95, f) * ring;
  // bord du verre
  col = mix(col, vec3(0.45, 0.68, 1.0), smoothstep(R * 0.86, R, r) * 0.7);
  // reflet en haut à gauche
  float shine = smoothstep(0.42, 0.0, length(uv - vec2(-0.33, -0.38)));
  col = mix(col, vec3(1.0), shine * 0.75);
  // bord net mais doux
  float edge = smoothstep(R, R - 0.012, r);
  float a = max(edge, aura);
  gl_FragColor = vec4(mix(vec3(0.55, 0.78, 1.0), col, edge) * a, a); // couleur prémultipliée
}
`;

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
    if (!canvas) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    const gl = canvas.getContext("webgl", { premultipliedAlpha: true, antialias: true });
    if (!gl) {
      canvas.classList.add("is-fallback");
      return;
    }

    const shader = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    };
    const program = gl.createProgram()!;
    gl.attachShader(program, shader(gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(program, shader(gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      canvas.classList.add("is-fallback");
      return;
    }
    gl.useProgram(program);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(program, "pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const uRes = gl.getUniformLocation(program, "res");
    const uTime = gl.getUniformLocation(program, "time");
    const uEnergy = gl.getUniformLocation(program, "energy");
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(uRes, canvas.width, canvas.height);

    let raf = 0;
    let energy = 0;
    let voice = 0;
    let nextSyllable = 0;
    let flow = 0;
    let last = performance.now();

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
              : 0.1;
      energy += (target - energy) * 0.1;
      flow += dt * (0.5 + energy * 2.5);

      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(uTime, flow);
      gl.uniform1f(uEnergy, energy);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (!reduce) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      gl.deleteProgram(program);
      gl.deleteBuffer(buffer);
    };
  }, [size]);

  return (
    <span className="pilote-orb" style={{ width: size, height: size }} aria-hidden="true">
      <canvas ref={canvasRef} className="pilote-orb-canvas" style={{ width: size, height: size }} />
    </span>
  );
}
