import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

type WordFrame = { text: string; startFrame: number; endFrame: number };

// Word-synced subtitle band (karaoke style), driven by the step's per-word
// timeline. Token-faithful so it reads on any theme (surface-2 scrim + --text,
// active word in --accent). Rendered as an overlay above each step's block.
export const Captions: React.FC<{ words: WordFrame[] }> = ({ words }) => {
  const frame = useCurrentFrame();
  if (!words || words.length === 0) return null;
  return (
    <AbsoluteFill style={{
      justifyContent: "flex-end", alignItems: "center",
      padding: "0 0 56px", pointerEvents: "none", zIndex: 5,
    }}>
      <div style={{
        maxWidth: "78%", display: "flex", flexWrap: "wrap",
        gap: "0.08em 0.34em", justifyContent: "center", textAlign: "center",
        background: "var(--surface-2)", border: "1px solid var(--rule)",
        borderRadius: 10, padding: "14px 26px",
        fontFamily: "var(--font-body)", fontSize: 30, lineHeight: 1.3,
        boxShadow: "0 16px 50px rgba(0,0,0,0.35)",
      }}>
        {words.map((w, i) => {
          const active = frame >= w.startFrame && frame <= w.endFrame;
          const spoken = frame >= w.startFrame;
          return (
            <span key={i} style={{
              color: active ? "var(--accent)" : "var(--text)",
              opacity: spoken ? 1 : 0.42,
              fontWeight: active ? 700 : 500,
            }}>{w.text}</span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
