// morph.ts — the overlay for truthful_morph: two real outlines (one per scene) are paired point to point and interpolated.
// It is only legitimate when both anchors are the SAME thing in two states, which the author asserts with the transition's
// rationale; the engine only refuses (falls back) when either side has no outline to deform.
import { s, set } from "./dom";
import { lerp, Rect, smoothstep } from "./math";
import type { MorphShape } from "./visuals/types";

type Pt = [number, number];
const signedArea = (p: Pt[]): number => p.reduce((acc, a, i) => { const b = p[(i + 1) % p.length]; return acc + (a[0] * b[1] - b[0] * a[1]); }, 0) / 2;

function sampleD(d: string, n: number): Pt[] {
  const svg = s("svg", { width: 0, height: 0, viewBox: "0 0 1 1" });
  const path = s("path", { d }, svg);
  svg.style.cssText = "position:absolute;left:-9999px;top:-9999px;visibility:hidden";
  document.body.appendChild(svg);
  const L = path.getTotalLength();
  const pts: Pt[] = [];
  for (let i = 0; i < n; i++) { const p = path.getPointAtLength((L * i) / n); pts.push([p.x, p.y]); }
  document.body.removeChild(svg);
  return pts;
}

export interface MorphPair { a: MorphShape; b: MorphShape; pa: Pt[]; pb: Pt[] }

export function prepareMorph(a: MorphShape, b: MorphShape, n = 128): MorphPair {
  const norm = (sh: MorphShape): Pt[] => (sh.points ? sh.points(n) : sampleD(sh.d, n)).map(([x, y]) => [x / sh.box[0], y / sh.box[1]] as Pt);
  const pa = norm(a);
  let pb = norm(b);
  if (pb.length !== pa.length) throw new Error(`morph outlines differ in point count (${pa.length} vs ${pb.length})`);
  if (Math.sign(signedArea(pa)) !== Math.sign(signedArea(pb))) pb = [...pb].reverse();
  // rotate B so the pairing twists as little as possible
  let best = 0, bestCost = Infinity;
  for (let k = 0; k < pb.length; k++) {
    let c = 0;
    for (let i = 0; i < pa.length; i++) { const q = pb[(i + k) % pb.length]; c += (pa[i][0] - q[0]) ** 2 + (pa[i][1] - q[1]) ** 2; }
    if (c < bestCost) { bestCost = c; best = k; }
  }
  pb = pb.map((_, i) => pb[(i + best) % pb.length]);
  return { a, b, pa, pb };
}

export class MorphOverlay {
  private svg: SVGSVGElement;
  private path: SVGPathElement;
  private la: SVGTextElement;
  private lb: SVGTextElement;
  private shown = false;
  constructor(stage: HTMLElement, W: number, H: number) {
    this.svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    Object.assign(this.svg.style, { position: "absolute", left: "0", top: "0", zIndex: "10", pointerEvents: "none", display: "none", overflow: "visible" });
    this.path = s("path", { "stroke-linejoin": "round", "stroke-linecap": "round" }, this.svg);
    this.la = s("text", { "text-anchor": "middle" }, this.svg);
    this.lb = s("text", { "text-anchor": "middle" }, this.svg);
    stage.appendChild(this.svg);
  }
  hide(): void { if (this.shown) { this.svg.style.display = "none"; this.shown = false; } }
  /** e: eased progress 0..1; rect: the interpolated HOST rect in frame pixels */
  draw(m: MorphPair, e: number, rect: Rect): void {
    if (!this.shown) { this.svg.style.display = "block"; this.shown = true; }
    const x0 = rect.cx - rect.w / 2, y0 = rect.cy - rect.h / 2;
    let d = "";
    for (let i = 0; i < m.pa.length; i++) {
      const nx = lerp(m.pa[i][0], m.pb[i][0], e), ny = lerp(m.pa[i][1], m.pb[i][1], e);
      d += `${i ? "L" : "M"}${(x0 + nx * rect.w).toFixed(2)},${(y0 + ny * rect.h).toFixed(2)}`;
    }
    const sa = m.a, sb = m.b, k = rect.w / ((sa.box[0] + sb.box[0]) / 2);
    set(this.path, {
      d: d + "Z",
      fill: e < 0.5 ? sa.fill ?? "none" : sb.fill ?? "none",
      stroke: e < 0.5 ? sa.stroke ?? "#fff" : sb.stroke ?? "#fff",
      "stroke-width": ((lerp(sa.strokeWidth ?? 8, sb.strokeWidth ?? 8, e)) * k).toFixed(3),
    });
    const lab = (el: SVGTextElement, sh: MorphShape, alpha: number) => {
      const L = sh.label;
      if (!L || alpha <= 0.002) { el.setAttribute("opacity", "0"); return; }
      el.textContent = L.text;
      set(el, { x: (x0 + (L.x / sh.box[0]) * rect.w).toFixed(2), y: (y0 + (L.y / sh.box[1]) * rect.h).toFixed(2), "font-size": (L.size * (rect.w / sh.box[0])).toFixed(2), "font-family": `"${L.family ?? "sans-serif"}", sans-serif`, "font-weight": L.weight ?? 700, fill: L.fill ?? "#fff", opacity: alpha.toFixed(4) });
    };
    lab(this.la, sa, 1 - smoothstep(0, 0.5, e));
    lab(this.lb, sb, smoothstep(0.5, 1, e));
  }
}
