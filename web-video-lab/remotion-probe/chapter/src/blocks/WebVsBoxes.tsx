import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../Surface";

// SIGNATURE DIAGRAM block. Left/right contrast: a small stack of separate,
// sealed "boxes" (how knowledge is taught) vs. a self-drawing node graph (how
// it actually is — one web). The edge-draw on the right is the hero motion: the
// connections literally draw themselves on, performing the "it's a web" reveal.
// Token-only styling; wraps in <Surface>; no <Audio>. useCurrentFrame() is
// relative to this step's start.
export type WebVsBoxesProps = {
  kicker?: string;
  headline?: string;
  boxes: string[];
  nodes: string[];
  revealFrames: number[]; // [0] headline, [1] boxes appear, [2] web nodes + edges draw
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Square SVG coordinate space for the web.
const VB = 760;
const C = VB / 2;
const RING = VB * 0.34; // node ring radius
const NODE_R = 46;

export const WebVsBoxes: React.FC<WebVsBoxesProps> = ({
  kicker = "the shape of knowledge",
  headline = "Taught as boxes — it's actually a web.",
  boxes,
  nodes,
  revealFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const rfHead = revealFrames[0] ?? 0;
  const rfBoxes = revealFrames[1] ?? rfHead + 10;
  const rfWeb = revealFrames[2] ?? rfBoxes + 20;

  const headApp = interpolate(frame, [rfHead, rfHead + 10], [0, 1], clamp);
  const headY = interpolate(headApp, [0, 1], [24, 0]);

  // Bridge arrow appears with the web.
  const bridge = interpolate(frame, [rfWeb - 4, rfWeb + 8], [0, 1], clamp);

  // --- Web geometry ---
  const pts = nodes.map((_, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / nodes.length;
    return { x: C + RING * Math.cos(a), y: C + RING * Math.sin(a) };
  });
  // Dense web: every pair of nodes (complete graph) → many edges to draw on.
  const edges: Array<[number, number]> = [];
  for (let i = 0; i < pts.length; i++)
    for (let j = i + 1; j < pts.length; j++) edges.push([i, j]);

  const EDGE_STAGGER = 2.2; // frames between each edge starting to draw
  const EDGE_DRAW = 26; // frames for one edge to fully draw

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {/* Header */}
        <div style={{ opacity: headApp, transform: `translateY(${headY}px)` }}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-micro)",
              letterSpacing: "var(--track-caps)",
              textTransform: "uppercase",
              color: "var(--text-faint)",
            }}
          >
            {kicker}
          </div>
          <div
            style={{
              fontFamily: "var(--font-display-en)",
              fontWeight: 900,
              fontSize: "var(--t-h1)",
              lineHeight: 1.04,
              color: "var(--text)",
              marginTop: "var(--space-3)",
              maxWidth: "26ch",
            }}
          >
            {headline}
          </div>
        </div>

        {/* Stage: boxes (~30%) → arrow → web (~55%) */}
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            marginTop: "var(--space-7)",
          }}
        >
          {/* LEFT — sealed, disconnected boxes */}
          <div
            style={{
              width: "30%",
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-5)",
            }}
          >
            {boxes.map((b, i) => {
              const rf = rfBoxes + i * 6;
              const s = spring({ frame: frame - rf, fps, durationInFrames: 16, config: { damping: 200 } });
              const app = interpolate(frame, [rf, rf + 6], [0, 1], clamp);
              const x = interpolate(s, [0, 1], [-40, 0]);
              return (
                <div
                  key={i}
                  style={{
                    opacity: app,
                    transform: `translateX(${x}px)`,
                    border: "var(--rule-w) solid var(--rule)",
                    borderRadius: "var(--space-2)",
                    padding: "var(--space-4) var(--space-5)",
                    color: "var(--text-mute)",
                    fontFamily: "var(--font-body)",
                    fontSize: "var(--t-body)",
                    background: "var(--surface-2)",
                  }}
                >
                  {b}
                </div>
              );
            })}
            <div
              style={{
                marginTop: "var(--space-3)",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--t-micro)",
                letterSpacing: "var(--track-caps)",
                textTransform: "uppercase",
                color: "var(--text-faint)",
                opacity: interpolate(frame, [rfBoxes, rfBoxes + 10], [0, 1], clamp),
              }}
            >
              sealed classes
            </div>
          </div>

          {/* Bridge arrow */}
          <div
            style={{
              width: "10%",
              textAlign: "center",
              fontFamily: "var(--font-display-en)",
              fontWeight: 900,
              fontSize: "var(--t-display-2)",
              color: "var(--accent)",
              opacity: bridge,
              transform: `translateX(${interpolate(bridge, [0, 1], [-16, 0])}px)`,
            }}
          >
            →
          </div>

          {/* RIGHT — the web (hero: edges draw themselves on) */}
          <div style={{ width: "55%", display: "flex", flexDirection: "column", alignItems: "center" }}>
            <svg viewBox={`0 0 ${VB} ${VB}`} style={{ width: "100%", maxWidth: 640, overflow: "visible" }}>
              {/* Edges — self-drawing via stroke-dashoffset */}
              <g>
                {edges.map(([i, j], k) => {
                  const a = pts[i];
                  const b = pts[j];
                  const len = Math.hypot(b.x - a.x, b.y - a.y);
                  const start = rfWeb + k * EDGE_STAGGER;
                  const p = interpolate(frame, [start, start + EDGE_DRAW], [0, 1], clamp);
                  return (
                    <line
                      key={k}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      stroke="var(--accent)"
                      strokeOpacity={0.28}
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeDasharray={len}
                      strokeDashoffset={len * (1 - p)}
                    />
                  );
                })}
              </g>
              {/* Nodes — small circles + labels, pop in staggered with the web */}
              {pts.map((pt, i) => {
                const rf = rfWeb + i * 3;
                const s = spring({ frame: frame - rf, fps, durationInFrames: 18, config: { damping: 180 } });
                const r = NODE_R * s;
                return (
                  <g key={i} opacity={interpolate(frame, [rf, rf + 6], [0, 1], clamp)}>
                    <circle
                      cx={pt.x}
                      cy={pt.y}
                      r={r}
                      fill="var(--surface-3)"
                      stroke="var(--accent)"
                      strokeWidth={2.5}
                    />
                    <text
                      x={pt.x}
                      y={pt.y}
                      textAnchor="middle"
                      dominantBaseline="central"
                      style={{
                        fontFamily: "var(--font-body)",
                        fontSize: 22,
                        fill: "var(--text-2)",
                      }}
                    >
                      {nodes[i]}
                    </text>
                  </g>
                );
              })}
            </svg>
            <div
              style={{
                marginTop: "var(--space-3)",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--t-micro)",
                letterSpacing: "var(--track-caps)",
                textTransform: "uppercase",
                color: "var(--accent-soft)",
                opacity: interpolate(frame, [rfWeb + 6, rfWeb + 18], [0, 1], clamp),
              }}
            >
              one web
            </div>
          </div>
        </div>
      </div>
    </Surface>
  );
};
