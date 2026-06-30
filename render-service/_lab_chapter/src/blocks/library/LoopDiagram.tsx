import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { getLength } from "@remotion/paths";
import { Surface } from "../../Surface";

// LoopDiagram — a circular feedback loop. N labelled nodes sit evenly on a circle
// (clockwise from the top). Each node is a --surface-2 disc with a --rule border
// and a --text label; it springs/scales in at its revealFrames[i] cue. Once a node
// AND its clockwise successor are both in, the curved --accent arrow between them
// DRAWS ON via stroke-dashoffset (a quadratic arc that hugs the circle, capped with
// an arrowhead) — the last → first arrow closes the cycle. An optional centerLabel
// (mono caps, --text-mute) fades into the middle once the loop has closed. Pure
// function of useCurrentFrame() (no random/dates/timers/CSS-transitions); token-only;
// wraps content in <Surface>. useCurrentFrame() is relative to this step's start.
type Word = { text: string; startFrame: number; endFrame: number };
export type LoopDiagramProps = {
  title?: string;
  nodes: string[];        // 3–6 labels, arranged clockwise on a circle
  centerLabel?: string;
  revealFrames: number[]; // one cue per node
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Square SVG coordinate space.
const VB = 760;
const C = VB / 2;
const RING = VB * 0.32;  // node-ring radius
const NODE_R = VB * 0.082;
const GAP = 14;          // breathing room between disc edge and arrow tip
const ARROW_DRAW = 22;   // frames for one arrow to fully draw on
const NODE_DELAY = 6;    // frames after both nodes are in before the arrow starts

// Is the narration mid-word at this frame? Drives a subtle "speaking" lift on the
// most-recently revealed (head) node so the loop breathes with the voice-over.
const isSpeaking = (frame: number, words: Word[]): boolean => {
  for (const w of words) if (frame >= w.startFrame && frame < w.endFrame) return true;
  return false;
};

export const LoopDiagram: React.FC<LoopDiagramProps> = ({
  title,
  nodes,
  centerLabel,
  revealFrames,
  words,
  durationInFrames: _durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const n = nodes.length;
  const rf = (i: number) => revealFrames[i] ?? 0;

  // Evenly spaced clockwise from the top (-90°).
  const pts = nodes.map((_, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return { x: C + RING * Math.cos(a), y: C + RING * Math.sin(a) };
  });

  // The "head" = the latest node whose cue has fired (gets an --accent ring + glow).
  let headIndex = -1;
  for (let i = 0; i < n; i++) if (frame >= rf(i)) headIndex = i;
  const speaking = headIndex >= 0 && isSpeaking(frame, words);

  // One curved arrow per clockwise pair (i → (i+1) mod n); the last closes the loop.
  const arcs = pts.map((S, i) => {
    const j = (i + 1) % n;
    const T = pts[j];
    // Control point pushed just outside the ring along the midpoint's angle, so the
    // quadratic arc bows outward and hugs the circle.
    const mx = (S.x + T.x) / 2;
    const my = (S.y + T.y) / 2;
    const midA = Math.atan2(my - C, mx - C);
    const ctrl = { x: C + (RING + 18) * Math.cos(midA), y: C + (RING + 18) * Math.sin(midA) };
    // Trim both ends to the disc edges.
    let sdx = ctrl.x - S.x, sdy = ctrl.y - S.y;
    const sl = Math.hypot(sdx, sdy) || 1; sdx /= sl; sdy /= sl;
    const p0 = { x: S.x + sdx * (NODE_R + GAP), y: S.y + sdy * (NODE_R + GAP) };
    let edx = T.x - ctrl.x, edy = T.y - ctrl.y;
    const el = Math.hypot(edx, edy) || 1; edx /= el; edy /= el;
    const p2 = { x: T.x - edx * (NODE_R + GAP), y: T.y - edy * (NODE_R + GAP) };
    const d = `M ${p0.x} ${p0.y} Q ${ctrl.x} ${ctrl.y} ${p2.x} ${p2.y}`;
    // Arrowhead: tangent at the end points from ctrl → p2.
    const ang = Math.atan2(p2.y - ctrl.y, p2.x - ctrl.x) + Math.PI; // backward
    const spread = 0.42;
    const ah = VB * 0.03;
    const a1 = { x: p2.x + ah * Math.cos(ang - spread), y: p2.y + ah * Math.sin(ang - spread) };
    const a2 = { x: p2.x + ah * Math.cos(ang + spread), y: p2.y + ah * Math.sin(ang + spread) };
    const head = `M ${a1.x} ${a1.y} L ${p2.x} ${p2.y} L ${a2.x} ${a2.y}`;
    const len = getLength(d);
    const cue = Math.max(rf(i), rf(j)) + NODE_DELAY;
    return { d, head, len, cue, end: cue + ARROW_DRAW };
  });

  // The loop is "closed" once the last-drawing arrow finishes.
  const loopClose = arcs.reduce((m, a) => Math.max(m, a.end), 0);
  const centerOpacity = centerLabel
    ? interpolate(frame, [loopClose, loopClose + 14], [0, 1], clamp)
    : 0;
  const centerS = spring({ frame: frame - loopClose, fps, durationInFrames: 18, config: { damping: 200 } });

  const titleRf = rf(0) - 10;
  const titleApp = interpolate(frame, [titleRf, titleRf + 8], [0, 1], clamp);
  const titleY = interpolate(titleApp, [0, 1], [16, 0]);

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", height: "100%", alignItems: "center" }}>
        {title ? (
          <div style={{
            fontFamily: "var(--font-display-cn)", fontWeight: 900,
            fontSize: "var(--t-h2)", lineHeight: 1.1, color: "var(--text)",
            textAlign: "center", maxWidth: "26ch",
            opacity: titleApp, transform: `translateY(${titleY}px)`,
            marginBottom: "var(--space-6)",
          }}>{title}</div>
        ) : null}

        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", minHeight: 0 }}>
          <svg viewBox={`0 0 ${VB} ${VB}`} style={{ height: "100%", maxHeight: "100%", overflow: "visible" }}>
            {/* Curved arrows — draw on via stroke-dashoffset once both endpoints are in */}
            <g>
              {arcs.map((arc, i) => {
                const p = interpolate(frame, [arc.cue, arc.end], [0, 1], clamp);
                if (p <= 0) return null;
                const headOpacity = interpolate(p, [0.82, 1], [0, 1], clamp);
                return (
                  <g key={`arc-${i}`}>
                    <path
                      d={arc.d}
                      fill="none"
                      stroke="var(--accent)"
                      strokeWidth={3.5}
                      strokeLinecap="round"
                      strokeDasharray={arc.len}
                      strokeDashoffset={arc.len * (1 - p)}
                    />
                    <path
                      d={arc.head}
                      fill="none"
                      stroke="var(--accent)"
                      strokeWidth={3.5}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      opacity={headOpacity}
                    />
                  </g>
                );
              })}
            </g>

            {/* Center label — fades in once the loop closes */}
            {centerLabel ? (
              <text
                x={C}
                y={C}
                textAnchor="middle"
                dominantBaseline="central"
                opacity={centerOpacity}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 26,
                  letterSpacing: "var(--track-caps)",
                  textTransform: "uppercase",
                  fill: "var(--text-mute)",
                }}
                transform={`translate(0 ${interpolate(centerS, [0, 1], [8, 0])})`}
              >
                {centerLabel}
              </text>
            ) : null}

            {/* Nodes — discs that spring/scale in at their cue */}
            {pts.map((pt, i) => {
              const r = rf(i);
              const s = spring({ frame: frame - r, fps, durationInFrames: 18, config: { damping: 180 } });
              const app = interpolate(frame, [r, r + 6], [0, 1], clamp);
              const isHead = i === headIndex;
              const glow = isHead ? (speaking ? 1 : 0.55) : 0;
              const ring = isHead ? "var(--accent)" : "var(--rule)";
              return (
                <g key={`node-${i}`} opacity={app} transform={`translate(${pt.x} ${pt.y}) scale(${s})`}>
                  {glow > 0 ? (
                    <circle cx={0} cy={0} r={NODE_R + 10 * glow} fill="var(--accent-glow)" opacity={glow * 0.6} />
                  ) : null}
                  <circle cx={0} cy={0} r={NODE_R} fill="var(--surface-2)" stroke={ring} strokeWidth={2.5} />
                  <text
                    x={0}
                    y={0}
                    textAnchor="middle"
                    dominantBaseline="central"
                    style={{
                      fontFamily: "var(--font-display-cn)",
                      fontWeight: 900,
                      fontSize: 26,
                      fill: "var(--text)",
                    }}
                  >
                    {nodes[i]}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>
    </Surface>
  );
};
