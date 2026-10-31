// build.ts — bundle the page-side engine (and the project's own visuals, if it has any) into one browser script.
// usage: npx tsx engine/build.ts [--project videos/<slug>] [--out <dir>]   → <dir>/engine.js + <dir>/index.html
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const arg = (k: string, d?: string): string | undefined => { const i = process.argv.indexOf(k); return i > -1 ? process.argv[i + 1] : d; };

export async function buildEngine({ project, out }: { project?: string; out?: string }) {
  const outDir = resolve(out ?? join(project ?? here, "render", "engine"));
  mkdirSync(outDir, { recursive: true });
  const visualsEntry = project ? ["index.ts", "index.js"].map((f) => resolve(project, "visuals", f)).find((f) => existsSync(f)) : undefined;
  const contents = [`import ${JSON.stringify(join(here, "src", "browser.ts"))};`];
  if (visualsEntry) contents.push(`import visuals from ${JSON.stringify(visualsEntry)};`, `for (const v of visuals) window.engine.registerVisual(v);`);
  const res = await build({
    stdin: { contents: contents.join("\n"), resolveDir: here, loader: "ts", sourcefile: "engine-entry.ts" },
    bundle: true, format: "iife", target: "chrome120", platform: "browser", sourcemap: false, minify: false, legalComments: "none",
    write: false, logLevel: "silent",
  });
  const code = res.outputFiles[0].text;
  writeFileSync(join(outDir, "engine.js"), code);
  writeFileSync(join(outDir, "index.html"), `<!doctype html><meta charset="utf-8"><title>engine</title><body style="margin:0;background:#000"><script src="engine.js"></script>`);
  const hash = createHash("sha256").update(code).digest("hex");
  return { outDir, hash, bytes: code.length, projectVisuals: visualsEntry ?? null };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const r = await buildEngine({ project: arg("--project"), out: arg("--out") });
  console.log(`engine built: ${r.outDir}/engine.js (${r.bytes} bytes, sha256 ${r.hash.slice(0, 16)}…)${r.projectVisuals ? ` + project visuals ${r.projectVisuals}` : ""}`);
}
