// schema/video.schema.ts — typed contracts for the Universal YouTube Production System (v3).
// Zod 3.x. Types come from z.infer, so the JSON files, the render engine (engine/src, which imports only the
// TYPES from here) and the stage prompts cannot drift apart. Validate with:
//   npx tsx schema/validate.ts <config|facts|scenes|shorts|manifest|state|tokens|plan|alignment|findings|ledger|evidence-review|shorts-review> <file>
//   npx tsx schema/validate.ts project videos/<slug> [--strict]      (every file + the cross-file rules)
//   npx tsx schema/validate.ts selftest
import { z } from "zod";

export const SCHEMA_VERSION = 1;

/* ───────────────────────── primitives ───────────────────────── */
export const Id = z.string().regex(/^[A-Za-z0-9_-]+$/, "ids use letters, digits, _ and - only");
const Ms = z.number().int().min(0).max(10_000);
const Unit = z.number().min(-0.5).max(1.5); // normalised frame coordinate; 0..1 is inside the frame
const Intensity = z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3)]);

/* ───────────────────────── run configuration ─────────────────────────
   Only videoIdea comes from the creator. Everything else has a default (CLAUDE.md §9). */
export const RunConfig = z
  .object({
    videoIdea: z.string().min(3),
    // production = the real thing (long video at least 5:00 + Shorts). test_clip = a deliberate short test the creator asked for;
    // smoke = the system's own end-to-end check. Only these two may be shorter than 5:00, and every report says which one it was.
    purpose: z.enum(["production", "test_clip", "smoke"]).default("production"),
    language: z.string().default("en-US"),
    targetDurationMin: z.tuple([z.number().min(0.25), z.number().max(15)]).default([6, 9]), // minutes; a production video is never under 5
    audience: z.string().default("general English-speaking viewers (mostly US); suitable for all ages"),
    creativeStyle: z.string().default("auto"), // "auto" | preset name | free text
    voiceProfile: z.string().default("auto"),
    // the narrator for the paid stack, stored once per video so /make never depends on a command-line flag (tools/voice_direction.py resolves it)
    voice: z.object({ elevenlabs: z.object({ voiceId: z.string().min(8), model: z.string().default("eleven_multilingual_v2"), baseSettings: z.record(z.string(), z.union([z.number(), z.boolean()])).optional() }).optional() }).optional(),
    budgetMode: z.enum(["LOW_COST", "BALANCED", "QUALITY_FIRST"]).default("LOW_COST"), // changes allocation, never the ceiling
    maxPaidSpend: z
      .object({
        higgsfieldCredits: z.number().min(0).default(15),
        higgsfieldCeilingRaisedByCreator: z.boolean().default(false),
        elevenlabsChars: z.number().int().min(0).nullable().default(null), // null = size from the script, show at the Spend Gate
        otherUsd: z.number().min(0).default(0),
      })
      .default({}),
    outputResolution: z.enum(["1080p", "1440p", "2160p"]).default("1080p"),
    fps: z.union([z.literal("auto"), z.literal(30), z.literal(60)]).default("auto"), // auto = 30; 60 only when asked (the report shows the measured ms/frame)
    shortsTarget: z.tuple([z.number().int().min(1), z.number().int().max(8)]).default([4, 5]),
    researchDepth: z.enum(["standard", "deep"]).default("standard"),
    sensitivity: z.enum(["normal", "care", "high"]).default("normal"), // set in stage 01; the creator may force it
    // "required": tools/pipeline.py refuses to run until the creator approved the creative preview (tools/preview.py) for the current look, voice direction and scene structure
    previewGate: z.enum(["required", "off"]).default("off"),
  })
  .superRefine((c, ctx) => {
    if (c.purpose === "production" && c.targetDurationMin[0] < 5) ctx.addIssue({ code: "custom", path: ["targetDurationMin"], message: "a production video is never under 5:00 (use purpose \"test_clip\" only for a short test the creator asked for)" });
    const m = c.maxPaidSpend;
    if (m.higgsfieldCredits > 20 && !m.higgsfieldCeilingRaisedByCreator)
      ctx.addIssue({ code: "custom", path: ["maxPaidSpend", "higgsfieldCredits"], message: "above 20 credits only if the creator raised the ceiling in this run" });
  });
export type RunConfig = z.infer<typeof RunConfig>;

/* ───────────────────────── facts ─────────────────────────
   A source label proves nothing by itself. Each claim therefore carries evidence pointers: where in which saved
   snapshot the supporting passage is, the exact quote, and how it supports the claim. tools/check_evidence.py verifies
   mechanically that the snapshot exists, its hash matches and the quote really occurs in it; an independent reviewer
   (stage 01, see review/evidence-review.json) judges whether the quote supports the claim. */
export const Evidence = z
  .object({
    sourceIndex: z.number().int().min(0), // index into claim.sources
    locator: z.object({ kind: z.enum(["quote", "page", "section", "table", "dataset", "timestamp"]), value: z.string().min(1) }),
    quote: z.string().min(12).max(400).optional(), // EXACT text from the snapshot (required for text sources)
    snapshot: z.string().min(1), // project-relative path of the saved page text / file (research/sources/<id>.txt)
    snapshotSha256: z.string().regex(/^[a-f0-9]{64}$/),
    // how the snapshot text was obtained. "raw": the bytes the server sent. "extracted": text pulled out of those bytes by a tool.
    // "model_processed": text a language model returned about the page (a fetch tool that summarises is this): a quote found in it proves
    // only that the model produced that sentence, so the checker asks a human to confirm it at the URL.
    snapshotKind: z.enum(["raw", "extracted", "model_processed"]).default("raw"),
    published: z.string().optional(),
    supports: z.enum(["direct", "partial", "context"]),
    interpretation: z.string().min(10), // how the passage supports (or only partly supports) the claim
    uncertainty: z.enum(["none", "minor", "significant"]).default("none"),
  })
  .superRefine((e, ctx) => {
    if (e.locator.kind === "quote" && !e.quote) ctx.addIssue({ code: "custom", path: ["quote"], message: "a quote locator needs the exact quote" });
  });
export const Claim = z
  .object({
    id: Id,
    text: z.string().min(5),
    spokenWording: z.string().optional(),
    sources: z.array(
      z.object({
        title: z.string(),
        url: z.string().url().optional(),
        type: z.enum(["primary", "peer_reviewed", "institution", "textbook", "reference", "news", "other"]),
        accessed: z.string(), // ISO date
      })
    ),
    evidence: z.array(Evidence).default([]),
    status: z.enum(["verified", "single_source", "contested", "unverified"]),
    note: z.string().optional(),
  })
  .superRefine((c, ctx) => {
    const strong = c.sources.some((s) => ["primary", "peer_reviewed", "institution"].includes(s.type));
    if (c.status === "verified" && !(c.sources.length >= 2 || strong))
      ctx.addIssue({ code: "custom", path: ["status"], message: "verified = 2+ independent sources or 1 primary/peer-reviewed/institutional source" });
    if (c.status === "verified" && !c.evidence.some((e) => e.supports === "direct"))
      ctx.addIssue({ code: "custom", path: ["evidence"], message: "verified needs at least one evidence pointer that supports the claim directly" });
    if (c.status !== "unverified" && c.sources.length === 0)
      ctx.addIssue({ code: "custom", path: ["sources"], message: "only unverified claims may have no source" });
    c.evidence.forEach((e, i) => {
      if (e.sourceIndex >= c.sources.length) ctx.addIssue({ code: "custom", path: ["evidence", i, "sourceIndex"], message: "sourceIndex points past the sources list" });
    });
  });
export const FactsFile = z.object({ claims: z.array(Claim) });

/* ───────────────────────── voice (identity stays fixed; performance varies per scene) ───────────────────────── */
export const VoiceDirection = z.object({
  intent: z.string(), // what this line must do for the viewer
  emotion: z.string().default("neutral-clear"), // vocabulary in reference/voice-direction.md
  intensity: Intensity.default(0), // 0 plain · 1 gentle colour · 2 clearly expressive · 3 peak (rare)
  pace: z.enum(["slower", "steady", "faster"]).default("steady"),
  emphasisWords: z.array(z.string()).default([]),
  pauseBeforeMs: Ms.default(0),
  pauseAfterMs: Ms.default(0),
  deliveryNotes: z.string().optional(),
  pronunciation: z.array(z.object({ word: z.string(), say: z.string() })).default([]), // TTS-only respellings
  takeId: z.string().optional(), // filled by stage 03
});

/* ───────────────────────── transitions ───────────────────────── */
export const TransitionType = z.enum([
  "cut",
  "dissolve",
  "match_geometry",
  "match_movement",
  "nested_scale",
  "occlusion_reveal",
  "depth_through_object",
  "focus_bridge",
  "truthful_morph",
]);
const Anchor = z.object({ entityId: Id, x: z.number().min(0).max(1).default(0.5), y: z.number().min(0).max(1).default(0.5) });
export const Transition = z.object({
  type: TransitionType,
  rationale: z.string().optional(), // required for anything except cut/dissolve
  anchorFrom: Anchor.optional(), // entity in THIS scene
  anchorTo: Anchor.optional(), // entity in the NEXT scene
  durationMs: z.number().int().min(0).max(4000).default(0), // 0 = the default for the type (reference/transition-grammar.md)
  offsetMs: z.number().int().min(-2000).max(2000).default(0), // shifts the window off the scene boundary (centred by default) to land on a cue word
  easing: z.enum(["standard", "emphasized", "soft"]).default("standard"), // never linear
  fallback: TransitionType.default("dissolve"), // applied automatically if the transition gate fails
  downgradedFrom: TransitionType.optional(), // stage 04 writes the originally planned type here when a gate forced a fallback
});
const NEEDS_ANCHORS: string[] = ["match_geometry", "match_movement", "nested_scale", "occlusion_reveal", "depth_through_object", "focus_bridge", "truthful_morph"];

/* ───────────────────────── scene graph: semantic entities + two authored layouts ───────────────────────── */
export const EnterStyle = z.enum(["none", "fade", "rise", "pop", "draw"]);
export const Entity = z.object({
  id: Id,
  role: z.enum(["subject", "context", "label", "number", "diagram", "backdrop", "decor"]),
  assetId: Id.optional(), // an asset from assets/manifest.json (image or svg); omitted until stage 02 resolves it
  visual: z.object({ component: Id, props: z.record(z.string(), z.unknown()).default({}) }).optional(), // a code-drawn visual: engine/src/visuals or videos/<slug>/visuals
  need: z.string().optional(), // stage 01: what the visual must show (abstract, no file names)
  text: z.string().max(40).optional(), // labels/numbers are text in code, never drawn into images
  enter: z.object({ style: EnterStyle.default("fade"), durationMs: z.number().int().min(0).max(3000).default(500) }).optional(),
  enterAtWord: z.number().int().min(0).optional(), // scene-relative word index; timing source is alignment.json
  exitAtWord: z.number().int().min(0).optional(), // scene-relative word index; the entity fades out at this word
});
export const Placement = z.object({
  x: Unit, y: Unit, w: z.number().positive().max(3), // centre and width, normalised to the frame
  rotate: z.number().default(0),
  z: z.number().int().default(0),
  depth: z.number().min(0).max(1).default(0), // parallax: 0 near … 1 far
});
const View = z.object({ x: z.number(), y: z.number(), scale: z.number().positive() });
export const CameraMove = z.object({
  from: View,
  to: View,
  startWord: z.number().int().min(0).optional(),
  endWord: z.number().int().min(0).optional(),
  easing: z.enum(["standard", "emphasized", "soft"]).default("emphasized"),
  reason: z.string().min(8), // what the movement explains or reveals; no reason, no move
});
export const Layout = z.object({
  placements: z.record(z.string(), Placement),
  camera: z.array(CameraMove).default([]), // empty = no camera move
  hold: z.object({ reason: z.string().min(8) }).optional(), // a DELIBERATE still hold (the only thing that authorises a frozen-frame window in QA); omitted = stillness is not planned
  notes: z.string().optional(),
});

export const QaRisk = z.enum(["morph_geometry", "text_safe_area", "planned_hold", "fast_motion", "low_contrast", "aspect_recompose", "sensitive_content", "audio_sync"]);

export const Scene = z
  .object({
    id: Id,
    section: Id,
    claimIds: z.array(Id).default([]),
    narration: z.string().min(1), // spoken words only: no tags, no stage directions
    intent: z.string(), // what the viewer must understand, feel or anticipate
    retentionBeat: z.enum(["promise", "orient", "develop", "evidence", "payoff", "settle", "next_question"]),
    presentation: z.enum(["illustration", "footage", "archival", "diagram", "text", "three_d", "comparison", "no_change"]),
    visualIntensity: z.union([z.literal(1), z.literal(2), z.literal(3)]).default(1),
    look: z.string().optional(), // a named look variant from style-tokens.json (a deliberate colour-script shift); omitted = the base look
    signature: z.object({ before: z.string(), after: z.string(), track: z.string() }).optional(), // required at level 3
    transition: Transition.default({ type: "cut" }), // into the NEXT scene
    voice: VoiceDirection,
    entities: z.array(Entity),
    layouts: z.object({ landscape: Layout, portrait: Layout.optional() }),
    shortIds: z.array(Id).default([]),
    assetIds: z.array(Id).default([]),
    qaRisk: z.array(QaRisk).default([]),
    timing: z.object({ startS: z.number().min(0), endS: z.number().min(0), firstWord: z.number().int(), lastWord: z.number().int() }).optional(), // stage 03
  })
  .superRefine((s, ctx) => {
    const bad = (path: (string | number)[], message: string) => ctx.addIssue({ code: "custom", path, message });
    const ids = s.entities.map((e) => e.id);
    if (new Set(ids).size !== ids.length) bad(["entities"], "entity ids must be unique within a scene");
    for (const [name, layout] of Object.entries(s.layouts))
      for (const k of Object.keys(layout?.placements ?? {})) if (!ids.includes(k)) bad(["layouts", name, "placements", k], "placement refers to an unknown entity");
    if (s.shortIds.length && !s.layouts.portrait) bad(["layouts", "portrait"], "a scene used by a Short needs an explicit portrait layout");
    if ((s.retentionBeat === "evidence" || s.retentionBeat === "payoff") && s.claimIds.length === 0) bad(["claimIds"], "evidence and payoff beats must cite claim IDs");
    if (!["cut", "dissolve"].includes(s.transition.type) && !(s.transition.rationale && s.transition.rationale.length >= 15))
      bad(["transition", "rationale"], "anything beyond a cut or dissolve needs a narrative reason (15+ characters)");
    if (NEEDS_ANCHORS.includes(s.transition.type) && !(s.transition.anchorFrom && s.transition.anchorTo)) bad(["transition"], "this transition type needs anchorFrom and anchorTo");
    if (s.transition.anchorFrom && !ids.includes(s.transition.anchorFrom.entityId)) bad(["transition", "anchorFrom"], "anchorFrom must be an entity of this scene");
    if (s.visualIntensity === 3 && !s.signature) bad(["signature"], "level-3 moments need before/after/track (what changes, and what the viewer follows)");
  });
export type Scene = z.infer<typeof Scene>;
// opening/ending are the ONLY things that authorise black frames or lead/tail silence at the file edges.
export const ScenesFile = z.object({
  schemaVersion: z.literal(SCHEMA_VERSION).default(SCHEMA_VERSION),
  fps: z.number().int().min(24).max(60).default(30),
  opening: z.object({ fadeInMs: z.number().int().min(0).max(3000).default(0), leadSilenceMs: z.number().int().min(0).max(3000).default(0) }).default({}),
  ending: z.object({ fadeOutMs: z.number().int().min(0).max(3000).default(0), holdBlackMs: z.number().int().min(0).max(3000).default(0), tailSilenceMs: z.number().int().min(0).max(5000).default(0) }).default({}),
  scenes: z.array(Scene).min(1),
});

/* ───────────────────────── Shorts: planned at outline time, validated before production ───────────────────────── */
export const ShortValidation = z.object({
  independentOpening: z.boolean(),
  oneQuestion: z.boolean(),
  minimumContext: z.boolean(),
  completeExplanation: z.boolean(),
  cleanPayoff: z.boolean(),
  sourceLinked: z.boolean(),
  deltaDefined: z.boolean(),
});
export const ShortPlan = z
  .object({
    id: Id,
    status: z.enum(["candidate", "validated", "rejected"]),
    title: z.string().max(60),
    question: z.string().max(140), // the one tension a brand-new viewer can feel
    minimumContext: z.array(z.string()).max(3),
    payoff: z.string(),
    sceneIds: z.array(Id).min(1), // source scenes in the long video (in order)
    delta: z.object({ openingLine: z.string().optional(), closingLine: z.string().optional(), portraitRestage: z.string().optional(), addedVisual: z.string().optional() }),
    targetDurationS: z.number().min(10).max(180), // prefer 35–60; eligible Shorts may run to 180
    validation: ShortValidation,
    rejectedReason: z.string().optional(),
  })
  .superRefine((p, ctx) => {
    if (p.status === "validated" && !Object.values(p.validation).every(Boolean)) ctx.addIssue({ code: "custom", path: ["validation"], message: "validated Shorts pass all seven checks" });
    if (p.status === "rejected" && !p.rejectedReason) ctx.addIssue({ code: "custom", path: ["rejectedReason"], message: "say why it was rejected" });
  });
export const ShortsFile = z.object({ shorts: z.array(ShortPlan) });

/* ───────────────────────── assets ───────────────────────── */
export const Asset = z
  .object({
    id: Id,
    kind: z.enum(["svg", "image", "video", "audio", "font", "data"]),
    file: z.string(),
    route: z.enum(["code", "retrieved", "generated_image", "generated_video", "reused"]),
    provenance: z.object({ tool: z.string().optional(), model: z.string().optional(), prompt: z.string().optional(), jobId: z.string().optional(), sourceUrl: z.string().optional() }).default({}),
    license: z.object({ name: z.string(), url: z.string().optional(), attribution: z.string().optional(), evidenceFile: z.string().optional() }).optional(),
    creditsSpent: z.number().min(0).default(0),
    width: z.number().int().optional(),
    height: z.number().int().optional(),
    hasAlpha: z.boolean().optional(),
    focal: z.object({ x: z.number().min(0).max(1), y: z.number().min(0).max(1) }).optional(), // where to keep the eye when cropping
    usedBy: z.array(Id).default([]),
  })
  .superRefine((a, ctx) => {
    if (a.route === "retrieved" && !(a.license && a.license.evidenceFile)) ctx.addIssue({ code: "custom", path: ["license"], message: "retrieved assets need license evidence saved in the project" });
    if (a.route.startsWith("generated") && !(a.provenance.tool && a.provenance.prompt)) ctx.addIssue({ code: "custom", path: ["provenance"], message: "generated assets need tool + prompt" });
    if (a.route !== "generated_image" && a.route !== "generated_video" && a.creditsSpent > 0) ctx.addIssue({ code: "custom", path: ["creditsSpent"], message: "only generated assets spend credits" });
  });
export const ManifestFile = z.object({ assets: z.array(Asset) });

/* ───────────────────────── state: the resumable checkpoint ───────────────────────── */
export const STAGES = ["00-preflight", "01-research-script", "02-assets", "03-voice", "04-motion", "05-render-shorts", "06-package-review"] as const;
// the verdict of the gates on one delivered file, as tools/report.py words it. PASSED means no check found a defect; it never means "good".
export const ProductionStatus = z.enum(["BLOCKED", "FAILED", "PASSED", "NOT RUN"]);
export const State = z.object({
  slug: Id,
  idea: z.string(),
  stages: z.record(
    z.string(),
    z.object({
      status: z.enum(["pending", "in_progress", "done", "blocked", "failed"]),
      step: z.string().optional(),
      at: z.string().optional(),
      evidence: z.array(z.string()).default([]),
      note: z.string().optional(),
    })
  ),
  // One gate screen, but approval is recorded PER SERVICE: Higgsfield credits, ElevenLabs characters, music/stock licences and
  // compute are different currencies. A service without an approved entry cannot be called (tools/paidcall.py refuses).
  spendGate: z.object({
    status: z.enum(["not_reached", "pending", "approved", "declined"]),
    approvedAt: z.string().optional(),
    ceiling: z.object({ higgsfieldCredits: z.number(), elevenlabsChars: z.number().nullable(), otherUsd: z.number() }).optional(),
    services: z.record(z.string(), z.object({ approved: z.boolean(), ceiling: z.number().min(0), unit: z.string(), quote: z.string().optional(), note: z.string().optional() })).default({}),
  }),
  ledger: z.object({ higgsfieldCredits: z.number().default(0), elevenlabsChars: z.number().default(0), otherUsd: z.number().default(0) }),
  engine: z.object({ backend: z.enum(["browser"]).default("browser"), smokeTestedAt: z.string().optional(), engineHash: z.string().optional() }).optional(),
  deliverables: z.record(z.string(), ProductionStatus).default({}), // e.g. { "long": "PASSED", "S01": "FAILED" }
  blocked: z.array(z.string()).default([]),
});

/* ───────────────────────── style tokens (style-tokens.json, written in stage 02, read by the engine) ───────────────────────── */
const Margins = z.object({ top: z.number().min(0).max(0.4), bottom: z.number().min(0).max(0.4), left: z.number().min(0).max(0.4), right: z.number().min(0).max(0.4) });
export const Palette = z.object({ bg: z.string(), bg2: z.string().optional(), fg: z.string(), muted: z.string(), accent: z.string(), accent2: z.string().optional(), warn: z.string().optional(), line: z.string().optional() });
export const StyleTokens = z.object({
  name: z.string(),
  palette: Palette,
  looks: z.record(z.string(), Palette.partial()).default({}), // deliberate colour-script variants selected by scene.look
  fonts: z.object({
    display: z.string(),
    body: z.string(),
    mono: z.string().optional(),
    files: z.array(z.object({ family: z.string(), file: z.string(), weight: z.number().int().default(400), style: z.enum(["normal", "italic"]).default("normal") })).default([]),
  }),
  type: z.object({ minPxAt1080: z.number().default(48), labelMaxPx: z.number().default(120), numberMaxPx: z.number().default(220) }).default({}),
  caption: z.object({ style: z.enum(["plain", "pill", "karaoke"]).default("karaoke"), position: z.enum(["bottom", "lower_third", "center"]).default("bottom"), sizeAt1080: z.number().default(54), maxWords: z.number().int().min(3).max(12).default(7), highlight: z.string().optional(), background: z.string().optional() }).default({}),
  grade: z.object({ contrast: z.number().default(1), saturation: z.number().default(1), vignette: z.number().min(0).max(1).default(0.25), grain: z.number().min(0).max(0.2).default(0.02), grainFps: z.number().min(0).max(30).default(0), tint: z.string().optional(), tintOpacity: z.number().min(0).max(0.5).default(0) }).default({}),
  motion: z.object({ easing: z.record(z.string(), z.tuple([z.number(), z.number(), z.number(), z.number()])).default({}), enterMs: z.number().int().default(500) }).default({}),
  safe: z
    .object({
      portrait: Margins.default({ top: 0.08, bottom: 0.18, left: 0.06, right: 0.12 }), // engineering defaults, not platform specs
      landscape: Margins.default({ top: 0.05, bottom: 0.08, left: 0.05, right: 0.05 }),
    })
    .default({}),
});

/* ───────────────────────── alignment: word times measured on the FINAL audio file ───────────────────────── */
export const Sha = z.string().regex(/^[a-f0-9]{64}$/);
export const AlignWord = z.object({ i: z.number().int().min(0), w: z.string(), s: z.number().min(0), e: z.number().min(0), scene: Id.optional(), conf: z.number().min(0).max(1).optional() });
export const Alignment = z
  .object({
    version: z.literal(1),
    source: z.enum(["elevenlabs_forced", "whisper", "dtw_reference"]), // "estimated" timing is not an alignment and is never accepted for finals
    audio: z.object({ file: z.string(), sha256: Sha, durationS: z.number().positive() }), // the exact file that was measured
    script: z.object({ file: z.string(), sha256: Sha }),
    coverage: z.number().min(0).max(1),
    words: z.array(AlignWord).min(1),
    sceneBounds: z.array(z.object({ sceneId: Id, startS: z.number().min(0), endS: z.number().min(0), firstWord: z.number().int(), lastWord: z.number().int() })).default([]),
    quality: z.object({ medianConf: z.number().optional(), notes: z.array(z.string()).default([]) }).optional(),
  })
  .superRefine((a, ctx) => {
    let prev = -1;
    a.words.forEach((w, i) => {
      if (w.e < w.s) ctx.addIssue({ code: "custom", path: ["words", i], message: "word ends before it starts" });
      if (w.s < prev - 1e-6) ctx.addIssue({ code: "custom", path: ["words", i, "s"], message: "word times are not monotonic" });
      if (w.e > a.audio.durationS + 0.05) ctx.addIssue({ code: "custom", path: ["words", i, "e"], message: "word ends after the audio file ends" });
      prev = w.s;
    });
  });

/* ───────────────────────── render plan: every derived time, one file per output (long, S01, …) ───────────────────────── */
const EasingName = z.enum(["standard", "emphasized", "soft"]);
export const PlanTransition = z.object({
  type: TransitionType,
  startS: z.number().min(0),
  endS: z.number().min(0),
  anchorFrom: Anchor.optional(),
  anchorTo: Anchor.optional(),
  easing: EasingName,
  rationale: z.string().optional(),
  downgradedFrom: TransitionType.optional(),
});
export const PlanScene = z.object({
  id: Id,
  startS: z.number().min(0),
  endS: z.number().min(0),
  layout: z.enum(["landscape", "portrait"]),
  look: z.string().optional(),
  entities: z.array(z.object({ id: Id, enterS: z.number().min(0), exitS: z.number().nullable().default(null), enterStyle: z.enum(["none", "fade", "rise", "pop", "draw"]).default("fade"), enterMs: z.number().min(0).default(0), motion: z.object({ kind: z.literal("continuous"), fromS: z.number().min(0), toS: z.number().min(0) }).optional(), viaTransition: z.boolean().default(false) })),
  camera: z.array(z.object({ fromS: z.number(), toS: z.number(), from: View, to: View, easing: EasingName })).default([]),
  hold: z.object({ fromS: z.number(), toS: z.number(), reason: z.string() }).optional(),
  transitionOut: PlanTransition.optional(),
});
export const PlanCaption = z.object({ startS: z.number().min(0), endS: z.number().min(0), text: z.string(), words: z.array(z.object({ w: z.string(), s: z.number(), e: z.number() })) });
export const RenderPlan = z.object({
  version: z.literal(1),
  target: Id, // "long", "S01", "preview-long" …
  layout: z.enum(["landscape", "portrait"]),
  fps: z.number().int().min(24).max(60),
  width: z.number().int().min(160),
  height: z.number().int().min(160),
  durationS: z.number().positive(),
  durationFrames: z.number().int().positive(),
  timingSource: z.enum(["alignment", "estimated"]), // "estimated" is allowed only in previews
  pictureRegion: z.object({ x: z.number(), y: z.number(), w: z.number(), h: z.number() }).nullable().optional(), // the caption-free part of the frame (stillness is measured there)
  audio: z.object({ file: z.string(), sha256: Sha, durationS: z.number() }).nullable(),
  opening: z.object({ fadeInMs: z.number().int().default(0), leadSilenceMs: z.number().int().default(0) }),
  ending: z.object({ fadeOutMs: z.number().int().default(0), holdBlackMs: z.number().int().default(0), tailSilenceMs: z.number().int().default(0) }),
  scenes: z.array(PlanScene).min(1),
  words: z.array(z.object({ i: z.number().int(), w: z.string(), s: z.number(), e: z.number(), sceneId: Id })),
  captions: z.array(PlanCaption),
  silences: z.array(z.object({ fromS: z.number(), toS: z.number(), reason: z.string() })).default([]), // the planned silences (declared pauses, lead and tail), nothing else is allowed
  warnings: z.array(z.string()).default([]),
});

/* ───────────────────────── review artefacts: independent checks that sit on top of schema validity ───────────────────────── */
const Reviewer = z.object({ kind: z.enum(["independent_agent", "human", "same_session"]), note: z.string().optional() }); // same_session is allowed but never counts as independent
export const EvidenceReview = z.object({
  reviewedAt: z.string(),
  reviewer: Reviewer,
  verdicts: z.array(z.object({ claimId: Id, verdict: z.enum(["supported", "partial", "unsupported"]), reason: z.string().min(8) })),
});
export const ShortsReview = z.object({
  reviewedAt: z.string(),
  reviewer: Reviewer,
  verdicts: z.array(
    z.object({
      shortId: Id,
      verdict: z.enum(["pass", "revise", "reject"]),
      standalone: z.boolean(), // would a viewer who has seen nothing else understand it?
      problems: z.array(z.object({ quote: z.string(), problem: z.string(), fix: z.string() })).default([]),
    })
  ),
});
export const Finding = z.object({
  issue_id: Id,
  affected: z.string(), // file, scene id or time range
  evidence: z.string(), // reproducible: command + output excerpt, file path, or a frame time
  severity: z.enum(["blocker", "major", "minor", "info"]),
  kind: z.enum(["machine", "inspected", "human_needed"]), // machine = a tool measured it; inspected = Claude looked at frames/audio data; human_needed = taste, ear, phone
  status: z.enum(["open", "fixed", "waived", "wontfix"]),
  attemptedFix: z.string().optional(),
  verifiedOutcome: z.string().optional(),
  at: z.string(),
});
export const LedgerEntry = z.object({
  ts: z.string(),
  key: z.string().min(1), // idempotency key, e.g. "higgsfield:hero_01" or "elevenlabs:take_03"
  service: z.string().min(1),
  status: z.enum(["intent", "submitted", "done", "failed"]),
  unit: z.string(), // "credits" | "chars" | "usd"
  estimate: z.number().min(0),
  actual: z.number().min(0).optional(),
  jobId: z.string().optional(), // the provider's job id: a resume queries it instead of paying again
  file: z.string().optional(),
  attempt: z.number().int().min(1).default(1),
  note: z.string().optional(),
});

/* ───────────────────────── inferred types (the engine imports these as types only) ───────────────────────── */
export type Layout = z.infer<typeof Layout>;
export type Placement = z.infer<typeof Placement>;
export type Entity = z.infer<typeof Entity>;
export type Asset = z.infer<typeof Asset>;
export type StyleTokens = z.infer<typeof StyleTokens>;
export type Palette = z.infer<typeof Palette>;
export type RenderPlan = z.infer<typeof RenderPlan>;
export type PlanScene = z.infer<typeof PlanScene>;
export type PlanTransition = z.infer<typeof PlanTransition>;
export type PlanCaption = z.infer<typeof PlanCaption>;
export type ManifestFile = z.infer<typeof ManifestFile>;
export type FactsFile = z.infer<typeof FactsFile>;
export type ShortsFile = z.infer<typeof ShortsFile>;
export type Alignment = z.infer<typeof Alignment>;
export type ScenesFile = z.infer<typeof ScenesFile>;
export type TransitionType = z.infer<typeof TransitionType>;

/* ───────────────────────── cross-file checks (what a per-file schema cannot see) ───────────────────────── */
export type Project = {
  config?: z.infer<typeof RunConfig>;
  facts: z.infer<typeof FactsFile>;
  scenes: z.infer<typeof ScenesFile>;
  shorts?: z.infer<typeof ShortsFile>;
  manifest?: z.infer<typeof ManifestFile>;
  evidenceReview?: z.infer<typeof EvidenceReview>;
  shortsReview?: z.infer<typeof ShortsReview>;
  strict?: boolean; // stage 06: reviews are mandatory and entities must have content
};
export function checkProject(p: Project): { errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];
  const claims = new Map(p.facts.claims.map((c) => [c.id, c]));
  const assets = new Set((p.manifest?.assets ?? []).map((a) => a.id));
  const sceneIds = p.scenes.scenes.map((s) => s.id);
  if (new Set(sceneIds).size !== sceneIds.length) errors.push("scene ids are not unique");
  const cap = p.config ? { normal: 3, care: 2, high: 1 }[p.config.sensitivity] : 3;

  p.scenes.scenes.forEach((s, i) => {
    for (const id of s.claimIds) {
      const c = claims.get(id);
      if (!c) errors.push(`${s.id}: unknown claim ${id}`);
      else if (c.status === "unverified") errors.push(`${s.id}: claim ${id} is unverified and may not be narrated`);
      else if (c.status === "single_source") warnings.push(`${s.id}: claim ${id} has a single source`);
      else if (c.status === "contested") warnings.push(`${s.id}: claim ${id} is contested; wording must be hedged`);
    }
    // checked whether or not a manifest exists: a reference to an asset that nothing defines is an error, never silently skipped
    const noManifest = p.manifest ? "" : " (the project has no assets/manifest.json)";
    for (const e of s.entities) if (e.assetId && !assets.has(e.assetId)) errors.push(`${s.id}: entity ${e.id} uses unknown asset ${e.assetId}${noManifest}`);
    for (const a of s.assetIds) if (!assets.has(a)) errors.push(`${s.id}: unknown asset ${a}${noManifest}`);
    if (s.voice.intensity > cap) errors.push(`${s.id}: voice intensity ${s.voice.intensity} exceeds the cap ${cap} for this sensitivity`);
    // layouts must place every entity (an unplaced entity cannot be rendered), and word indices must exist in the narration
    const nWords = s.narration.trim().split(/\s+/).length;
    for (const [lname, lay] of Object.entries(s.layouts)) {
      if (!lay) continue;
      for (const e of s.entities) if (!(e.id in lay.placements)) errors.push(`${s.id}: entity ${e.id} has no placement in the ${lname} layout`);
      for (const [ci, cm] of lay.camera.entries()) {
        if (cm.startWord !== undefined && cm.startWord >= nWords) errors.push(`${s.id}: ${lname} camera[${ci}].startWord ${cm.startWord} is past the ${nWords} words of the narration`);
        if (cm.endWord !== undefined && cm.endWord >= nWords) errors.push(`${s.id}: ${lname} camera[${ci}].endWord ${cm.endWord} is past the ${nWords} words of the narration`);
        if (cm.startWord !== undefined && cm.endWord !== undefined && cm.endWord < cm.startWord) errors.push(`${s.id}: ${lname} camera[${ci}] ends before it starts`);
      }
    }
    for (const e of s.entities) {
      if (e.enterAtWord !== undefined && e.enterAtWord >= nWords) errors.push(`${s.id}: entity ${e.id} enterAtWord ${e.enterAtWord} is past the ${nWords} words of the narration`);
      if (e.exitAtWord !== undefined && e.exitAtWord >= nWords) errors.push(`${s.id}: entity ${e.id} exitAtWord ${e.exitAtWord} is past the ${nWords} words of the narration`);
      if (p.manifest && !(e.assetId || e.text || e.visual)) errors.push(`${s.id}: entity ${e.id} has no visual content (assetId, text or visual) although assets exist`);
    }
    const t = s.transition;
    if (t.anchorTo) {
      const next = p.scenes.scenes[i + 1];
      if (!next) errors.push(`${s.id}: transition has anchorTo but there is no next scene`);
      else if (!next.entities.some((e) => e.id === t.anchorTo!.entityId)) errors.push(`${s.id}: anchorTo ${t.anchorTo.entityId} is not an entity of ${next.id}`);
    }
  });
  // timing (written by stage 03): all or none; windows contiguous and non-empty
  const timed = p.scenes.scenes.filter((s) => s.timing);
  if (timed.length > 0 && timed.length < p.scenes.scenes.length) errors.push("some scenes have timing and some do not");
  if (timed.length === p.scenes.scenes.length) {
    const tol = 1.5 / p.scenes.fps;
    p.scenes.scenes.forEach((s, i) => {
      const t = s.timing!;
      if (t.endS <= t.startS) errors.push(`${s.id}: timing window is empty or reversed`);
      const prev = p.scenes.scenes[i - 1]?.timing;
      if (prev && Math.abs(prev.endS - t.startS) > tol) errors.push(`${s.id}: timing window is not contiguous with the previous scene`);
    });
  }
  if (timed.length === p.scenes.scenes.length && (p.config?.purpose ?? "production") === "production") {
    const total = p.scenes.scenes[p.scenes.scenes.length - 1].timing!.endS - p.scenes.scenes[0].timing!.startS;
    if (total < 300) errors.push(`the long video runs ${total.toFixed(0)} s; a production video is never under 5:00 (deepen the idea, or set purpose "test_clip" for a deliberate short test)`);
  }
  const l3 = p.scenes.scenes.filter((s) => s.visualIntensity === 3).length;
  if (l3 > 4) warnings.push(`${l3} level-3 moments; they only work when rare`);

  const shorts = p.shorts?.shorts ?? [];
  for (const sh of shorts) {
    for (const id of sh.sceneIds) {
      const s = p.scenes.scenes.find((x) => x.id === id);
      if (!s) errors.push(`${sh.id}: unknown scene ${id}`);
      else if (sh.status === "validated" && !s.shortIds.includes(sh.id)) errors.push(`${sh.id}: scene ${id} does not list this Short in shortIds`);
    }
  }
  for (const s of p.scenes.scenes) for (const id of s.shortIds) if (!shorts.some((x) => x.id === id)) errors.push(`${s.id}: shortIds refers to unknown Short ${id}`);
  if (timed.length === p.scenes.scenes.length)
    for (const sh of shorts.filter((x) => x.status === "validated")) {
      const dur = sh.sceneIds.reduce((a, id) => { const t = p.scenes.scenes.find((x) => x.id === id)?.timing; return a + (t ? t.endS - t.startS : 0); }, 0);
      if (dur > 180) errors.push(`${sh.id}: its scenes alone run ${dur.toFixed(0)} s, over the 180 s Shorts limit`);
      else if (dur > sh.targetDurationS * 1.25) warnings.push(`${sh.id}: its scenes run ${dur.toFixed(0)} s against a ${sh.targetDurationS} s target; trim or re-scope`);
    }
  // independent reviews sit on top of structural validity: schema-valid is not the same as supported or standalone
  const narrated = new Set(p.scenes.scenes.flatMap((s) => s.claimIds));
  const reviewIssue = (msg: string) => (p.strict ? errors.push(msg) : warnings.push(msg));
  if (p.evidenceReview) {
    if (p.evidenceReview.reviewer.kind === "same_session") reviewIssue("evidence review was done by the same session that wrote the claims: not independent");
    const verdicts = new Map(p.evidenceReview.verdicts.map((v) => [v.claimId, v]));
    for (const id of narrated) {
      const v = verdicts.get(id);
      if (!v) reviewIssue(`claim ${id} is narrated but was not evidence-reviewed`);
      else if (v.verdict === "unsupported") errors.push(`claim ${id}: the reviewer found it unsupported by its cited evidence (${v.reason})`);
      else if (v.verdict === "partial") warnings.push(`claim ${id}: only partially supported (${v.reason}); narration must not claim more than the evidence shows`);
    }
  } else if (narrated.size > 0) reviewIssue("no evidence review (review/evidence-review.json): claims are not independently checked");
  const validatedShorts = shorts.filter((x) => x.status === "validated");
  if (p.shortsReview) {
    if (p.shortsReview.reviewer.kind === "same_session") reviewIssue("Shorts review was done by the same session that planned them: not independent");
    const sv = new Map(p.shortsReview.verdicts.map((v) => [v.shortId, v]));
    for (const sh of validatedShorts) {
      const v = sv.get(sh.id);
      if (!v) reviewIssue(`${sh.id}: validated but not editorially reviewed`);
      else if (v.verdict !== "pass" || !v.standalone) errors.push(`${sh.id}: editorial review says ${v.verdict}${v.standalone ? "" : " and not standalone"} (${v.problems.map((x) => x.problem).join("; ") || "no detail"})`);
    }
  } else if (validatedShorts.length > 0) reviewIssue("no Shorts review (review/shorts-review.json): the seven checks are claims, not evidence");
  const validated = validatedShorts.length;
  if (p.config && (p.config.purpose ?? "production") === "production" && validated < p.config.shortsTarget[0]) warnings.push(`only ${validated} validated Shorts (target ${p.config.shortsTarget[0]}–${p.config.shortsTarget[1]}); revise the outline or report the shortfall`);
  if (p.config && (p.config.purpose ?? "production") === "production" && validated > p.config.shortsTarget[1]) warnings.push(`${validated} validated Shorts exceeds the target maximum`);
  return { errors, warnings };
}
