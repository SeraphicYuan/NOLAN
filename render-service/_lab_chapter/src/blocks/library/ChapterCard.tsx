import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library blocks for structuring a long explainer. Both are pure
// functions of useCurrentFrame() — no random/date/timers/CSS-transitions — wrap
// their content in <Surface>, and use ONLY semantic theme tokens so all themes
// apply unchanged. `useCurrentFrame()` is step-relative (Remotion resets it per
// Series.Sequence); `revealFrames` are computed upstream from the narration's
// per-word timestamps. No <Audio> — the Chapter driver supplies narration.
//
//   ChapterCard — a section-divider / act card (big ordinal + title + rule).
//   EndCard     — a closing card (short takeaway list + citation line).

type Word = { text: string; startFrame: number; endFrame: number };

export type ChapterCardProps = {
  index?: number | string;     // big ordinal, e.g. 2 or "II"
  title: string;
  subtitle?: string;
  revealFrames: number[];      // [index cue, title cue]
  words: Word[];
  durationInFrames: number;
};

export type EndCardProps = {
  headline?: string;           // e.g. "Attention is all you need."
  takeaways?: string[];        // 2-4 bullet summary points
  source?: string;             // citation line (mono)
  revealFrames: number[];      // [headline cue, then takeaways stagger]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
// Cadence between sibling reveals, mirroring the --stagger-step token (~70ms)
// translated to whole frames for deterministic, font-safe timing.
const STAGGER = 8;

// ---------------------------------------------------------------------------
// ChapterCard — act / section divider
// ---------------------------------------------------------------------------
export const ChapterCard: React.FC<ChapterCardProps> = ({
  index,
  title,
  subtitle,
  revealFrames,
  words = [],
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Cues fall back to the first spoken word so the card still lands if the
  // upstream reveal schedule is short.
  const firstWord = words[0]?.startFrame ?? 0;
  const indexRf = revealFrames[0] ?? firstWord;
  const titleRf = revealFrames[1] ?? indexRf + STAGGER * 2;
  const ruleRf = indexRf + STAGGER; // wipe rides in between number and title

  // Big ordinal: scales down a touch and fades up, with an accent glow that
  // blooms on entry then settles — "drawing in big".
  const idS = spring({ frame: frame - indexRf, fps, durationInFrames: 22, config: { damping: 200 } });
  const idAppear = interpolate(frame, [indexRf, indexRf + 6], [0, 1], clamp);
  const idScale = interpolate(idS, [0, 1], [1.12, 1]);
  const idGlow = interpolate(idS, [0, 1], [4, 34]);

  // Accent rule wipes horizontally left-to-right.
  const ruleW = interpolate(
    spring({ frame: frame - ruleRf, fps, durationInFrames: 20, config: { damping: 200 } }),
    [0, 1],
    [0, 100],
    clamp,
  );

  // Title masks up from below.
  const titleS = spring({ frame: frame - titleRf, fps, durationInFrames: 18, config: { damping: 200 } });
  const titleY = interpolate(titleS, [0, 1], [110, 0]);
  const titleAppear = interpolate(frame, [titleRf, titleRf + 5], [0, 1], clamp);

  const subRf = titleRf + STAGGER;
  const subAppear = interpolate(frame, [subRf, subRf + 6], [0, 1], clamp);

  // Whole card eases out as the chapter ends so the cut feels intentional.
  const outro = interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0.88], clamp);

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%", opacity: outro }}>
        {index != null ? (
          <div style={{
            fontFamily: "var(--hero-num-font)",
            fontStyle: "var(--hero-num-style)" as React.CSSProperties["fontStyle"],
            fontWeight: "var(--hero-num-weight)" as React.CSSProperties["fontWeight"],
            fontSize: "var(--t-display-1)",
            lineHeight: 0.9,
            letterSpacing: "var(--hero-num-track)",
            color: "var(--accent)",
            textShadow: `0 0 ${idGlow}px var(--accent-glow)`,
            opacity: idAppear,
            transform: `scale(${idScale})`,
            transformOrigin: "left center",
            fontVariantNumeric: "tabular-nums",
            marginBottom: "var(--space-6)",
          }}>{index}</div>
        ) : null}

        <div style={{
          height: "var(--rule-w)",
          width: `${ruleW}%`,
          maxWidth: "62%",
          background: "var(--accent)",
          marginBottom: "var(--space-8)",
        }} />

        <div style={{ overflow: "hidden", paddingBottom: "0.08em" }}>
          <div style={{
            fontFamily: "var(--font-display-cn)",
            fontWeight: 900,
            fontSize: "var(--t-h1)",
            lineHeight: 1.05,
            color: "var(--text)",
            transform: `translateY(${titleY}%)`,
            opacity: titleAppear,
          }}>{title}</div>
        </div>

        {subtitle ? (
          <div style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)",
            textTransform: "uppercase",
            color: "var(--text-mute)",
            marginTop: "var(--space-5)",
            opacity: subAppear,
          }}>{subtitle}</div>
        ) : null}
      </div>
    </Surface>
  );
};

// ---------------------------------------------------------------------------
// EndCard — closing / takeaway card
// ---------------------------------------------------------------------------
export const EndCard: React.FC<EndCardProps> = ({
  headline,
  takeaways = [],
  source,
  revealFrames,
  words = [],
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headRf = revealFrames[0] ?? words[0]?.startFrame ?? 0;
  // Each takeaway gets revealFrames[i+1] if scheduled, else a steady stagger.
  const cueFor = (i: number) => revealFrames[i + 1] ?? headRf + STAGGER * 2 + i * STAGGER;

  // Headline masks up.
  const headS = spring({ frame: frame - headRf, fps, durationInFrames: 18, config: { damping: 200 } });
  const headY = interpolate(headS, [0, 1], [90, 0]);
  const headAppear = interpolate(frame, [headRf, headRf + 5], [0, 1], clamp);

  // Source fades in last — after the final spoken word, anchored to the end.
  const lastWord = words.length ? words[words.length - 1].endFrame : cueFor(takeaways.length - 1);
  const sourceRf = Math.min(
    Math.max(lastWord, cueFor(Math.max(takeaways.length - 1, 0)) + STAGGER),
    Math.max(durationInFrames - 18, 0),
  );
  const sourceAppear = interpolate(frame, [sourceRf, sourceRf + 8], [0, 1], clamp);

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        {headline ? (
          <div style={{ overflow: "hidden", paddingBottom: "0.08em", marginBottom: "var(--space-9)" }}>
            <div style={{
              fontFamily: "var(--font-display-en)",
              fontWeight: 900,
              fontSize: "var(--t-display-2)",
              lineHeight: 1.02,
              letterSpacing: "var(--hero-num-track)",
              color: "var(--text)",
              transform: `translateY(${headY}%)`,
              opacity: headAppear,
            }}>{headline}</div>
          </div>
        ) : null}

        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
          {takeaways.map((t, i) => {
            const rf = cueFor(i);
            const s = spring({ frame: frame - rf, fps, durationInFrames: 16, config: { damping: 200 } });
            const x = interpolate(s, [0, 1], [-48, 0]);
            const appear = interpolate(frame, [rf, rf + 5], [0, 1], clamp);
            return (
              <div key={i} style={{
                display: "flex",
                alignItems: "baseline",
                gap: "var(--space-5)",
                transform: `translateX(${x}px)`,
                opacity: appear,
              }}>
                <span style={{
                  flex: "none",
                  width: "var(--space-3)",
                  height: "var(--space-3)",
                  background: "var(--accent)",
                  boxShadow: `0 0 ${interpolate(s, [0, 1], [0, 12], clamp)}px var(--accent-glow)`,
                  transform: "translateY(-0.12em)",
                }} />
                <span style={{
                  fontFamily: "var(--font-display-cn)",
                  fontWeight: 700,
                  fontSize: "var(--t-h2)",
                  lineHeight: 1.2,
                  color: "var(--text-2)",
                }}>{t}</span>
              </div>
            );
          })}
        </div>

        {source ? (
          <div style={{
            marginTop: "var(--space-12)",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)",
            color: "var(--text-mute)",
            opacity: sourceAppear,
          }}>{source}</div>
        ) : null}
      </div>
    </Surface>
  );
};
