// Patch reacticle's hardcoded Chinese UI strings -> English, for English articles.
// reacticle 0.2.6 has no locale switch; these are the user-facing labels that can
// surface in this article (TOC heading, CodeBlock copy buttons, default component
// labels). Re-run after any `npm install reacticle@latest`.
//
//   node scripts/patch-reacticle-i18n.mjs
import { readFileSync, writeFileSync } from "node:fs";

const FILE = "node_modules/reacticle/dist/index.js";
// Longest keys first so substrings (e.g. 摘要) don't pre-empt 摘要要点 / 复制失败.
const MAP = [
  ["复制为 Action Items", "Copy as Action Items"],
  ["复制为 Prompt", "Copy as Prompt"],
  ["导出 PDF（打印）", "Export PDF (print)"],
  ["复制失败", "Copy failed"],
  ["已复制", "Copied"],
  ["复制", "Copy"],
  ["摘要要点", "Key points"],
  ["摘要行", "Summary"],
  ["摘要", "Summary"],
  ["目录", "Contents"],
  ["结论", "Conclusion"],
  ["补充说明", "Note"],
  ["旁注内容", "Aside"],
  ["注意", "Warning"],
  ["原则", "Principle"],
  ["能力", "Capability"],
  ["导出", "Export"],
];

let src = readFileSync(FILE, "utf8");
let total = 0;
for (const [zh, en] of MAP) {
  const parts = src.split(zh);
  const n = parts.length - 1;
  if (n > 0) {
    src = parts.join(en);
    total += n;
    console.log(`  ${zh} -> ${en}  (${n})`);
  }
}
writeFileSync(FILE, src);
console.log(`patched ${total} occurrences in ${FILE}`);
