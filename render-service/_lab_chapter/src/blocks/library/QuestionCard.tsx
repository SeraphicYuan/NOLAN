import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library block: a rhetorical-question card. Rebuild of NOLAN's PIL
// QuestionRenderer — an oversized decorative "?" sits behind a single question
// line, with an optional small context label above. Wraps content in <Surface>,
// uses ONLY semantic theme tokens, and reveals on the frame given in
// `revealFrames` (computed upstream from the narration). No <Audio>, no random,
// no timers, no CSS transitions. `useCurrentFrame()` is step-relative.
type Word = { text: string; startFrame: number; endFrame: number };
export type QuestionCardProps = {
  question: string;
  context?: string; // small label above
  accentPhrase?: string; // substring of question rendered in --accent
  revealFrames: number[]; // [question cue]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Split `question` into [before, accent, after] around the first occurrence of
// `accentPhrase`. Returns the whole string as `before` when there's no match.
function splitAccent(question: string, accentPhrase?: string) {
  if (accentPhrase) {
    const i = question.indexOf(accentPhrase);
    if (i >= 0) {
      return {
        before: question.slice(0, i),
        accent: question.slice(i, i + accentPhrase.length),
        after: question.slice(i + accentPhrase.length),
      };
    }
  }
  return { before: question, accent: "", after: "" };
}

export const QuestionCard: React.FC<QuestionCardProps> = ({
  question,
  context,
  accentPhrase,
  revealFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rf = revealFrames[0] ?? 0;

  // Decorative "?" rises slightly earlier, scaling + fading into the backdrop.
  const markRf = rf - 8;
  const markS = spring({ frame: frame - markRf, fps, durationInFrames: 26, config: { damping: 200 } });
  const markScale = interpolate(markS, [0, 1], [0.78, 1]);
  const markOpacity = interpolate(frame, [markRf, markRf + 18], [0, 0.12], clamp);

  // Context label fades in just before the question.
  const ctxRf = rf - 4;
  const ctxOpacity = interpolate(frame, [ctxRf, ctxRf + 6], [0, 1], clamp);

  // Question fades + slides up on its cue.
  const qS = spring({ frame: frame - rf, fps, durationInFrames: 18, config: { damping: 200 } });
  const qY = interpolate(qS, [0, 1], [28, 0]);
  const qOpacity = interpolate(frame, [rf, rf + 6], [0, 1], clamp);

  // Underline draws/fades in shortly after the question settles.
  const ulRf = rf + 6;
  const ulOpacity = interpolate(frame, [ulRf, ulRf + 8], [0, 1], clamp);
  const ulWidth = interpolate(frame, [ulRf, ulRf + 14], [0, 100], clamp);

  const { before, accent, after } = splitAccent(question, accentPhrase);

  return (
    <Surface>
      <div style={{
        position: "relative",
        display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
        height: "100%", textAlign: "center",
      }}>
        {/* Oversized decorative "?" behind the text, slightly offset. */}
        <div style={{
          position: "absolute",
          top: "50%", left: "50%",
          transform: `translate(calc(-50% + 0.12em), calc(-50% - 0.06em)) scale(${markScale})`,
          fontFamily: "var(--font-display-en)", fontWeight: 900,
          fontSize: "var(--t-display-1)", lineHeight: 1,
          color: "var(--accent)", opacity: markOpacity,
          pointerEvents: "none", zIndex: 0,
        }}>?</div>

        <div style={{ position: "relative", zIndex: 1, maxWidth: 1500 }}>
          {context ? (
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)", textTransform: "uppercase",
              color: "var(--text-mute)", marginBottom: "var(--space-6)",
              opacity: ctxOpacity,
            }}>{context}</div>
          ) : null}

          <div style={{
            fontFamily: "var(--font-display-cn)", fontWeight: 700,
            fontSize: "var(--t-h1)", lineHeight: "var(--lh-head)",
            color: "var(--text)",
            transform: `translateY(${qY}px)`, opacity: qOpacity,
          }}>
            {before}
            {accent ? <span style={{ color: "var(--accent)" }}>{accent}</span> : null}
            {after}
          </div>

          {/* Short accent underline, centered under the question. */}
          <div style={{ display: "flex", justifyContent: "center", marginTop: "var(--space-5)" }}>
            <div style={{
              height: "var(--rule-w)",
              width: `${interpolate(ulWidth, [0, 100], [0, 120])}px`,
              background: "var(--accent)",
              opacity: ulOpacity,
            }} />
          </div>
        </div>
      </div>
    </Surface>
  );
};
