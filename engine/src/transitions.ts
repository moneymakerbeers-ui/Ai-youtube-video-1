// transitions.ts — the transition operators as PURE functions of progress. The renderer applies the returned state to two
// retained scene views (A leaving, B arriving). Every operator starts with A untouched and B invisible, and ends with B
// untouched and A invisible, so a window can never pop at its edges. Anchors are rects in frame pixels.
import { clamp, lerp, lerpLog, smoothstep, mul, translate, scaleAbout, apply, I, Mat, Rect, Ease } from "./math";
import type { ViewMod } from "./camera";

export type OpType = "cut" | "dissolve" | "match_geometry" | "match_movement" | "nested_scale" | "occlusion_reveal" | "depth_through_object" | "focus_bridge" | "truthful_morph";
export interface Clip { cx: number; cy: number; r: number; feather: number }
export interface SideFx { m: Mat; back: number; content: number; anchor: number; blur: number; clip: Clip | null; mod: ViewMod | null }
export interface TransitionCtx { W: number; H: number; ease: Ease; easing: string; a: Rect | null; b: Rect | null; velocity?: { x: number; y: number } | null }
export interface TransitionFx { A: SideFx; B: SideFx; bAbove: boolean; morph: { e: number; rect: Rect } | null; usedType: OpType; fellBack: boolean }

const visible = (): SideFx => ({ m: I, back: 1, content: 1, anchor: 1, blur: 0, clip: null, mod: null });
const hidden = (): SideFx => ({ ...visible(), back: 0, content: 0, anchor: 0 });
const band = (e: number, a: number, b: number) => smoothstep(a, b, e);

/** both worlds are moved so that the two anchors coincide for the whole window */
function lock(a: Rect, b: Rect, e: number, rClamp: [number, number]) {
  const r = clamp(b.w / a.w, rClamp[0], rClamp[1]);
  const sA = Math.pow(r, e), sB = Math.pow(r, e - 1);
  const lx = lerp(a.cx, b.cx, e), ly = lerp(a.cy, b.cy, e);
  return {
    mA: mul(translate(lx - a.cx, ly - a.cy), scaleAbout(a.cx, a.cy, sA)),
    mB: mul(translate(lx - b.cx, ly - b.cy), scaleAbout(b.cx, b.cy, sB)),
    rect: { cx: lx, cy: ly, w: lerpLog(a.w, b.w, e), h: lerpLog(a.h, b.h, e) } as Rect, // geometric: the same perceived speed as the zoom
  };
}

export function transitionFx(type: OpType, p: number, ctx: TransitionCtx): TransitionFx {
  const e = ctx.ease(ctx.easing, clamp(p));
  const { W, H, a, b } = ctx;
  const A = visible(), B = hidden();
  const done = (bAbove: boolean, used: OpType = type, morph: TransitionFx["morph"] = null, fellBack = false): TransitionFx => ({ A, B, bAbove, morph, usedType: used, fellBack });
  const needsBoth: OpType[] = ["match_geometry", "focus_bridge", "truthful_morph"];
  let t: OpType = type;
  if ((needsBoth.includes(t) && !(a && b)) || ((t === "nested_scale" || t === "occlusion_reveal" || t === "depth_through_object") && !a)) t = "dissolve";
  const fellBack = t !== type;

  switch (t) {
    case "dissolve": {
      const f = 1 - e;
      Object.assign(A, { back: f, content: f, anchor: f });
      Object.assign(B, visible());
      return done(false, t, null, fellBack);
    }
    case "match_geometry": {
      const L = lock(a!, b!, e, [1 / 8, 8]);
      A.m = L.mA; B.m = L.mB;
      Object.assign(A, { back: 1 - band(e, 0.25, 0.75), content: 1 - band(e, 0, 0.5), anchor: 1 - band(e, 0.35, 0.65) });
      Object.assign(B, { back: band(e, 0.25, 0.75), content: band(e, 0.5, 1), anchor: band(e, 0.35, 0.65) });
      return done(true, t, null, fellBack);
    }
    case "focus_bridge": {
      const L = lock(a!, b!, e, [0.5, 2]);
      A.m = L.mA; B.m = L.mB;
      const bl = 0.014 * H;
      Object.assign(A, { back: 1 - band(e, 0.2, 0.8), content: 1 - band(e, 0.2, 0.7), anchor: 1 - band(e, 0.3, 0.7), blur: bl * band(e, 0, 0.6) });
      Object.assign(B, { back: band(e, 0.2, 0.8), content: band(e, 0.3, 0.8), anchor: band(e, 0.3, 0.7), blur: bl * (1 - band(e, 0.4, 1)) });
      return done(true, t, null, fellBack);
    }
    case "truthful_morph": {
      const L = lock(a!, b!, e, [1 / 8, 8]);
      A.m = L.mA; B.m = L.mB;
      // the two real anchors are replaced by ONE deforming outline (the overlay) from the very first step: an anchor that fades out
      // while the overlay already moves would leave a ghost outline. At e = 0 the overlay is pixel-identical to A's anchor.
      Object.assign(A, { back: 1 - band(e, 0.25, 0.75), content: 1 - band(e, 0, 0.5), anchor: e <= 1e-9 ? 1 : 0 });
      Object.assign(B, { back: band(e, 0.25, 0.75), content: band(e, 0.5, 1), anchor: 0 });
      return done(true, t, { e, rect: L.rect }, fellBack);
    }
    case "match_movement": {
      const v = ctx.velocity ?? { x: 1, y: 0 };
      const n = Math.hypot(v.x, v.y) || 1;
      const dx = (v.x / n) * 0.42 * W, dy = (v.y / n) * 0.42 * H;
      A.m = translate(-dx * e, -dy * e);
      B.m = translate(dx * (1 - e), dy * (1 - e));
      const f = band(e, 0.3, 0.7), bl = 0.011 * H * Math.sin(Math.PI * e);
      Object.assign(A, { back: 1 - f, content: 1 - f, anchor: 1 - f, blur: bl });
      Object.assign(B, { back: f, content: f, anchor: f, blur: bl });
      return done(true, t, null, fellBack);
    }
    case "nested_scale": {
      // B is the INSIDE of A's anchor: both are seen through one camera that zooms from the whole frame into the anchor rect.
      const k = clamp(Math.min(a!.w / W, a!.h / H), 0.05, 0.8);
      const z = Math.pow(k, -e);
      const cf = { x: W / 2, y: H / 2 };
      const P = { x: (k * cf.x - a!.cx) / (k - 1), y: (k * cf.y - a!.cy) / (k - 1) };
      A.m = scaleAbout(P.x, P.y, z);
      const [acx, acy] = apply(A.m, a!.cx, a!.cy);
      B.m = mul(translate(acx - cf.x, acy - cf.y), scaleAbout(cf.x, cf.y, k * z));
      Object.assign(A, { back: 1 - band(e, 0.55, 1), content: 1 - band(e, 0.5, 0.95), anchor: 1 - band(e, 0.6, 1) });
      const f = band(e, 0.3, 0.75);
      Object.assign(B, { back: f, content: f, anchor: f });
      return done(true, t, null, fellBack);
    }
    case "depth_through_object": {
      const tw = { x: a!.cx / W, y: a!.cy / H };
      A.mod = { zoomMul: lerpLog(1, 3.2, e), toward: tw, amount: e };
      Object.assign(A, { back: 1 - band(e, 0.55, 1), content: 1 - band(e, 0.45, 0.9), anchor: 1 - band(e, 0.45, 0.9) });
      const f = band(e, 0.35, 0.8);
      B.mod = { zoomMul: lerpLog(1.9, 1, e), toward: b ? { x: b.cx / W, y: b.cy / H } : { x: 0.5, y: 0.5 }, amount: 1 - e };
      Object.assign(B, { back: f, content: f, anchor: f });
      return done(true, t, null, fellBack);
    }
    case "occlusion_reveal": {
      const far = Math.max(Math.hypot(a!.cx, a!.cy), Math.hypot(W - a!.cx, a!.cy), Math.hypot(a!.cx, H - a!.cy), Math.hypot(W - a!.cx, H - a!.cy)) * 1.03;
      Object.assign(B, visible());
      B.clip = { cx: a!.cx, cy: a!.cy, r: far * e, feather: 0.03 * Math.min(W, H) * Math.sin(Math.PI * Math.min(e * 1.2, 1)) };
      A.m = scaleAbout(a!.cx, a!.cy, 1 + 0.05 * e);
      return done(true, t, null, fellBack);
    }
    default:
      return done(false, "dissolve", null, true);
  }
}

/** Sanity bounds used by tests and by the plan builder: how large the camera factor of an operator gets. */
export function maxZoom(type: OpType, a: Rect | null, W: number, H: number): number {
  if (type === "nested_scale" && a) return 1 / clamp(Math.min(a.w / W, a.h / H), 0.05, 0.8);
  if (type === "depth_through_object") return 3.2;
  return 1;
}
