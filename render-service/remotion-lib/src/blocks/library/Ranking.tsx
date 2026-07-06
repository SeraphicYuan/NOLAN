import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// REFERENCE BLOCK for the chapter library. Rebuild of NOLAN's PIL RankingRenderer:
// a numbered leaderboard whose rows reveal top-to-bottom at frames given in
// `revealFrames` (computed upstream from narration word timestamps). The #1 row is
// emphasized on an --accent-fill band. Wraps content in <Surface>, uses ONLY
// semantic theme tokens, and is a pure function of useCurrentFrame(). No <Audio>.
type Word = { text: string; startFrame: number; endFrame: number };
type RankItem = { name: string; value?: string };

export type RankingProps = {
  title?: string;
  items: RankItem[]; // in rank order, 2–6
  highlightTop?: boolean; // emphasize #1 (default true)
  revealFrames: number[]; // one cue per item
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Ranking: React.FC<RankingProps> = ({
  title,
  items,
  highlightTop = true,
  revealFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title fades in first, ahead of the earliest row.
  const titleFade = interpolate(frame, [0, 10], [0, 1], clamp);

  return (
    <Surface>
      {title ? (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)",
            textTransform: "uppercase",
            color: "var(--text-mute)",
            opacity: titleFade,
          }}
        >
          {title}
        </div>
      ) : null}

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-5)",
          marginTop: title ? "var(--space-9)" : 0,
        }}
      >
        {items.map((it, i) => {
          const rf = revealFrames[i] ?? 0;
          const appear = interpolate(frame, [rf, rf + 6], [0, 1], clamp);
          const rise = spring({
            frame: frame - rf,
            fps,
            durationInFrames: 18,
            config: { damping: 200 },
          });
          const y = interpolate(rise, [0, 1], [28, 0]);

          const isTop = highlightTop && i === 0;
          const nameColor = isTop ? "var(--accent)" : "var(--text-2)";

          return (
            <div
              key={i}
              style={{
                position: "relative",
                display: "flex",
                alignItems: "baseline",
                gap: "var(--space-6)",
                padding: isTop
                  ? "var(--space-5) var(--space-6)"
                  : "var(--space-3) var(--space-6)",
                background: isTop ? "var(--accent-fill)" : "transparent",
                borderLeft: isTop
                  ? "var(--space-2) solid var(--accent)"
                  : "var(--space-2) solid transparent",
                boxShadow: isTop ? "0 0 40px var(--accent-glow)" : "none",
                borderBottom: isTop ? "none" : "var(--rule-w) solid var(--rule)",
                transform: `translateY(${y}px)`,
                opacity: appear,
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-display-en)",
                  fontWeight: 900,
                  fontSize: "var(--t-h2)",
                  lineHeight: 1,
                  color: "var(--accent)",
                  fontVariantNumeric: "tabular-nums",
                  opacity: isTop ? 1 : 0.7,
                }}
              >
                {String(i + 1).padStart(2, "0")}
              </span>

              <span
                style={{
                  flex: 1,
                  fontFamily: "var(--font-display, var(--font-display-cn))",
                  fontWeight: isTop ? 900 : 700,
                  fontSize: "var(--t-h2)",
                  lineHeight: 1.1,
                  color: nameColor,
                }}
              >
                {it.name}
              </span>

              {it.value != null ? (
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--t-body)",
                    fontVariantNumeric: "tabular-nums",
                    textAlign: "right",
                    color: isTop ? "var(--accent)" : "var(--text-mute)",
                  }}
                >
                  {it.value}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </Surface>
  );
};
