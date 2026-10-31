#!/usr/bin/env -S npx tsx
// visuals-manifest.ts — what each registered visual declares about itself, as JSON the Python tools can read before any render.
//   npx tsx engine/visuals-manifest.ts --project videos/<slug> --out videos/<slug>/render/visuals-manifest.json
// The registry is the single source of truth (VisualDef.motion); this file only reads it. Project visuals (visuals/index.ts)
// are imported the same way the page bundle imports them, and override a built-in of the same id.
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { builtinVisuals } from "./src/visuals/builtin.ts";
import type { VisualDef } from "./src/visuals/types.ts";

const argv = process.argv.slice(2);
const arg = (k: string): string | undefined => { const i = argv.indexOf(k); return i > -1 ? argv[i + 1] : undefined; };

async function main(): Promise<number> {
  const project = arg("--project") ? resolve(arg("--project")!) : null;
  const out = arg("--out");
  const reg: Record<string, { motion: "continuous" | "enter"; source: string }> = {};
  for (const [id, d] of Object.entries(builtinVisuals)) reg[id] = { motion: d.motion ?? "enter", source: "builtin" };
  if (project) {
    const entry = ["index.ts", "index.js"].map((f) => resolve(project, "visuals", f)).find((f) => existsSync(f));
    if (entry) {
      try {
        const mod = await import(pathToFileURL(entry).href);
        for (const v of (mod.default ?? []) as VisualDef[]) reg[v.id] = { motion: v.motion ?? "enter", source: "project" };
      } catch (e) {
        console.error(`could not import the project's visuals (${entry}): ${(e as Error).message}`);
        return 3; // the manifest would be incomplete: say so instead of silently treating every project visual as still
      }
    }
  }
  const json = JSON.stringify({ schema: 1, visuals: reg }, null, 2);
  if (out) { mkdirSync(dirname(resolve(out)), { recursive: true }); writeFileSync(resolve(out), json + "\n"); }
  console.log(`visuals manifest: ${Object.keys(reg).length} visuals, ${Object.values(reg).filter((v) => v.motion === "continuous").length} continuous${out ? ` -> ${out}` : ""}`);
  return 0;
}
main().then((c) => process.exit(c), (e) => { console.error(e); process.exit(4); });
