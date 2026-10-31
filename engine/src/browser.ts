// browser.ts — the page-side entry. The Node driver (render.ts) calls window.engine.init(bundle) once, then renderFrame(n) per frame.
import { Bundle, ENGINE_VERSION, FrameRenderer, FrameTrace } from "./renderer";
import { builtinVisuals } from "./visuals/builtin";
import type { VisualDef, VisualRegistry } from "./visuals/types";

const registry: VisualRegistry = { ...builtinVisuals };
let renderer: FrameRenderer | null = null;

const api = {
  version: ENGINE_VERSION,
  registerVisual(def: VisualDef): void {
    if (registry[def.id] && registry[def.id] !== def && !(def.id in builtinVisuals)) throw new Error(`visual "${def.id}" registered twice`);
    registry[def.id] = def; // a project visual may deliberately replace a built-in of the same id
  },
  visuals(): string[] { return Object.keys(registry); },
  async init(bundle: Bundle) {
    renderer = await FrameRenderer.create(bundle, registry);
    return { warnings: renderer.buildWarnings, describe: renderer.describe(), version: ENGINE_VERSION };
  },
  async renderFrame(n: number): Promise<FrameTrace> {
    if (!renderer) throw new Error("engine.init() has not run");
    return renderer.renderFrame(n);
  },
  stateAt(t: number) { return renderer ? renderer.stateAt(t) : null; },
};
(window as unknown as { engine: typeof api }).engine = api;
