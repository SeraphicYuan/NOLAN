import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library block: a social-post (X/Twitter-style) card mockup — a rebuild
// of NOLAN's PIL `TweetCardRenderer`. A rounded --surface-2 card slides up and
// fades in, carrying an avatar disc, display name (+ optional verified check),
// handle, post content, a divider, and timestamp + repost/like metrics. Wraps in
// <Surface>, uses ONLY semantic theme tokens, and is a pure function of
// useCurrentFrame(): reveals are timestamp-driven via `revealFrames` (computed
// upstream from the narration) and the content can word-sync via `words`. No
// <Audio>, no random, no Date, no timers, no CSS transitions. `useCurrentFrame()`
// is relative to this step's start.
type Word = { text: string; startFrame: number; endFrame: number };
export type TweetCardProps = {
  content: string;
  username: string;
  handle: string; // e.g. "@handle"
  timestamp?: string;
  retweets?: string; // e.g. "12.4K"
  likes?: string;
  verified?: boolean;
  // [card cue, content cue]
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const TweetCard: React.FC<TweetCardProps> = ({
  content = "",
  username = "",
  handle = "",
  timestamp,
  retweets,
  likes,
  verified = false,
  revealFrames,
  words = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rf0 = revealFrames[0] ?? 0; // card cue
  const rf1 = revealFrames[1] ?? rf0 + 18; // content cue

  // Whole card slides up + fades in at the card cue.
  const cardS = spring({ frame: frame - rf0, fps, durationInFrames: 26, config: { damping: 200 } });
  const cardY = interpolate(cardS, [0, 1], [40, 0]);
  const cardAppear = interpolate(frame, [rf0, rf0 + 8], [0, 1], clamp);

  // Header (avatar + name/handle) eases in right behind the card body.
  const headAppear = interpolate(frame, [rf0 + 3, rf0 + 12], [0, 1], clamp);

  // Verified check pops with a tiny spring after the name lands.
  const vS = spring({ frame: frame - (rf0 + 8), fps, durationInFrames: 16, config: { damping: 12, stiffness: 160 } });
  const vScale = interpolate(vS, [0, 1], [0, 1], clamp);

  const initial = (username.trim()[0] ?? "?").toUpperCase();

  // Content tokens: word-by-word if a word timeline is present, else a single
  // block fade at the content cue.
  const tokens = content.split(/\s+/).filter(Boolean);
  const hasWords = words.length > 0;
  const stagger = 3; // fallback per-word cadence
  const contentAppear = interpolate(frame, [rf1, rf1 + 10], [0, 1], clamp);

  // Divider draws in (scaleX, left-anchored) after the content begins.
  const divS = spring({ frame: frame - (rf1 + 6), fps, durationInFrames: 20, config: { damping: 200 } });
  const divScale = interpolate(divS, [0, 1], [0, 1], clamp);

  // Metrics row rides up + fades in last.
  const metS = spring({ frame: frame - (rf1 + 10), fps, durationInFrames: 18, config: { damping: 200 } });
  const metY = interpolate(metS, [0, 1], [12, 0]);
  const metAppear = interpolate(frame, [rf1 + 10, rf1 + 18], [0, 1], clamp);

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        <div
          style={{
            maxWidth: "26em",
            width: "100%",
            margin: "0 auto",
            boxSizing: "border-box",
            padding: "var(--space-6)",
            background: "var(--surface-2)",
            border: "1px solid var(--rule)",
            borderRadius: "var(--r-md)",
            boxShadow: "var(--elev-3)",
            transform: `translateY(${cardY}px)`,
            opacity: cardAppear,
          }}
        >
          {/* Header: avatar + name/handle */}
          <div style={{ display: "flex", flexDirection: "row", gap: "var(--space-4)", alignItems: "center", opacity: headAppear }}>
            <div
              aria-hidden
              style={{
                flex: "0 0 auto",
                width: "3em",
                height: "3em",
                borderRadius: "50%",
                background: "var(--accent-fill)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontFamily: "var(--font-display-cn)",
                fontWeight: 700,
                fontSize: "var(--t-h2)",
                color: "var(--accent)",
                boxShadow: "0 0 18px var(--accent-glow)",
                userSelect: "none",
              }}
            >
              {initial}
            </div>

            <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
              <div
                style={{
                  display: "flex",
                  flexDirection: "row",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  fontFamily: "var(--font-display-cn)",
                  fontWeight: 700,
                  fontSize: "var(--t-body)",
                  color: "var(--text)",
                  letterSpacing: "var(--track-tight)",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{username}</span>
                {verified ? (
                  <span
                    aria-hidden
                    style={{
                      flex: "0 0 auto",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: "1.15em",
                      height: "1.15em",
                      borderRadius: "50%",
                      background: "var(--accent-fill)",
                      color: "var(--accent)",
                      fontSize: "0.72em",
                      fontWeight: 900,
                      lineHeight: 1,
                      transform: `scale(${vScale})`,
                    }}
                  >
                    ✓
                  </span>
                ) : null}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--t-micro)",
                  color: "var(--text-mute)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {handle}
              </div>
            </div>
          </div>

          {/* Post content */}
          <div
            style={{
              marginTop: "var(--space-5)",
              display: "flex",
              flexWrap: "wrap",
              fontFamily: "var(--font-body)",
              fontWeight: 400,
              fontSize: "var(--t-h2)",
              lineHeight: 1.4,
              color: "var(--text)",
            }}
          >
            {hasWords
              ? tokens.map((tok, i) => {
                  const wt = words[i];
                  const rf = wt ? wt.startFrame : rf1 + i * stagger;
                  const appear = interpolate(frame, [rf, rf + 6], [0, 1], clamp);
                  const yS = spring({ frame: frame - rf, fps, durationInFrames: 12, config: { damping: 200 } });
                  const y = interpolate(yS, [0, 1], [10, 0]);
                  return (
                    <span
                      key={i}
                      style={{
                        display: "inline-block",
                        marginRight: "0.28em",
                        opacity: appear,
                        transform: `translateY(${y}px)`,
                      }}
                    >
                      {tok}
                    </span>
                  );
                })
              : <span style={{ opacity: contentAppear }}>{content}</span>}
          </div>

          {/* Divider */}
          <div
            style={{
              marginTop: "var(--space-5)",
              height: 1,
              background: "var(--rule)",
              transformOrigin: "left",
              transform: `scaleX(${divScale})`,
            }}
          />

          {/* Metrics: timestamp · reposts · likes */}
          <div
            style={{
              marginTop: "var(--space-4)",
              display: "flex",
              flexDirection: "row",
              flexWrap: "wrap",
              alignItems: "center",
              gap: "var(--space-5)",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)",
              color: "var(--text-mute)",
              opacity: metAppear,
              transform: `translateY(${metY}px)`,
            }}
          >
            {timestamp ? <span>{timestamp}</span> : null}
            {retweets ? (
              <span>
                <span style={{ color: "var(--text-2)" }}>{retweets}</span> Reposts
              </span>
            ) : null}
            {likes ? (
              <span>
                <span style={{ color: "var(--accent)" }}>{likes}</span> Likes
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </Surface>
  );
};
