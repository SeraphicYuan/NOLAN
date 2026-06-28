// figures/ProportionBar.tsx — proportion / capacity visual (weighted segments in a bar).
//
// Theme-portable: styled via --ra-* tokens through primitives + helpers.
// SSR-safe: presentational, no state/effects. Responsive: flex weights + rem, wraps on mobile.
import type { CSSProperties, ReactNode } from "react";
import { FRow, FStack, Chip, figureTokens as T, figureRadius as rad, figureText as tx } from "./primitives";

export type BarSegment = {
  label: ReactNode;
  sub?: ReactNode;
  weight: number;
  dashed?: boolean;
  hatch?: boolean;
  tag?: ReactNode;
};

/** One weighted block in the bar. flexGrow = weight so widths reflect proportion. */
function Segment({ seg }: { seg: BarSegment }): JSX.Element {
  // Solid blocks sit on surface-2; dashed (headroom) blocks on the lighter surface.
  const baseBg = seg.dashed ? T.surface : T.surface2;
  // hatch overlays a faint diagonal stripe to read as "stretch / spare capacity".
  const background = seg.hatch
    ? `repeating-linear-gradient(45deg, ${T.accentSoft} 0, ${T.accentSoft} 2px, transparent 2px, transparent 9px), ${baseBg}`
    : baseBg;
  const style: CSSProperties = {
    flex: `${seg.weight} 1 12rem`,
    minHeight: "3rem",
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    gap: "0.15rem",
    padding: "0.6rem 0.75rem",
    borderRadius: rad("sm"),
    border: `1px ${seg.dashed ? "dashed" : "solid"} ${T.border}`,
    background,
  };
  return (
    <div style={style}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span style={{ fontWeight: 700, color: T.heading }}>{seg.label}</span>
        {seg.tag !== undefined && (
          <span style={{ marginLeft: "auto" }}>
            <Chip tone="soft">{seg.tag}</Chip>
          </span>
        )}
      </div>
      {seg.sub !== undefined && <div style={{ color: T.muted, fontSize: tx("xs") }}>{seg.sub}</div>}
    </div>
  );
}

export function ProportionBar(props: { segments: BarSegment[]; caption?: ReactNode }): JSX.Element {
  const { segments, caption } = props;
  return (
    <FStack gap={2}>
      <FRow gap={2} wrap align="stretch">
        {segments.map((seg, i) => (
          <Segment key={i} seg={seg} />
        ))}
      </FRow>
      {caption !== undefined && (
        <div style={{ fontFamily: T.mono, fontSize: tx("xs"), color: T.faint }}>{caption}</div>
      )}
    </FStack>
  );
}
