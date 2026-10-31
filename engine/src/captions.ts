// captions.ts — word-synchronised captions from the plan's phrases. The same phrases become the SRT, so on-screen text and the
// caption file cannot disagree. Words never include control text: they come from the aligned clean script.
import type { PlanCaption, StyleTokens } from "../../schema/video.schema";
import { h } from "./dom";

export interface Margins { top: number; bottom: number; left: number; right: number }
export class CaptionLayer {
  readonly el: HTMLElement;
  private box: HTMLElement;
  private cur = -1;
  private spans: HTMLElement[] = [];
  constructor(stage: HTMLElement, private caps: PlanCaption[], private tokens: StyleTokens, private W: number, private H: number, private safe: Margins) {
    this.el = h("div", { position: "absolute", left: "0", top: "0", width: "100%", height: "100%", pointerEvents: "none", zIndex: "30" });
    const c = tokens.caption;
    const px = c.sizeAt1080 * (Math.min(W, H) / 1080);
    const bottom = c.position === "center" ? (H - px * 2.6) / 2 : (c.position === "lower_third" ? safe.bottom + 0.08 : safe.bottom) * H;
    this.box = h("div", {
      position: "absolute", left: `${safe.left * W}px`, width: `${W * (1 - safe.left - safe.right)}px`, bottom: `${bottom}px`,
      textAlign: "center", fontFamily: `${tokens.fonts.body}, sans-serif`, fontWeight: "700", fontSize: `${px}px`, lineHeight: "1.22", color: tokens.palette.fg, opacity: "0", textWrap: "balance",
    } as any);
    if (c.style === "pill") Object.assign(this.box.style, { background: c.background ?? "rgba(0,0,0,0.55)", padding: `${px * 0.28}px ${px * 0.55}px`, borderRadius: `${px * 0.5}px`, width: "auto", left: "50%", transform: "translateX(-50%)", maxWidth: `${W * (1 - safe.left - safe.right)}px` });
    else Object.assign(this.box.style, { textShadow: `0 ${px * 0.04}px ${px * 0.16}px rgba(0,0,0,0.75), 0 0 ${px * 0.5}px rgba(0,0,0,0.35)` });
    this.el.append(this.box);
    stage.append(this.el);
  }
  /** returns the caption rect (frame px) when one is visible, for the layout check */
  update(t: number): { rect: DOMRect | null; text: string } {
    const i = this.caps.findIndex((c) => t >= c.startS - 0.02 && t <= c.endS + 0.28);
    if (i !== this.cur) {
      this.cur = i;
      this.box.textContent = "";
      this.spans = [];
      if (i >= 0) {
        this.caps[i].words.forEach((w, k) => {
          const sp = h("span", { display: "inline-block", whiteSpace: "pre" });
          sp.textContent = w.w + (k < this.caps[i].words.length - 1 ? " " : "");
          this.box.append(sp);
          this.spans.push(sp);
        });
      }
    }
    if (i < 0) { this.box.style.opacity = "0"; return { rect: null, text: "" }; }
    const c = this.caps[i];
    const fin = Math.min(1, Math.max(0, (t - c.startS + 0.02) / 0.1)), fout = Math.min(1, Math.max(0, (c.endS + 0.28 - t) / 0.12));
    this.box.style.opacity = String(Math.min(fin, fout));
    const hl = this.tokens.caption.highlight ?? this.tokens.palette.accent;
    const karaoke = this.tokens.caption.style === "karaoke";
    c.words.forEach((w, k) => {
      const sp = this.spans[k];
      const active = t >= w.s && t < (c.words[k + 1]?.s ?? c.endS + 0.28);
      sp.style.color = karaoke && active ? hl : this.tokens.palette.fg;
      sp.style.opacity = karaoke && t < w.s - 0.001 ? "0.62" : "1";
    });
    return { rect: this.box.getBoundingClientRect(), text: c.text };
  }
}
