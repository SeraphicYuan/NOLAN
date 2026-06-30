import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// SourceCitation — a rebuild of NOLAN's PIL SourceCitationRenderer as a pure,
// theme-faithful Remotion block. A flush-left source-attribution card: a small
// mono "SOURCE" caps label over a short accent rule, the source title set big
// in the display face, then the publication / author / date / url stacked in
// mono beneath. Pure function of useCurrentFrame() — no random/date/timers/
// CSS-transitions — wrapped in <Surface>, using ONLY semantic theme tokens so
// all themes apply unchanged. `useCurrentFrame()` is step-relative; the
// `revealFrames` are computed upstream from the narration's per-word stamps.

type Word = { text: string; startFrame: number; endFrame: number };

export type SourceCitationProps = {
  sourceName: string;
  publication?: string;
  date?: string;
  author?: string;
  url?: string;
  revealFrames: number[];   // [source cue, then meta stagger]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
// Cadence between sibling reveals, mirroring the --stagger-step token (~70ms)
// translated to whole frames for deterministic, font-safe timing.
const STAGGER = 8;

export const SourceCitation: React.FC<SourceCitationProps> = ({
  sourceName,
  publication,
  date,
  author,
  url,
  revealFrames,
  words = [],
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Cues fall back to the first spoken word so the card still lands if the
  // upstream reveal schedule is short.
  const firstWord = words[0]?.startFrame ?? 0;
  const sourceRf = revealFrames[0] ?? firstWord;
  // The label + rule lead in just ahead of the title.
  const labelRf = Math.max(sourceRf - STAGGER, 0);

  // Label fades in.
  const labelAppear = interpolate(frame, [labelRf, labelRf + 6], [0, 1], clamp);

  // Accent rule wipes horizontally left-to-right under the label.
  const ruleW = interpolate(
    spring({ frame: frame - labelRf, fps, durationInFrames: 18, config: { damping: 200 } }),
    [0, 1],
    [0, 100],
    clamp,
  );

  // Source title masks up from below and fades in at the primary cue.
  const titleS = spring({ frame: frame - sourceRf, fps, durationInFrames: 18, config: { damping: 200 } });
  const titleY = interpolate(titleS, [0, 1], [80, 0]);
  const titleAppear = interpolate(frame, [sourceRf, sourceRf + 6], [0, 1], clamp);

  // Meta lines fade in staggered below the title. Each takes revealFrames[i+1]
  // when scheduled, else a steady stagger off the title cue.
  const meta = [
    { label: "PUBLICATION", value: publication, color: "var(--text-2)" },
    { label: "AUTHOR", value: author, color: "var(--text-2)" },
    { label: "DATE", value: date, color: "var(--text-mute)" },
    { label: "URL", value: url, color: "var(--text-mute)" },
  ].filter((m) => m.value);

  const cueFor = (i: number) => revealFrames[i + 1] ?? sourceRf + STAGGER * 2 + i * STAGGER;

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        <div style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--t-micro)",
          letterSpacing: "var(--track-caps)",
          textTransform: "uppercase",
          color: "var(--text-mute)",
          opacity: labelAppear,
          marginBottom: "var(--space-4)",
        }}>SOURCE</div>

        <div style={{
          height: "var(--rule-w)",
          width: `${ruleW}%`,
          maxWidth: "var(--space-12)",
          background: "var(--accent)",
          marginBottom: "var(--space-6)",
        }} />

        <div style={{ overflow: "hidden", paddingBottom: "0.08em" }}>
          <div style={{
            fontFamily: "var(--font-display-cn)",
            fontWeight: 800,
            fontSize: "var(--t-h2)",
            lineHeight: 1.12,
            color: "var(--text)",
            transform: `translateY(${titleY}%)`,
            opacity: titleAppear,
          }}>{sourceName}</div>
        </div>

        {meta.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", marginTop: "var(--space-7)" }}>
            {meta.map((m, i) => {
              const rf = cueFor(i);
              const appear = interpolate(frame, [rf, rf + 7], [0, 1], clamp);
              return (
                <div key={m.label} style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "var(--space-4)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--t-body)",
                  lineHeight: 1.3,
                  opacity: appear,
                }}>
                  <span style={{
                    flex: "none",
                    fontSize: "var(--t-micro)",
                    letterSpacing: "var(--track-caps)",
                    textTransform: "uppercase",
                    color: "var(--accent)",
                  }}>{m.label}</span>
                  <span style={{ color: m.color, wordBreak: "break-word" }}>{m.value}</span>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </Surface>
  );
};
