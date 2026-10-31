import type { Palette, StyleTokens } from "../../../schema/video.schema";

export interface VisualCtx {
  t: number; // seconds since the entity entered
  progress: number; // eased enter progress 0..1 (1 once fully entered)
  sceneT: number; // seconds since the scene started
  frame: number;
  fps: number;
  w: number; // host box size in px
  h: number;
  palette: Palette;
  tokens: StyleTokens;
}
export interface VisualInstance { update(ctx: VisualCtx): void }
export interface VisualInit { w: number; h: number; palette: Palette; tokens: StyleTokens }
/** What a visual offers so a truthful morph can deform it: its outline (d, in host coordinates 0..box), how it strokes it, an optional
 *  label, and optionally its own point sampler (n points, same segment structure for every shape of the same kind, so corners meet corners). */
export interface MorphShape {
  d: string;
  box: [number, number];
  stroke?: string;
  strokeWidth?: number;
  fill?: string;
  label?: { text: string; x: number; y: number; size: number; fill?: string; family?: string; weight?: number };
  points?: (n: number) => [number, number][];
}
export interface VisualDef {
  id: string;
  /** "continuous" = the picture keeps changing after it has entered (a wave, a flow of particles). The plan then records motion for the
   *  whole time the entity is on screen, so QA can tell a deliberate rest from a stall. Omitted = it changes only while it enters. */
  motion?: "continuous";
  aspect: (props: Record<string, unknown>) => number; // height / width of the host box
  create(host: HTMLElement, props: Record<string, unknown>, init: VisualInit): VisualInstance;
  /** optional outline for truthful morphs: a closed SVG path in the HOST coordinate space (0..box), plus how the visual strokes it */
  path?(props: Record<string, unknown>, init: VisualInit): MorphShape;
}
export type VisualRegistry = Record<string, VisualDef>;
export const num = (v: unknown, d: number): number => (typeof v === "number" && isFinite(v) ? v : d);
export const str = (v: unknown, d: string): string => (typeof v === "string" ? v : d);
export const arr = <T>(v: unknown, d: T[]): T[] => (Array.isArray(v) ? (v as T[]) : d);
export const clamp01 = (x: number): number => Math.min(1, Math.max(0, x));
export const ramp = (p: number, a: number, b: number): number => clamp01((p - a) / (b - a));
