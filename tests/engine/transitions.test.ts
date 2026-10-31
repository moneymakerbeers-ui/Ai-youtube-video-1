// Unit tests of the pure transition operators and the math under them (node:test, run with tsx). The renderer applies these functions to two retained
// scene views, so their invariants are what keeps a transition from popping, flashing or distorting the anchors, in 16:9 and in 9:16.
import test from "node:test";
import assert from "node:assert/strict";
import { transitionFx, maxZoom, type OpType, type TransitionCtx } from "../../engine/src/transitions";
import { makeEase, EASING_TOKENS, apply, mul, scaleAbout, translate, isIdentity, lerpLog, smoothstep, type Rect, type Mat } from "../../engine/src/math";

const OPS: OpType[] = ["dissolve", "match_geometry", "focus_bridge", "truthful_morph", "match_movement", "nested_scale", "occlusion_reveal", "depth_through_object"];
const LOCKED: OpType[] = ["match_geometry", "focus_bridge", "truthful_morph"];
const CLAMP: Record<string, [number, number]> = { match_geometry: [1 / 8, 8], truthful_morph: [1 / 8, 8], focus_bridge: [0.5, 2] }; // the size-ratio clamp of each locked operator
const FRAMES: [string, number, number][] = [["16:9", 1920, 1080], ["9:16", 1080, 1920]];
const ease = makeEase();
const near = (a: number, b: number, tol = 1e-6) => Math.abs(a - b) <= tol;
const scaleOf = (m: Mat) => Math.hypot(m[0], m[1]);
const ctx = (W: number, H: number, a: Rect | null, b: Rect | null, extra: Partial<TransitionCtx> = {}): TransitionCtx => ({ W, H, ease, easing: "standard", a, b, velocity: { x: 1, y: 0.3 }, ...extra });
const rects = (W: number, H: number): [string, Rect, Rect][] => [
  ["centre to centre, same size", { cx: W / 2, cy: H / 2, w: W * 0.3, h: H * 0.3 }, { cx: W / 2, cy: H / 2, w: W * 0.3, h: H * 0.3 }],
  ["travels and grows", { cx: W * 0.3, cy: H * 0.4, w: W * 0.2, h: H * 0.15 }, { cx: W * 0.65, cy: H * 0.55, w: W * 0.35, h: H * 0.3 }],
  ["travels and shrinks", { cx: W * 0.7, cy: H * 0.3, w: W * 0.4, h: H * 0.4 }, { cx: W * 0.25, cy: H * 0.7, w: W * 0.12, h: H * 0.1 }],
  ["near a corner", { cx: W * 0.9, cy: H * 0.9, w: W * 0.1, h: H * 0.1 }, { cx: W * 0.1, cy: H * 0.1, w: W * 0.2, h: H * 0.2 }],
  ["extreme ratio (clamped)", { cx: W * 0.5, cy: H * 0.5, w: W * 0.02, h: H * 0.02 }, { cx: W * 0.5, cy: H * 0.5, w: W * 0.9, h: H * 0.9 }],
];
const steps = Array.from({ length: 101 }, (_, i) => i / 100);

for (const [fname, W, H] of FRAMES) {
  for (const [rname, a, b] of rects(W, H)) {
    for (const op of OPS) {
      test(`${op} ${fname}: ${rname}`, () => {
        const fx = steps.map((p) => transitionFx(op, p, ctx(W, H, a, b)));
        // nothing falls back when both anchors exist
        assert.ok(fx.every((f) => f.usedType === op && !f.fellBack), "no silent fallback with both anchors present");
        // finite numbers, alphas in [0,1], matrices that keep orientation
        for (const f of fx) for (const s of [f.A, f.B]) {
          assert.ok(s.m.every(Number.isFinite), "finite matrix");
          assert.ok(scaleOf(s.m) > 0 && s.m[0] * s.m[3] - s.m[1] * s.m[2] > 0, "positive, orientation-keeping scale");
          for (const v of [s.back, s.content, s.anchor]) assert.ok(v >= -1e-9 && v <= 1 + 1e-9, `alpha ${v} within [0,1]`);
          assert.ok(Number.isFinite(s.blur) && s.blur >= 0);
        }
        // the window cannot pop at its edges: A untouched and fully there at p=0 ...
        const f0 = fx[0], f1 = fx[100];
        assert.ok(isIdentity(f0.A.m) && near(f0.A.back, 1) && near(f0.A.content, 1), "A untouched at p=0");
        // ... B untouched and fully there at p=1, A gone (or covered, for the reveal)
        assert.ok(isIdentity(f1.B.m) && near(f1.B.back, 1) && near(f1.B.content, 1), "B untouched at p=1");
        if (op === "occlusion_reveal") {
          const far = Math.max(Math.hypot(a.cx, a.cy), Math.hypot(W - a.cx, a.cy), Math.hypot(a.cx, H - a.cy), Math.hypot(W - a.cx, H - a.cy));
          assert.ok(f1.B.clip && f1.B.clip.r >= far && near(f1.B.clip.feather, 0, 1e-6) && f0.B.clip!.r === 0, "the reveal starts as nothing and ends covering the whole frame, with no feather left");
        } else {
          assert.ok(near(f1.A.back, 0) && near(f1.A.content, 0), "A gone at p=1");
        }
        // A only ever fades out, B only ever fades in
        for (let i = 1; i < fx.length; i++) {
          assert.ok(fx[i].A.back <= fx[i - 1].A.back + 1e-9 && fx[i].A.content <= fx[i - 1].A.content + 1e-9, `A never reappears (p=${steps[i]})`);
          assert.ok(fx[i].B.back >= fx[i - 1].B.back - 1e-9 && fx[i].B.content >= fx[i - 1].B.content - 1e-9, `B never fades back out (p=${steps[i]})`);
        }
        if (LOCKED.includes(op)) {
          // the two anchors coincide for the whole window, in position and in drawn size, and travel the straight line
          let prevW = a.w;
          for (let i = 0; i < fx.length; i++) {
            const [ax, ay] = apply(fx[i].A.m, a.cx, a.cy), [bx, by] = apply(fx[i].B.m, b.cx, b.cy);
            assert.ok(near(ax, bx, 1e-6) && near(ay, by, 1e-6), `anchors locked at p=${steps[i]}`);
            const [lo, hi] = CLAMP[op], within = b.w / a.w >= lo && b.w / a.w <= hi;
            if (within) assert.ok(near(scaleOf(fx[i].A.m) * a.w, scaleOf(fx[i].B.m) * b.w, 1e-6 * W), `drawn anchor widths agree at p=${steps[i]}`);
            // beyond the clamp the sizes cannot match (make_plan warns), but the worlds never scale past the clamp
            for (const s of [fx[i].A, fx[i].B]) assert.ok(scaleOf(s.m) <= hi + 1e-9 && scaleOf(s.m) >= 1 / hi - 1e-9, "world scale stays inside the clamp");
            const cross = (ax - a.cx) * (b.cy - a.cy) - (ay - a.cy) * (b.cx - a.cx);
            assert.ok(Math.abs(cross) <= 1e-6 * W * W, "the anchor stays on the straight line between its two rest positions");
            const w = scaleOf(fx[i].A.m) * a.w;
            const dir = Math.sign(Math.log(Math.min(Math.max(b.w / a.w, lo), hi)));
            assert.ok(dir === 0 || (w - prevW) * dir >= -1e-6, "anchor size changes monotonically");
            prevW = w;
          }
        }
        if (op === "nested_scale") assert.ok(near(scaleOf(fx[100].A.m), maxZoom(op, a, W, H), 1e-6 * maxZoom(op, a, W, H)), "the camera ends at exactly maxZoom");
      });
    }
  }
  test(`anchored operators fall back to dissolve when an anchor is missing (${fname})`, () => {
    const a: Rect = { cx: W / 2, cy: H / 2, w: W / 4, h: H / 4 };
    for (const op of OPS.filter((o) => o !== "dissolve" && o !== "match_movement")) {
      const f = transitionFx(op, 0.5, ctx(W, H, null, null));
      assert.ok(f.usedType === "dissolve" && f.fellBack, `${op} without anchors reports its fallback`);
    }
    assert.ok(!transitionFx("match_movement", 0.5, ctx(W, H, null, null)).fellBack, "match_movement moves with the outgoing scene's velocity and needs no anchor rectangle");
    for (const op of LOCKED) assert.ok(transitionFx(op, 0.5, ctx(W, H, a, null)).fellBack, `${op} needs both anchors`);
    assert.ok(!transitionFx("occlusion_reveal", 0.5, ctx(W, H, a, null)).fellBack, "operators that need one anchor keep working with one");
  });
}

test("easing tokens start at 0, end at 1 and never run backwards", () => {
  for (const name of Object.keys(EASING_TOKENS)) {
    let prev = ease(name, 0);
    assert.ok(near(prev, 0, 1e-9) && near(ease(name, 1), 1, 1e-9), `${name} endpoints`);
    for (let i = 1; i <= 200; i++) { const v = ease(name, i / 200); assert.ok(v >= prev - 1e-9, `${name} monotone at ${i / 200}`); prev = v; }
  }
});

test("matrix helpers: scaleAbout keeps its centre, mul composes right to left, lerpLog is geometric", () => {
  const m = scaleAbout(100, 50, 2.5);
  const [x, y] = apply(m, 100, 50);
  assert.ok(near(x, 100) && near(y, 50));
  const t = mul(translate(10, 0), scaleAbout(0, 0, 2));
  assert.deepEqual(apply(t, 1, 0), [12, 0]); // scale first, then translate
  assert.ok(near(lerpLog(2, 8, 0.5), 4) && near(lerpLog(2, 8, 0), 2) && near(lerpLog(2, 8, 1), 8));
  assert.ok(smoothstep(0.2, 0.8, 0) === 0 && smoothstep(0.2, 0.8, 1) === 1 && near(smoothstep(0.2, 0.8, 0.5), 0.5));
});
