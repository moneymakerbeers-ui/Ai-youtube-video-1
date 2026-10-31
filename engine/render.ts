#!/usr/bin/env -S npx tsx
// render.ts — render one target (long, S01, preview-…) from its render plan to an H.264/AAC mp4, deterministically.
//
//   npx tsx engine/render.ts --project videos/<slug> --target long
//   npx tsx engine/render.ts --project videos/<slug> --target S01 --out out/short-01.mp4
//   npx tsx engine/render.ts --project videos/<slug> --target long --range 300:420 --out render/previews/tr-s03.mp4    (frames 300..419, audio sliced)
//   npx tsx engine/render.ts --project videos/<slug> --target long --dump-times 12.5,13.0 --dump-dir render/frames      (PNG stills, no video)
//
// Exit codes: 0 ok · 2 invalid or missing input · 3 blocking problem in the scene graph (unresolved entity, missing asset, blocked
// transition) unless --allow-placeholders · 4 a tool failed (browser, ffmpeg, ffprobe) · 5 the written file does not match the plan.
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { chromium, type Page } from "playwright";
import { buildEngine } from "./build.ts";
import { Fail, ffprobe, loadBundle, REPO, serve } from "./node-lib.ts";
import type { FrameTrace } from "./src/renderer.ts";

const argv = process.argv.slice(2);
const flag = (k: string) => argv.includes(k);
const arg = (k: string, d?: string): string | undefined => { const i = argv.indexOf(k); return i > -1 ? argv[i + 1] : d; };
const BLOCKING = /^(unresolved_entity|missing_asset|missing_asset_file|missing_visual|asset_load_failed|asset_not_drawable|transition_blocked|no_placement|no_timing|anchor_missing|font_file_missing)\b/;

// --disable-partial-raster: without it Chromium repaints only the damaged part of a tile, so a frame's pixels depend on which frames this page drew
// before, and with several workers the same DOM state gave different bytes from run to run (74 of 150 frames). With it, 3 runs x 2 workers were identical.
// Extra Chromium flags for experiments (ENGINE_CHROMIUM_FLAGS="--a --b"); the default is the configuration the QA and the tests were run with.
const EXTRA_FLAGS = (process.env.ENGINE_CHROMIUM_FLAGS ?? "").split(/\s+/).filter(Boolean);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function main(): Promise<number> {
  const project = resolve(arg("--project") ?? "");
  const target = arg("--target") ?? "";
  if (!arg("--project") || !target) throw new Fail(2, "usage: render.ts --project <dir> --target <long|S01|preview-…> [--out file.mp4] [--range a:b] [--dump-times t,t] [--dump-frames n,n] [--dump-dir dir] [--workers N] [--crf N] [--preset name] [--audio auto|none|file] [--allow-placeholders]");
  const t0 = Date.now();
  const eng = await buildEngine({ project });
  const srv = await serve({ engine: eng.outDir, proj: project, repo: REPO });
  const { plan, bundle, problems } = loadBundle(project, target, srv.base, { planFile: arg("--plan") });
  const allow = flag("--allow-placeholders");
  const fps = plan.fps;

  // ── range, outputs ──
  const [a0, b0] = (arg("--range") ?? `0:${plan.durationFrames}`).split(":").map(Number);
  const dumpT = arg("--dump-times")?.split(",").map((x) => Math.min(Math.max(Math.round(parseFloat(x) * fps), 0), plan.durationFrames - 1));
  const dumpF = arg("--dump-frames")?.split(",").map(Number);
  const dump = dumpT ?? dumpF;
  const from = dump ? 0 : Math.max(0, a0), to = dump ? 0 : Math.min(plan.durationFrames, b0);
  if (!dump && !(to > from)) throw new Fail(2, `empty frame range ${from}:${to}`);
  const defaultOut = target === "long" ? "out/full-video.mp4" : /^S\d+$/.test(target) ? `out/short-${target.slice(1).padStart(2, "0")}.mp4` : `out/${target}.mp4`;
  const outFile = resolve(project, arg("--out") ?? defaultOut);
  mkdirSync(dirname(outFile), { recursive: true });
  const partial = !dump && (from !== 0 || to !== plan.durationFrames);

  // ── audio ──
  let audioPath: string | null = null;
  const am = arg("--audio", "auto")!;
  if (am !== "none") {
    const master = join(project, "audio", `master-${target}.wav`);
    const cand = am === "auto" ? (existsSync(master) ? master : plan.audio ? join(project, plan.audio.file) : null) : resolve(project, am);
    if (cand && !existsSync(cand)) throw new Fail(2, `audio file missing: ${cand}`);
    audioPath = cand;
  }

  // ── browser ──
  const workers = Math.max(1, Number(arg("--workers", "2")));
  // One browser process per worker: headless Chromium rasterises in its single GPU/compositor process, so pages that share one browser
  // queue behind one CPU core. Separate browsers parallelise the raster; the frame-to-page assignment stays fixed (reproducible output).
  const launch = () => chromium.launch({ args: ["--force-color-profile=srgb", "--font-render-hinting=none", "--disable-lcd-text", "--hide-scrollbars", "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-partial-raster", ...EXTRA_FLAGS] }).catch((e) => { throw new Fail(4, `could not launch Chromium (run: npx playwright install chromium): ${e.message}`); });
  const browser = await launch();
  const extraBrowsers: Awaited<ReturnType<typeof launch>>[] = [];
  const pages: Page[] = [];
  let initInfo: { warnings: string[]; describe: unknown; version: string } | null = null;
  try {
    for (let i = 0; i < (dump ? 1 : workers); i++) {
      const b = i === 0 ? browser : (extraBrowsers[extraBrowsers.push(await launch()) - 1]);
      const ctx = await b.newContext({ viewport: { width: plan.width, height: plan.height }, deviceScaleFactor: 1 });
      const page = await ctx.newPage();
      page.on("pageerror", (e) => console.error("[page error]", e.message));
      page.on("console", (m) => m.type() === "error" && console.error("[page console]", m.text()));
      await page.goto(`${srv.base}/engine/index.html`);
      const info = await page.evaluate((b) => (window as any).engine.init(b), bundle as any);
      if (!initInfo) initInfo = info;
      pages.push(page);
    }
    const warn = [...problems, ...(initInfo!.warnings as string[])];
    const blocking = warn.filter((w) => BLOCKING.test(w));
    for (const w of warn) console.error(`${BLOCKING.test(w) ? "BLOCKING" : "warn"}: ${w}`);
    if (blocking.length && !allow) throw new Fail(3, `${blocking.length} blocking problem(s) in the scene graph; fix them or pass --allow-placeholders for a preview`);

    // RENDER_FRAME_FORMAT=jpeg trades a lossless PNG hand-off for a q95 JPEG (several times faster to encode in software Chromium at 1080p;
    // the frame is re-encoded to 4:2:0 H.264 anyway). Default stays png (the tested, bit-exact path).
    const frameFmt = process.env.RENDER_FRAME_FORMAT === "jpeg" ? "jpeg" : "png";
    const shot = (p: Page) => (frameFmt === "jpeg" ? p.screenshot({ type: "jpeg", quality: 95, animations: "disabled", caret: "initial" }) : p.screenshot({ type: "png", animations: "disabled", caret: "initial" }));

    // ── dump mode: stills ──
    if (dump) {
      const dir = resolve(project, arg("--dump-dir") ?? "render/frames");
      mkdirSync(dir, { recursive: true });
      for (const f of dump) {
        const tr: FrameTrace = await pages[0].evaluate((n) => (window as any).engine.renderFrame(n), f);
        const file = join(dir, `${target}-f${String(f).padStart(6, "0")}.png`);
        writeFileSync(file, await shot(pages[0]));
        console.log(`frame ${f} (t=${tr.t.toFixed(3)}s, ${tr.mode}${tr.transition ? ` ${tr.transition.used} p=${tr.transition.p.toFixed(2)}` : ""}) -> ${file}`);
      }
      return 0;
    }

    // ── encode ──
    const crf = arg("--crf", "18"), preset = arg("--preset", "veryfast");
    const audioArgs = audioPath ? ["-ss", String(partial ? from / fps : 0), "-t", String(((partial ? to - from : plan.durationFrames) / fps).toFixed(6)), "-i", audioPath] : [];
    // The same ffmpeg process also measures the picture before it is encoded: area-pooled to POOL px wide, caption-free crop, luma, the
    // frame-to-frame max difference (tblend + signalstats YMAX). tools/qa_media.py runs the identical chain on the delivered file and
    // compares the two, so "the file is still where the source moves" (dropped/duplicated frames, codec smoothing) is told apart from
    // "the source itself changes by less than anyone can see" (the tail of a slow ease).
    const POOL = 96;
    const region = (plan as any).pictureRegion as { x: number; y: number; w: number; h: number } | null | undefined;
    const crop = region ? `crop=iw*${region.w}:ih*${region.h}:iw*${region.x}:ih*${region.y},` : "";
    const probeName = `probe-${target}${partial ? `.${from}-${to}` : ""}.txt`;
    const probeFile = join(project, "render", probeName);
    mkdirSync(dirname(probeFile), { recursive: true });
    const graph = `[0:v]split=2[enc][prb];` +
      `[enc]scale=in_range=pc:out_range=tv:out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int+bitexact,format=yuv420p[v];` +
      `[prb]${crop}scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p,scale=${POOL}:-2:flags=area,format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YMAX:file=${probeName}[m]`;
    const ffArgs = [
      "-hide_banner", "-v", "error", "-y",
      "-f", "image2pipe", "-framerate", String(fps), "-c:v", frameFmt === "jpeg" ? "mjpeg" : "png", "-i", "pipe:0", ...audioArgs,
      "-filter_complex", graph,
      "-map", "[v]", ...(audioPath ? ["-map", "1:a:0"] : []),
      "-c:v", "libx264", "-preset", preset!, "-crf", crf!, "-pix_fmt", "yuv420p", "-g", String(fps * 2), "-bf", "2",
      "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
      "-r", String(fps), "-fps_mode", "cfr",
      ...(audioPath ? ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"] : ["-an"]),
      "-movflags", "+faststart", outFile,
      "-map", "[m]", "-an", "-f", "null", "-",
    ];
    const ff = spawn("ffmpeg", ffArgs, { stdio: ["pipe", "ignore", "pipe"], cwd: dirname(probeFile) });
    let ffErr = "";
    ff.stderr.on("data", (d) => (ffErr += d));
    let ffDead = false;
    const ffDone = new Promise<number>((res) => { ff.on("exit", (c) => { ffDead = true; res(c ?? -1); }); ff.on("error", () => { ffDead = true; res(-1); }); });
    ff.stdin.on("error", () => undefined);

    const total = to - from;
    const hashes: string[] = new Array(total);
    const states: string[] = new Array(total);
    const traces: FrameTrace[] = new Array(total);
    const ready = new Map<number, Buffer>();
    const waiting = new Map<number, (b: Buffer) => void>();
    let writePos = from, failed: Error | null = null;
    const cap = workers * 3;
    // Fixed frame assignment: page k always draws frames from+k, from+k+N, from+k+2N, ... in increasing order (N = pages). A page's pixels can
    // depend on which frames it drew before (Chromium keeps raster state between frames), so a first-come-first-served queue made the output
    // depend on thread timing: the demo Short differed between runs in up to 120 of 425 frames (text edges, up to 44 luma levels). A fixed
    // assignment gives every page the same history in every run, so a render is reproducible for a given worker count.
    const worker = async (page: Page, k: number) => {
      for (let n = from + k; n < to && !failed; n += pages.length) {
        while (n - writePos > cap && !failed) await sleep(2);
        try {
          const tr: FrameTrace = await page.evaluate((k) => (window as any).engine.renderFrame(k), n);
          const buf = await shot(page);
          traces[n - from] = tr;
          states[n - from] = tr.state.slice(0, 12);
          hashes[n - from] = createHash("sha1").update(buf).digest("hex").slice(0, 12);
          const w = waiting.get(n);
          if (w) { waiting.delete(n); w(buf); } else ready.set(n, buf);
        } catch (e) { failed = e as Error; for (const w of waiting.values()) w(Buffer.alloc(0)); }
      }
    };
    const progress = setInterval(() => process.stderr.write(`\r  frame ${writePos - from}/${total}  ${(((Date.now() - t0) / 1000) | 0)}s`), 2000);
    const tCapture = Date.now();
    const jobs = pages.map((p, k) => worker(p, k));
    for (let n = from; n < to; n++) {
      const buf = ready.get(n) ?? (await new Promise<Buffer>((res) => waiting.set(n, res)));
      ready.delete(n);
      if (failed) break;
      if (ffDead) { failed = new Error("ffmpeg exited early"); break; }
      if (!ff.stdin.write(buf)) await new Promise<void>((r) => ff.stdin.once("drain", () => r()));
      writePos = n + 1;
    }
    clearInterval(progress);
    ff.stdin.end();
    await Promise.all(jobs);
    const code = await ffDone;
    process.stderr.write("\r" + " ".repeat(60) + "\r");
    if (failed) throw new Fail(4, `rendering failed at frame ${writePos}: ${failed.message}`);
    if (code !== 0) throw new Fail(4, `ffmpeg exited with ${code}: ${ffErr.trim().split("\n").slice(-6).join(" | ")}`);
    const secs = (Date.now() - tCapture) / 1000;

    // ── verify what was written against the plan ──
    const pr = ffprobe(outFile);
    const vs = pr.streams.find((s: any) => s.codec_type === "video");
    const as = pr.streams.find((s: any) => s.codec_type === "audio");
    const probs: string[] = [];
    if (!vs) probs.push("no video stream");
    else {
      if (vs.width !== plan.width || vs.height !== plan.height) probs.push(`size ${vs.width}x${vs.height} != plan ${plan.width}x${plan.height}`);
      if (vs.pix_fmt !== "yuv420p") probs.push(`pix_fmt ${vs.pix_fmt}`);
      const [n, d] = String(vs.avg_frame_rate).split("/").map(Number);
      if (Math.abs(n / d - fps) > 0.01) probs.push(`frame rate ${vs.avg_frame_rate} != ${fps}`);
      const nb = Number(vs.nb_frames);
      if (!nb || nb !== total) probs.push(`frame count ${vs.nb_frames} != ${total}`);
      if (vs.color_space !== "bt709") probs.push(`color_space tag ${vs.color_space}`);
    }
    if (audioPath && !as) probs.push("audio expected but absent");
    if (as) {
      const dv = Number(vs?.duration ?? pr.format.duration), da = Number(as.duration);
      if (Math.abs(dv - da) > 1.5 / fps + 0.03) probs.push(`audio/video durations differ by ${Math.abs(dv - da).toFixed(3)}s`);
    }
    if (probs.length) throw new Fail(5, `the written file does not match the plan: ${probs.join("; ")}`);

    // ── trace and meta ──
    const warns = new Map<string, { code: string; scene: string; entity: string; msg: string; first: number; last: number; frames: number }>();
    for (const tr of traces) for (const w of tr.warnings) {
      const [code, scene, rest] = [w.split(":")[0], w.split(":")[1], w.split(":").slice(2).join(":")];
      const key = `${code}|${scene}|${rest.split(":")[0]}`;
      const cur = warns.get(key);
      if (cur) { cur.last = tr.t; cur.frames++; } else warns.set(key, { code, scene, entity: rest.split(":")[0], msg: w, first: tr.t, last: tr.t, frames: 1 });
    }
    const runs: { from: number; to: number; len: number }[] = [];
    for (let i = 0; i < total;) { let j = i; while (j + 1 < total && hashes[j + 1] === hashes[i]) j++; if (j - i + 1 >= 3) runs.push({ from: from + i, to: from + j, len: j - i + 1 }); i = j + 1; }
    const trans = new Map<string, { from: string; to: string; planned: string; used: string; firstFrame: number; lastFrame: number; fellBack: boolean }>();
    for (const [i, tr] of traces.entries()) if (tr.transition) {
      const k = `${tr.transition.from}>${tr.transition.to}`;
      const c = trans.get(k);
      if (c) c.lastFrame = from + i; else trans.set(k, { from: tr.transition.from, to: tr.transition.to, planned: tr.transition.planned, used: tr.transition.used, firstFrame: from + i, lastFrame: from + i, fellBack: tr.transition.fellBack });
    }
    // source-side motion series: sourceMotion.ymax[j] is the pooled max luma change from frame first+j-1 to first+j (absolute frame numbers)
    const sm: { pool: number; region: unknown; first: number; ymax: number[]; error?: string } = { pool: POOL, region: region ?? null, first: from + 1, ymax: [] };
    try {
      const txt = readFileSync(probeFile, "utf8");
      const idx: number[] = [], val: number[] = [];
      let cur = -1;
      for (const line of txt.split("\n")) {
        const mf = /pts_time:([0-9.]+)/.exec(line);
        if (mf) { cur = Math.round(parseFloat(mf[1]) * fps); continue; }
        const mv = /lavfi\.signalstats\.YMAX=([0-9.]+)/.exec(line);
        if (mv && cur >= 0) { idx.push(cur); val.push(parseFloat(mv[1])); }
      }
      const ok = idx.length === total - 1 && idx.every((k, j) => k === j + 1);
      if (ok) sm.ymax = val; else sm.error = `probe has ${idx.length} samples for ${total} frames (first ${idx[0]}, last ${idx[idx.length - 1]})`;
    } catch (e) { sm.error = `probe unreadable: ${(e as Error).message}`; }
    const transitionFrames = traces.flatMap((tr, i) => (tr.transition ? [{ f: from + i, t: +tr.t.toFixed(4), ...tr.transition }] : []));
    const ver = spawnSync("ffmpeg", ["-version"], { encoding: "utf8" }).stdout.split("\n")[0];
    const trace = {
      target, fps, width: plan.width, height: plan.height, range: [from, to], engine: { version: initInfo!.version, sha256: eng.hash, backend: "browser", chromium: browser.version(), ffmpeg: ver },
      output: { file: outFile, bytes: Number(pr.format.size), durationS: Number(pr.format.duration), sha256: createHash("sha256").update(readFileSync(outFile)).digest("hex") },
      frameHashes: hashes.join(""), stateHashes: states.join(""), hashChars: 12, identicalRuns: runs, sourceMotion: sm,
      transitions: [...trans.values()], transitionFrames, warnings: [...warns.values()], buildWarnings: warn,
      timing: { captureS: +secs.toFixed(1), msPerFrame: +((secs * 1000) / total).toFixed(1), workers: pages.length },
    };
    const traceFile = join(project, "render", partial ? `trace-${target}.${from}-${to}.json` : `trace-${target}.json`);
    mkdirSync(dirname(traceFile), { recursive: true });
    writeFileSync(traceFile, JSON.stringify(trace));
    console.log(`${basename(outFile)}: ${total} frames ${plan.width}x${plan.height} @ ${fps} fps, ${(total / fps).toFixed(2)}s, ${(Number(pr.format.size) / 1e6).toFixed(2)} MB, ${trace.timing.msPerFrame} ms/frame (${pages.length} worker${pages.length > 1 ? "s" : ""}); audio ${as ? `${as.codec_name} ${as.sample_rate} Hz` : "none"}`);
    console.log(`trace: ${traceFile} · identical-frame runs ≥3: ${runs.length} · render warnings: ${warns.size}`);
    return 0;
  } finally {
    for (const b of extraBrowsers) await b.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
    await srv.close();
  }
}

main().then((c) => process.exit(c), (e) => {
  if (e instanceof Fail) { console.error(`FAILED (${e.code}): ${e.message}`); process.exit(e.code); }
  console.error(e); process.exit(4);
});
