// dom.ts — tiny DOM/SVG helpers (the engine is plain TypeScript on the DOM; no UI framework is needed for frame-driven drawing).
export const SVG_NS = "http://www.w3.org/2000/svg";
export function h<K extends keyof HTMLElementTagNameMap>(tag: K, style: Partial<CSSStyleDeclaration> | Record<string, string> = {}, attrs: Record<string, string> = {}): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(style)) (el.style as any)[k] = v as string;
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}
export function s<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}, parent?: Element): SVGElementTagNameMap[K] {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  if (parent) parent.appendChild(el);
  return el;
}
export const set = (el: Element, attrs: Record<string, string | number>): void => { for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v)); };
/** deterministic PRNG (mulberry32): visuals and grain must be pure functions of the frame */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
