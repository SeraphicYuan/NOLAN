import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library block: a broadcast lower-third ID card — name + title with a
// vertical accent bar, anchored to the lower third of the frame. Rebuild of
// NOLAN's PIL `LowerThirdRenderer`. Wraps content in <Surface>, uses ONLY
// semantic theme tokens, and is a pure function of `useCurrentFrame()`.
// `useCurrentFrame()` is relative to this step's start.
type Word = { text: string; startFrame: number; endFrame: number };
export type LowerThirdProps = {
  name: string;
  title?: string;
  align?: "left" | "right"; // default "left"
  revealFrames: number[]; // [in cue]
  // Per-word timeline for THIS step (step-relative frames). The Chapter driver
  // passes this to every block; unused here but kept for a uniform signature.
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const LowerThird: React.FC<LowerThirdProps> = ({
  name,
  title,
  align = "left",
  revealFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const cue = revealFrames[0] ?? 0;
  const isLeft = align === "left";

  // The accent bar wipes in first (scaleY 0 -> 1, anchored from the bottom).
  const barS = spring({ frame: frame - cue, fps, durationInFrames: 14, config: { damping: 200 } });
  const barScale = interpolate(barS, [0, 1], [0, 1], clamp);

  // The name slides out from the bar (toward the content side) and fades in,
  // starting just after the bar begins to grow.
  const nameRf = cue + 4;
  const nameS = spring({ frame: frame - nameRf, fps, durationInFrames: 18, config: { damping: 200 } });
  const nameDx = interpolate(nameS, [0, 1], [isLeft ? -36 : 36, 0]);
  const nameOpacity = interpolate(frame, [nameRf, nameRf + 6], [0, 1], clamp);

  // The title fades up just after the name has settled.
  const titleRf = cue + 12;
  const titleOpacity = interpolate(frame, [titleRf, titleRf + 7], [0, 1], clamp);
  const titleDy = interpolate(
    spring({ frame: frame - titleRf, fps, durationInFrames: 16, config: { damping: 200 } }),
    [0, 1],
    [8, 0],
  );

  return (
    <Surface>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
          alignItems: isLeft ? "flex-start" : "flex-end",
          height: "100%",
          // Anchor the card to ~70% down the frame: leave the bottom ~30% as
          // breathing room beneath the ID card.
          paddingBottom: "30%",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: isLeft ? "row" : "row-reverse",
            alignItems: "stretch",
            gap: "var(--space-4)",
            // Generous side padding flush to the chosen edge.
            paddingLeft: isLeft ? "var(--space-2)" : 0,
            paddingRight: isLeft ? 0 : "var(--space-2)",
            textAlign: isLeft ? "left" : "right",
          }}
        >
          {/* Vertical accent bar — wipes in from the bottom. */}
          <div
            style={{
              flex: "0 0 auto",
              width: "var(--rule-w, 4px)",
              alignSelf: "stretch",
              background: "var(--accent)",
              boxShadow: "0 0 16px var(--accent-glow)",
              transform: `scaleY(${barScale})`,
              transformOrigin: "bottom",
              borderRadius: "999px",
            }}
          />

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: isLeft ? "flex-start" : "flex-end",
              gap: "var(--space-3)",
            }}
          >
            <div
              style={{
                fontFamily: "var(--font-display, var(--font-display-cn))",
                fontSize: "var(--t-h2)",
                lineHeight: 1.05,
                color: "var(--text)",
                transform: `translateX(${nameDx}px)`,
                opacity: nameOpacity,
              }}
            >
              {name}
            </div>

            {title ? (
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--t-micro)",
                  letterSpacing: "var(--track-caps)",
                  textTransform: "uppercase",
                  color: "var(--text-mute)",
                  transform: `translateY(${titleDy}px)`,
                  opacity: titleOpacity,
                }}
              >
                {title}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </Surface>
  );
};
