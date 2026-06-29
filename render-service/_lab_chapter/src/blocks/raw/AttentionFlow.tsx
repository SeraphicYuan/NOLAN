import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// BESPOKE self-attention block. One-off signature visual — NOT a reusable
// library block. The idea it conveys, literally drawn:
//   "every word looks at every other word, all at once."
//
// A sentence is laid out as a row of mono token-chips. Then an ALL-TO-ALL web of
// curved arcs draws itself ON between every pair of chips (SVG stroke-dashoffset
// self-drawing, borrowed from NpcStrike / SelfFeedingCurve), staggered so the
// whole dense web fills in almost at once — the hero motion. If a `focus` word is
// given, it and every arc that touches it brighten to --accent while the rest of
// the web dims to --rule/--text-faint: one word attending to all the others.
//
// Uses ONLY semantic theme tokens, wraps in <Surface>, no <Audio>. Frames are
// step-relative (Remotion resets per Series.Sequence).
//   revealFrames[0] — the row of word-chips appears
//   revealFrames[1] — the all-to-all connections draw on
//   revealFrames[2] — the focus word + its connections highlight

type Word = { text: string; startFrame: number; endFrame: number };
export type AttentionFlowProps = {
  // The tokens, in reading order, laid left→right as chips.
  sentence: string[];
  // Optional word to emphasize as "the one attending to all others".
  focus?: string;
  // Mono caption, e.g. "self-attention".
  label?: string;
  // Stage cues (step-relative): [row, connections, focus].
  revealFrames: number[];
  // Per-word spoken timeline for THIS step (step-relative frames).
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

// --- Chip metrics (SVG user units) -----------------------------------------
const VH = 540;
const ROW_Y = VH / 2; // vertical center of the token row
const FONT = 30;
const CHAR_W = 17.5; // approx mono advance per char at FONT
const PAD_X = 22;
const CHIP_H = 62;
const GAP = 22;
const DRAW_DUR = 16; // frames each arc takes to draw on

export const AttentionFlow: React.FC<AttentionFlowProps> = ({
  sentence,
  focus,
  label = "self-attention",
  revealFrames,
  words,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const n = sentence.length;
  const r0 = revealFrames[0] ?? 0;
  const r1 = revealFrames[1] ?? r0 + 18;
  const r2 = revealFrames[2] ?? Math.min(durationInFrames - 12, r1 + 40);

  // ---- Layout: place chips left→right, centered as a group --------------------
  const widths = sentence.map((w) => Math.max(1, w.length) * CHAR_W + PAD_X * 2);
  const totalW = widths.reduce((a, b) => a + b, 0) + GAP * Math.max(0, n - 1);
  const VW = Math.max(1000, totalW + 160); // widen the canvas if the row is long
  const startX = (VW - totalW) / 2;
  const chips: { x: number; w: number; cx: number }[] = [];
  {
    let x = startX;
    for (let i = 0; i < n; i++) {
      chips.push({ x, w: widths[i], cx: x + widths[i] / 2 });
      x += widths[i] + GAP;
    }
  }

  // ---- Focus resolution ------------------------------------------------------
  const fIdx = focus ? sentence.findIndex((w) => norm(w) === norm(focus)) : -1;
  const spokenFocus = focus ? words.find((w) => norm(w.text) === norm(focus)) : undefined;
  const focusStart = spokenFocus?.startFrame ?? r2;
  const focusProg = interpolate(frame, [focusStart, focusStart + 18], [0, 1], clamp);

  // ---- All-to-all pairs, ordered short→long so the web blooms outward ---------
  const pairs: { i: number; j: number; span: number }[] = [];
  for (let i = 0; i < n; i++)
    for (let j = i + 1; j < n; j++) pairs.push({ i, j, span: j - i });
  pairs.sort((a, b) => a.span - b.span || a.i - b.i);
  const P = pairs.length;
  // Stagger the draw-on across [r1 → webEnd]; the whole web lands well before r2.
  const webEnd = Math.max(r1 + DRAW_DUR + 4, Math.min(r2 - 2, r1 + Math.max(30, (r2 - r1) * 0.7)));
  const lastStart = Math.max(r1, webEnd - DRAW_DUR);
  const startK = (k: number) => (P <= 1 ? r1 : interpolate(k, [0, P - 1], [r1, lastStart], clamp));

  const topY = ROW_Y - CHIP_H / 2;
  const botY = ROW_Y + CHIP_H / 2;

  // Arc path between two chips. Alternates above/below the row by (i+j) parity;
  // the arc bulges further out for longer-range pairs (wider span).
  const arcPath = (i: number, j: number) => {
    const span = j - i;
    const above = (i + j) % 2 === 0;
    const h = Math.min(214, 40 + span * 26);
    const x1 = chips[i].cx;
    const x2 = chips[j].cx;
    const mx = (x1 + x2) / 2;
    if (above) {
      const y = topY;
      return `M ${x1.toFixed(1)} ${y} Q ${mx.toFixed(1)} ${(y - h).toFixed(1)} ${x2.toFixed(1)} ${y}`;
    }
    const y = botY;
    return `M ${x1.toFixed(1)} ${y} Q ${mx.toFixed(1)} ${(y + h * 0.78).toFixed(1)} ${x2.toFixed(1)} ${y}`;
  };

  // A chip glows briefly while its word is spoken (ties the web to narration).
  const isSpeaking = (i: number) => {
    const w = words.find((wd) => norm(wd.text) === norm(sentence[i]));
    return w ? frame >= w.startFrame && frame <= w.endFrame : false;
  };

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: "var(--space-5)" }}>
        {/* hero: token row + all-to-all attention web */}
        <div style={{ flex: 1, position: "relative" }}>
          <svg
            viewBox={`0 0 ${VW} ${VH}`}
            preserveAspectRatio="xMidYMid meet"
            style={{ width: "100%", height: "100%", overflow: "visible" }}
          >
            {/* ---- the dense all-to-all web (drawn first, sits behind chips) ---- */}
            {pairs.map(({ i, j }, k) => {
              const d = arcPath(i, j);
              const draw = interpolate(frame, [startK(k), startK(k) + DRAW_DUR], [0, 1], clamp);
              if (draw <= 0) return null;
              const isFocusArc = fIdx >= 0 && (i === fIdx || j === fIdx);
              // Neutral web → on focus, focus-arcs brighten, the rest dim away.
              const op = isFocusArc
                ? interpolate(focusProg, [0, 1], [0.5, 0.95], clamp)
                : interpolate(focusProg, [0, 1], [0.42, 0.16], clamp);
              const stroke = isFocusArc && focusProg > 0 ? "var(--accent)" : "var(--rule)";
              const sw = isFocusArc ? interpolate(focusProg, [0, 1], [1.6, 3.4], clamp) : 1.6;
              return (
                <g key={`${i}-${j}`}>
                  {isFocusArc && focusProg > 0 && (
                    <path
                      d={d}
                      pathLength={1}
                      fill="none"
                      stroke="var(--accent-glow)"
                      strokeWidth={9}
                      strokeLinecap="round"
                      strokeDasharray={1}
                      strokeDashoffset={1 - draw}
                      opacity={focusProg * 0.5}
                    />
                  )}
                  <path
                    d={d}
                    pathLength={1}
                    fill="none"
                    stroke={stroke}
                    strokeWidth={sw}
                    strokeLinecap="round"
                    strokeDasharray={1}
                    strokeDashoffset={1 - draw}
                    opacity={op}
                  />
                </g>
              );
            })}

            {/* ---- the token chips (on top, anchoring the arcs) ---- */}
            {chips.map((c, i) => {
              const cs = r0 + i * 2;
              const enter = spring({ frame: frame - cs, fps, durationInFrames: 16, config: { damping: 200 } });
              const dy = interpolate(enter, [0, 1], [16, 0]);
              const op = interpolate(frame, [cs, cs + 6], [0, 1], clamp);
              const isFocus = i === fIdx;
              const speaking = isSpeaking(i);
              // Focus chip ramps to accent; a spoken chip gets a soft accent tint.
              const fill = isFocus && focusProg > 0 ? "var(--surface-3)" : "var(--surface-2)";
              const stroke =
                isFocus && focusProg > 0
                  ? "var(--accent)"
                  : speaking
                    ? "var(--accent-soft, var(--accent))"
                    : "var(--rule)";
              const textColor =
                isFocus && focusProg > 0 ? "var(--accent)" : speaking ? "var(--accent)" : "var(--text)";
              // Non-focus chips fade slightly when the focus word is spotlighted.
              const chipOp =
                fIdx >= 0 && !isFocus ? op * interpolate(focusProg, [0, 1], [1, 0.5], clamp) : op;
              const sw = isFocus ? interpolate(focusProg, [0, 1], [1.6, 3], clamp) : 1.6;
              return (
                <g key={i} transform={`translate(0 ${dy})`} opacity={chipOp}>
                  {isFocus && focusProg > 0 && (
                    <rect
                      x={c.x - 5}
                      y={topY - 5}
                      width={c.w + 10}
                      height={CHIP_H + 10}
                      rx={12}
                      fill="none"
                      stroke="var(--accent-glow)"
                      strokeWidth={8}
                      opacity={focusProg * 0.55}
                    />
                  )}
                  <rect
                    x={c.x}
                    y={topY}
                    width={c.w}
                    height={CHIP_H}
                    rx={10}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={sw}
                  />
                  <text
                    x={c.cx}
                    y={ROW_Y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontFamily="var(--font-mono)"
                    fontSize={FONT}
                    fill={textColor}
                  >
                    {sentence[i]}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* label caption */}
        <div
          style={{
            textAlign: "center",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)",
            textTransform: "uppercase",
            color: "var(--text-mute)",
            opacity: interpolate(frame, [r1, r1 + 12], [0, 1], clamp),
          }}
        >
          {label}
        </div>
      </div>
    </Surface>
  );
};
