import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// BESPOKE compounding-growth block. One-off signature visual — NOT a reusable
// library block. Narration beat:
//   "The idea is simple. You earn interest. Then you earn interest on the
//    interest. And the growth starts feeding itself."
//
// Builds a self-feeding growth picture across THREE synced reveals:
//   R1 (first "interest")  — a principal bar earns a small interest slab on top.
//   R2 (2nd "interest" = "interest on the interest") — that slab sprouts its OWN
//        smaller increment, and a feedback loop-arrow draws from the stack top
//        back down to the base (SVG path drawn on via stroke-dashoffset).
//   R3 ("feeding")         — the stacked bars resolve into a smooth, accelerating
//        exponential curve (drawn left→low to right→high via stroke-dashoffset),
//        while the loop arrow keeps cycling (a subtle continuous flow).
//
// Uses ONLY semantic theme tokens, wraps in <Surface>, no <Audio>. Frames are
// step-relative (Remotion resets per Series.Sequence). The loop snaps precisely
// to the 2nd "interest" word's startFrame and the curve ignites on "feeding".

type Word = { text: string; startFrame: number; endFrame: number };
export type SelfFeedingCurveProps = {
  // Per-word timeline for THIS step (step-relative frames).
  words: Word[];
  // Three entrance cues (step-relative): [principal, increment+loop, curve].
  revealFrames: number[];
  durationInFrames: number;
  // Bespoke copy — defaults hard-coded since this is a one-off scene.
  kicker?: string;
  caption?: string;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

// --- Stage geometry (SVG user units) ---------------------------------------
const VW = 1000;
const VH = 520;
const BASE_Y = 440; // baseline / "principal" floor
const CURVE_TOP = 116; // highest point the exponential reaches
const BAR_X = 150;
const BAR_W = 96;
const BAR_CX = BAR_X + BAR_W / 2;
// stacked-bar segment tops (smaller increments → accelerating stack)
const PRINCIPAL_TOP = 300; // h 140
const SLAB1_TOP = 254; //     h 46
const SLAB2_TOP = 222; //     h 32
const STACK_TOP_Y = SLAB2_TOP;

// Feedback loop: from the stack top, arc out and curl back down into the base —
// the "output" being fed back to the "input".
const LOOP_PATH =
  "M 198 214 C 322 150, 332 36, 196 50 C 44 66, 36 300, 132 414";
// Accelerating exponential, sampled once (pathLength normalized to 1 below).
const EXP_PATH = (() => {
  const N = 48;
  const k = 3.05; // steepness of the acceleration
  const denom = Math.exp(k) - 1;
  let d = "";
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    const x = BAR_X - 70 + t * (VW - 120 - (BAR_X - 70));
    const y = BASE_Y - (BASE_Y - CURVE_TOP) * ((Math.exp(k * t) - 1) / denom);
    d += `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)} `;
  }
  return d.trim();
})();

export const SelfFeedingCurve: React.FC<SelfFeedingCurveProps> = ({
  words,
  revealFrames,
  durationInFrames,
  kicker = "interest on interest",
  caption = "Growth that compounds on itself — the loop starts feeding the loop.",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const r1 = revealFrames[0] ?? 0;
  const r2 = revealFrames[1] ?? r1 + 40;
  const r3 = revealFrames[2] ?? r2 + 40;

  // Word snaps: 2nd "interest" → loop draw-on; "feeding" → curve ignition.
  const interests = words.filter((w) => norm(w.text) === "interest");
  const loopStart = interests[1]?.startFrame ?? r2;
  const feeding = words.find((w) => norm(w.text) === "feeding");
  const curveStart = feeding?.startFrame ?? r3;

  // Entrance for the whole panel.
  const enter = spring({ frame: frame - r1, fps, durationInFrames: 18, config: { damping: 200 } });
  const enterOpacity = interpolate(frame, [r1, r1 + 6], [0, 1], clamp);

  // Per-segment grow springs (transform-origin bottom via animated y/height).
  const grow = (start: number, dur = 16) =>
    spring({ frame: frame - start, fps, durationInFrames: dur, config: { damping: 200 } });
  const pPrincipal = grow(r1);
  const pSlab1 = grow(r1 + 8);
  const pSlab2 = grow(r2 + 4);

  // Loop arrow draws on across its spoken span (snapped to 2nd "interest").
  const loopDraw = interpolate(frame, [loopStart, loopStart + 20], [0, 1], clamp);
  // Continuous feedback flow once the curve ignites — a subtle moving dash.
  const flowOffset = -((frame * 0.012) % 1);
  const flowOn = interpolate(frame, [curveStart, curveStart + 10], [0, 1], clamp);

  // Curve ignites on "feeding": draws left→low to right→high; bars dissolve.
  const curveDraw = interpolate(frame, [curveStart, curveStart + 34], [0, 1], clamp);
  const barFade = interpolate(frame, [curveStart, curveStart + 18], [1, 0.12], clamp);
  // A travelling spark sits at the drawing head for the "accelerating" feel.
  const sparkOn = interpolate(frame, [curveStart, curveStart + 4, curveStart + 38], [0, 1, 0], clamp);

  const seg = (top: number, prog: number, fill: string, op = 1) => {
    const fullH = BASE_Y - top;
    const h = Math.max(0.01, fullH * prog);
    return <rect x={BAR_X} y={BASE_Y - h} width={BAR_W} height={h} fill={fill} opacity={op * barFade} rx={2} />;
  };

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: "var(--space-6)" }}>
        {/* kicker */}
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)",
            textTransform: "uppercase",
            color: "var(--accent)",
            opacity: enterOpacity,
          }}
        >
          {kicker}
        </div>

        {/* hero: stacked bars resolving into an accelerating curve + feedback loop */}
        <div
          style={{
            flex: 1,
            position: "relative",
            opacity: enterOpacity,
            transform: `translateY(${interpolate(enter, [0, 1], [40, 0])}px)`,
          }}
        >
          <svg
            viewBox={`0 0 ${VW} ${VH}`}
            preserveAspectRatio="xMidYMid meet"
            style={{ width: "100%", height: "100%", overflow: "visible" }}
          >
            <defs>
              <marker
                id="sfc-arrow"
                viewBox="0 0 10 10"
                refX={7}
                refY={5}
                markerWidth={7}
                markerHeight={7}
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent)" />
              </marker>
            </defs>

            {/* baseline */}
            <line
              x1={BAR_X - 70}
              y1={BASE_Y}
              x2={VW - 120}
              y2={BASE_Y}
              stroke="var(--rule)"
              strokeWidth={2}
            />

            {/* stacked bars — principal + interest + interest-on-interest */}
            {seg(PRINCIPAL_TOP, pPrincipal, "var(--surface-3)")}
            {seg(SLAB1_TOP, pSlab1, "var(--accent-soft)")}
            {seg(SLAB2_TOP, pSlab2, "var(--accent)")}

            {/* feedback loop — drawn on at the 2nd "interest", then keeps flowing */}
            <path
              d={LOOP_PATH}
              pathLength={1}
              fill="none"
              stroke="var(--accent)"
              strokeWidth={3}
              strokeLinecap="round"
              strokeDasharray={1}
              strokeDashoffset={1 - loopDraw}
              markerEnd="url(#sfc-arrow)"
              opacity={0.85}
            />
            {/* continuous feedback flow once the growth feeds itself */}
            <path
              d={LOOP_PATH}
              pathLength={1}
              fill="none"
              stroke="var(--accent-glow)"
              strokeWidth={6}
              strokeLinecap="round"
              strokeDasharray="0.05 0.07"
              strokeDashoffset={flowOffset}
              opacity={flowOn * 0.7}
            />

            {/* the hero curve — accelerating exponential, ignited on "feeding" */}
            <path
              d={EXP_PATH}
              pathLength={1}
              fill="none"
              stroke="var(--accent-glow)"
              strokeWidth={12}
              strokeLinecap="round"
              strokeDasharray={1}
              strokeDashoffset={1 - curveDraw}
              opacity={0.5}
            />
            <path
              d={EXP_PATH}
              pathLength={1}
              fill="none"
              stroke="var(--accent)"
              strokeWidth={4}
              strokeLinecap="round"
              strokeDasharray={1}
              strokeDashoffset={1 - curveDraw}
            />
            {/* travelling spark at the drawing head (the acceleration) */}
            <circle
              cx={interpolate(curveDraw, [0, 1], [BAR_X - 70, VW - 120])}
              cy={BASE_Y - (BASE_Y - CURVE_TOP) * ((Math.exp(3.05 * curveDraw) - 1) / (Math.exp(3.05) - 1))}
              r={7}
              fill="var(--accent)"
              opacity={sparkOn}
            />
          </svg>
        </div>

        {/* caption */}
        <div
          style={{
            fontFamily: "var(--font-body)",
            fontSize: "var(--t-body)",
            color: "var(--text-mute)",
            maxWidth: "62%",
            opacity: interpolate(frame, [r2, r2 + 12], [0, 1], clamp),
          }}
        >
          {caption}
        </div>
      </div>
    </Surface>
  );
};
