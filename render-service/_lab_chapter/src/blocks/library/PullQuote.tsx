import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library block: a pull-quote / definition card. Lands a memorable
// line (oversized display type, flush-left, accent rule + decorative quote
// mark) or defines jargon (term + definition) — built for research-paper
// content. Wraps in <Surface>, uses ONLY semantic theme tokens, and is a pure
// function of useCurrentFrame(): reveals are timestamp-driven via
// `revealFrames` (computed upstream from the narration) and word-synced via
// `words`. No <Audio>, no random, no timers. `useCurrentFrame()` is relative
// to this step's start.
type Word = { text: string; startFrame: number; endFrame: number };
export type PullQuoteProps = {
  mode?: "quote" | "definition"; // default "quote"
  // quote mode:
  quote?: string; // the line; may contain an accented phrase via `accentPhrase`
  accentPhrase?: string; // substring of quote rendered in --accent
  attribution?: string; // e.g. "— Vaswani et al., 2017"
  // definition mode:
  term?: string;
  definition?: string;
  // [quote/term cue, attribution/definition cue]
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9一-鿿]/g, "");

// Indices of `tokens` (the quote split on whitespace) that fall inside the
// `accentPhrase` substring — found by contiguous, normalized token matching so
// the accent lands on exactly the spoken phrase.
const accentIndexSet = (tokens: string[], phrase?: string): Set<number> => {
  const out = new Set<number>();
  if (!phrase) return out;
  const needle = phrase.split(/\s+/).filter(Boolean).map(norm);
  if (!needle.length) return out;
  for (let i = 0; i + needle.length <= tokens.length; i++) {
    let hit = true;
    for (let j = 0; j < needle.length; j++) {
      if (norm(tokens[i + j]) !== needle[j]) { hit = false; break; }
    }
    if (hit) {
      for (let j = 0; j < needle.length; j++) out.add(i + j);
      break;
    }
  }
  return out;
};

export const PullQuote: React.FC<PullQuoteProps> = ({
  mode = "quote",
  quote = "",
  accentPhrase,
  attribution,
  term = "",
  definition = "",
  revealFrames,
  words = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rf0 = revealFrames[0] ?? 0;
  const rf1 = revealFrames[1] ?? rf0 + 24;

  // Thick left accent bar: height draws DOWN (scaleY 0→1, top-anchored) as the
  // line lands — the editorial rule of the original .pull-quote, animated.
  const barS = spring({ frame: frame - rf0, fps, durationInFrames: 22, config: { damping: 200 } });
  const barScale = interpolate(barS, [0, 1], [0, 1]);

  const bar = (
    <div
      style={{
        flex: "0 0 auto",
        width: "var(--bw-4, 5px)",
        alignSelf: "stretch",
        background: "var(--accent)",
        borderRadius: "var(--r-xs)",
        transformOrigin: "top",
        transform: `scaleY(${barScale})`,
        boxShadow: `0 0 24px var(--accent-glow)`,
      }}
    />
  );

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%" }}>
        <div style={{ display: "flex", flexDirection: "row", gap: "var(--space-5)", alignItems: "stretch" }}>
          {bar}

          <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
            {mode === "definition" ? (
              <DefinitionBody
                term={term}
                definition={definition}
                rf0={rf0}
                rf1={rf1}
                frame={frame}
                fps={fps}
              />
            ) : (
              <QuoteBody
                quote={quote}
                accentPhrase={accentPhrase}
                attribution={attribution}
                rf0={rf0}
                rf1={rf1}
                words={words}
                frame={frame}
                fps={fps}
              />
            )}
          </div>
        </div>
      </div>
    </Surface>
  );
};

// ── Quote mode ────────────────────────────────────────────────────────────
const QuoteBody: React.FC<{
  quote: string;
  accentPhrase?: string;
  attribution?: string;
  rf0: number;
  rf1: number;
  words: Word[];
  frame: number;
  fps: number;
}> = ({ quote, accentPhrase, attribution, rf0, rf1, words, frame, fps }) => {
  const tokens = quote.split(/\s+/).filter(Boolean);
  const accentIdx = accentIndexSet(tokens, accentPhrase);
  const stagger = 4; // fallback per-word cadence when no word timeline is given

  // Big decorative opening quote mark — accent, low opacity, fades in with bar.
  const markAppear = interpolate(frame, [rf0, rf0 + 8], [0, 1], clamp);

  // Attribution rides in after the line, at revealFrames[1].
  const attrS = spring({ frame: frame - rf1, fps, durationInFrames: 18, config: { damping: 200 } });
  const attrAppear = interpolate(frame, [rf1, rf1 + 6], [0, 1], clamp);

  return (
    <>
      <div
        aria-hidden
        style={{
          fontFamily: "var(--font-display-en)",
          fontWeight: 900,
          fontSize: "var(--t-display-1)",
          lineHeight: 0.7,
          color: "var(--accent)",
          opacity: interpolate(markAppear, [0, 1], [0, 0.18]),
          height: "0.42em",
          marginBottom: "var(--space-3)",
          userSelect: "none",
        }}
      >
        &ldquo;
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          fontFamily: "var(--font-display-cn)",
          fontWeight: 700,
          fontSize: "var(--t-h1)",
          lineHeight: "var(--lh-head)",
          letterSpacing: "var(--track-tight)",
          color: "var(--text)",
        }}
      >
        {tokens.map((tok, i) => {
          const wt = words[i];
          const rf = wt ? wt.startFrame : rf0 + i * stagger;
          const s = spring({ frame: frame - rf, fps, durationInFrames: 14, config: { damping: 200 } });
          // Mask-up reveal: each word slides up from below into a clipped row.
          const y = interpolate(s, [0, 1], [100, 0]);
          const appear = interpolate(frame, [rf, rf + 4], [0, 1], clamp);
          const isAccent = accentIdx.has(i);
          // Accent words bloom a soft glow as they are spoken.
          const glow = isAccent ? interpolate(frame, [rf, rf + 10], [0, 1], clamp) : 0;
          return (
            <span key={i} style={{ overflow: "hidden", paddingBottom: "0.08em", marginRight: "0.28em" }}>
              <span
                style={{
                  display: "inline-block",
                  transform: `translateY(${y}%)`,
                  opacity: appear,
                  color: isAccent ? "var(--accent)" : "var(--text)",
                  textShadow: isAccent ? `0 0 ${interpolate(glow, [0, 1], [0, 26])}px var(--accent-glow)` : undefined,
                }}
              >
                {tok}
              </span>
            </span>
          );
        })}
      </div>

      {attribution ? (
        <div
          style={{
            marginTop: "var(--space-7)",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)",
            textTransform: "uppercase",
            color: "var(--text-mute)",
            opacity: attrAppear,
            transform: `translateX(${interpolate(attrS, [0, 1], [-18, 0])}px)`,
          }}
        >
          {attribution}
        </div>
      ) : null}
    </>
  );
};

// ── Definition mode ───────────────────────────────────────────────────────
const DefinitionBody: React.FC<{
  term: string;
  definition: string;
  rf0: number;
  rf1: number;
  frame: number;
  fps: number;
}> = ({ term, definition, rf0, rf1, frame, fps }) => {
  // Term lands first (mask-up), definition slides/fades in below at rf1.
  const termS = spring({ frame: frame - rf0, fps, durationInFrames: 18, config: { damping: 200 } });
  const termY = interpolate(termS, [0, 1], [100, 0]);
  const termAppear = interpolate(frame, [rf0, rf0 + 4], [0, 1], clamp);

  const defS = spring({ frame: frame - rf1, fps, durationInFrames: 20, config: { damping: 200 } });
  const defY = interpolate(defS, [0, 1], [28, 0]);
  const defAppear = interpolate(frame, [rf1, rf1 + 8], [0, 1], clamp);

  return (
    <>
      <div style={{ overflow: "hidden", paddingBottom: "0.08em" }}>
        <div
          style={{
            display: "inline-block",
            fontFamily: "var(--font-display-cn)",
            fontWeight: 700,
            fontSize: "var(--t-display-2)",
            lineHeight: "var(--lh-head)",
            letterSpacing: "var(--track-tight)",
            color: "var(--text)",
            transform: `translateY(${termY}%)`,
            opacity: termAppear,
          }}
        >
          {term}
        </div>
      </div>

      <div
        style={{
          marginTop: "var(--space-5)",
          maxWidth: "22em",
          fontFamily: "var(--font-display-cn)",
          fontWeight: 400,
          fontSize: "var(--t-h2)",
          lineHeight: "var(--lh-head)",
          color: "var(--text-2)",
          transform: `translateY(${defY}px)`,
          opacity: defAppear,
        }}
      >
        {definition}
      </div>
    </>
  );
};
