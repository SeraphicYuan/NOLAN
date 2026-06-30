import { fitText } from "@remotion/layout-utils";

// Auto-fit big type to its slot so a long line shrinks instead of overflowing /
// wrapping ugly. `@remotion/layout-utils` measureText runs in Chromium at render;
// we read the theme's font off the CSS var, fit each line within `withinWidth`,
// and use the smallest (so every line shares one size that fits), capped at `max`.
// Pure + deterministic (measurement is a function of text/font, not time).
export function fitFontSize(
  texts: string[],
  opts: { withinWidth: number; fontVar?: string; fontWeight?: number; max: number; min?: number },
): number {
  if (typeof document === "undefined") return opts.max;
  const fam =
    (opts.fontVar ? getComputedStyle(document.documentElement).getPropertyValue(opts.fontVar).trim() : "") ||
    "sans-serif";
  let size = opts.max;
  for (const t of texts) {
    if (!t.trim()) continue;
    try {
      const { fontSize } = fitText({
        text: t, withinWidth: opts.withinWidth, fontFamily: fam, fontWeight: opts.fontWeight ?? 700,
      });
      size = Math.min(size, fontSize);
    } catch {
      /* font not measurable yet — keep current cap */
    }
  }
  return Math.max(opts.min ?? 0, Math.min(opts.max, size));
}
