import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library block: a breaking-news banner card. A solid accent type-label
// box ("BREAKING" / "ALERT" / …) pops in, a banner strip holds an oversized
// display headline that slides up into view, and a mono source line fades in
// beneath. Rebuild of NOLAN's PIL NewsHeadlineRenderer — editorial, urgent.
// Wraps in <Surface>, uses ONLY semantic theme tokens, and is a pure function
// of useCurrentFrame(): reveals are timestamp-driven via `revealFrames`
// (computed upstream from the narration). No <Audio>, no random, no timers,
// no CSS transitions. `useCurrentFrame()` is relative to this step's start.
type Word = { text: string; startFrame: number; endFrame: number };
export type NewsHeadlineProps = {
  headline: string;
  source?: string;
  newsType?: "breaking" | "alert" | "update" | "exclusive" | "developing"; // default "breaking"
  label?: string; // overrides the type word
  // [label cue, headline cue, source cue]
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const TYPE_WORD: Record<NonNullable<NewsHeadlineProps["newsType"]>, string> = {
  breaking: "BREAKING",
  alert: "ALERT",
  update: "UPDATE",
  exclusive: "EXCLUSIVE",
  developing: "DEVELOPING",
};

export const NewsHeadline: React.FC<NewsHeadlineProps> = ({
  headline,
  source,
  newsType = "breaking",
  label,
  revealFrames,
  words = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rf0 = revealFrames[0] ?? 0; // label box pops in
  const rf1 = revealFrames[1] ?? rf0 + 12; // headline slides up
  const rf2 = revealFrames[2] ?? rf1 + 18; // source fades in

  const typeWord = (label ?? TYPE_WORD[newsType] ?? TYPE_WORD.breaking).toUpperCase();

  // ── Label box: scale + opacity pop on a damped spring ────────────────────
  const labelS = spring({ frame: frame - rf0, fps, durationInFrames: 16, config: { damping: 200 } });
  const labelScale = interpolate(labelS, [0, 1], [0.6, 1]);
  const labelAppear = interpolate(frame, [rf0, rf0 + 5], [0, 1], clamp);

  // ── Banner strip + headline: slide up + fade in ──────────────────────────
  const headS = spring({ frame: frame - rf1, fps, durationInFrames: 24, config: { damping: 200 } });
  const headY = interpolate(headS, [0, 1], [40, 0]);
  const headAppear = interpolate(frame, [rf1, rf1 + 8], [0, 1], clamp);

  // ── Source line: mono, mute, fades in ────────────────────────────────────
  const srcAppear = interpolate(frame, [rf2, rf2 + 8], [0, 1], clamp);

  // Headline is word-synced when a word timeline is given, else lands as a block.
  const tokens = headline.split(/\s+/).filter(Boolean);
  const hasWords = words.length > 0;

  return (
    <Surface>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          height: "100%",
          gap: "var(--space-5)",
        }}
      >
        {/* Type-label box */}
        <div
          style={{
            alignSelf: "flex-start",
            display: "inline-flex",
            alignItems: "center",
            padding: "var(--space-2) var(--space-4)",
            background: "var(--accent)",
            borderRadius: "var(--r-xs)",
            boxShadow: `0 0 28px var(--accent-glow)`,
            opacity: labelAppear,
            transform: `scale(${labelScale})`,
            transformOrigin: "left center",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontWeight: 700,
              fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)",
              textTransform: "uppercase",
              color: "var(--surface)",
            }}
          >
            {typeWord}
          </span>
        </div>

        {/* Banner strip holding the headline */}
        <div
          style={{
            background: "var(--surface-2)",
            borderLeft: "var(--bw-4, 5px) solid var(--accent)",
            borderRadius: "var(--r-sm)",
            boxShadow: "var(--elev-3)",
            padding: "var(--space-5) var(--space-6)",
            opacity: headAppear,
            transform: `translateY(${headY}px)`,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              fontFamily: "var(--font-display-cn)",
              fontWeight: 800,
              fontSize: "var(--t-h1)",
              lineHeight: "var(--lh-head)",
              letterSpacing: "var(--track-tight)",
              color: "var(--text)",
            }}
          >
            {hasWords ? (
              <div style={{ display: "flex", flexWrap: "wrap" }}>
                {tokens.map((tok, i) => {
                  const wt = words[i];
                  const rf = wt ? wt.startFrame : rf1 + i * 3;
                  const s = spring({ frame: frame - rf, fps, durationInFrames: 14, config: { damping: 200 } });
                  const y = interpolate(s, [0, 1], [100, 0]);
                  const appear = interpolate(frame, [rf, rf + 4], [0, 1], clamp);
                  return (
                    <span key={i} style={{ overflow: "hidden", paddingBottom: "0.08em", marginRight: "0.28em" }}>
                      <span
                        style={{
                          display: "inline-block",
                          transform: `translateY(${y}%)`,
                          opacity: appear,
                        }}
                      >
                        {tok}
                      </span>
                    </span>
                  );
                })}
              </div>
            ) : (
              headline
            )}
          </div>
        </div>

        {/* Source line */}
        {source ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-3)",
              opacity: srcAppear,
            }}
          >
            <span
              style={{
                width: "var(--space-6)",
                height: "var(--bw-2, 2px)",
                background: "var(--rule)",
                flex: "0 0 auto",
              }}
            />
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--t-micro)",
                letterSpacing: "var(--track-caps)",
                textTransform: "uppercase",
                color: "var(--text-mute)",
              }}
            >
              {source}
            </span>
          </div>
        ) : null}
      </div>
    </Surface>
  );
};
