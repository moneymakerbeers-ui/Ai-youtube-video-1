// grade.ts — the unifying grade that makes mixed sources (code, retrieved, generated) look like one world, plus fades.
import type { StyleTokens } from "../../schema/video.schema";
import { h, rng } from "./dom";

export class GradeLayer {
  readonly tint: HTMLElement;
  readonly vignette: HTMLElement;
  readonly grain: HTMLCanvasElement;
  readonly fade: HTMLElement;
  private ctx: CanvasRenderingContext2D;
  private img: ImageData;
  constructor(stage: HTMLElement, private W: number, private H: number, private g: StyleTokens["grade"], private fps: number) {
    const full = { position: "absolute", left: "0", top: "0", width: "100%", height: "100%", pointerEvents: "none" } as const;
    this.tint = h("div", { ...full, zIndex: "20", background: g.tint ?? "transparent", opacity: String(g.tint ? g.tintOpacity : 0), mixBlendMode: "soft-light" });
    this.vignette = h("div", { ...full, zIndex: "21", background: `radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,${g.vignette}) 100%)` });
    this.grain = document.createElement("canvas");
    this.grain.width = Math.ceil(W / 2);
    this.grain.height = Math.ceil(H / 2);
    Object.assign(this.grain.style, { ...full, zIndex: "22" });
    this.fade = h("div", { ...full, zIndex: "40", background: "#000", opacity: "0" });
    stage.append(this.tint, this.vignette, this.grain, this.fade);
    this.ctx = this.grain.getContext("2d")!;
    this.img = this.ctx.createImageData(this.grain.width, this.grain.height);
  }
  private lastKey = -1;
  update(frame: number, fadeOpacity: number): void {
    this.fade.style.opacity = fadeOpacity > 0.0005 ? String(+fadeOpacity.toFixed(4)) : "0";
    if (this.g.grain <= 0) return;
    // grain is a texture: static unless grainFps asks for animation (animated noise multiplies the encoded file size by ~20)
    const key = this.g.grainFps > 0 ? Math.floor((frame * this.g.grainFps) / this.fps) : 0;
    if (key === this.lastKey) return;
    this.lastKey = key;
    const r = rng(key * 7919 + 13);
    const d = new Uint32Array(this.img.data.buffer);
    const amp = Math.round(this.g.grain * 255 * 2);
    for (let i = 0; i < d.length; i++) {
      const a = Math.floor(r() * amp);
      d[i] = r() < 0.5 ? (a << 24) | 0x000000 : (a << 24) | 0xffffff; // little-endian ABGR: alpha, then black or white
    }
    this.ctx.putImageData(this.img, 0, 0);
  }
  /** CSS filter for the scene host */
  static filter(g: StyleTokens["grade"]): string {
    const f: string[] = [];
    if (Math.abs(g.contrast - 1) > 1e-3) f.push(`contrast(${g.contrast})`);
    if (Math.abs(g.saturation - 1) > 1e-3) f.push(`saturate(${g.saturation})`);
    return f.join(" ") || "none";
  }
}
