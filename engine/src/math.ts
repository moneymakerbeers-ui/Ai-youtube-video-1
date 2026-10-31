// math.ts — pure helpers: clamping, easing (cubic-bezier tokens), 2D affine matrices. No DOM, fully unit-tested.
export const clamp = (x: number, a = 0, b = 1): number => Math.min(b, Math.max(a, x));
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
export const smoothstep = (a: number, b: number, x: number): number => {
  const t = clamp((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};
/** geometric interpolation: constant perceived zoom speed */
export const lerpLog = (a: number, b: number, t: number): number => a * Math.pow(b / a, t);

export type Bezier = [number, number, number, number];
/** CSS-style cubic-bezier(x1,y1,x2,y2): returns f(x) for x in [0,1], solved with Newton steps and a bisection fallback. */
export function bezier(x1: number, y1: number, x2: number, y2: number): (x: number) => number {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const X = (t: number) => ((ax * t + bx) * t + cx) * t;
  const Y = (t: number) => ((ay * t + by) * t + cy) * t;
  const dX = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) {
      const err = X(t) - x;
      if (Math.abs(err) < 1e-7) return Y(t);
      const d = dX(t);
      if (Math.abs(d) < 1e-6) break;
      t -= err / d;
    }
    let lo = 0, hi = 1;
    t = x;
    for (let i = 0; i < 40; i++) {
      const v = X(t);
      if (Math.abs(v - x) < 1e-7) break;
      if (v < x) lo = t; else hi = t;
      t = (lo + hi) / 2;
    }
    return Y(t);
  };
}

export const EASING_TOKENS: Record<string, Bezier> = {
  standard: [0.4, 0, 0.2, 1],
  emphasized: [0.65, 0, 0.35, 1],
  soft: [0.37, 0, 0.63, 1],
};
export type Ease = (name: string, t: number) => number;
export function makeEase(extra: Record<string, Bezier> = {}): Ease {
  const table: Record<string, (x: number) => number> = {};
  for (const [k, v] of Object.entries({ ...EASING_TOKENS, ...extra })) table[k] = bezier(...v);
  return (name, t) => (table[name] ?? table.standard)(clamp(t));
}

/** 2D affine as CSS matrix(a,b,c,d,e,f): x' = a x + c y + e ; y' = b x + d y + f */
export type Mat = [number, number, number, number, number, number];
export const I: Mat = [1, 0, 0, 1, 0, 0];
export function mul(m: Mat, n: Mat): Mat { // m ∘ n : apply n first, then m
  return [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3], m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]];
}
export const translate = (x: number, y: number): Mat => [1, 0, 0, 1, x, y];
export const scale = (s: number, sy = s): Mat => [s, 0, 0, sy, 0, 0];
export const rotate = (deg: number): Mat => { const r = (deg * Math.PI) / 180, c = Math.cos(r), s = Math.sin(r); return [c, s, -s, c, 0, 0]; };
export const scaleAbout = (cx: number, cy: number, s: number): Mat => mul(translate(cx, cy), mul(scale(s), translate(-cx, -cy)));
export const apply = (m: Mat, x: number, y: number): [number, number] => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
export const css = (m: Mat): string => `matrix(${m.map((v) => (Math.abs(v) < 1e-9 ? 0 : +v.toFixed(5))).join(",")})`;
export const isIdentity = (m: Mat): boolean => m.every((v, i) => Math.abs(v - I[i]) < 1e-9);

export interface Rect { cx: number; cy: number; w: number; h: number }
