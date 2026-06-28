// Shared helper for the runtime figures (Mermaid, Chart): read concrete values of
// the active theme's --ra-* tokens from a mounted, themed element. Used because
// mermaid/recharts want concrete colors, not CSS var() refs.
export function readVar(el: Element, name: string, fallback: string): string {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback;
}

export type ThemePalette = {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
  borderStrong: string;
  heading: string;
  text: string;
  muted: string;
  faint: string;
  accent: string;
  accentSoft: string;
  fontBody: string;
  /** a small categorical series palette derived from theme tokens */
  series: string[];
};

export function readPalette(el: Element): ThemePalette {
  const r = (n: string, f: string) => readVar(el, n, f);
  const accent = r("--ra-color-accent", "#3257d6");
  return {
    bg: r("--ra-color-bg", "#ffffff"),
    surface: r("--ra-color-surface", "#f5f5f2"),
    surface2: r("--ra-color-surface-2", "#ecebe6"),
    border: r("--ra-color-border", "#e3e1da"),
    borderStrong: r("--ra-color-border-strong", "#cfccc1"),
    heading: r("--ra-color-heading", "#1b1a17"),
    text: r("--ra-color-text", "#2b2a26"),
    muted: r("--ra-color-muted", "#6b6860"),
    faint: r("--ra-color-faint", "#98948a"),
    accent,
    accentSoft: r("--ra-color-accent-soft", "#e7e9ed"),
    fontBody: r("--ra-font-body", "system-ui, sans-serif"),
    series: [
      accent,
      r("--ra-color-info", accent),
      r("--ra-color-success", "#2f7d4f"),
      r("--ra-color-warn", "#c63d1a"),
      r("--ra-color-accent-strong", accent),
      r("--ra-color-muted", "#6b6860"),
    ],
  };
}
