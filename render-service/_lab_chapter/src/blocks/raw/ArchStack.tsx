import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// BESPOKE block — "The Transformer architecture at a glance."
// A clean, schematic blueprint of an encoder–decoder stack. NOT a reusable
// library block; a one-off explainer visual.
//
// Layout (SVG user units): two columns, ENCODER (left) and DECODER (right).
// Each column shows ~2 representative layer-boxes (with faint depth-ghosts
// behind them) plus a "× {layers}" multiplier badge — so the full N-deep
// stack reads without drawing all N. Each layer-box holds the `subLayers`
// as labeled inner blocks; the attention sub-layer is rendered in --accent
// to mark it as the focus. A thin curved wrap-arrow hugs the left edge of
// every sub-layer to suggest the residual + layer-norm skip connection.
// Encoder context flows into the decoder via a dashed "K · V" cross-link.
//
// Motion is reveal-driven (step-relative useCurrentFrame; Remotion resets
// frames per Series.Sequence):
//   revealFrames[0] — column labels + badges fade in
//   revealFrames[1] — encoder boxes spring/scale in (staggered)
//   revealFrames[2] — decoder boxes spring/scale in (staggered) + cross-link
// Tokens only, wrapped in <Surface>, no <Audio>.

type Word = { text: string; startFrame: number; endFrame: number };

export type ArchStackProps = {
  layers?: number;
  subLayers?: string[];
  note?: string;
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// ── Stage geometry (SVG user units) ──────────────────────────────────────
const VW = 1040;
const VH = 420;
const BW = 320; // layer-box width
const PAD_X = 18; // box inner horizontal padding
const PAD_Y = 16; // box inner vertical padding
const SUB_H = 46; // sub-layer block height
const SUB_GAP = 12; // gap between sub-layer blocks
const LABEL_Y = 36; // ENCODER / DECODER label baseline
const BOX1_TOP = 92; // top of first representative box
const CONNECTOR = 30; // vertical gap (data flow) between the two boxes
const ENC_CX = 272;
const DEC_CX = 768;

export const ArchStack: React.FC<ArchStackProps> = ({
  layers = 6,
  subLayers = ["Multi-Head Attention", "Feed-Forward"],
  note,
  revealFrames,
  // words / durationInFrames accepted per contract; staging is reveal-driven.
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const r0 = revealFrames[0] ?? 0; // labels
  const r1 = revealFrames[1] ?? r0 + 18; // encoder build
  const r2 = revealFrames[2] ?? r1 + 30; // decoder build

  const n = subLayers.length;
  const BOX_H = PAD_Y * 2 + n * SUB_H + (n - 1) * SUB_GAP;
  const BOX1_BOT = BOX1_TOP + BOX_H;
  const BOX2_TOP = BOX1_BOT + CONNECTOR;
  const BOX2_MID = BOX2_TOP + BOX_H / 2;

  const noteText = note ?? `× ${layers} · residual + layer-norm · d_model = 512`;

  const labelOp = interpolate(frame, [r0, r0 + 8], [0, 1], clamp);
  const noteOp = interpolate(frame, [r2 + 10, r2 + 24], [0, 1], clamp);

  // One representative layer-box: faint depth-ghosts (suggesting the N-stack),
  // an outline container, the sub-layer inner blocks, and per-sub residual
  // wrap-arrows. Springs/scales in from `startFrame`.
  const renderBox = (cx: number, startFrame: number, key: string) => {
    const p = spring({ frame: frame - startFrame, fps, durationInFrames: 18, config: { damping: 200 } });
    const op = interpolate(frame, [startFrame, startFrame + 6], [0, 1], clamp);
    const s = interpolate(p, [0, 1], [0.9, 1]);
    const wrap = interpolate(frame, [startFrame + 8, startFrame + 26], [0, 1], clamp);
    const bx = cx - BW / 2;
    const cy = BOX1_TOP + BOX_H / 2;

    return (
      <g key={key} opacity={op} transform={`translate(${cx} ${cy}) scale(${s}) translate(${-cx} ${-cy})`}>
        {/* depth-ghosts behind — the box repeats N times */}
        {[12, 6].map((o) => (
          <rect
            key={o}
            x={bx + o}
            y={BOX1_TOP - o}
            width={BW}
            height={BOX_H}
            rx={6}
            fill="none"
            stroke="var(--rule)"
            strokeWidth={1}
            opacity={0.18}
          />
        ))}

        {/* container outline */}
        <rect x={bx} y={BOX1_TOP} width={BW} height={BOX_H} rx={6} fill="none" stroke="var(--rule)" strokeWidth={1.5} />

        {subLayers.map((label, i) => {
          const subTop = BOX1_TOP + PAD_Y + i * (SUB_H + SUB_GAP);
          const isAttn = /attention/i.test(label);
          const fill = isAttn ? "var(--accent-soft)" : "var(--surface-2)";
          const stroke = isAttn ? "var(--accent)" : "var(--rule)";
          const textFill = isAttn ? "var(--accent)" : "var(--text-2)";
          return (
            <g key={i}>
              {/* residual + layer-norm wrap-arrow hugging the left edge */}
              <path
                d={`M ${bx + PAD_X} ${subTop + SUB_H - 5} C ${bx + PAD_X - 22} ${subTop + SUB_H - 5}, ${bx + PAD_X - 22} ${subTop + 5}, ${bx + PAD_X} ${subTop + 5}`}
                pathLength={1}
                fill="none"
                stroke="var(--rule)"
                strokeWidth={1.25}
                strokeDasharray={1}
                strokeDashoffset={1 - wrap}
                markerEnd="url(#as-tip)"
                opacity={0.75}
              />
              <rect
                x={bx + PAD_X}
                y={subTop}
                width={BW - 2 * PAD_X}
                height={SUB_H}
                rx={4}
                fill={fill}
                stroke={stroke}
                strokeWidth={1.25}
              />
              <text
                x={cx}
                y={subTop + SUB_H / 2}
                textAnchor="middle"
                dominantBaseline="central"
                fontFamily="var(--font-mono)"
                fontSize={16}
                letterSpacing={0.5}
                fill={textFill}
              >
                {label}
              </text>
            </g>
          );
        })}
      </g>
    );
  };

  // Vertical data-flow connector between the two representative boxes.
  const connector = (cx: number, startFrame: number, key: string) => {
    const d = interpolate(frame, [startFrame + 4, startFrame + 16], [0, 1], clamp);
    return (
      <line
        key={key}
        x1={cx}
        y1={BOX1_BOT}
        x2={cx}
        y2={BOX1_BOT + (BOX2_TOP - BOX1_BOT) * d}
        stroke="var(--rule)"
        strokeWidth={1.5}
        markerEnd="url(#as-tip)"
        opacity={d * 0.85}
      />
    );
  };

  // Column header: ENCODER / DECODER label + "× N" multiplier badge.
  const header = (cx: number, label: string, key: string) => {
    const bx = cx + BW / 2 + 10;
    const by = BOX1_TOP + BOX_H / 2 - 13;
    return (
      <g key={key} opacity={labelOp}>
        <text
          x={cx}
          y={LABEL_Y}
          textAnchor="middle"
          fontFamily="var(--font-mono)"
          fontSize={18}
          letterSpacing={4}
          fill="var(--text-mute)"
        >
          {label}
        </text>
        <rect x={bx} y={by} width={50} height={26} rx={13} fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth={1} />
        <text
          x={bx + 25}
          y={by + 13}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily="var(--font-mono)"
          fontSize={14}
          fill="var(--accent)"
        >
          {`× ${layers}`}
        </text>
      </g>
    );
  };

  // Encoder context → decoder cross-attention (K · V).
  const crossOp = interpolate(frame, [r2 + 14, r2 + 32], [0, 1], clamp);
  const encRight = ENC_CX + BW / 2; // 432
  const decLeft = DEC_CX - BW / 2; // 608

  return (
    <Surface>
      <div style={{ display: "flex", flexDirection: "column", height: "100%", justifyContent: "center", gap: "var(--space-5)" }}>
        <svg viewBox={`0 0 ${VW} ${VH}`} preserveAspectRatio="xMidYMid meet" style={{ width: "100%", flex: 1, overflow: "visible" }}>
          <defs>
            <marker id="as-tip" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={6} markerHeight={6} orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="var(--rule)" />
            </marker>
            <marker id="as-tip-accent" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={6} markerHeight={6} orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="var(--accent)" />
            </marker>
          </defs>

          {/* headers */}
          {header(ENC_CX, "ENCODER", "h-enc")}
          {header(DEC_CX, "DECODER", "h-dec")}

          {/* encoder column — stage 1 (staggered) */}
          {renderBox(ENC_CX, r1, "enc-1")}
          {connector(ENC_CX, r1 + 10, "enc-c")}
          <g transform={`translate(0 ${BOX2_TOP - BOX1_TOP})`}>{renderBox(ENC_CX, r1 + 10, "enc-2")}</g>

          {/* decoder column — stage 2 (staggered) */}
          {renderBox(DEC_CX, r2, "dec-1")}
          {connector(DEC_CX, r2 + 10, "dec-c")}
          <g transform={`translate(0 ${BOX2_TOP - BOX1_TOP})`}>{renderBox(DEC_CX, r2 + 10, "dec-2")}</g>

          {/* cross-attention link: encoder context (K · V) → decoder */}
          <g opacity={crossOp * 0.9}>
            <line x1={encRight} y1={BOX2_MID} x2={decLeft - 2} y2={BOX2_MID} stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="5 5" markerEnd="url(#as-tip-accent)" opacity={0.7} />
            <text x={(encRight + decLeft) / 2} y={BOX2_MID - 12} textAnchor="middle" fontFamily="var(--font-mono)" fontSize={13} letterSpacing={2} fill="var(--text-mute)">
              K · V
            </text>
          </g>
        </svg>

        {/* note caption */}
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-micro)",
            letterSpacing: "var(--track-caps)",
            textTransform: "uppercase",
            color: "var(--text-mute)",
            textAlign: "center",
            opacity: noteOp,
          }}
        >
          {noteText}
        </div>
      </div>
    </Surface>
  );
};
