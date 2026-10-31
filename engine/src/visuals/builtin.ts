// builtin.ts — generic, topic-independent code visuals. Topic-specific visuals live in videos/<slug>/visuals/index.ts.
import { s, set } from "../dom";
import { VisualDef, VisualRegistry, arr, clamp01, num, ramp, str } from "./types";

const FONT = (init: { tokens: { fonts: { body: string } } }) => `${init.tokens.fonts.body}, sans-serif`;

const roundRectPath = (w: number, h: number, r: number, x0 = 0, y0 = 0): string =>
  `M${x0 + r},${y0} H${x0 + w - r} Q${x0 + w},${y0} ${x0 + w},${y0 + r} V${y0 + h - r} Q${x0 + w},${y0 + h} ${x0 + w - r},${y0 + h} H${x0 + r} Q${x0},${y0 + h} ${x0},${y0 + h - r} V${y0 + r} Q${x0},${y0} ${x0 + r},${y0} Z`;

/** a flow of labelled boxes joined by arrows; each step appears as `progress` advances */
const flow: VisualDef = {
  id: "flow",
  aspect: (p) => (str(p.direction, "row") === "column" ? Math.max(arr<string>(p.steps, []).length, 1) * 0.42 : 0.2),
  create(host, props, init) {
    const steps = arr<string>(props.steps, ["one", "two", "three"]);
    const col = str(props.direction, "row") === "column";
    const n = steps.length;
    const VW = 1000, VH = col ? n * 420 : 200;
    const svg = s("svg", { viewBox: `0 0 ${VW} ${VH}`, width: "100%", height: "100%" }, host);
    const boxes: SVGElement[] = [], texts: SVGElement[] = [], arrows: SVGElement[] = [];
    const bw = col ? 760 : (VW - (n - 1) * 70) / n, bh = col ? 300 : 150;
    steps.forEach((label, i) => {
      const x = col ? (VW - bw) / 2 : i * (bw + 70), y = col ? i * 420 + 30 : 25;
      const g = s("g", {}, svg);
      boxes.push(s("rect", { x, y, width: bw, height: bh, rx: 26, fill: init.palette.bg2 ?? init.palette.bg, stroke: i === num(props.accent, -1) ? init.palette.accent : init.palette.line ?? init.palette.muted, "stroke-width": 6 }, g));
      const t = s("text", { x: x + bw / 2, y: y + bh / 2 + 14, "text-anchor": "middle", "font-family": FONT(init), "font-weight": 700, "font-size": col ? 96 : Math.min(58, (bw / Math.max(label.length, 4)) * 1.5), fill: init.palette.fg }, g);
      t.textContent = label;
      texts.push(t);
      if (i < n - 1) {
        const a = col ? s("path", { d: `M${VW / 2},${y + bh + 8} V${y + 420 - 14} m-22,-30 l22,30 l22,-30`, fill: "none", stroke: init.palette.accent, "stroke-width": 9, "stroke-linecap": "round", "stroke-linejoin": "round" }, svg) : s("path", { d: `M${x + bw + 10},${y + bh / 2} H${x + bw + 58} m-24,-22 l24,22 l-24,22`, fill: "none", stroke: init.palette.accent, "stroke-width": 9, "stroke-linecap": "round", "stroke-linejoin": "round" }, svg);
        arrows.push(a);
      }
    });
    return {
      update(ctx) {
        const p = ctx.progress;
        steps.forEach((_, i) => {
          const a = ramp(p, i / n, (i + 0.7) / n);
          set(boxes[i], { opacity: a });
          set(texts[i], { opacity: a });
          if (arrows[i]) {
            const b = ramp(p, (i + 0.5) / n, (i + 1) / n);
            set(arrows[i], { opacity: b });
          }
        });
      },
    };
  },
};

/** an outlined frame with a given aspect ratio (16:9 → 9:16 demonstrations), label inside */
const aspect_frame: VisualDef = {
  id: "aspect_frame",
  aspect: () => 1,
  path: (p, init) => {
    const rw = num(p.ratioW, 16), rh = num(p.ratioH, 9);
    const k = 900 / Math.max(rw, rh);
    const w = rw * k, h = rh * k;
    // the outline in HOST coordinates (the 1000 x 1000 square the visual draws in), so a morph can map it through the host rect
    const x0 = (1000 - w) / 2, y0 = (1000 - h) / 2, r = 40;
    const lab = str(p.label, `${rw}:${rh}`);
    // same segment structure for every aspect (4 edges, 4 corner curves), so a morph pairs edge with edge and corner with corner
    const points = (n: number): [number, number][] => {
      const pts: [number, number][] = [];
      const nl = Math.max(4, Math.round(n * 0.17)), nc = Math.max(3, Math.round(n * 0.08));
      const line = (ax: number, ay: number, bx: number, by: number) => { for (let i = 0; i < nl; i++) pts.push([ax + ((bx - ax) * i) / nl, ay + ((by - ay) * i) / nl]); };
      const quad = (ax: number, ay: number, cx: number, cy: number, bx: number, by: number) => { for (let i = 0; i < nc; i++) { const t = i / nc, u = 1 - t; pts.push([u * u * ax + 2 * u * t * cx + t * t * bx, u * u * ay + 2 * u * t * cy + t * t * by]); } };
      line(x0 + r, y0, x0 + w - r, y0); quad(x0 + w - r, y0, x0 + w, y0, x0 + w, y0 + r);
      line(x0 + w, y0 + r, x0 + w, y0 + h - r); quad(x0 + w, y0 + h - r, x0 + w, y0 + h, x0 + w - r, y0 + h);
      line(x0 + w - r, y0 + h, x0 + r, y0 + h); quad(x0 + r, y0 + h, x0, y0 + h, x0, y0 + h - r);
      line(x0, y0 + h - r, x0, y0 + r); quad(x0, y0 + r, x0, y0, x0 + r, y0);
      return pts;
    };
    return { d: roundRectPath(w, h, r, x0, y0), box: [1000, 1000], stroke: str(p.color, init.palette.accent), strokeWidth: 14, fill: init.palette.bg2 ?? init.palette.bg, label: { text: lab, x: 500, y: 526, size: Math.min(150, w / 4), fill: init.palette.fg, family: init.tokens.fonts.body, weight: 800 }, points };
  },
  create(host, props, init) {
    const rw = num(props.ratioW, 16), rh = num(props.ratioH, 9);
    const k = 900 / Math.max(rw, rh);
    const w = rw * k, h = rh * k, x = (1000 - w) / 2, y = (1000 - h) / 2;
    const svg = s("svg", { viewBox: "0 0 1000 1000", width: "100%", height: "100%" }, host);
    const rect = s("path", { d: roundRectPath(w, h, 40), transform: `translate(${x},${y})`, fill: init.palette.bg2 ?? init.palette.bg, stroke: str(props.color, init.palette.accent), "stroke-width": 14, "stroke-linejoin": "round" }, svg);
    const label = s("text", { x: 500, y: 500 + 26, "text-anchor": "middle", "font-family": FONT(init), "font-weight": 800, "font-size": Math.min(150, w / 4), fill: init.palette.fg }, svg);
    label.textContent = str(props.label, `${rw}:${rh}`);
    const perim = 2 * (w + h);
    set(rect, { "stroke-dasharray": perim, "stroke-dashoffset": perim });
    return {
      update(ctx) {
        set(rect, { "stroke-dashoffset": perim * (1 - ramp(ctx.progress, 0, 0.8)) });
        set(label, { opacity: ramp(ctx.progress, 0.55, 1) });
      },
    };
  },
};

const bars: VisualDef = {
  id: "bars",
  aspect: (p) => num(p.aspect, 0.55),
  create(host, props, init) {
    const values = arr<number>(props.values, [3, 5, 2]);
    const labels = arr<string>(props.labels, values.map((_, i) => String(i + 1)));
    const max = num(props.max, Math.max(...values));
    const asp = num(props.aspect, 0.55), VW = 1000, VH = 1000 * asp;
    const svg = s("svg", { viewBox: `0 0 ${VW} ${VH}`, width: "100%", height: "100%" }, host);
    const n = values.length, gap = 40, bw = (VW - gap * (n + 1)) / n;
    const rects: SVGElement[] = [], vals: SVGElement[] = [];
    values.forEach((v, i) => {
      const x = gap + i * (bw + gap);
      rects.push(s("rect", { x, y: VH - 90, width: bw, height: 0, rx: 10, fill: i === num(props.accent, -1) ? init.palette.accent : init.palette.accent2 ?? init.palette.muted }, svg));
      const t = s("text", { x: x + bw / 2, y: VH - 30, "text-anchor": "middle", "font-family": FONT(init), "font-size": 44, "font-weight": 600, fill: init.palette.fg }, svg);
      t.textContent = labels[i] ?? "";
      const vv = s("text", { x: x + bw / 2, y: VH - 110, "text-anchor": "middle", "font-family": FONT(init), "font-size": 48, "font-weight": 800, fill: init.palette.fg, opacity: 0 }, svg);
      vv.textContent = String(v);
      vals.push(vv);
    });
    return {
      update(ctx) {
        values.forEach((v, i) => {
          const a = ramp(ctx.progress, i * 0.08, 0.6 + i * 0.08);
          const hgt = ((VH - 220) * v) / max * a;
          set(rects[i], { y: VH - 90 - hgt, height: hgt });
          set(vals[i], { y: VH - 110 - hgt, opacity: ramp(a, 0.7, 1) });
        });
      },
    };
  },
};

const counter: VisualDef = {
  id: "counter",
  aspect: () => 0.5,
  create(host, props, init) {
    const from = num(props.from, 0), to = num(props.to, 100), dec = num(props.decimals, 0), suf = str(props.suffix, "");
    const svg = s("svg", { viewBox: "0 0 1000 500", width: "100%", height: "100%" }, host);
    const t = s("text", { x: 500, y: 330, "text-anchor": "middle", "font-family": `${init.tokens.fonts.display}, sans-serif`, "font-weight": 800, "font-size": 300, fill: init.palette.fg }, svg);
    return { update(ctx) { t.textContent = (from + (to - from) * clamp01(ctx.progress)).toFixed(dec) + suf; } };
  },
};

const wave: VisualDef = {
  id: "wave",
  motion: "continuous", // the phase advances with scene time
  aspect: (p) => num(p.aspect, 0.4),
  create(host, props, init) {
    const asp = num(props.aspect, 0.4), VW = 1000, VH = 1000 * asp;
    const cycles = num(props.cycles, 3), amp = num(props.amplitude, 0.3), speed = num(props.speed, 0.5);
    const svg = s("svg", { viewBox: `0 0 ${VW} ${VH}`, width: "100%", height: "100%" }, host);
    const path = s("path", { fill: "none", stroke: str(props.color, init.palette.accent), "stroke-width": 10, "stroke-linecap": "round", "stroke-linejoin": "round" }, svg);
    return {
      update(ctx) {
        const N = 160, pts: string[] = [], reach = ramp(ctx.progress, 0, 0.9);
        for (let i = 0; i <= N * reach; i++) {
          const x = (i / N) * VW;
          const y = VH / 2 - Math.sin((i / N) * cycles * 2 * Math.PI - ctx.sceneT * speed * 2 * Math.PI) * amp * VH;
          pts.push(`${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`);
        }
        set(path, { d: pts.join(" ") || "M0,0" });
      },
    };
  },
};

const arrow: VisualDef = {
  id: "arrow",
  aspect: (p) => num(p.aspect, 0.3),
  create(host, props, init) {
    const asp = num(props.aspect, 0.3), VW = 1000, VH = 1000 * asp;
    const svg = s("svg", { viewBox: `0 0 ${VW} ${VH}`, width: "100%", height: "100%" }, host);
    const y = VH / 2, len = VW - 160;
    const shaft = s("path", { d: `M40,${y} H${40 + len}`, stroke: str(props.color, init.palette.accent), "stroke-width": 16, "stroke-linecap": "round", fill: "none" }, svg);
    const head = s("path", { d: `M${VW - 150},${y - 60} L${VW - 40},${y} L${VW - 150},${y + 60}`, stroke: str(props.color, init.palette.accent), "stroke-width": 16, "stroke-linecap": "round", "stroke-linejoin": "round", fill: "none" }, svg);
    return { update(ctx) { set(shaft, { "stroke-dasharray": len, "stroke-dashoffset": len * (1 - ramp(ctx.progress, 0, 0.8)) }); set(head, { opacity: ramp(ctx.progress, 0.7, 1) }); } };
  },
};

const grid: VisualDef = {
  id: "grid",
  aspect: (p) => num(p.aspect, 0.5625),
  create(host, props, init) {
    const asp = num(props.aspect, 0.5625), VW = 1600, VH = 1600 * asp, step = num(props.step, 100);
    const svg = s("svg", { viewBox: `0 0 ${VW} ${VH}`, width: "100%", height: "100%" }, host);
    let d = "";
    for (let x = 0; x <= VW; x += step) d += `M${x},0 V${VH} `;
    for (let y = 0; y <= VH; y += step) d += `M0,${y} H${VW} `;
    s("path", { d, stroke: init.palette.line ?? init.palette.muted, "stroke-width": 1.5, opacity: num(props.opacity, 0.25), fill: "none" }, svg);
    return { update() {} };
  },
};

export const builtinVisuals: VisualRegistry = { flow, aspect_frame, bars, counter, wave, arrow, grid };
