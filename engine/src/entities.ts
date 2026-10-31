// entities.ts — one scene-graph entity = one retained DOM element, created once and then only restyled per frame.
// Kinds: raster image, inline SVG, frame sequence (extracted video), text (auto-fitted), code visual, or a loud placeholder.
import type { Entity, Palette, Placement, StyleTokens } from "../../schema/video.schema";
import type { AssetInfo } from "./assets";
import { entityGeometry, Place, View } from "./camera";
import { h } from "./dom";
import { clamp, css, Ease, Rect } from "./math";
import type { VisualDef, VisualInstance, VisualRegistry } from "./visuals/types";

export type EntityKind = "image" | "svg" | "video" | "text" | "visual" | "placeholder";
export interface EntityRT {
  id: string;
  ent: Entity;
  kind: EntityKind;
  role: Entity["role"];
  place: Place;
  z: number;
  el: HTMLElement;
  aspectHW: number;
  bw: number;
  bh: number;
  enterS: number;
  exitS: number | null;
  enterStyle: "none" | "fade" | "rise" | "pop" | "draw";
  enterMs: number;
  textPx: number | null; // nominal font size in px at scale 1 (text entities)
  visual: { def: VisualDef; inst: VisualInstance } | null;
  frames: AssetInfo["frames"] | null;
  img: HTMLImageElement | null;
  lastFrameIdx: number;
  pathOf: (() => { d: string; box: [number, number]; stroke?: string; strokeWidth?: number; fill?: string }) | null;
}

export interface BuildCtx {
  W: number;
  H: number;
  tokens: StyleTokens;
  palette: Palette;
  assets: Record<string, AssetInfo>;
  registry: VisualRegistry;
  measureHost: HTMLElement;
  warnings: string[];
  sceneId: string;
}

const px = (v: number) => `${+v.toFixed(3)}px`;

function textStyle(ctx: BuildCtx, role: Entity["role"]): { family: string; weight: number; color: string } {
  const f = ctx.tokens.fonts, p = ctx.palette;
  if (role === "number") return { family: f.display, weight: 800, color: p.accent };
  if (role === "label") return { family: f.body, weight: 700, color: p.fg };
  if (role === "subject") return { family: f.display, weight: 800, color: p.fg };
  if (role === "context") return { family: f.body, weight: 600, color: p.muted };
  return { family: f.body, weight: 600, color: p.fg };
}

function makeText(ctx: BuildCtx, ent: Entity, bw: number): { el: HTMLElement; bh: number; px: number } {
  const st = textStyle(ctx, ent.role);
  const short = Math.min(ctx.W, ctx.H) / 1080;
  const minPx = ctx.tokens.type.minPxAt1080 * short;
  const maxPx = (ent.role === "number" ? ctx.tokens.type.numberMaxPx : ctx.tokens.type.labelMaxPx) * short;
  const c2 = document.createElement("canvas").getContext("2d")!;
  c2.font = `${st.weight} 100px "${st.family}", sans-serif`;
  const w100 = Math.max(c2.measureText(ent.text ?? "").width, 1);
  const fit = (100 * bw) / w100 * 0.985;
  const size = clamp(fit, minPx, maxPx);
  const wrap = fit < minPx; // even the minimum size does not fit on one line: wrap instead of shrinking below the floor
  const el = h("div", {
    position: "absolute", left: "0", top: "0", width: px(bw), color: st.color, textAlign: "center", fontFamily: `"${st.family}", sans-serif`, fontWeight: String(st.weight),
    fontSize: px(size), lineHeight: "1.14", whiteSpace: wrap ? "normal" : "nowrap", transformOrigin: "0 0", display: "block", margin: "0", padding: "0",
  });
  el.textContent = ent.text ?? "";
  ctx.measureHost.appendChild(el);
  const bh = Math.max(el.getBoundingClientRect().height, size);
  ctx.measureHost.removeChild(el);
  el.style.height = px(bh);
  if (wrap) ctx.warnings.push(`text_wrapped:${ctx.sceneId}:${ent.id}: "${ent.text}" needs ${(fit).toFixed(0)}px to stay on one line, minimum is ${minPx.toFixed(0)}px, so it wraps`);
  return { el, bh, px: size };
}

export function createEntity(ctx: BuildCtx, ent: Entity, pl: Placement, enterS: number, exitS: number | null): EntityRT {
  const rt = buildEntity(ctx, ent, pl, enterS, exitS);
  // explicit from the start, so the serialised state never depends on whether an element was ever hidden
  rt.el.style.display = "block";
  rt.el.style.opacity = "0";
  rt.el.style.transform = "none";
  rt.el.style.clipPath = "none";
  return rt;
}

function buildEntity(ctx: BuildCtx, ent: Entity, pl: Placement, enterS: number, exitS: number | null): EntityRT {
  const place: Place = { x: pl.x, y: pl.y, w: pl.w, rotate: pl.rotate, depth: pl.depth };
  const bw = pl.w * ctx.W;
  const common = { id: ent.id, ent, role: ent.role, place, z: pl.z, enterS, exitS, enterStyle: (ent.enter?.style ?? "fade") as EntityRT["enterStyle"], enterMs: ent.enter?.durationMs ?? ctx.tokens.motion.enterMs, textPx: null as number | null, visual: null as EntityRT["visual"], frames: null as EntityRT["frames"], img: null as HTMLImageElement | null, lastFrameIdx: -1, pathOf: null as EntityRT["pathOf"] };
  const box = (el: HTMLElement, aspectHW: number): { el: HTMLElement; bh: number } => {
    const bh = bw * aspectHW;
    Object.assign(el.style, { position: "absolute", left: "0", top: "0", width: px(bw), height: px(bh), transformOrigin: "0 0", overflow: "visible" });
    return { el, bh };
  };

  if (ent.visual) {
    const def = ctx.registry[ent.visual.component];
    if (!def) {
      ctx.warnings.push(`missing_visual:${ctx.sceneId}:${ent.id}: no visual component "${ent.visual.component}" is registered`);
      return placeholder(ctx, common, `visual "${ent.visual.component}" missing`, bw);
    }
    const aspect = def.aspect(ent.visual.props);
    const { el, bh } = box(h("div"), aspect);
    const init = { w: bw, h: bh, palette: ctx.palette, tokens: ctx.tokens };
    const inst = def.create(el, ent.visual.props, init);
    const rt: EntityRT = { ...common, kind: "visual", el, aspectHW: aspect, bw, bh, visual: { def, inst } };
    if (def.path) rt.pathOf = () => def.path!(ent.visual!.props, init);
    return rt;
  }
  if (ent.assetId) {
    const a = ctx.assets[ent.assetId];
    if (!a) {
      ctx.warnings.push(`missing_asset:${ctx.sceneId}:${ent.id}: asset "${ent.assetId}" is not in the bundle`);
      return placeholder(ctx, common, `asset ${ent.assetId} missing`, bw);
    }
    const aspect = a.height / a.width;
    if (a.kind === "svg" && a.svg) {
      const { el, bh } = box(h("div"), aspect);
      const svg = a.svg.cloneNode(true) as SVGSVGElement;
      svg.setAttribute("width", "100%");
      svg.setAttribute("height", "100%");
      svg.style.display = "block";
      el.appendChild(svg);
      return { ...common, kind: "svg", el, aspectHW: aspect, bw, bh };
    }
    const img = document.createElement("img");
    img.decoding = "sync";
    img.draggable = false;
    Object.assign(img.style, { width: "100%", height: "100%", display: "block", objectFit: "fill", userSelect: "none" });
    if (a.kind === "video" && a.frames) img.src = a.frames.url(0);
    else img.src = a.url;
    const { el, bh } = box(h("div"), aspect);
    el.appendChild(img);
    return { ...common, kind: a.kind === "video" ? "video" : "image", el, aspectHW: aspect, bw, bh, frames: a.frames ?? null, img };
  }
  if (ent.text) {
    const { el, bh, px: size } = makeText(ctx, ent, bw);
    return { ...common, kind: "text", el, aspectHW: bh / bw, bw, bh, textPx: size };
  }
  return placeholder(ctx, common, ent.need ? `need: ${ent.need}` : "empty entity", bw);
}

function placeholder(ctx: BuildCtx, common: Omit<EntityRT, "kind" | "el" | "aspectHW" | "bw" | "bh">, label: string, bw: number): EntityRT {
  const bh = bw * 0.5;
  const el = h("div", { position: "absolute", left: "0", top: "0", width: px(bw), height: px(bh), border: `4px dashed ${ctx.palette.warn ?? "#ff4d4d"}`, color: ctx.palette.warn ?? "#ff4d4d", fontFamily: "monospace", fontSize: px(Math.min(ctx.W, ctx.H) * 0.03), display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", boxSizing: "border-box", transformOrigin: "0 0" });
  el.textContent = `UNRESOLVED ${common.id}: ${label}`;
  ctx.warnings.push(`unresolved_entity:${ctx.sceneId}:${common.id}: ${label}`);
  return { ...common, kind: "placeholder", el, aspectHW: 0.5, bw, bh };
}

export interface DrawArgs {
  t: number; // seconds on the timeline
  sceneT: number; // seconds since the scene's own start
  frame: number;
  fps: number;
  W: number;
  H: number;
  view: View;
  mult: number; // opacity multiplier from the transition (back / content / anchor)
  forceEntered: boolean; // the transition itself is this entity's entrance
  ease: Ease;
  palette: Palette;
  tokens: StyleTokens;
}
export interface DrawResult { opacity: number; rect: Rect; scale: number; entered: number }

const easeOutBack = (x: number, k = 1.4) => 1 + (k + 1) * Math.pow(x - 1, 3) + k * Math.pow(x - 1, 2);

/** Restyle one entity for time t. Pure function of its arguments plus the retained DOM. Returns geometry for anchors and layout checks. */
export function drawEntity(e: EntityRT, a: DrawArgs, pending: Promise<void>[]): DrawResult {
  // enter progress (eased) and exit fade
  let p = 1;
  if (!a.forceEntered) {
    if (a.t < e.enterS) p = 0;
    else if (e.enterStyle !== "none" && e.enterMs > 0) p = clamp((a.t - e.enterS) / (e.enterMs / 1000));
  }
  const pe = a.forceEntered ? 1 : a.ease("standard", p);
  let exit = 1;
  if (e.exitS !== null && a.t >= e.exitS) exit = 1 - a.ease("standard", (a.t - e.exitS) / 0.3);

  let opacity = a.mult * exit, extraScale = 1, dy = 0, clipRight = 0;
  switch (e.enterStyle) {
    case "fade": opacity *= pe; break;
    case "rise": opacity *= pe; dy = (1 - pe) * 0.035 * a.H; break;
    case "pop": opacity *= clamp(pe * 2.2); extraScale = 0.84 + 0.16 * easeOutBack(clamp(p)); break;
    case "draw": if (e.kind !== "visual") clipRight = (1 - pe) * 100; else opacity *= p > 0 ? 1 : 0; break;
    case "none": opacity *= p > 0 ? 1 : 0; break;
  }
  if (a.t < e.enterS && !a.forceEntered) opacity = 0;

  const g = entityGeometry(e.place, e.aspectHW, a.W, a.H, a.view, { scale: extraScale, dy });
  const out: DrawResult = { opacity, rect: g.rect, scale: g.rect.w / g.bw, entered: p };
  if (opacity <= 0.0015) {
    if (e.el.style.display !== "none") e.el.style.display = "none";
    return out;
  }
  if (e.el.style.display === "none") e.el.style.display = "block";
  e.el.style.opacity = opacity >= 0.9995 ? "1" : String(+opacity.toFixed(4));
  e.el.style.transform = css(g.m);
  e.el.style.clipPath = clipRight > 0.01 ? `inset(0 ${clipRight.toFixed(2)}% 0 0)` : "none";
  if (e.visual) {
    e.visual.inst.update({ t: Math.max(a.t - e.enterS, 0), progress: a.forceEntered ? 1 : e.enterStyle === "draw" || e.enterStyle === "fade" || e.enterStyle === "rise" || e.enterStyle === "pop" ? pe : 1, sceneT: a.sceneT, frame: a.frame, fps: a.fps, w: e.bw, h: e.bh, palette: a.palette, tokens: a.tokens });
  }
  if (e.kind === "video" && e.frames && e.img) {
    const idx = Math.max(0, Math.min(e.frames.count - 1, Math.floor(Math.max(a.t - e.enterS, 0) * e.frames.fps)));
    if (idx !== e.lastFrameIdx) {
      e.lastFrameIdx = idx;
      e.img.src = e.frames.url(idx);
      pending.push(e.img.decode().catch(() => undefined));
    }
  }
  return out;
}
