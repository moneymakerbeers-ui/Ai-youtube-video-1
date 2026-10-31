// renderer.ts — FrameRenderer: turns (plan, scene graph, style tokens, assets) into a pure function frame → pixels.
// Retained DOM: every scene and entity is built once; renderFrame(n) only restyles. There is no hidden state between frames
// (no CSS transitions, no timers, no randomness that is not seeded by the frame number), so any frame can be rendered
// alone, out of order, or twice, with identical results.
import type { Entity, Palette, PlanScene, PlanTransition, Placement, RenderPlan, StyleTokens } from "../../schema/video.schema";
import { AssetInfo, AssetSpec, FontSpec, fontAvailable, loadAsset, loadFonts } from "./assets";
import { applyMod, CamMove, entityGeometry, View, viewAt } from "./camera";
import { CaptionLayer, Margins } from "./captions";
import { h } from "./dom";
import { BuildCtx, createEntity, drawEntity, EntityRT } from "./entities";
import { GradeLayer } from "./grade";
import { apply, clamp, css, Ease, isIdentity, makeEase, Mat, Rect } from "./math";
import { MorphOverlay, MorphPair, prepareMorph } from "./morph";
import { OpType, SideFx, transitionFx } from "./transitions";
import type { VisualRegistry } from "./visuals/types";

export const ENGINE_VERSION = "3.0.0-dom";

export interface BundleScene { id: string; entities: Entity[]; placements: Record<string, Placement> }
export interface Bundle {
  plan: RenderPlan;
  scenes: Record<string, BundleScene>; // placements already resolved for plan.layout
  tokens: StyleTokens;
  assets: Record<string, AssetSpec>;
  fonts: FontSpec[];
}
/** per-frame truth about a transition, for tools/qa_motion.py: where each anchor really lands on screen (input rect `a`/`b`, rect after the
 *  operator moved the world `aOut`/`bOut`, all in frame pixels) and how visible each side is. Nothing here is a QA verdict. */
export interface TransitionTrace {
  from: string; to: string; planned: string; used: string; p: number; e: number; fellBack: boolean;
  a: Rect | null; b: Rect | null; aOut: Rect | null; bOut: Rect | null;
  alpha: { A: [number, number, number]; B: [number, number, number] }; // [back, content, anchor]
  morphE: number | null;
}
export interface FrameTrace {
  frame: number;
  t: number;
  mode: "solo" | "transition";
  scenes: { id: string; role: "solo" | "A" | "B" }[];
  transition: TransitionTrace | null;
  fade: number;
  caption: string | null;
  state: string; // hash of the picture's DOM (scenes + morph, no captions, no grain, no fade): equal hashes mean an identical picture
  warnings: string[];
}

interface SceneRT {
  idx: number;
  plan: PlanScene;
  palette: Palette;
  root: HTMLElement;
  back: HTMLElement;
  ents: EntityRT[];
  byId: Map<string, EntityRT>;
  moves: CamMove[];
  shown: boolean;
  incoming: { id: string; from: number } | null; // the previous transition IS this entity's entrance, from that time on
}
interface TrRT { from: number; tr: PlanTransition; morph: MorphPair | null; blocked: string | null }

const SAFE_TOL = 0.004;

export class FrameRenderer {
  readonly W: number;
  readonly H: number;
  readonly fps: number;
  readonly plan: RenderPlan;
  readonly buildWarnings: string[] = [];
  private stage: HTMLElement;
  private world: HTMLElement;
  private scenes: SceneRT[] = [];
  private trs: TrRT[] = [];
  private ease: Ease;
  private captions: CaptionLayer;
  private grade: GradeLayer;
  private morph: MorphOverlay;
  private tokens: StyleTokens;
  private safe: Margins;

  private constructor(private bundle: Bundle, private assets: Record<string, AssetInfo>, private registry: VisualRegistry) {
    this.plan = bundle.plan;
    this.W = bundle.plan.width;
    this.H = bundle.plan.height;
    this.fps = bundle.plan.fps;
    this.tokens = bundle.tokens;
    this.ease = makeEase(bundle.tokens.motion.easing as Record<string, [number, number, number, number]>);
    this.safe = bundle.tokens.safe[bundle.plan.layout];
    document.body.style.cssText = "margin:0;background:#000;overflow:hidden";
    this.stage = h("div", { position: "relative", width: `${this.W}px`, height: `${this.H}px`, overflow: "hidden", background: bundle.tokens.palette.bg });
    this.stage.id = "stage";
    document.body.replaceChildren(this.stage);
    // the contrast/saturation grade applies to the picture only (scenes + morph), never to captions or the fade overlay
    const gf = GradeLayer.filter(bundle.tokens.grade);
    this.world = h("div", { position: "absolute", left: "0", top: "0", width: "100%", height: "100%", filter: gf });
    this.stage.appendChild(this.world);
    const measureHost = h("div", { position: "absolute", left: "-99999px", top: "0", visibility: "hidden", width: `${this.W}px` });
    this.stage.appendChild(measureHost);
    this.buildScenes(measureHost);
    this.morph = new MorphOverlay(this.world, this.W, this.H);
    this.captions = new CaptionLayer(this.stage, bundle.plan.captions, bundle.tokens, this.W, this.H, this.safe);
    this.grade = new GradeLayer(this.stage, this.W, this.H, bundle.tokens.grade, this.fps);
    this.buildTransitions();
    this.stage.removeChild(measureHost);
  }

  static async create(bundle: Bundle, registry: VisualRegistry): Promise<FrameRenderer> {
    const problems: string[] = [];
    problems.push(...(await loadFonts(bundle.fonts)));
    const needed = new Set<string>();
    for (const bs of Object.values(bundle.scenes)) for (const e of bs.entities) if (e.assetId) needed.add(e.assetId);
    const assets: Record<string, AssetInfo> = {};
    for (const id of needed) {
      const spec = bundle.assets[id];
      if (!spec) { problems.push(`missing_asset:*:${id}: asset is referenced by the scene graph but is not in the bundle`); continue; }
      try { assets[id] = await loadAsset(spec); } catch (e) { problems.push(`asset_load_failed:*:${id}: ${(e as Error).message}`); }
    }
    for (const fam of new Set([bundle.tokens.fonts.display, bundle.tokens.fonts.body, bundle.tokens.fonts.mono].filter(Boolean) as string[])) {
      if (!fontAvailable(fam)) problems.push(`font_missing:*:${fam}: the font family resolves to a fallback; ship it in style-tokens.fonts.files for a reproducible render`);
    }
    const r = new FrameRenderer(bundle, assets, registry);
    r.buildWarnings.unshift(...problems);
    return r;
  }

  private paletteFor(look?: string): Palette {
    return { ...this.tokens.palette, ...((look && this.tokens.looks[look]) || {}) } as Palette;
  }

  private buildScenes(measureHost: HTMLElement): void {
    this.plan.scenes.forEach((ps, idx) => {
      const bs = this.bundle.scenes[ps.id];
      if (!bs) throw new Error(`plan scene ${ps.id} is not in the bundle`);
      const palette = this.paletteFor(ps.look);
      const root = h("div", { position: "absolute", left: "0", top: "0", width: `${this.W}px`, height: `${this.H}px`, transformOrigin: "0 0", display: "none" });
      const back = h("div", { position: "absolute", left: "0", top: "0", width: "100%", height: "100%", background: palette.bg2 ? `radial-gradient(ellipse at 50% 42%, ${palette.bg2} 0%, ${palette.bg} 78%)` : palette.bg });
      root.appendChild(back);
      const ctx: BuildCtx = { W: this.W, H: this.H, tokens: this.tokens, palette, assets: this.assets, registry: this.registry, measureHost, warnings: this.buildWarnings, sceneId: ps.id };
      const timing = new Map(ps.entities.map((e) => [e.id, e]));
      const ents: EntityRT[] = [];
      for (const e of bs.entities) {
        const pl = bs.placements[e.id];
        const tm = timing.get(e.id);
        if (!pl) { this.buildWarnings.push(`no_placement:${ps.id}:${e.id}: the entity has no placement in the ${this.plan.layout} layout, so it is not drawn`); continue; }
        if (!tm) { this.buildWarnings.push(`no_timing:${ps.id}:${e.id}: the plan has no timing for this entity, so it is not drawn`); continue; }
        ents.push(createEntity(ctx, e, pl, tm.enterS, tm.exitS));
      }
      ents.sort((a, b) => a.z - b.z);
      ents.forEach((e, i) => { e.el.style.zIndex = String(i + 1); root.appendChild(e.el); });
      this.world.appendChild(root);
      this.scenes.push({ idx, plan: ps, palette, root, back, ents, byId: new Map(ents.map((e) => [e.id, e])), moves: ps.camera.map((c) => ({ fromS: c.fromS, toS: c.toS, from: c.from, to: c.to, easing: c.easing })), shown: false, incoming: null });
    });
  }

  private buildTransitions(): void {
    this.scenes.forEach((sc, i) => {
      const tr = sc.plan.transitionOut;
      if (!tr) return;
      const rt: TrRT = { from: i, tr, morph: null, blocked: null };
      const B = this.scenes[i + 1];
      if (B && tr.anchorTo) {
        if (B.byId.has(tr.anchorTo.entityId)) B.incoming = { id: tr.anchorTo.entityId, from: tr.startS };
        else this.buildWarnings.push(`anchor_missing:${B.plan.id}:${tr.anchorTo.entityId}: anchorTo is not an entity of the next scene`);
      }
      if (tr.anchorFrom && !sc.byId.has(tr.anchorFrom.entityId)) this.buildWarnings.push(`anchor_missing:${sc.plan.id}:${tr.anchorFrom.entityId}: anchorFrom is not an entity of this scene`);
      if (!B) { rt.blocked = "transition out of the last scene"; }
      else if (tr.type === "truthful_morph") {
        const ea = tr.anchorFrom && sc.byId.get(tr.anchorFrom.entityId), eb = tr.anchorTo && B.byId.get(tr.anchorTo.entityId);
        if (!ea?.pathOf || !eb?.pathOf) rt.blocked = `truthful_morph needs both anchors to be visuals with an outline (path()); ${ea ? (ea.pathOf ? "" : `${ea.id} has none`) : "anchorFrom is missing"} ${eb ? (eb.pathOf ? "" : `${eb.id} has none`) : "anchorTo is missing"}`.trim();
        else { try { rt.morph = prepareMorph(ea.pathOf(), eb.pathOf()); } catch (e) { rt.blocked = `morph outlines could not be paired: ${(e as Error).message}`; } }
      }
      if (rt.blocked) this.buildWarnings.push(`transition_blocked:${sc.plan.id}:${tr.type}: ${rt.blocked}; rendering a dissolve instead`);
      this.trs.push(rt);
    });
  }

  /** the rectangle of an anchor in frame pixels at time t (camera included, transition modifiers not) */
  anchorRect(scene: SceneRT, a: { entityId: string; x?: number; y?: number } | undefined, t: number): Rect | null {
    if (!a) return null;
    const e = scene.byId.get(a.entityId);
    if (!e) return null;
    const v = viewAt(scene.moves, t, this.ease);
    // measure with entityGeometry through drawEntity's own rule: same function, no DOM
    const g = geometry(e, this.W, this.H, v);
    return { cx: g.cx + ((a.x ?? 0.5) - 0.5) * g.w, cy: g.cy + ((a.y ?? 0.5) - 0.5) * g.h, w: g.w, h: g.h };
  }

  private velocityOf(sc: SceneRT, t: number): { x: number; y: number } | null {
    const mv = [...sc.moves].reverse().find((m) => m.fromS <= t + 1e-6);
    if (!mv) return null;
    const dx = mv.to.x - mv.from.x, dy = mv.to.y - mv.from.y;
    return Math.hypot(dx, dy) < 1e-4 ? null : { x: dx, y: dy };
  }

  /** which scene(s) show at time t */
  stateAt(t: number): { kind: "solo"; i: number } | { kind: "transition"; i: number; rt: TrRT; p: number } {
    for (const rt of this.trs) if (t >= rt.tr.startS && t < rt.tr.endS) return { kind: "transition", i: rt.from, rt, p: (t - rt.tr.startS) / (rt.tr.endS - rt.tr.startS) };
    let k = this.scenes.length - 1;
    for (let i = 0; i < this.scenes.length; i++) if (t < this.scenes[i].plan.endS) { k = i; break; }
    return { kind: "solo", i: k };
  }

  fadeAt(t: number): number {
    const o = this.plan.opening, e = this.plan.ending;
    let f = 0;
    if (o.fadeInMs > 0) f = Math.max(f, 1 - this.ease("soft", t / (o.fadeInMs / 1000)));
    const outMs = e.fadeOutMs + e.holdBlackMs;
    if (outMs > 0) {
      const tBlack = this.plan.durationS - e.holdBlackMs / 1000;
      const d = Math.max(e.fadeOutMs / 1000, 1e-6);
      f = Math.max(f, this.ease("soft", (t - (tBlack - e.fadeOutMs / 1000)) / d));
    }
    return clamp(f);
  }

  private drawScene(sc: SceneRT, t: number, fx: SideFx, anchorId: string | null, z: number, frame: number, pending: Promise<void>[], layoutWarn: string[] | null): void {
    if (!sc.shown) { sc.root.style.display = "block"; sc.shown = true; }
    sc.root.style.zIndex = String(z);
    sc.root.style.transform = isIdentity(fx.m) ? "none" : css(fx.m);
    sc.root.style.filter = fx.blur > 0.05 ? `blur(${fx.blur.toFixed(2)}px)` : "none";
    // always assigned (never "only when it changes"), so the serialised state of a drawn scene never depends on which frames this page rendered before
    let mask = "none";
    if (fx.clip) {
      const c = fx.clip, f = Math.max(c.feather, 0);
      mask = `radial-gradient(circle at ${c.cx.toFixed(1)}px ${c.cy.toFixed(1)}px, #000 ${Math.max(c.r - f, 0).toFixed(1)}px, rgba(0,0,0,0) ${Math.max(c.r, 0.5).toFixed(1)}px)`;
    }
    sc.root.style.maskImage = mask;
    // A uniform fade (back, content and anchor share one opacity, e.g. a dissolve) is applied to the scene as ONE layer. Fading the backdrop and
    // each entity separately composites them through each other (at 50 % an entity shows 75 % of itself and 25 % of its own faded backdrop),
    // which reads as a brightness dip in the middle of every dissolve.
    const uniform = Math.abs(fx.back - fx.content) < 1e-6 && (anchorId === null || Math.abs(fx.anchor - fx.back) < 1e-6) && fx.back < 0.9995;
    sc.root.style.opacity = uniform ? String(+fx.back.toFixed(4)) : "1";
    const fxe = uniform ? { ...fx, back: 1, content: 1, anchor: 1 } : fx;
    sc.back.style.opacity = fxe.back >= 0.9995 ? "1" : String(+fxe.back.toFixed(4));
    const view: View = applyMod(viewAt(sc.moves, t, this.ease), fx.mod);
    // The incoming scene is drawn through the first half of a transition window, i.e. before its own start: entities whose entrance is instant
    // (style none / 0 ms: plates, backdrops) must be present then, or they pop in at the boundary at the crossfade's current opacity. Entrances
    // with a duration still start from alpha 0 at the scene start, so nothing else changes.
    const sceneT = Math.max(0, t - sc.plan.startS);
    const forceId = sc.incoming && t >= sc.incoming.from ? sc.incoming.id : null;
    const short = Math.min(this.W, this.H) / 1080;
    const minPx = this.tokens.type.minPxAt1080 * short;
    for (const e of sc.ents) {
      const isAnchor = e.id === anchorId;
      const mult = isAnchor ? fxe.anchor : e.role === "backdrop" ? fxe.back : fxe.content;
      const r = drawEntity(e, { t: Math.max(t, sc.plan.startS), sceneT, frame, fps: this.fps, W: this.W, H: this.H, view, mult, forceEntered: e.id === forceId, ease: this.ease, palette: sc.palette, tokens: this.tokens }, pending);
      if (layoutWarn && r.opacity > 0.5) {
        if (e.kind === "text" && e.textPx !== null && e.textPx * r.scale < minPx - 0.5) layoutWarn.push(`text_small:${sc.plan.id}:${e.id}: ${(e.textPx * r.scale).toFixed(1)}px < minimum ${minPx.toFixed(0)}px`);
        if (e.kind === "text" && e.role !== "backdrop" && e.role !== "decor") {
          const L = r.rect.cx - r.rect.w / 2, R = r.rect.cx + r.rect.w / 2, T = r.rect.cy - r.rect.h / 2, B = r.rect.cy + r.rect.h / 2;
          const s = this.safe, tol = SAFE_TOL;
          if (L < (s.left - tol) * this.W || R > (1 - s.right + tol) * this.W || T < (s.top - tol) * this.H || B > (1 - s.bottom + tol) * this.H) layoutWarn.push(`safe_area:${sc.plan.id}:${e.id}: text box leaves the ${this.plan.layout} safe area`);
        }
      }
    }
  }

  private hideScene(sc: SceneRT): void {
    if (sc.shown) { sc.root.style.display = "none"; sc.shown = false; }
  }

  /** Render frame n into the DOM. Resolves once every image needed by this frame has decoded. */
  async renderFrame(frame: number): Promise<FrameTrace> {
    const t = frame / this.fps;
    const st = this.stateAt(t);
    const pending: Promise<void>[] = [];
    const warnings: string[] = [];
    const trace: FrameTrace = { frame, t, mode: st.kind, scenes: [], transition: null, fade: 0, caption: null, state: "", warnings };
    const visible = (): SideFx => ({ m: [1, 0, 0, 1, 0, 0], back: 1, content: 1, anchor: 1, blur: 0, clip: null, mod: null });

    if (st.kind === "solo") {
      const sc = this.scenes[st.i];
      this.scenes.forEach((o, i) => i !== st.i && this.hideScene(o));
      this.morph.hide();
      this.drawScene(sc, t, visible(), null, 1, frame, pending, warnings);
      trace.scenes.push({ id: sc.plan.id, role: "solo" });
    } else {
      const A = this.scenes[st.i], B = this.scenes[st.i + 1];
      const { rt, p } = st;
      this.scenes.forEach((o, i) => i !== st.i && i !== st.i + 1 && this.hideScene(o));
      const tr = rt.tr;
      const type: OpType = rt.blocked ? "dissolve" : (tr.type as OpType);
      const a = this.anchorRect(A, tr.anchorFrom, t), b = this.anchorRect(B, tr.anchorTo, t);
      const fx = transitionFx(type, p, { W: this.W, H: this.H, ease: this.ease, easing: tr.easing, a, b, velocity: this.velocityOf(A, t) });
      const aId = tr.anchorFrom?.entityId ?? null, bId = tr.anchorTo?.entityId ?? null;
      this.drawScene(A, t, fx.A, aId, fx.bAbove ? 1 : 2, frame, pending, null);
      this.drawScene(B, t, fx.B, bId, fx.bAbove ? 2 : 1, frame, pending, null);
      if (fx.morph && rt.morph) this.morph.draw(rt.morph, fx.morph.e, fx.morph.rect); else this.morph.hide();
      trace.scenes.push({ id: A.plan.id, role: "A" }, { id: B.plan.id, role: "B" });
      const land = (m: Mat, r: Rect | null): Rect | null => { if (!r) return null; const [cx, cy] = apply(m, r.cx, r.cy), k = Math.hypot(m[0], m[1]); return { cx, cy, w: r.w * k, h: r.h * k }; };
      trace.transition = { from: A.plan.id, to: B.plan.id, planned: tr.type, used: fx.usedType, p, e: this.ease(tr.easing, p), fellBack: fx.fellBack || !!rt.blocked, a, b, aOut: land(fx.A.m, a), bOut: land(fx.B.m, b), alpha: { A: [fx.A.back, fx.A.content, fx.A.anchor], B: [fx.B.back, fx.B.content, fx.B.anchor] }, morphE: fx.morph ? fx.morph.e : null };
    }

    const cap = this.captions.update(t);
    trace.caption = cap.rect ? cap.text : null;
    if (cap.rect && st.kind === "solo") {
      const sc = this.scenes[st.i], cr = cap.rect, area = Math.max(cr.width * cr.height, 1);
      for (const e of sc.ents) {
        if (e.role === "backdrop" || e.role === "decor" || e.el.style.display === "none") continue;
        const r = e.el.getBoundingClientRect();
        const ix = Math.max(0, Math.min(r.right, cr.right) - Math.max(r.left, cr.left)), iy = Math.max(0, Math.min(r.bottom, cr.bottom) - Math.max(r.top, cr.top));
        if ((ix * iy) / area > 0.08 && parseFloat(e.el.style.opacity || "1") > 0.5) warnings.push(`caption_overlap:${sc.plan.id}:${e.id}: the entity covers ${(100 * ix * iy / area).toFixed(0)}% of the caption box`);
      }
      const s = this.safe, r = cap.rect;
      if (r.left < (s.left - SAFE_TOL) * this.W || r.right > (1 - s.right + SAFE_TOL) * this.W || r.bottom > (1 - Math.min(s.bottom, 0.5) + SAFE_TOL) * this.H) warnings.push(`caption_safe:*:caption: caption box leaves the ${this.plan.layout} safe area at ${t.toFixed(2)}s`);
    }
    trace.state = stateHash(this.world);
    trace.fade = this.fadeAt(t);
    this.grade.update(frame, trace.fade);
    if (pending.length) await Promise.all(pending);
    // two animation frames: layout and paint settle before the screenshot
    await new Promise<void>((res) => requestAnimationFrame(() => requestAnimationFrame(() => res())));
    return trace;
  }

  /** for tests and QA: scene geometry without drawing */
  describe(): { scenes: { id: string; startS: number; endS: number; entities: { id: string; kind: string; role: string; bw: number; bh: number; textPx: number | null }[] }[]; transitions: { from: string; type: string; startS: number; endS: number; blocked: string | null }[] } {
    return {
      scenes: this.scenes.map((s) => ({ id: s.plan.id, startS: s.plan.startS, endS: s.plan.endS, entities: s.ents.map((e) => ({ id: e.id, kind: e.kind, role: e.role, bw: e.bw, bh: e.bh, textPx: e.textPx })) })),
      transitions: this.trs.map((t) => ({ from: this.scenes[t.from].plan.id, type: t.tr.type, startS: t.tr.startS, endS: t.tr.endS, blocked: t.blocked })),
    };
  }
}

/** Canonical hash of the picture's DOM: tag, attributes sorted by name, style declarations sorted, text. Independent of the order in
 *  which properties were first set, so two browser pages that rendered different frames before agree on identical pictures. */
function stateHash(root: Element): string {
  let a = 0x811c9dc5, b = 0x9747b28c;
  const feed = (str: string) => {
    for (let i = 0; i < str.length; i++) {
      const c = str.charCodeAt(i);
      a = Math.imul(a ^ c, 0x01000193);
      b = Math.imul(b ^ c, 0x01000193) ^ (b >>> 13);
    }
    a = Math.imul(a ^ 0x1f, 0x01000193);
  };
  const walk = (el: Element) => {
    feed(el.tagName);
    if ((el as HTMLElement).style && (el as HTMLElement).style.display === "none") { feed("hidden"); return; } // a hidden element and everything below it is not part of the picture
    for (const n of el.getAttributeNames().sort()) {
      let v = el.getAttribute(n) ?? "";
      if (n === "style") v = v.split(";").map((x) => x.trim()).filter(Boolean).sort().join(";");
      feed(n);
      feed(v);
    }
    for (const c of Array.from(el.childNodes)) {
      if (c.nodeType === 1) walk(c as Element);
      else if (c.nodeType === 3) feed((c as Text).data);
    }
  };
  walk(root);
  return (a >>> 0).toString(16).padStart(8, "0") + (b >>> 0).toString(16).padStart(8, "0");
}
function geometry(e: EntityRT, W: number, H: number, view: View): { cx: number; cy: number; w: number; h: number } {
  return entityGeometry(e.place, e.aspectHW, W, H, view).rect;
}
