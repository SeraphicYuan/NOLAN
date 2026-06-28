// figures/primitives.tsx — token-styled building blocks that figures compose from.
//
// Rules (so figures stay theme-portable and consistent):
//   • Style ONLY via --ra-* tokens with fallbacks. NEVER theme-specific tokens
//     (no --mc-yellow): use --ra-color-accent / -soft / -contrast so every theme restyles.
//   • SSR-safe: presentational only, no useState / effects.
//   • Responsive: flex/grid + %, never absolute-px layout.
import type { CSSProperties, ReactNode } from "react";

const T = {
  bg: "var(--ra-color-bg, #fff)",
  surface: "var(--ra-color-surface, #f6f5f2)",
  surface2: "var(--ra-color-surface-2, #ecebe6)",
  border: "var(--ra-color-border, #e3e1da)",
  borderStrong: "var(--ra-color-border-strong, #cfccc1)",
  heading: "var(--ra-color-heading, #1b1a17)",
  text: "var(--ra-color-text, #2b2a26)",
  muted: "var(--ra-color-muted, #6b6860)",
  faint: "var(--ra-color-faint, #98948a)",
  accent: "var(--ra-color-accent, #222)",
  accentSoft: "var(--ra-color-accent-soft, #eee)",
  accentContrast: "var(--ra-color-accent-contrast, #fff)",
  mono: "var(--ra-font-mono, ui-monospace, Menlo, monospace)",
  label: "var(--ra-font-label, inherit)",
  heads: "var(--ra-font-heading, Georgia, serif)",
};
const sp = (n: number) => `var(--ra-space-${n}, ${[0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5][n]}rem)`;
const rad = (k: "sm" | "md" | "lg" | "full") =>
  `var(--ra-radius-${k}, ${{ sm: "6px", md: "10px", lg: "16px", full: "999px" }[k]})`;
const tx = (k: string) => `var(--ra-text-${k})`;

/** Vertical flex stack. */
export function FStack({ gap = 3, style, children }: { gap?: number; style?: CSSProperties; children: ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap: sp(gap), ...style }}>{children}</div>;
}

/** Horizontal flex row (wraps by default). */
export function FRow({
  gap = 3,
  wrap = true,
  align = "stretch",
  justify = "flex-start",
  style,
  children,
}: {
  gap?: number;
  wrap?: boolean;
  align?: CSSProperties["alignItems"];
  justify?: CSSProperties["justifyContent"];
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: wrap ? "wrap" : "nowrap",
        alignItems: align,
        justifyContent: justify,
        gap: sp(gap),
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** Responsive auto-fit grid; collapses to one column on narrow screens. */
export function FGrid({ min = "14rem", gap = 3, style, children }: { min?: string; gap?: number; style?: CSSProperties; children: ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${min}, 1fr))`, gap: sp(gap), ...style }}>
      {children}
    </div>
  );
}

/** Surface card. variant: surface (default) · plain (paper) · accent (highlight fill). */
export function Card({
  variant = "surface",
  dashed = false,
  style,
  children,
}: {
  variant?: "surface" | "plain" | "accent";
  dashed?: boolean;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const bg = variant === "accent" ? T.accentSoft : variant === "plain" ? T.bg : T.surface;
  return (
    <div
      style={{
        background: bg,
        border: `1px ${dashed ? "dashed" : "solid"} ${T.border}`,
        borderRadius: rad("md"),
        padding: sp(4),
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** Small pill. tone: default · strong (ink fill) · soft (accent-soft) · struck (disabled). */
export function Chip({
  tone = "default",
  mono = false,
  style,
  children,
}: {
  tone?: "default" | "strong" | "soft" | "struck";
  mono?: boolean;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const map: Record<string, CSSProperties> = {
    default: { background: T.bg, border: `1px solid ${T.borderStrong}`, color: T.heading },
    strong: { background: T.accent, border: `1px solid ${T.accent}`, color: T.accentContrast },
    soft: { background: T.accentSoft, border: `1px solid ${T.accentSoft}`, color: T.heading },
    struck: { background: "transparent", border: `1px dashed ${T.border}`, color: T.faint, textDecoration: "line-through" },
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: sp(2),
        fontSize: tx("xs"),
        fontFamily: mono ? T.mono : T.label,
        borderRadius: rad("full"),
        padding: "0.12rem 0.55rem",
        whiteSpace: "nowrap",
        ...map[tone],
        ...style,
      }}
    >
      {children}
    </span>
  );
}

/** Rotated accent "sticker" label (uppercase, small). */
export function Sticker({ rotate = -2, style, children }: { rotate?: number; style?: CSSProperties; children: ReactNode }) {
  return (
    <span
      style={{
        alignSelf: "flex-start",
        fontFamily: T.label,
        fontSize: tx("xs"),
        fontWeight: 700,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: T.heading,
        background: T.accentSoft,
        borderRadius: rad("sm"),
        padding: "0.18rem 0.5rem",
        transform: `rotate(${rotate}deg)`,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

/** Circular numbered/iconic badge (accent fill). */
export function NumberBadge({ children, size = 1.6, style }: { children: ReactNode; size?: number; style?: CSSProperties }) {
  return (
    <span
      style={{
        flex: "0 0 auto",
        display: "inline-grid",
        placeItems: "center",
        width: `${size}rem`,
        height: `${size}rem`,
        borderRadius: rad("full"),
        background: T.accentSoft,
        color: T.heading,
        fontWeight: 700,
        fontSize: tx("sm"),
        ...style,
      }}
    >
      {children}
    </span>
  );
}

/** Directional connector. */
export function Arrow({ dir = "right", style }: { dir?: "right" | "down"; style?: CSSProperties }) {
  return (
    <span aria-hidden="true" style={{ color: T.faint, fontSize: tx("lg"), lineHeight: 1, alignSelf: "center", ...style }}>
      {dir === "down" ? "↓" : "→"}
    </span>
  );
}

/** Small uppercase field label. */
export function FLabel({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <span
      style={{
        fontFamily: T.label,
        fontSize: tx("xs"),
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: T.faint,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

/** Inline accent underline highlight (theme-safe emphasis — never colors the text). */
export function Highlight({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <span style={{ boxShadow: `inset 0 -0.4em 0 ${T.accentSoft}`, ...style }}>{children}</span>;
}

export { T as figureTokens, sp as figureSpace, rad as figureRadius, tx as figureText };
