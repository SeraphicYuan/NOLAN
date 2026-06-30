import React from "react";
import { AbsoluteFill } from "remotion";

// Shared theme-faithful stage: solid --surface + the theme's --surface-pattern
// overlay (mirrors the skill's .stage-frame::after) + standard stage padding.
// Every block wraps its content in <Surface> so all 23 themes apply unchanged.
export const Surface: React.FC<{ children: React.ReactNode; pad?: boolean }> = ({ children, pad = true }) => (
  <AbsoluteFill style={{ backgroundColor: "var(--surface)", color: "var(--text)", fontFamily: "var(--font-body)" }}>
    <AbsoluteFill style={{
      backgroundImage: "var(--surface-pattern, none)",
      backgroundSize: "var(--surface-pattern-size, auto)",
      mixBlendMode: "var(--surface-pattern-blend, normal)",
      opacity: "var(--surface-pattern-opacity, 1)",
    } as React.CSSProperties} />
    <AbsoluteFill style={{ padding: pad ? "var(--stage-pad-y) var(--stage-pad-x)" : 0, zIndex: 1 }}>
      {children}
    </AbsoluteFill>
  </AbsoluteFill>
);
