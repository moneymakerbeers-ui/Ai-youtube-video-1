// schema/validate.ts — validate one project file, a whole video folder, or run the built-in selftest.
//   npx tsx schema/validate.ts <config|facts|scenes|shorts|manifest|state|tokens|plan|alignment|evidence-review|shorts-review> <file.json>
//   npx tsx schema/validate.ts <findings|ledger> <file.jsonl>
//   npx tsx schema/validate.ts project videos/<slug> [--strict]
//   npx tsx schema/validate.ts selftest
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import * as S from "./video.schema";
import { checkProject } from "./video.schema";

const here = dirname(fileURLToPath(import.meta.url));
const types: Record<string, z.ZodTypeAny> = {
  config: S.RunConfig,
  facts: S.FactsFile,
  scenes: S.ScenesFile,
  shorts: S.ShortsFile,
  manifest: S.ManifestFile,
  state: S.State,
  tokens: S.StyleTokens,
  plan: S.RenderPlan,
  alignment: S.Alignment,
  "evidence-review": S.EvidenceReview,
  "shorts-review": S.ShortsReview,
};
const jsonl: Record<string, z.ZodTypeAny> = { findings: S.Finding, ledger: S.LedgerEntry };

function show(label: string, r: z.SafeParseReturnType<unknown, unknown>): boolean {
  if (r.success) return console.log(`ok    ${label}`), true;
  console.log(`FAIL  ${label}`);
  for (const i of r.error.issues) console.log(`      ${i.path.join(".") || "(root)"}: ${i.message}`);
  return false;
}
const readJson = (path: string): unknown => JSON.parse(readFileSync(path, "utf8"));
const sha256 = (path: string): string => createHash("sha256").update(readFileSync(path)).digest("hex");
function parseJsonl(kind: string, path: string): boolean {
  let ok = true;
  readFileSync(path, "utf8")
    .split("\n")
    .filter((l) => l.trim())
    .forEach((l, i) => (ok = show(`${kind} ${path}:${i + 1}`, jsonl[kind].safeParse(JSON.parse(l))) && ok));
  return ok;
}

const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const strict = process.argv.includes("--strict");
const [kind, file] = args;

if (kind === "selftest") {
  const ex = readJson(join(here, "examples", "selftest.json")) as any;
  let ok = true;
  // 1) the example project must be valid, file by file and across files
  const parsed: Record<string, any> = {};
  for (const k of ["config", "facts", "scenes", "shorts", "manifest", "state", "evidence-review", "shorts-review"]) {
    const r = types[k].safeParse(ex[k]);
    ok = show(`example ${k}`, r) && ok;
    if (r.success) parsed[k] = r.data;
  }
  const full = (p: any, extra: Partial<S.Project> = {}) =>
    checkProject({ config: S.RunConfig.parse(p.config), facts: S.FactsFile.parse(p.facts), scenes: S.ScenesFile.parse(p.scenes), shorts: S.ShortsFile.parse(p.shorts), manifest: S.ManifestFile.parse(p.manifest), evidenceReview: S.EvidenceReview.parse(p["evidence-review"]), shortsReview: S.ShortsReview.parse(p["shorts-review"]), ...extra });
  if (ok) {
    const c = full(parsed, { strict: true });
    c.warnings.forEach((w) => console.log(`warn  ${w}`));
    c.errors.forEach((e) => console.log(`FAIL  ${e}`));
    ok = c.errors.length === 0 && ok;
  }
  // 2) the rules must actually bite: each mutation below has to be rejected
  const clone = () => JSON.parse(JSON.stringify(ex));
  const scenesBad = (p: any) => !S.ScenesFile.safeParse(p.scenes).success;
  const projectBad = (p: any, extra: Partial<S.Project> = {}) => full(p, extra).errors.length > 0;
  const mutations: [string, (p: any) => void, (p: any) => boolean][] = [
    ["level-3 without signature", (p) => delete p.scenes.scenes[1].signature, scenesBad],
    ["match transition without anchors", (p) => delete p.scenes.scenes[1].transition.anchorTo, scenesBad],
    ["Short scene without portrait layout", (p) => delete p.scenes.scenes[0].layouts.portrait, scenesBad],
    ["payoff without claim ids", (p) => (p.scenes.scenes[2].claimIds = []), scenesBad],
    ["camera move without a reason", (p) => (p.scenes.scenes[1].layouts.landscape.camera[0].reason = ""), scenesBad],
    ["hold without a reason", (p) => (p.scenes.scenes[0].layouts.landscape.hold = { reason: "" }), scenesBad],
    ["credits above 20 without creator raise", (p) => (p.config.maxPaidSpend.higgsfieldCredits = 30), (p) => !S.RunConfig.safeParse(p.config).success],
    ["target duration under 5 minutes", (p) => ((p.config.purpose = "production"), (p.config.targetDurationMin = [4, 6])), (p) => !S.RunConfig.safeParse(p.config).success],
    ["production video whose aligned scenes run under 5:00 (cross-file)", (p) => (p.config.purpose = "production"), (p) => projectBad(p)],
    ["a test clip may be short (control: must stay valid)", (p) => ((p.config.purpose = "test_clip"), (p.config.targetDurationMin = [0.5, 1.5])), (p) => S.RunConfig.safeParse(p.config).success && !projectBad(p)],
    ["validated Short with a failed check", (p) => (p.shorts.shorts[0].validation.cleanPayoff = false), (p) => !S.ShortsFile.safeParse(p.shorts).success],
    ["retrieved asset without license evidence", (p) => delete p.manifest.assets[2].license.evidenceFile, (p) => !S.ManifestFile.safeParse(p.manifest).success],
    ["generated asset without prompt", (p) => delete p.manifest.assets[0].provenance.prompt, (p) => !S.ManifestFile.safeParse(p.manifest).success],
    ["verified claim with one weak source", (p) => (p.facts.claims[0].sources = [{ title: "blog", type: "news", accessed: "2026-10-30" }]), (p) => !S.FactsFile.safeParse(p.facts).success],
    ["verified claim without any direct evidence pointer", (p) => (p.facts.claims[0].evidence = []), (p) => !S.FactsFile.safeParse(p.facts).success],
    ["quote locator without the quote", (p) => delete p.facts.claims[0].evidence[0].quote, (p) => !S.FactsFile.safeParse(p.facts).success],
    ["evidence points past the sources list", (p) => (p.facts.claims[0].evidence[0].sourceIndex = 9), (p) => !S.FactsFile.safeParse(p.facts).success],
    ["unknown claim id (cross-file)", (p) => (p.scenes.scenes[0].claimIds = ["F99"]), (p) => projectBad(p)],
    ["voice intensity above the sensitivity cap (cross-file)", (p) => ((p.config.sensitivity = "high"), (p.scenes.scenes[2].voice.intensity = 2)), (p) => projectBad(p)],
    ["gap between scene timing windows (cross-file)", (p) => (p.scenes.scenes[2].timing.startS += 1.0), (p) => projectBad(p)],
    ["entity without a placement (cross-file)", (p) => delete p.scenes.scenes[1].layouts.landscape.placements.e_label, (p) => projectBad(p)],
    ["camera word index past the narration (cross-file)", (p) => (p.scenes.scenes[1].layouts.landscape.camera[0].endWord = 400), (p) => projectBad(p)],
    ["entity without any content once assets exist (cross-file)", (p) => (p.scenes.scenes[1].entities[0] = { id: "e_beam", role: "diagram", need: "x" }), (p) => projectBad(p)],
    ["claim narrated but judged unsupported by the reviewer", (p) => (p["evidence-review"].verdicts[0].verdict = "unsupported"), (p) => projectBad(p)],
    ["narrated claim missing from the evidence review (strict)", (p) => p["evidence-review"].verdicts.pop(), (p) => projectBad(p, { strict: true })],
    ["same-session review is not independent (strict)", (p) => (p["evidence-review"].reviewer.kind = "same_session"), (p) => projectBad(p, { strict: true })],
    ["validated Short judged not standalone", (p) => (p["shorts-review"].verdicts[0].standalone = false), (p) => projectBad(p)],
    ["alignment that runs backwards", (p) => 0, () => !S.Alignment.safeParse({ version: 1, source: "dtw_reference", audio: { file: "a.wav", sha256: "0".repeat(64), durationS: 5 }, script: { file: "s.txt", sha256: "0".repeat(64) }, coverage: 1, words: [{ i: 0, w: "a", s: 2, e: 3 }, { i: 1, w: "b", s: 1, e: 1.5 }] }).success],
    ["alignment word past the end of the audio", (p) => 0, () => !S.Alignment.safeParse({ version: 1, source: "dtw_reference", audio: { file: "a.wav", sha256: "0".repeat(64), durationS: 5 }, script: { file: "s.txt", sha256: "0".repeat(64) }, coverage: 1, words: [{ i: 0, w: "a", s: 4.9, e: 7 }] }).success],
    ["estimated alignment source is not accepted", (p) => 0, () => !S.Alignment.safeParse({ version: 1, source: "estimated", audio: { file: "a.wav", sha256: "0".repeat(64), durationS: 5 }, script: { file: "s.txt", sha256: "0".repeat(64) }, coverage: 1, words: [{ i: 0, w: "a", s: 0, e: 1 }] }).success],
  ];
  for (const [name, mutate, rejected] of mutations) {
    const p = clone();
    mutate(p);
    const good = rejected(p);
    console.log(`${good ? "ok   " : "FAIL "} rule bites: ${name}`);
    ok = good && ok;
  }
  console.log(ok ? `\nSELFTEST PASSED (${mutations.length} rules proven)` : "\nSELFTEST FAILED");
  process.exit(ok ? 0 : 1);
}

if (kind === "project") {
  // npx tsx schema/validate.ts project videos/<slug> [--strict]
  if (!file) (console.log("usage: npx tsx schema/validate.ts project videos/<slug> [--strict]"), process.exit(2));
  const files: [string, string, boolean][] = [
    ["config", "config.json", true],
    ["facts", "facts.json", true],
    ["scenes", "scenes.json", true],
    ["shorts", "shorts.json", false],
    ["manifest", join("assets", "manifest.json"), false],
    ["state", "state.json", false],
    ["tokens", "style-tokens.json", false],
    ["evidence-review", join("review", "evidence-review.json"), false],
    ["shorts-review", join("review", "shorts-review.json"), false],
  ];
  const parsed: Record<string, any> = {};
  let allOk = true;
  for (const [k, name, required] of files) {
    const path = join(file, name);
    if (!existsSync(path)) {
      if (required) (console.log(`FAIL  missing ${path}`), (allOk = false));
      continue;
    }
    const r = types[k].safeParse(readJson(path));
    allOk = show(`${k} ${path}`, r) && allOk;
    if (r.success) parsed[k] = r.data;
  }
  for (const [k, name] of [["findings", join("review", "findings.jsonl")], ["ledger", "ledger.jsonl"]]) {
    const path = join(file, name);
    if (existsSync(path)) allOk = parseJsonl(k, path) && allOk;
  }
  // render plans and alignments: schema + "the hash in the file is the hash of the audio on disk" (stops copied timestamps)
  const audioChecks: [string, string, string][] = []; // [label, metadata file, kind]
  const rdir = join(file, "render");
  if (existsSync(rdir)) for (const f of readdirSync(rdir).filter((x) => /^plan-.*\.json$/.test(x))) audioChecks.push([`plan ${join(rdir, f)}`, join(rdir, f), "plan"]);
  for (const a of [join(file, "audio", "alignment.json")]) if (existsSync(a)) audioChecks.push([`alignment ${a}`, a, "alignment"]);
  const sdir = join(file, "audio", "shorts");
  if (existsSync(sdir)) for (const d of readdirSync(sdir)) if (existsSync(join(sdir, d, "alignment.json"))) audioChecks.push([`alignment ${join(sdir, d, "alignment.json")}`, join(sdir, d, "alignment.json"), "alignment"]);
  for (const [label, path, k] of audioChecks) {
    const r = types[k].safeParse(readJson(path));
    allOk = show(label, r) && allOk;
    if (r.success) {
      const au = (r.data as any).audio;
      if (au) {
        const ap = join(file, au.file);
        if (!existsSync(ap)) (console.log(`FAIL  ${label}: audio file ${au.file} does not exist`), (allOk = false));
        else if (sha256(ap) !== au.sha256) (console.log(`FAIL  ${label}: audio ${au.file} changed after it was measured (hash mismatch); re-align or re-plan`), (allOk = false));
      }
      if (k === "plan" && (r.data as any).timingSource === "estimated" && !(r.data as any).target.startsWith("preview")) (console.log(`FAIL  ${label}: estimated timing is only allowed for previews`), (allOk = false));
    }
  }
  if (parsed.facts && parsed.scenes) {
    const c = checkProject({ config: parsed.config, facts: parsed.facts, scenes: parsed.scenes, shorts: parsed.shorts, manifest: parsed.manifest, evidenceReview: parsed["evidence-review"], shortsReview: parsed["shorts-review"], strict });
    c.warnings.forEach((w) => console.log(`warn  ${w}`));
    c.errors.forEach((e) => console.log(`FAIL  ${e}`));
    allOk = c.errors.length === 0 && allOk;
    console.log(allOk ? `\nPROJECT OK${strict ? " (strict)" : ""} (${c.warnings.length} warnings)` : `\nPROJECT HAS ERRORS (${c.errors.length} cross-file)`);
  } else console.log("\nPROJECT HAS ERRORS (files missing or invalid; cross-file rules not run)");
  process.exit(allOk ? 0 : 1);
}

if (!kind || !file || !(types[kind] || jsonl[kind])) {
  console.log("usage: npx tsx schema/validate.ts <config|facts|scenes|shorts|manifest|state|tokens|plan|alignment|evidence-review|shorts-review> <file.json> | <findings|ledger> <file.jsonl> | project <videos/slug> [--strict] | selftest");
  process.exit(2);
}
if (jsonl[kind]) process.exit(parseJsonl(kind, file) ? 0 : 1);
const ok = show(`${kind} ${file}`, types[kind].safeParse(readJson(file)));
process.exit(ok ? 0 : 1);
