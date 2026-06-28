// add-figure.mjs — local "add by name" for the figure registry (registry.json).
// Installs an item's npm deps and copies its files into the current article workspace.
// Run FROM the article workspace:
//   node <skill>/scripts/add-figure.mjs figure-mermaid
//   node <skill>/scripts/add-figure.mjs figure-chart
import { readFileSync, copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

const SKILL = dirname(dirname(fileURLToPath(import.meta.url)));
const reg = JSON.parse(readFileSync(join(SKILL, "registry.json"), "utf8"));
const name = process.argv[2];
const item = reg.items.find((i) => i.name === name);
if (!item) {
  console.error(`✗ unknown item "${name}". Available: ${reg.items.map((i) => i.name).join(", ")}`);
  process.exit(1);
}

// 1. install npm deps (DrvFs-safe: fall back to --no-bin-links)
const deps = (item.dependencies || []).filter((d) => d !== "reacticle"); // reacticle already present
if (deps.length) {
  console.log(`▸ installing: ${deps.join(" ")}`);
  try {
    execSync(`npm install ${deps.join(" ")}`, { stdio: "inherit" });
  } catch {
    console.log("  (retrying with --no-bin-links)");
    execSync(`npm install --no-bin-links ${deps.join(" ")}`, { stdio: "inherit" });
  }
}

// 2. copy files to their targets (under the current workspace)
for (const f of item.files) {
  const src = join(SKILL, f.path);
  const dest = join(process.cwd(), f.target);
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(src, dest);
  console.log(`▸ ${f.target}`);
}
console.log(`✓ added ${name}. Import directly: ${item.meta?.importPath ?? "(see registry.md)"}`);
if (item.meta?.bundleCostMB) console.log(`  note: ~+${item.meta.bundleCostMB} MB to the article when used.`);
