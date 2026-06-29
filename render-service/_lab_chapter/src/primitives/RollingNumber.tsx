import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

// Shared primitive: "a number that rolls from `from` to `value` exactly as its
// spoken `word` lands." Extracted because StatCount and ValueLadder (and any
// future stat block) all need the same per-word count-up — the reusable atom is
// the mechanic, not the block. Blocks compose from this.
export type Word = { text: string; startFrame: number; endFrame: number };

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Live integer rolling `from`→`value` across the word's window, + helpers. */
export function useCountToWord(
  words: Word[],
  word: string,
  value: number,
  opts: { from?: number; fallback?: number; spanSec?: number; decimals?: number } = {},
) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const from = opts.from ?? 0;
  const w = words.find((x) => norm(x.text) === norm(word));
  const start = w ? w.startFrame : opts.fallback ?? 0;
  const span = Math.round(fps * (opts.spanSec ?? 0.7));
  // round to `decimals` (default 0) so non-integer stats (e.g. 1.95) count cleanly.
  const f = 10 ** (opts.decimals ?? 0);
  const live = Math.round(
    interpolate(frame, [start, start + span], [from, value], { ...clamp, easing: Easing.out(Easing.cubic) }) * f,
  ) / f;
  const rolling = interpolate(frame, [start, start + span], [1, 0], clamp); // 1 while ticking → 0
  return { live, start, rolling };
}

/** Ready-made rolling number span (tabular nums + accent-glow while ticking). */
export const RollingNumber: React.FC<{
  words: Word[];
  word: string;
  value: number;
  from?: number;
  fallback?: number;
  format?: (n: number) => string;
  style?: React.CSSProperties;
}> = ({ words, word, value, from, fallback, format, style }) => {
  const { live, rolling } = useCountToWord(words, word, value, { from, fallback });
  return (
    <span style={{
      fontVariantNumeric: "tabular-nums",
      textShadow: `0 0 ${interpolate(rolling, [0, 1], [12, 42], clamp)}px var(--accent-glow)`,
      ...style,
    }}>{format ? format(live) : live}</span>
  );
};
