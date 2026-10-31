// visuals/index.ts — code-drawn visuals for "star birth to black hole". Pure functions of time (deterministic PRNG), palette from tokens.
import { s, set, rng } from "../../../engine/src/dom";
import type { VisualDef, VisualInit } from "../../../engine/src/visuals/types";

const num = (v: unknown, d: number): number => (typeof v === "number" && isFinite(v) ? v : d);
const str = (v: unknown, d: string): string => (typeof v === "string" ? v : d);
const arr = <T,>(v: unknown, d: T[]): T[] => (Array.isArray(v) ? (v as T[]) : d);
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const ramp = (p: number, a: number, b: number) => clamp01((p - a) / (b - a));
const ease = (x: number) => { x = clamp01(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
const FONT = (init: VisualInit) => `${init.tokens.fonts.body}, sans-serif`;
let uid = 0;
const gid = (p: string) => `${p}${++uid}`;

function text(parent: Element, x: number, y: number, t: string, size: number, fill: string, init: VisualInit, weight = 700, anchor = "middle") {
  const el = s("text", { x, y, "text-anchor": anchor, "font-family": FONT(init), "font-weight": weight, "font-size": size, fill }, parent);
  el.textContent = t;
  return el;
}
function radial(defs: Element, id: string, stops: [number, string, number][]) {
  const g = s("radialGradient", { id, cx: "50%", cy: "50%", r: "50%" }, defs);
  for (const [o, c, a] of stops) s("stop", { offset: `${o}%`, "stop-color": c, "stop-opacity": a }, g);
  return `url(#${id})`;
}
function arrowPath(x1: number, y1: number, x2: number, y2: number, head: number): string {
  const a = Math.atan2(y2 - y1, x2 - x1), l = a + Math.PI * 0.82, r = a - Math.PI * 0.82;
  return `M${x1},${y1} L${x2},${y2} M${x2 + Math.cos(l) * head},${y2 + Math.sin(l) * head} L${x2},${y2} L${x2 + Math.cos(r) * head},${y2 + Math.sin(r) * head}`;
}

/** quiet deep-space background: fixed stars, a few twinkle slowly (continuous, low amplitude) */
const starfield: VisualDef = {
  id: "starfield",
  motion: "continuous",
  aspect: () => 1.8,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 1800", width: "100%", height: "100%", preserveAspectRatio: "xMidYMid slice" }, host);
    const defs = s("defs", {}, svg);
    s("rect", { x: 0, y: 0, width: 1000, height: 1800, fill: init.palette.bg }, svg);
    s("rect", { x: 0, y: 0, width: 1000, height: 1800, fill: radial(defs, gid("neb"), [[0, "#1a2340", 0.55], [60, "#0d1222", 0.25], [100, init.palette.bg, 0]]) }, svg);
    const r = rng(num(props.seed, 7));
    const tw: { el: SVGElement; ph: number; sp: number; base: number }[] = [];
    for (let i = 0; i < 420; i++) {
      const big = r() < 0.06;
      const base = 0.25 + r() * 0.6;
      const c = r() < 0.2 ? "#ffd9a8" : r() < 0.35 ? "#bcd4ff" : "#f3efe6";
      const el = s("circle", { cx: r() * 1000, cy: r() * 1800, r: big ? 1.6 + r() * 1.2 : 0.5 + r() * 0.9, fill: c, opacity: base }, svg);
      if (r() < 0.25) tw.push({ el, ph: r() * Math.PI * 2, sp: 0.25 + r() * 0.5, base });
    }
    return { update(ctx) { for (const t of tw) set(t.el, { opacity: (t.base * (0.75 + 0.25 * Math.sin(ctx.sceneT * t.sp * 2 * Math.PI + t.ph))).toFixed(3) }); } };
  },
};

/** a soft warm glow (the heart of a collapsing clump): the anchor of the nested zoom */
const glowdot: VisualDef = {
  id: "glowdot",
  motion: "continuous",
  aspect: () => 1,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 100 100", width: "100%", height: "100%" }, host);
    const defs = s("defs", {}, svg);
    const c = str(props.color, init.palette.accent);
    const g = s("circle", { cx: 50, cy: 50, r: 50, fill: radial(defs, gid("gd"), [[0, "#fff6e0", 0.95], [18, c, 0.75], [55, c, 0.22], [100, c, 0]]) }, svg);
    return { update(ctx) { set(g, { r: (44 + 6 * Math.sin(ctx.sceneT * 0.9 * Math.PI)).toFixed(2) }); } };
  },
};

/** a core-temperature readout that climbs to `to` (in millions) over `over` seconds */
const thermo: VisualDef = {
  id: "thermo",
  motion: "continuous",
  aspect: () => 0.42,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 420", width: "100%", height: "100%" }, host);
    const to = num(props.to, 15), over = num(props.over, 3.2), unit = str(props.unit, "million °");
    const track = s("rect", { x: 80, y: 330, width: 840, height: 26, rx: 13, fill: init.palette.bg2, stroke: init.palette.line, "stroke-width": 3 }, svg);
    void track;
    const bar = s("rect", { x: 80, y: 330, width: 0, height: 26, rx: 13, fill: init.palette.accent }, svg);
    const t = text(svg, 500, 285, "0", 190, init.palette.fg, init, 800);
    const u = text(svg, 500, 70, unit, 60, init.palette.accent, init, 700);
    void u;
    return {
      update(ctx) {
        const p = ease(ctx.t / over);
        t.textContent = (to * p).toFixed(p < 1 ? 1 : 0).replace(/\.0$/, "");
        set(bar, { width: (840 * p).toFixed(1) });
      },
    };
  },
};

/** gravity in, pressure out: a star disc with two rings of arrows */
const balance: VisualDef = {
  id: "balance",
  motion: "continuous",
  aspect: () => 1,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 1000", width: "100%", height: "100%" }, host);
    const defs = s("defs", {}, svg);
    s("circle", { cx: 500, cy: 500, r: 230, fill: radial(defs, gid("st"), [[0, "#fff4d6", 1], [45, "#ffc56b", 1], [85, "#ff8a3d", 1], [100, "#ff6a2a", 0.9]]) }, svg);
    const ins: SVGElement[] = [], outs: SVGElement[] = [];
    const n = 8;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + Math.PI / 8;
      const ca = Math.cos(a), sa = Math.sin(a);
      ins.push(s("path", { d: arrowPath(500 + ca * 470, 500 + sa * 470, 500 + ca * 300, 500 + sa * 300, 34), stroke: init.palette.accent2 ?? "#86b9ff", "stroke-width": 16, "stroke-linecap": "round", "stroke-linejoin": "round", fill: "none", opacity: 0 }, svg));
      const b = a + Math.PI / n;
      const cb = Math.cos(b), sb = Math.sin(b);
      outs.push(s("path", { d: arrowPath(500 + cb * 150, 500 + sb * 150, 500 + cb * 330, 500 + sb * 330, 34), stroke: "#fff8ea", "stroke-width": 14, "stroke-linecap": "round", "stroke-linejoin": "round", fill: "none", opacity: 0 }, svg));
    }
    const inAt = num(props.inAtS, 1.0), outAt = num(props.outAtS, 3.6);
    return {
      update(ctx) {
        const wob = Math.sin(ctx.sceneT * 1.4 * Math.PI) * 6;
        ins.forEach((el, i) => set(el, { opacity: ramp(ctx.t, inAt + i * 0.06, inAt + 0.6 + i * 0.06).toFixed(3), transform: `translate(${(-Math.cos(((i / n) * Math.PI * 2 + Math.PI / 8)) * wob).toFixed(2)},${(-Math.sin(((i / n) * Math.PI * 2 + Math.PI / 8)) * wob).toFixed(2)})` }));
        outs.forEach((el, i) => set(el, { opacity: ramp(ctx.t, outAt + i * 0.06, outAt + 0.6 + i * 0.06).toFixed(3) }));
      },
    };
  },
};

/** a Sun-like star next to a heavy star that burns faster */
const twostars: VisualDef = {
  id: "twostars",
  motion: "continuous",
  aspect: () => 0.62,
  create(host, _props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 620", width: "100%", height: "100%" }, host);
    const defs = s("defs", {}, svg);
    const a = s("circle", { cx: 230, cy: 280, r: 70, fill: radial(defs, gid("a"), [[0, "#fff6dc", 1], [60, "#ffcf6e", 1], [100, "#ff9d3c", 0.95]]) }, svg);
    const bg = s("circle", { cx: 660, cy: 280, r: 250, fill: radial(defs, gid("bh"), [[0, "#dfe9ff", 0.6], [70, "#86b9ff", 0.18], [100, "#86b9ff", 0]]) }, svg);
    const b = s("circle", { cx: 660, cy: 280, r: 175, fill: radial(defs, gid("b"), [[0, "#ffffff", 1], [55, "#d5e4ff", 1], [100, "#8fb6ff", 0.95]]) }, svg);
    text(svg, 230, 470, "Sun-like", 54, init.palette.fg, init);
    text(svg, 660, 570, "heavy star", 54, init.palette.fg, init);
    void a;
    return { update(ctx) {
      set(bg, { r: (250 + 18 * Math.sin(ctx.sceneT * 2.2 * Math.PI)).toFixed(2) });
      set(a, { r: (70 + 1.5 * Math.sin(ctx.sceneT * 0.6 * Math.PI)).toFixed(2) });
      set(b, { opacity: 0.94 + 0.06 * Math.sin(ctx.sceneT * 2.2 * Math.PI) });
    } };
  },
};

/** two lifetime bars on ONE linear scale (the honest comparison: the massive star's bar is almost invisible) */
const lifebars: VisualDef = {
  id: "lifebars",
  motion: "continuous",
  aspect: () => 0.62,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 620", width: "100%", height: "100%" }, host);
    const A = (props.a ?? {}) as any, B = (props.b ?? {}) as any;
    const max = Math.max(num(A.value, 1), num(B.value, 1));
    text(svg, 40, 110, str(A.label, "A"), 52, init.palette.fg, init, 700, "start");
    const ra = s("rect", { x: 40, y: 140, width: 0, height: 70, rx: 10, fill: init.palette.accent }, svg);
    const ta = text(svg, 40, 270, str(A.text, ""), 46, init.palette.accent, init, 700, "start");
    text(svg, 40, 400, str(B.label, "B"), 52, init.palette.fg, init, 700, "start");
    const wb = Math.max(4, (920 * num(B.value, 1)) / max);
    const rb = s("rect", { x: 40, y: 430, width: 0, height: 70, rx: 3, fill: init.palette.accent2 ?? "#86b9ff" }, svg);
    const tb = text(svg, 40, 560, str(B.text, ""), 46, init.palette.accent2 ?? "#86b9ff", init, 700, "start");
    return { update(ctx) {
      const pa = ease(ctx.t / 2.4), pb = ease((ctx.t - 2.6) / 0.8);
      set(ra, { width: (920 * pa).toFixed(1) }); set(ta, { opacity: ramp(ctx.t, 1.6, 2.4).toFixed(3) });
      set(rb, { width: (wb * pb).toFixed(2) }); set(tb, { opacity: ramp(ctx.t, 3.0, 3.6).toFixed(3) });
      set(ra, { opacity: (0.92 + 0.08 * Math.sin(ctx.sceneT * 0.8 * Math.PI)).toFixed(3) });
    } };
  },
};

/** starting mass → ending: white dwarf | neutron star (from ~8) | black hole (from ~20, fuzzy edge = uncertain) */
const fatechart: VisualDef = {
  id: "fatechart",
  motion: "continuous",
  aspect: () => 0.56,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 560", width: "100%", height: "100%" }, host);
    const defs = s("defs", {}, svg);
    const max = num(props.max, 40), sn = num(props.sn, 8), bh = num(props.bh, 20);
    const X = (m: number) => 40 + (920 * m) / max;
    const lg = s("linearGradient", { id: gid("fz"), x1: "0", x2: "1", y1: "0", y2: "0" }, defs);
    s("stop", { offset: "0%", "stop-color": "#4f5fae", "stop-opacity": 0.85 }, lg);
    s("stop", { offset: "100%", "stop-color": "#c9b8ff", "stop-opacity": 0.85 }, lg);
    const z1 = s("rect", { x: X(0), y: 170, width: X(sn) - X(0), height: 120, fill: "#ffcf6e", opacity: 0 }, svg);
    const z2 = s("rect", { x: X(sn), y: 170, width: X(bh - 3) - X(sn), height: 120, fill: "#86b9ff", opacity: 0 }, svg);
    const zf = s("rect", { x: X(bh - 3), y: 170, width: X(bh + 3) - X(bh - 3), height: 120, fill: `url(#${lg.getAttribute("id")})`, opacity: 0 }, svg);
    const z3 = s("rect", { x: X(bh + 3), y: 170, width: X(max) - X(bh + 3), height: 120, fill: "#c9b8ff", opacity: 0 }, svg);
    const l1 = text(svg, (X(0) + X(sn)) / 2, 130, "white dwarf", 36, init.palette.fg, init);
    const l2 = text(svg, (X(sn) + X(bh)) / 2, 130, "neutron star", 36, init.palette.fg, init);
    const l3 = text(svg, (X(bh) + X(max)) / 2, 130, "black hole", 36, init.palette.fg, init);
    s("path", { d: `M${X(0)},310 H${X(max)}`, stroke: init.palette.line ?? "#64728f", "stroke-width": 4 }, svg);
    for (const m of [1, sn, bh, max]) { s("path", { d: `M${X(m)},300 V322`, stroke: init.palette.muted, "stroke-width": 4 }, svg); text(svg, X(m), 372, m === bh ? `~${m}` : `${m}`, 40, init.palette.muted, init, 600); }
    text(svg, 500, 450, "starting mass (× the Sun)", 42, init.palette.muted, init, 600);
    const tiles = [[z1, l1], [z2, l2], [zf, null], [z3, l3]] as const;
    return { update(ctx) {
      tiles.forEach(([z, l], i) => {
        const a = ramp(ctx.t, 0.4 + i * 0.9, 1.0 + i * 0.9);
        set(z, { opacity: (0.85 * a).toFixed(3) });
        if (l) set(l, { opacity: a.toFixed(3) });
      });
      set(zf, { opacity: (ramp(ctx.t, 2.2, 2.8) * (0.7 + 0.15 * Math.sin(ctx.sceneT * 1.2 * Math.PI))).toFixed(3) });
    } };
  },
};

/** the layered core: shells of heavier elements appear one by one; iron arrives last at the centre */
const SHELL_COLORS = ["#ff7a4d", "#ffa65a", "#ffd166", "#9be08a", "#6fd0e0", "#8fa2ff", "#9a9aa6"];
const onion: VisualDef = {
  id: "onion",
  motion: "continuous",
  aspect: () => 1,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 1000", width: "100%", height: "100%" }, host);
    const shells = arr<string>(props.shells, ["H", "He", "C", "Ne", "O", "Si", "Fe"]);
    const n = shells.length, R = 470, stop = num(props.stop, n - 1), over = num(props.revealOver, 8);
    const ironAt = props.ironAtS === undefined ? -1 : num(props.ironAtS, -1);
    const rings: { c: SVGElement; t: SVGElement; i: number }[] = [];
    shells.forEach((sym, i) => {
      const r = R * (1 - i / n);
      const c = s("circle", { cx: 500, cy: 500, r, fill: SHELL_COLORS[i % SHELL_COLORS.length], stroke: init.palette.bg, "stroke-width": 6, opacity: 0 }, svg);
      const ty = 500 - r + (R / n) * 0.62 + 14;
      const t = text(svg, 500, i === n - 1 ? 520 : ty, sym, i === n - 1 ? 64 : 50, "#0b0e16", init, 800);
      set(t, { opacity: 0 });
      rings.push({ c, t, i });
    });
    return { update(ctx) {
      rings.forEach(({ c, t, i }) => {
        let a = 0;
        if (i < stop) a = over <= 0.05 ? 1 : ramp(ctx.t, (i / Math.max(stop, 1)) * over, (i / Math.max(stop, 1)) * over + 0.7);
        else if (i === n - 1 && ironAt >= 0) a = ramp(ctx.t, ironAt, ironAt + 0.8);
        const br = 1 + 0.006 * Math.sin(ctx.sceneT * 0.7 * Math.PI + i);
        set(c, { opacity: a.toFixed(3), transform: `translate(500 500) scale(${br.toFixed(4)}) translate(-500 -500)` });
        set(t, { opacity: a.toFixed(3) });
      });
    } };
  },
};

/** the iron core alone: inward gravity arrows stay, outward pressure arrows fade */
const ironcore: VisualDef = {
  id: "ironcore",
  motion: "continuous",
  aspect: () => 1,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 1000", width: "100%", height: "100%" }, host);
    const defs = s("defs", {}, svg);
    s("circle", { cx: 500, cy: 500, r: 200, fill: radial(defs, gid("fe"), [[0, "#d8d8e0", 1], [70, "#9a9aa6", 1], [100, "#6d6d78", 1]]) }, svg);
    text(svg, 500, 530, "Fe", 96, "#0b0e16", init, 800);
    const ins: SVGElement[] = [], outs: SVGElement[] = [];
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2 + Math.PI / 8, b = a + Math.PI / 8;
      ins.push(s("path", { d: arrowPath(500 + Math.cos(a) * 470, 500 + Math.sin(a) * 470, 500 + Math.cos(a) * 270, 500 + Math.sin(a) * 270, 34), stroke: init.palette.accent2 ?? "#86b9ff", "stroke-width": 16, "stroke-linecap": "round", "stroke-linejoin": "round", fill: "none" }, svg));
      outs.push(s("path", { d: arrowPath(500 + Math.cos(b) * 215, 500 + Math.sin(b) * 215, 500 + Math.cos(b) * 380, 500 + Math.sin(b) * 380, 30), stroke: "#fff8ea", "stroke-width": 13, "stroke-linecap": "round", "stroke-linejoin": "round", fill: "none" }, svg));
    }
    const fadeAt = num(props.fadeAtS, 2.4);
    return { update(ctx) {
      const f = 1 - ease((ctx.t - fadeAt) / 1.6);
      outs.forEach((el) => set(el, { opacity: f.toFixed(3) }));
      const k = 1 + 0.025 * ease((ctx.t - fadeAt) / 3) + 0.01 * Math.sin(ctx.sceneT * 1.6 * Math.PI);
      ins.forEach((el) => set(el, { transform: `translate(500 500) scale(${(1 / k).toFixed(4)}) translate(-500 -500)` }));
    } };
  },
};

/** the core collapses in well under a second (eased), leaving a tiny hot point; no flash (H7) */
const collapse: VisualDef = {
  id: "collapse",
  motion: "continuous",
  aspect: () => 1,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 1000", width: "100%", height: "100%" }, host);
    const defs = s("defs", {}, svg);
    const halo = s("circle", { cx: 500, cy: 500, r: 260, fill: radial(defs, gid("ha"), [[0, "#ffd9a0", 0.5], [100, "#ff7a4d", 0]]) }, svg);
    const core = s("circle", { cx: 500, cy: 500, r: 200, fill: radial(defs, gid("co"), [[0, "#e6e6ee", 1], [70, "#9a9aa6", 1], [100, "#6d6d78", 1]]) }, svg);
    const hot = s("circle", { cx: 500, cy: 500, r: 0, fill: radial(defs, gid("ho"), [[0, "#fff4dc", 1], [50, "#ffc861", 0.9], [100, "#ff7a4d", 0]]) }, svg);
    const at = num(props.collapseAtS, 1.2), dur = num(props.collapseS, 0.8);
    return { update(ctx) {
      const p = ease((ctx.t - at) / dur);
      const r = 200 * (1 - 0.9 * p);
      set(core, { r: r.toFixed(2), opacity: (1 - 0.6 * p).toFixed(3) });
      set(hot, { r: (60 * ramp(ctx.t, at + dur * 0.5, at + dur + 0.6) * (1 + 0.05 * Math.sin(ctx.sceneT * 2 * Math.PI))).toFixed(2) });
      set(halo, { r: (260 - 120 * p).toFixed(2), opacity: (0.6 + 0.3 * p).toFixed(3) });
    } };
  },
};

/** a colour key: never colour alone — every swatch is named */
const legend: VisualDef = {
  id: "legend",
  aspect: (p) => { const n = arr(p.items, [1]).length, c = Math.max(1, num(p.cols, 1)); return (300 * Math.ceil(n / c)) / (1000 * c); },
  create(host, props, init) {
    const items = arr<[string, string]>(props.items, []);
    const cols = Math.max(1, num(props.cols, 1)), rows = Math.ceil(items.length / cols);
    const svg = s("svg", { viewBox: `0 0 ${1000 * cols} ${300 * rows}`, width: "100%", height: "100%" }, host);
    const g0: SVGElement[] = [];
    items.forEach(([name, color], i) => {
      const x = (i % cols) * 1000, y = Math.floor(i / cols) * 300;
      const g = s("g", { opacity: 0 }, svg);
      s("rect", { x: x + 30, y: y + 70, width: 160, height: 160, rx: 26, fill: color }, g);
      text(g, x + 240, y + 198, name, 130, init.palette.fg, init, 700, "start");
      g0.push(g);
    });
    return { update(ctx) { g0.forEach((g, i) => set(g, { opacity: ramp(ctx.progress, i * 0.15, i * 0.15 + 0.4).toFixed(3) })); } };
  },
};

/** share of each element made by exploding massive stars (NASA/Chandra) */
const elementbars: VisualDef = {
  id: "elementbars",
  motion: "continuous",
  aspect: () => 0.62,
  create(host, props, init) {
    const items = arr<[string, number, string]>(props.items, []);
    const svg = s("svg", { viewBox: "0 0 1000 620", width: "100%", height: "100%" }, host);
    const cols = ["#9be08a", "#ffd166", "#b47aff"];
    const bars: { r: SVGElement; v: number; t: SVGElement }[] = [];
    items.forEach(([name, v, lab], i) => {
      const y = 40 + i * 195;
      text(svg, 40, y + 50, name, 54, init.palette.fg, init, 700, "start");
      s("rect", { x: 40, y: y + 75, width: 920, height: 64, rx: 12, fill: init.palette.bg2, stroke: init.palette.line, "stroke-width": 3 }, svg);
      const r = s("rect", { x: 40, y: y + 75, width: 0, height: 64, rx: 12, fill: cols[i % cols.length] }, svg);
      const t = text(svg, 960, y + 50, lab, 50, cols[i % cols.length], init, 800, "end");
      bars.push({ r, v, t });
    });
    return { update(ctx) {
      bars.forEach(({ r, v, t }, i) => {
        const p = ease((ctx.t - i * 0.7) / 1.4);
        set(r, { width: ((920 * v) / 100 * p).toFixed(1) });
        set(t, { opacity: ramp(ctx.t, i * 0.7 + 0.8, i * 0.7 + 1.4).toFixed(3) });
      });
      bars[0] && set(bars[0].r, { opacity: (0.92 + 0.08 * Math.sin(ctx.sceneT * 0.8 * Math.PI)).toFixed(3) });
    } };
  },
};

/** the collapsed core's two possible endings */
const fork: VisualDef = {
  id: "fork",
  motion: "continuous",
  aspect: () => 0.62,
  create(host, props, init) {
    const svg = s("svg", { viewBox: "0 0 1000 620", width: "100%", height: "100%" }, host);
    const defs = s("defs", {}, svg);
    const core = s("circle", { cx: 500, cy: 110, r: 70, fill: radial(defs, gid("fc"), [[0, "#fff4dc", 1], [60, "#ffc861", 0.95], [100, "#ff7a4d", 0.4]]) }, svg);
    text(svg, 500, 230, "collapsed core", 46, init.palette.muted, init, 600);
    const la = s("path", { d: arrowPath(440, 260, 250, 370, 30), stroke: init.palette.accent2 ?? "#86b9ff", "stroke-width": 12, "stroke-linecap": "round", "stroke-linejoin": "round", fill: "none" }, svg);
    const ra = s("path", { d: arrowPath(560, 260, 750, 370, 30), stroke: "#c9b8ff", "stroke-width": 12, "stroke-linecap": "round", "stroke-linejoin": "round", fill: "none" }, svg);
    const g1 = s("g", {}, svg), g2 = s("g", {}, svg);
    text(g1, 230, 450, str(props.left, "neutron star"), 58, init.palette.fg, init, 800);
    text(g1, 230, 520, str(props.leftNote, ""), 44, init.palette.accent2 ?? "#86b9ff", init, 600);
    text(g2, 770, 450, str(props.right, "black hole"), 58, init.palette.fg, init, 800);
    text(g2, 770, 520, str(props.rightNote, ""), 44, "#c9b8ff", init, 600);
    return { update(ctx) {
      set(core, { r: (70 + 4 * Math.sin(ctx.sceneT * 1.2 * Math.PI)).toFixed(2) });
      set(la, { opacity: ramp(ctx.t, 0.6, 1.2).toFixed(3) }); set(g1, { opacity: ramp(ctx.t, 1.0, 1.6).toFixed(3) });
      set(ra, { opacity: ramp(ctx.t, 1.4, 2.0).toFixed(3) }); set(g2, { opacity: ramp(ctx.t, 1.8, 2.4).toFixed(3) });
    } };
  },
};

/** a provenance tag ("Real image · Webb" / "Illustration") on a translucent pill, readable on any background */
const tag: VisualDef = {
  id: "tag",
  aspect: (p) => 110 / (36 * str(p.text, "").length + 80),
  create(host, props, init) {
    const t = str(props.text, "");
    const W = 36 * t.length + 80;
    const svg = s("svg", { viewBox: `0 0 ${W} 110`, width: "100%", height: "100%" }, host);
    s("rect", { x: 2, y: 2, width: W - 4, height: 106, rx: 53, fill: init.palette.bg, "fill-opacity": 0.62, stroke: init.palette.line, "stroke-opacity": 0.6, "stroke-width": 2 }, svg);
    text(svg, W / 2, 76, t, 60, init.palette.fg, init, 600);
    return { update() {} };
  },
};

export default [tag, starfield, glowdot, thermo, balance, twostars, lifebars, fatechart, onion, ironcore, collapse, legend, elementbars, fork];
