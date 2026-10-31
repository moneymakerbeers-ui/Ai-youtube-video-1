// node-lib.ts — Node-side helpers for the renderer: static server, project → bundle assembly, ffprobe, video-asset frame extraction.
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { createReadStream, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { dirname, extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { ManifestFile, RenderPlan, ScenesFile, StyleTokens } from "../schema/video.schema";
import type { Bundle } from "./src/renderer";

export const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const MIME: Record<string, string> = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml", ".otf": "font/otf", ".ttf": "font/ttf", ".woff": "font/woff", ".woff2": "font/woff2" };

export class Fail extends Error {
  constructor(public code: number, msg: string) { super(msg); }
}

/** a loopback-only static server: /engine → the built engine, /proj → the project folder, /repo → this repository */
export function serve(roots: Record<string, string>): Promise<{ base: string; close: () => Promise<void> }> {
  const server = http.createServer((req, res) => {
    try {
      const url = new URL(req.url ?? "/", "http://x");
      const m = /^\/(engine|proj|repo)\/(.*)$/.exec(decodeURIComponent(url.pathname));
      const root = m && roots[m[1]];
      if (!m || !root) { res.writeHead(404).end("not found"); return; }
      const file = normalize(join(root, m[2]));
      if (file !== resolve(root) && !file.startsWith(resolve(root) + sep)) { res.writeHead(403).end("outside root"); return; }
      if (!existsSync(file) || !statSync(file).isFile()) { res.writeHead(404).end(`not found: ${m[2]}`); return; }
      res.writeHead(200, { "content-type": MIME[extname(file).toLowerCase()] ?? "application/octet-stream", "cache-control": "no-store" });
      createReadStream(file).pipe(res);
    } catch (e) { res.writeHead(500).end(String(e)); }
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok({ base: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, close: () => new Promise<void>((r) => server.close(() => r())) })));
}

export const readJson = (p: string): unknown => JSON.parse(readFileSync(p, "utf8"));

export function ffprobe(file: string): any {
  const r = spawnSync("ffprobe", ["-v", "error", "-show_format", "-show_streams", "-of", "json", file], { encoding: "utf8" });
  if (r.status !== 0) throw new Fail(4, `ffprobe failed on ${file}: ${r.stderr.trim()}`);
  return JSON.parse(r.stdout);
}

function extractVideoFrames(project: string, assetId: string, file: string, fps: number): { dir: string; count: number } {
  const hash = createHash("sha1").update(`${file}:${statSync(file).size}:${statSync(file).mtimeMs}:${fps}`).digest("hex").slice(0, 10);
  const dir = join(project, "render", "cache", "video", `${assetId}-${hash}`);
  if (!existsSync(dir) || !readdirSync(dir).length) {
    mkdirSync(dir, { recursive: true });
    const r = spawnSync("ffmpeg", ["-v", "error", "-y", "-i", file, "-vf", `fps=${fps}`, "-start_number", "0", "-q:v", "2", join(dir, "f%d.jpg")], { encoding: "utf8" });
    if (r.status !== 0) throw new Fail(4, `ffmpeg could not extract frames of ${file}: ${r.stderr.trim()}`);
  }
  return { dir, count: readdirSync(dir).filter((f) => f.endsWith(".jpg")).length };
}

export interface LoadedProject { plan: RenderPlan; bundle: Bundle; problems: string[] }

/** Read and strictly validate the project files for one render target and assemble the bundle the page-side engine consumes. */
export function loadBundle(project: string, target: string, base: string, opts: { planFile?: string } = {}): LoadedProject {
  const problems: string[] = [];
  const must = (p: string, what: string): string => { if (!existsSync(p)) throw new Fail(2, `${what} is missing: ${p}`); return p; };
  const parse = <T>(schema: { safeParse: (x: unknown) => { success: boolean; data?: T; error?: { issues: { path: PropertyKey[]; message: string }[] } } }, file: string, what: string): T => {
    const r = schema.safeParse(readJson(must(file, what)));
    if (!r.success) throw new Fail(2, `${what} (${file}) is invalid:\n` + r.error!.issues.slice(0, 12).map((i) => `  ${i.path.join(".")}: ${i.message}`).join("\n"));
    return r.data as T;
  };
  const plan = parse<RenderPlan>(RenderPlan, opts.planFile ?? join(project, "render", `plan-${target}.json`), "render plan");
  const scenes = parse<ScenesFile>(ScenesFile, join(project, "scenes.json"), "scenes.json");
  const tokens = parse<StyleTokens>(StyleTokens, join(project, "style-tokens.json"), "style-tokens.json");
  const manPath = join(project, "assets", "manifest.json");
  const manifest = existsSync(manPath) ? parse<ManifestFile>(ManifestFile, manPath, "assets/manifest.json") : { assets: [] };
  const byScene = new Map(scenes.scenes.map((s) => [s.id, s]));
  const outScenes: Bundle["scenes"] = {};
  const assets: Bundle["assets"] = {};
  const url = (rel: string) => `${base}/proj/${rel.split(sep).join("/").split("/").map(encodeURIComponent).join("/")}`;
  for (const ps of plan.scenes) {
    const sc = byScene.get(ps.id);
    if (!sc) throw new Fail(2, `plan scene ${ps.id} is not in scenes.json`);
    const lay = sc.layouts[plan.layout] ?? (plan.layout === "landscape" ? sc.layouts.landscape : undefined);
    if (!lay) throw new Fail(2, `scene ${ps.id} has no ${plan.layout} layout`);
    outScenes[ps.id] = { id: ps.id, entities: sc.entities, placements: lay.placements };
    for (const e of sc.entities) {
      if (!e.assetId || assets[e.assetId]) continue;
      const a = manifest.assets.find((x) => x.id === e.assetId);
      if (!a) { problems.push(`missing_asset:${ps.id}:${e.id}: asset "${e.assetId}" is not in assets/manifest.json`); continue; }
      const abs = join(project, a.file);
      if (!existsSync(abs)) { problems.push(`missing_asset_file:${ps.id}:${e.id}: ${a.file} (asset ${a.id}) does not exist on disk`); continue; }
      if (a.kind === "image" || a.kind === "svg") assets[a.id] = { id: a.id, kind: a.kind, url: url(a.file), width: a.width, height: a.height };
      else if (a.kind === "video") {
        const fr = extractVideoFrames(project, a.id, abs, plan.fps);
        const rel = join("render", "cache", "video", fr.dir.split(sep).pop()!);
        const pr = ffprobe(abs).streams.find((s: any) => s.codec_type === "video");
        assets[a.id] = { id: a.id, kind: "video", url: url(a.file), width: pr.width, height: pr.height, frames: { count: fr.count, fps: plan.fps, pattern: `${base}/proj/${rel.split(sep).join("/")}/f{n}.jpg` } };
      } else problems.push(`asset_not_drawable:${ps.id}:${e.id}: asset ${a.id} is of kind "${a.kind}"`);
    }
  }
  const fonts: Bundle["fonts"] = tokens.fonts.files.map((f) => {
    const inProj = join(project, f.file);
    const rel = existsSync(inProj) ? `proj/${f.file}` : existsSync(join(REPO, f.file)) ? `repo/${f.file}` : null;
    if (!rel) problems.push(`font_file_missing:*:${f.family}: ${f.file}`);
    return { family: f.family, url: `${base}/${(rel ?? `proj/${f.file}`).split(sep).join("/")}`, weight: f.weight, style: f.style };
  });
  return { plan, bundle: { plan, scenes: outScenes, tokens, assets, fonts }, problems };
}
