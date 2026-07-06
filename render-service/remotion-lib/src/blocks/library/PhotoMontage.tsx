import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

// PhotoMontage — rebuild of NOLAN's PIL PhotoMontageRenderer. A scrapbook cluster of
// polaroid-framed photos scattered on the surface: each card flies in with a slight tilt
// at its cue, settling into a tasteful overlapping pile, while a slow Ken Burns drift
// breathes over the whole arrangement. One "hero" card sits larger and on top, captioned
// in a handwritten-ish display face. Everything is a pure function of the frame —
// scatter offsets + rotations are DERIVED FROM THE CARD INDEX, never random.
type Word = { text: string; startFrame: number; endFrame: number };
type Card = { src: string; caption?: string; x?: number; y?: number; rot?: number };
export type PhotoMontageProps = {
  cards: Card[];          // x/y fractions of the stage, rot degrees (optional; else auto-scatter by index)
  hero?: number;          // index of the emphasized card (larger, on top, captioned)
  kenBurns?: boolean;     // slow drift over the cluster (default true)
  revealFrames: number[]; // one cue per card (cards fly in staggered)
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Deterministic phyllotaxis scatter: golden-angle spiral around the centre, squashed
// vertically into a loose pile. Same index → same spot, every render.
const autoPos = (i: number, n: number) => {
  const ang = i * 2.39996323;                       // golden angle (radians)
  const rad = 0.2 * Math.sqrt((i + 0.5) / Math.max(1, n));
  return { x: 0.5 + Math.cos(ang) * rad, y: 0.5 + Math.sin(ang) * rad * 0.66 };
};
// Deterministic per-index tilt in [-4, 4] degrees.
const autoRot = (i: number) => ((i * 37) % 9) - 4;

export const PhotoMontage: React.FC<PhotoMontageProps> = ({
  cards, hero, kenBurns = true, revealFrames, words, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const n = cards.length;
  const heroIdx = typeof hero === "number" && hero >= 0 && hero < n ? hero : -1;

  // Ken Burns: slow scale 1.0 → 1.06 + a gentle diagonal drift over the whole cluster.
  const kb = kenBurns ? interpolate(frame, [0, Math.max(1, durationInFrames)], [0, 1], clamp) : 0;
  const clusterScale = 1 + kb * 0.06;
  const clusterX = kb * -1.4;   // percent
  const clusterY = kb * 1.2;

  const baseW = width * 0.2;    // base polaroid width in px

  return (
    <AbsoluteFill style={{ background: "var(--surface)", color: "var(--text)", fontFamily: "var(--font-body)" }}>
      <AbsoluteFill style={{
        transform: `translate(${clusterX}%, ${clusterY}%) scale(${clusterScale})`,
        transformOrigin: "50% 48%",
      }}>
        {cards.map((card, i) => {
          const isHero = i === heroIdx;
          const pos = card.x != null && card.y != null ? { x: card.x, y: card.y } : autoPos(i, n);
          const rot = card.rot != null ? card.rot : autoRot(i);
          const cue = revealFrames[i] ?? revealFrames[0] ?? 0;

          // Fly + scale in from a small offset at this card's cue (staggered by the cue track).
          const s = spring({ frame: frame - cue, fps, config: { damping: 200, mass: 0.9 }, durationInFrames: 26 });
          const op = interpolate(s, [0, 1], [0, 1]);
          // approach direction derived from the deterministic tilt — cards drift in from
          // the side they're tilted toward, so the entrance reads with the final pose.
          const dx = interpolate(s, [0, 1], [rot * 2.2 - 6, 0]);
          const dy = interpolate(s, [0, 1], [34, 0]);
          const scl = interpolate(s, [0, 1], [0.82, isHero ? 1.36 : 1]);
          const tilt = interpolate(s, [0, 1], [rot * 1.6, rot]);

          const w = baseW;
          const imgH = w * 0.82;        // polaroid image window (slightly landscape)

          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${pos.x * 100}%`,
                top: `${pos.y * 100}%`,
                width: w,
                zIndex: isHero ? 100 : 10 + i,
                opacity: op,
                transform: `translate(-50%, -50%) translate(${dx}px, ${dy}px) rotate(${tilt}deg) scale(${scl})`,
                transformOrigin: "50% 50%",
              }}
            >
              {/* white polaroid frame: padding + image window + caption strip below */}
              <div style={{
                background: "#fbfaf6",
                padding: "10px 10px 0 10px",
                borderRadius: 3,
                boxShadow: isHero
                  ? "0 28px 60px rgba(0,0,0,0.45), 0 8px 18px rgba(0,0,0,0.30)"
                  : "0 16px 34px rgba(0,0,0,0.34), 0 4px 10px rgba(0,0,0,0.22)",
              }}>
                <div style={{ width: "100%", height: imgH, overflow: "hidden", background: "#e7e4dc" }}>
                  <Img src={staticFile(card.src)} style={{ display: "block", width: "100%", height: "100%", objectFit: "cover" }} />
                </div>
                {/* caption strip — the polaroid's bottom band */}
                <div style={{
                  minHeight: isHero ? 52 : 34,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: isHero ? "8px 10px 12px" : "6px 8px 10px",
                }}>
                  {card.caption ? (
                    isHero ? (
                      <span style={{
                        fontFamily: "var(--font-display, var(--font-display-cn))",
                        fontStyle: "italic",
                        fontWeight: 600,
                        fontSize: 26,
                        lineHeight: 1.1,
                        color: "#262220",
                        textAlign: "center",
                      }}>{card.caption}</span>
                    ) : (
                      <span style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "var(--t-micro)",
                        letterSpacing: "0.04em",
                        color: "#6b665e",
                        textAlign: "center",
                      }}>{card.caption}</span>
                    )
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
