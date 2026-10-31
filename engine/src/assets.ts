// assets.ts — loading what the scene graph points at: raster images, inline SVG, frame sequences (extracted video) and fonts.
// Everything is decoded BEFORE the first frame so that a screenshot can never catch a half-loaded asset.
import { SVG_NS } from "./dom";

export interface AssetSpec {
  id: string;
  kind: "svg" | "image" | "video";
  url: string;
  width?: number;
  height?: number;
  frames?: { count: number; fps: number; pattern: string }; // pattern uses {n} for the zero-based frame number
}
export interface AssetInfo {
  id: string;
  kind: "svg" | "image" | "video";
  url: string;
  width: number;
  height: number;
  svg?: SVGSVGElement; // a sanitised template to clone (kind svg)
  frames?: { count: number; fps: number; url: (i: number) => string };
}
export interface FontSpec { family: string; url: string; weight?: number; style?: string }

/** inline SVG is allowed to draw with page fonts, so it is parsed, stripped of anything active, and cloned per entity */
export function sanitiseSvg(text: string): SVGSVGElement {
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  const root = doc.documentElement as unknown as SVGSVGElement;
  if (!root || root.nodeName.toLowerCase() !== "svg" || doc.querySelector("parsererror")) throw new Error("not a valid SVG document");
  doc.querySelectorAll("script, foreignObject, iframe, object, embed, audio, video").forEach((n) => n.remove());
  doc.querySelectorAll("*").forEach((n) => {
    for (const a of Array.from(n.attributes)) {
      const name = a.name.toLowerCase();
      const val = a.value.trim().toLowerCase();
      if (name.startsWith("on")) n.removeAttribute(a.name);
      else if ((name === "href" || name === "xlink:href") && !val.startsWith("#") && !val.startsWith("data:image/")) n.removeAttribute(a.name); // no network, no javascript:
    }
  });
  return root;
}

function svgSize(root: SVGSVGElement): { w: number; h: number } {
  const vb = root.getAttribute("viewBox")?.trim().split(/[\s,]+/).map(Number);
  if (vb && vb.length === 4 && vb[2] > 0 && vb[3] > 0) return { w: vb[2], h: vb[3] };
  const w = parseFloat(root.getAttribute("width") ?? ""), h = parseFloat(root.getAttribute("height") ?? "");
  if (w > 0 && h > 0) return { w, h };
  throw new Error("SVG has neither a viewBox nor width/height");
}

async function decodeImage(url: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.decoding = "sync";
  img.src = url;
  await img.decode();
  return img;
}

export async function loadAsset(spec: AssetSpec): Promise<AssetInfo> {
  if (spec.kind === "svg") {
    const res = await fetch(spec.url);
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${spec.url}`);
    const root = sanitiseSvg(await res.text());
    const { w, h } = svgSize(root);
    return { id: spec.id, kind: "svg", url: spec.url, width: w, height: h, svg: root };
  }
  if (spec.kind === "video") {
    if (!spec.frames || !spec.width || !spec.height) throw new Error("video assets are rendered from extracted frames; render.mjs extracts them (frames/width/height missing)");
    const f = spec.frames;
    const first = await decodeImage(f.pattern.replace("{n}", "0"));
    return { id: spec.id, kind: "video", url: spec.url, width: first.naturalWidth, height: first.naturalHeight, frames: { count: f.count, fps: f.fps, url: (i) => f.pattern.replace("{n}", String(Math.max(0, Math.min(f.count - 1, i)))) } };
  }
  const img = await decodeImage(spec.url);
  return { id: spec.id, kind: "image", url: spec.url, width: img.naturalWidth, height: img.naturalHeight };
}

export async function loadFonts(faces: FontSpec[]): Promise<string[]> {
  const problems: string[] = [];
  for (const f of faces) {
    try {
      const face = new FontFace(f.family, `url(${f.url})`, { weight: String(f.weight ?? 400), style: f.style ?? "normal" });
      await face.load();
      document.fonts.add(face);
    } catch (e) {
      problems.push(`font ${f.family} (${f.url}) failed to load: ${(e as Error).message}`);
    }
  }
  await document.fonts.ready;
  return problems;
}

/** A family that the browser cannot resolve silently falls back; compare widths with a reference fallback to notice. */
export function fontAvailable(family: string, weight = 700): boolean {
  const c = document.createElement("canvas").getContext("2d")!;
  const sample = "mmmmmmmmmmlliWQ@#0123456789";
  const measure = (stack: string) => { c.font = `${weight} 72px ${stack}`; return c.measureText(sample).width; };
  const q = `"${family}"`;
  return Math.abs(measure(`${q}, monospace`) - measure("monospace")) > 0.5 || Math.abs(measure(`${q}, serif`) - measure("serif")) > 0.5;
}

export { SVG_NS };
