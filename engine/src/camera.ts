// camera.ts — camera views, parallax and entity geometry as pure functions of time.
import { clamp, lerp, mul, translate, rotate, scale, Mat, Rect, Ease } from "./math";

export interface View { x: number; y: number; scale: number }
export interface CamMove { fromS: number; toS: number; from: View; to: View; easing: string }
export const NEUTRAL: View = { x: 0.5, y: 0.5, scale: 1 };
/** a transition may modify a scene's own camera (zoom multiplier and a pull toward a point) without breaking continuity */
export interface ViewMod { zoomMul: number; toward: { x: number; y: number } | null; amount: number }

/** The camera at time t. Before the first move it rests at the first move's start; between moves it holds; after the last it holds. */
export function viewAt(moves: CamMove[], t: number, ease: Ease): View {
  if (!moves.length) return NEUTRAL;
  if (t <= moves[0].fromS) return moves[0].from;
  for (let i = 0; i < moves.length; i++) {
    const m = moves[i];
    if (t < m.toS) {
      if (t < m.fromS) return moves[i - 1].to;
      const e = ease(m.easing, (t - m.fromS) / (m.toS - m.fromS));
      return { x: lerp(m.from.x, m.to.x, e), y: lerp(m.from.y, m.to.y, e), scale: m.from.scale * Math.pow(m.to.scale / m.from.scale, e) };
    }
  }
  return moves[moves.length - 1].to;
}
export function applyMod(v: View, mod?: ViewMod | null): View {
  if (!mod) return v;
  const amt = mod.toward ? clamp(mod.amount) : 0;
  return { x: mod.toward ? lerp(v.x, mod.toward.x, amt) : v.x, y: mod.toward ? lerp(v.y, mod.toward.y, amt) : v.y, scale: v.scale * mod.zoomMul };
}

/** parallax: far layers (depth→1) follow the camera less, near layers more */
export const parallaxK = (depth: number): number => 1 - 0.55 * clamp(depth);

export interface Place { x: number; y: number; w: number; rotate: number; depth: number }
/** Matrix and rect of one entity for a camera view. The element is laid out at left/top 0 with size (bw, bh) and transform-origin 0 0. */
export function entityGeometry(p: Place, aspectHW: number, W: number, H: number, view: View, extra?: { scale?: number; dy?: number }): { m: Mat; rect: Rect; bw: number; bh: number } {
  const k = parallaxK(p.depth);
  const se = (1 + (view.scale - 1) * k) * (extra?.scale ?? 1);
  const vcx = lerp(0.5, view.x, k) * W, vcy = lerp(0.5, view.y, k) * H;
  const cx = W / 2 + (p.x * W - vcx) * (1 + (view.scale - 1) * k);
  const cy = H / 2 + (p.y * H - vcy) * (1 + (view.scale - 1) * k) + (extra?.dy ?? 0);
  const bw = p.w * W, bh = bw * aspectHW;
  const m = mul(translate(cx, cy), mul(rotate(p.rotate), mul(scale(se), translate(-bw / 2, -bh / 2))));
  return { m, rect: { cx, cy, w: bw * se, h: bh * se }, bw, bh };
}
