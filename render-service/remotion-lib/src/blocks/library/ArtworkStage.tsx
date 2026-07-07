import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { Spotlight, type Region } from "../../primitives/annotate";
import { type CamPose, easeInOut, glideFor, driftScale, MIN_HOLD } from "../../camera";

// ArtworkStage — the workhorse of the ART flow. An artwork beat is a PERSISTENT hero
// image the camera TOURS: establish the whole, then — as the narration names a detail —
// the camera GLIDES (eased pan+zoom) to it, dims the rest (spotlight), and labels it.
// The image IS the subject; the explanation is the camera. Motion is native +
// frame-driven (no external lib): a keyframed camera with distance-proportional eased
// glides between regions (camera grammar in ../../camera.ts — no pull-back before the
// cut, ambient drift between moves). Focus regions are anchored to spoken words via
// CURSOR matching (so a word that recurs — "Death" — hits the right occurrence).
type Word = { text: string; startFrame: number; endFrame: number };
type Focus = { word: string; x: number; y: number; w: number; h: number; caption?: string };
type Label = { title: string; artist?: string; date?: string; medium?: string; collection?: string };
export type ArtworkStageProps = {
  src: string;
  label?: Label;
  focuses?: Focus[];
  introHold?: number;   // frames to hold the whole before the first move
  maxZoom?: number;     // cap zoom — keep lower-res scans legible (default 1.6)
  glide?: number;       // frames a camera move takes (default 26 — slow/cinematic)
  // Camera mode. "tour" = word-anchored keyframe track (deliberate moves).
  // The kenburns-* modes are ONE continuous eased move across the WHOLE
  // step — no hold-then-lunge gear change (the aeneid feedback: every still
  // sat, then zoomed abruptly). in = push to the focus; out = start at the
  // focus, ease to the whole (reveal); pan = lateral drift at fixed zoom;
  // drift = the ambient push only.
  mode?: "tour" | "kenburns-in" | "kenburns-out" | "kenburns-pan" | "drift";
  revealFrames: number[];
  words: Word[];
  durationInFrames: number;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const _norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

type Cam = { at: number; region: Region | null; caption?: string; deliberate?: boolean };
const camParams = (region: Region | null, maxZoom: number): CamPose => {
  if (!region) return { s: 1, ox: 50, oy: 50 };
  const s = Math.min(maxZoom, 0.78 / Math.max(region.w, region.h, 0.01));
  return { s, ox: (region.x + region.w / 2) * 100, oy: (region.y + region.h / 2) * 100 };
};

export const ArtworkStage: React.FC<ArtworkStageProps> = ({
  src, label, focuses = [], introHold = 40, maxZoom = 1.6, glide = 26,
  mode = "tour", revealFrames, words, durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const r0 = revealFrames[0] ?? 0;

  // Continuous Ken Burns modes: ONE eased move spanning the whole step.
  if (mode !== "tour") {
    const f0 = focuses[0];
    const target = camParams(f0 ? { x: f0.x, y: f0.y, w: f0.w, h: f0.h } : null, maxZoom);
    const whole: CamPose = { s: 1.04, ox: 50, oy: 50 };   // never a dead-flat frame
    const p = easeInOut(Math.min(1, Math.max(0,
      (frame - r0) / Math.max(1, durationInFrames - r0 - 1))));
    let s = 1, ox = 50, oy = 50;
    if (mode === "kenburns-in") {
      s = whole.s + (target.s - whole.s) * p;
      ox = whole.ox + (target.ox - whole.ox) * p;
      oy = whole.oy + (target.oy - whole.oy) * p;
    } else if (mode === "kenburns-out") {
      s = target.s + (whole.s - target.s) * p;
      ox = target.ox + (whole.ox - target.ox) * p;
      oy = target.oy + (whole.oy - target.oy) * p;
    } else if (mode === "kenburns-pan") {
      s = Math.min(maxZoom, 1.16);
      const x0 = target.ox <= 50 ? Math.min(72, 100 - target.ox)
                                 : Math.max(28, 100 - target.ox);
      ox = x0 + (target.ox - x0) * p;
      oy = target.oy;
    } else {                                               // drift
      s = 1 + 0.06 * p;
      ox = target.ox; oy = target.oy;
    }
    const imgIn0 = interpolate(frame - r0, [0, 18], [0, 1], clamp);
    const labelOp0 = interpolate(frame - r0, [16, 32], [0, 1], clamp);
    return (
      <AbsoluteFill style={{ background: "var(--surface)" }}>
        <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center", opacity: imgIn0 }}>
          <div style={{ position: "relative", height: "86%", transform: `scale(${s})`, transformOrigin: `${ox}% ${oy}%` }}>
            <Img src={staticFile(src)} style={{ display: "block", height: "100%", width: "auto", boxShadow: "0 30px 90px rgba(0,0,0,0.6)" }} />
          </div>
        </AbsoluteFill>
        {label ? (
          <div style={{ position: "absolute", left: "var(--space-9)", top: "var(--space-7)", opacity: labelOp0,
            borderLeft: "3px solid var(--accent)", paddingLeft: "var(--space-4)", maxWidth: 460 }}>
            <div style={{ fontFamily: "var(--font-display, var(--font-display-cn))", fontWeight: 700, fontSize: 30, color: "var(--text)", lineHeight: 1.1 }}>{label.title}</div>
            {label.artist || label.date ? (
              <div style={{ fontFamily: "var(--font-body)", fontStyle: "italic", fontSize: 20, color: "var(--text-2)", marginTop: 6 }}>
                {[label.artist, label.date].filter(Boolean).join(", ")}</div>
            ) : null}
            {label.medium || label.collection ? (
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)", marginTop: 8 }}>
                {[label.medium, label.collection].filter(Boolean).join(" · ")}</div>
            ) : null}
          </div>
        ) : null}
      </AbsoluteFill>
    );
  }

  // Resolve each focus to its spoken word via a CURSOR (first match after the previous),
  // then build the camera keyframe track: establish → each focus. There is NO final
  // pull-back — the camera grammar bans resetting before a cut (the "zip back" incident);
  // the shot ends easing into (or slowly drifting past) its last framing.
  let cur = 0;
  const cams: Cam[] = [{ at: r0, region: null }];
  focuses.forEach((f, i) => {
    let at = r0 + introHold + i * 90;
    const t = _norm(f.word);
    for (let j = cur; j < words.length; j++) {
      const wn = _norm(words[j].text);
      if (wn && (wn === t || (t.length >= 3 && wn.length >= 3 && (wn.includes(t) || t.includes(wn))))) {
        at = words[j].startFrame; cur = j + 1; break;
      }
    }
    cams.push({ at, region: { x: f.x, y: f.y, w: f.w, h: f.h }, caption: f.caption,
      deliberate: Boolean(f.word || f.caption) });
  });
  cams.sort((a, b) => a.at - b.at);

  // Per-segment glides: proportional to travel distance (tempo's `glide` is the pacing
  // floor), and each move may only start after the previous one has landed + MIN_HOLD.
  const poses = cams.map((c) => camParams(c.region, maxZoom));
  const glides: number[] = [0];
  for (let i = 1; i < cams.length; i++) {
    glides.push(glideFor(poses[i - 1], poses[i], fps, glide));
    const earliest = cams[i - 1].at + glides[i - 1] + MIN_HOLD;
    if (cams[i].at < earliest) cams[i] = { ...cams[i], at: earliest };
  }

  // current camera = glide from the previous keyframe to the one we've reached.
  let ti = 0;
  for (let i = 0; i < cams.length; i++) if (frame >= cams[i].at) ti = i;
  const target = cams[ti];
  const seg = ti === 0 ? 0 : glides[ti];
  const t = ti === 0 ? 1 : easeInOut(interpolate(frame, [target.at, target.at + seg], [0, 1], clamp));
  const a = poses[Math.max(0, ti - 1)];
  const b = poses[ti];
  // Ambient drift: a slow push that accumulates ONLY across rest windows (it pauses,
  // never rewinds, while a deliberate glide runs) — nothing is ever fully still, and
  // the cut lands on motion instead of a freeze.
  let rested = 0;
  for (let i = 0; i <= ti; i++) {
    const restStart = cams[i].at + (i === 0 ? 0 : glides[i]);
    const restEnd = i < ti ? cams[i + 1].at : frame;
    rested += Math.max(0, Math.min(restEnd, frame) - restStart);
  }
  const drift = driftScale(rested, fps, Math.min(1.08, (maxZoom * 1.02) / Math.max(b.s, 1)));
  const s = (a.s + (b.s - a.s) * t) * drift;
  const ox = a.ox + (b.ox - a.ox) * t;
  const oy = a.oy + (b.oy - a.oy) * t;

  const imgIn = interpolate(frame - r0, [0, 18], [0, 1], clamp);
  const labelOp = interpolate(frame - r0, [introHold * 0.4, introHold * 0.4 + 16], [0, 1], clamp);
  // spotlight tracks the target focus (off when resting on the whole). Only
  // DELIBERATE focuses (word-anchored or captioned — an annotation) dim the
  // rest; the synthesized camera targets premium's still-motion generates
  // (word "") are pure camera moves, and dimming there reads as a glass
  // panel over bright footage.
  const spotAmt = target.region && target.deliberate ? t : 0;

  return (
    <AbsoluteFill style={{ background: "var(--surface)" }}>
      <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center", opacity: imgIn }}>
        <div style={{ position: "relative", height: "86%", transform: `scale(${s})`, transformOrigin: `${ox}% ${oy}%` }}>
          <Img src={staticFile(src)} style={{ display: "block", height: "100%", width: "auto", boxShadow: "0 30px 90px rgba(0,0,0,0.6)" }} />
          <Spotlight region={target.region} amount={spotAmt} id={`art-${r0}`} />
          {target.caption && t > 0.4 ? (
            // place the callout above the region, but flip it BELOW when the region hugs the
            // top edge (else the pill clips off-screen).
            (() => {
              const below = target.region!.y < 0.16;
              const top = below ? (target.region!.y + target.region!.h) * 100 : target.region!.y * 100;
              return (
                <div style={{ position: "absolute", left: `${target.region!.x * 100}%`, top: `${top}%`,
                  transform: below ? "translateY(20%)" : "translateY(-130%)", opacity: interpolate(t, [0.4, 0.8], [0, 1], clamp) }}>
                  <div style={{ display: "inline-block", whiteSpace: "nowrap", padding: "6px 12px", background: "var(--accent)",
                    color: "var(--surface)", fontFamily: "var(--font-mono)", fontSize: 15, letterSpacing: "0.04em",
                    borderRadius: "var(--r-sm, 4px)", boxShadow: "0 0 18px var(--accent-glow)" }}>{target.caption}</div>
                </div>
              );
            })()
          ) : null}
        </div>
      </AbsoluteFill>

      {label ? (
        <div style={{ position: "absolute", left: "var(--space-9)", top: "var(--space-7)", opacity: labelOp,
          transform: `translateY(${interpolate(labelOp, [0, 1], [-14, 0])}px)`, borderLeft: "3px solid var(--accent)",
          paddingLeft: "var(--space-4)", maxWidth: 460 }}>
          <div style={{ fontFamily: "var(--font-display, var(--font-display-cn))", fontWeight: 700, fontSize: 30, color: "var(--text)", lineHeight: 1.1 }}>{label.title}</div>
          {label.artist || label.date ? (
            <div style={{ fontFamily: "var(--font-body)", fontStyle: "italic", fontSize: 20, color: "var(--text-2)", marginTop: 6 }}>
              {[label.artist, label.date].filter(Boolean).join(", ")}</div>
          ) : null}
          {label.medium || label.collection ? (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, letterSpacing: "var(--track-caps)", textTransform: "uppercase", color: "var(--text-mute)", marginTop: 8 }}>
              {[label.medium, label.collection].filter(Boolean).join(" · ")}</div>
          ) : null}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
