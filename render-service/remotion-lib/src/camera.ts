// Camera grammar — the ONE place premium camera physics lives.
//
// Every comp that moves a virtual camera over a still (ArtworkStage,
// StillMotion, montage/grid cards) obeys the same rules, so "the same module
// name" always means "the same craft":
//
//  1. Glide time is PROPORTIONAL to travel distance (a deep zoom takes longer
//     than a nudge) — a fixed-length glide reads as a whiplash "zip".
//  2. Ease both ends (easeInOutCubic). No linear starts, no hard stops.
//  3. NEVER reset the camera before a cut. Editors either cut while the move
//     is still going (cut on motion) or ease into a hold at the framing —
//     the pull-back-to-whole keyframe is banned (the Ken Burns "zip back"
//     incident, homer-2beat-test 2026-07).
//  4. A focus rests at least MIN_HOLD frames before the next move starts.
//  5. Nothing is ever fully still: outside deliberate moves the camera
//     drifts at DRIFT_RATE (slow push), capped by the comp's maxZoom.

export type CamPose = { s: number; ox: number; oy: number }; // scale, origin %

export const easeInOut = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

export const MIN_HOLD = 18;        // frames a focus rests before the next move
export const MIN_GLIDE = 20;       // floor for any deliberate move (frames)
export const MAX_GLIDE = 75;       // ceiling — past this a move feels detached
export const ZOOM_RATE = 0.4;      // deliberate-move budget: scale units / s
export const PAN_RATE = 0.6;       // deliberate-move budget: frame-widths / s
export const DRIFT_RATE = 0.014;   // ambient push: scale units / s (2–6% over a hold)

// Normalized travel between two poses (scale term + pan term).
export const camDistance = (a: CamPose, b: CamPose) =>
  Math.abs(b.s - a.s) / ZOOM_RATE +
  Math.hypot(b.ox - a.ox, b.oy - a.oy) / 100 / PAN_RATE;

// Frames a glide between two poses should take. `base` carries the tempo
// pass's speed intent (slow/medium/fast) as a floor — pacing can slow a move
// down, but distance decides how long it NEEDS.
export const glideFor = (a: CamPose, b: CamPose, fps: number, base = MIN_GLIDE) =>
  Math.round(Math.min(MAX_GLIDE,
    Math.max(MIN_GLIDE, base, camDistance(a, b) * fps)));

// Ambient drift multiplier: slow push applied OUTSIDE deliberate moves so no
// frame is a freeze — returns the scale factor for `framesResting` at rest.
export const driftScale = (framesResting: number, fps: number, cap = 1.08) =>
  Math.min(cap, 1 + (Math.max(0, framesResting) / fps) * DRIFT_RATE);
