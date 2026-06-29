import React from "react";
import {
  AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig,
  interpolate, spring,
} from "remotion";

// A parameterized, step-aware "block": each item reveals at an explicit frame
// (computed from the narration's per-word timestamps — compute, don't capture).
type Item = { model: string; domain: string };
type Props = {
  title?: string;
  items: Item[];
  revealFrames: number[]; // frame at which item i appears (from word timestamps)
  audioSrc?: string;      // basename in public/, muxed by Remotion
  durationInFrames: number;
};

export const ListReveal: React.FC<Props> = ({ title, items, revealFrames, audioSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

  return (
    <AbsoluteFill style={{
      background: "#0b0b0c", color: "#f4f2ee", padding: "110px 130px",
      fontFamily: "Inter, Helvetica, Arial, sans-serif",
    }}>
      {audioSrc ? <Audio src={staticFile(audioSrc)} /> : null}

      {title ? (
        <div style={{
          fontSize: 26, letterSpacing: 6, textTransform: "uppercase",
          color: "#8a8a86", fontWeight: 600,
        }}>{title}</div>
      ) : null}

      <div style={{ display: "flex", flexDirection: "column", gap: 34, marginTop: 90 }}>
        {items.map((it, i) => {
          const rf = revealFrames[i] ?? 0;
          const s = spring({ frame: frame - rf, fps, durationInFrames: 16, config: { damping: 200 } });
          const appear = interpolate(frame, [rf, rf + 5], [0, 1], clamp);
          const x = interpolate(s, [0, 1], [-70, 0]);
          // once a later item has revealed, dim earlier ones to keep focus (context, not clutter)
          const nextRf = revealFrames[i + 1];
          const dim = nextRf != null && frame >= nextRf ? 0.4 : 1;

          return (
            <div key={i} style={{
              display: "flex", alignItems: "baseline", gap: 34,
              transform: `translateX(${x}px)`, opacity: appear * dim,
            }}>
              <span style={{ fontSize: 30, color: "#6f6f6b", fontVariantNumeric: "tabular-nums" }}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <span style={{ fontSize: 70, fontWeight: 800, lineHeight: 1 }}>{it.model}</span>
              <span style={{ flex: 1, height: 2, background: "rgba(255,255,255,0.12)" }} />
              <span style={{ fontSize: 44, fontWeight: 800, color: "#ff5a1f" }}>{it.domain}</span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
