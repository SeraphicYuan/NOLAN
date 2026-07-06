import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { Surface } from "../../Surface";

// Chapter-library block: a documentary establishing-shot location stamp — a
// place name slides up under an accent underline, then a date / sublocation /
// coordinates meta column fades in staggered. Pure function of useCurrentFrame()
// — no random/date/timers/CSS-transitions — wraps content in <Surface> and uses
// ONLY semantic theme tokens so all themes apply unchanged. `useCurrentFrame()`
// is step-relative; `revealFrames` come from the narration upstream. No <Audio>.
//
// Rebuild of NOLAN's PIL LocationStampRenderer.

type Word = { text: string; startFrame: number; endFrame: number };

export type LocationStampProps = {
  location: string;
  date?: string;
  sublocation?: string;
  coordinates?: string;       // e.g. "47.5596° N, 7.5886° E"
  align?: "left" | "center";  // default "left"
  revealFrames: number[];     // [location cue, then meta stagger]
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
// Cadence between sibling meta reveals, mirroring the --stagger-step token
// (~70ms) translated to whole frames for deterministic, font-safe timing.
const STAGGER = 8;

export const LocationStamp: React.FC<LocationStampProps> = ({
  location,
  date,
  sublocation,
  coordinates,
  align = "left",
  revealFrames,
  words = [],
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const centered = align === "center";

  // Location cue falls back to the first spoken word so the stamp still lands
  // if the upstream reveal schedule is short.
  const locRf = revealFrames[0] ?? words[0]?.startFrame ?? 0;
  const ruleRf = locRf + STAGGER; // underline wipes just after the name settles

  // Location: masks up from below and fades in (--font-display-cn / --t-h1).
  const locS = spring({ frame: frame - locRf, fps, durationInFrames: 18, config: { damping: 200 } });
  const locY = interpolate(locS, [0, 1], [90, 0]);
  const locAppear = interpolate(frame, [locRf, locRf + 5], [0, 1], clamp);

  // Accent underline expands from the left (scaleX 0 → 1).
  const ruleS = spring({ frame: frame - ruleRf, fps, durationInFrames: 20, config: { damping: 200 } });
  const ruleScale = interpolate(ruleS, [0, 1], [0, 1], clamp);
  const ruleGlow = interpolate(ruleS, [0, 1], [0, 16], clamp);

  // Meta rows fade in staggered after the underline. Each takes revealFrames[i+1]
  // if scheduled, else a steady stagger from the rule cue.
  const meta = [date, sublocation, coordinates];
  const metaStart = ruleRf + STAGGER;
  const cueFor = (i: number) => revealFrames[i + 1] ?? metaStart + i * STAGGER;

  // Whole stamp eases out as the step ends so the cut feels intentional.
  const outro = interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0.92], clamp);

  return (
    <Surface>
      <div style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: centered ? "center" : "flex-start",
        textAlign: centered ? "center" : "left",
        height: "100%",
        opacity: outro,
      }}>
        {/* Location name — masks up under the clipped row. */}
        <div style={{ overflow: "hidden", paddingBottom: "0.08em" }}>
          <div style={{
            fontFamily: "var(--font-display, var(--font-display-cn))",
            fontWeight: 900,
            fontSize: "var(--t-h1)",
            lineHeight: 1.04,
            color: "var(--text)",
            transform: `translateY(${locY}%)`,
            opacity: locAppear,
          }}>{location}</div>
        </div>

        {/* Accent underline — scaleX wipe from the leading edge. */}
        <div style={{
          height: "var(--rule-w)",
          width: centered ? "44%" : "38%",
          background: "var(--accent)",
          boxShadow: `0 0 ${ruleGlow}px var(--accent-glow)`,
          transform: `scaleX(${ruleScale})`,
          transformOrigin: centered ? "center" : "left center",
          marginTop: "var(--space-5)",
          marginBottom: "var(--space-7)",
        }} />

        {/* Meta column — mono, muted, staggered fade-in. */}
        <div style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-4)",
          alignItems: centered ? "center" : "flex-start",
        }}>
          {meta.map((text, i) => {
            if (!text) return null;
            const rf = cueFor(i);
            const s = spring({ frame: frame - rf, fps, durationInFrames: 16, config: { damping: 200 } });
            const y = interpolate(s, [0, 1], [12, 0]);
            const appear = interpolate(frame, [rf, rf + 6], [0, 1], clamp);
            // Date reads a touch stronger than the rest of the meta.
            return (
              <div key={i} style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--t-micro)",
                letterSpacing: "var(--track-caps)",
                textTransform: "uppercase",
                color: i === 0 ? "var(--text-2)" : "var(--text-mute)",
                transform: `translateY(${y}px)`,
                opacity: appear,
              }}>{text}</div>
            );
          })}
        </div>
      </div>
    </Surface>
  );
};
