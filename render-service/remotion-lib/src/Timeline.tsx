import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring, Easing} from 'remotion';
import {Theme, resolveTheme} from './theme';

// Timeline — the reference-video "home base" device: era bands over a year
// axis, event markers dropping in as the narration reaches them. Built for
// the MOTIF layer: markers carry `isNew` — accumulated (old) markers are
// visible from frame 0, only this scene's delta animates. A `focus` window
// eases the camera onto the era under discussion. (The Samurai-in-Venice
// Sengoku/Edo/Meiji bar, as a first-class effect.)

export type Era = {label: string; from: number; to: number; color?: string};
export type Marker = {year: number; label: string; emphasis?: boolean; isNew?: boolean};
export type TimelineProps = {
  title?: string;
  start: number;                     // axis start year (negative = BC)
  end: number;                       // axis end year
  eras?: Era[];
  markers?: Marker[];
  focus?: {from: number; to: number};   // zoom window (years)
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const easeInOut = Easing.inOut(Easing.cubic);

const fmtYear = (y: number) => (y < 0 ? `${-y} BC` : `${y}`);

// "nice" tick interval for the span
const tickStep = (span: number) => {
  for (const s of [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500])
    if (span / s <= 12) return s;
  return 5000;
};

export const Timeline: React.FC<TimelineProps> = ({
  title, start, end, eras = [], markers = [], focus, theme,
}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const th = resolveTheme(theme);

  const mx = width * 0.08;                       // axis margins
  const axisW = width - 2 * mx;
  const axisY = height * 0.6;
  const span = Math.max(1, end - start);
  const x = (year: number) => mx + ((year - start) / span) * axisW;

  // --- schedule ---------------------------------------------------------
  const axisIn = interpolate(frame, [0, 18], [0, 1], {...clamp, easing: easeInOut});
  const eraAt = (i: number) => 8 + i * 10;
  const oldMarkers = markers.filter((m) => !m.isNew);
  const newMarkers = markers.filter((m) => m.isNew);
  const newAt = (i: number) => 42 + i * 28;
  const lastNew = newMarkers.length ? newAt(newMarkers.length - 1) + 24 : 40;

  // --- focus zoom (after the delta lands) --------------------------------
  let scale = 1, tx = 0;
  if (focus && focus.to > focus.from) {
    const fw = x(focus.to) - x(focus.from);
    const target = Math.min(2.2, (axisW * 0.7) / Math.max(fw, 1));
    const fc = (x(focus.from) + x(focus.to)) / 2;
    const t = interpolate(frame, [lastNew, lastNew + 34], [0, 1], {...clamp, easing: easeInOut});
    scale = 1 + (target - 1) * t;
    tx = (width / 2 - fc) * t;
  }

  const palette = [th.accent, th.neutral, `${th.accent}99`, `${th.neutral}99`];

  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      {title ? (
        <div style={{position: 'absolute', top: height * 0.12, width: '100%', textAlign: 'center',
          color: th.fg, fontSize: 56, fontWeight: 800, letterSpacing: '-0.02em',
          opacity: interpolate(frame, [0, 14], [0, 1], clamp)}}>{title}</div>
      ) : null}

      <div style={{position: 'absolute', inset: 0,
        transform: `translateX(${tx}px) scale(${scale})`,
        transformOrigin: `50% ${axisY}px`}}>

        {/* era bands above the axis (grow left→right, staggered) */}
        {eras.map((e, i) => {
          const g = interpolate(frame, [eraAt(i), eraAt(i) + 20], [0, 1], {...clamp, easing: easeInOut});
          const left = x(e.from), w = Math.max(0, x(e.to) - x(e.from));
          const c = e.color || palette[i % palette.length];
          return (
            <div key={i}>
              <div style={{position: 'absolute', left, top: axisY - 64, width: w * g, height: 40,
                background: c, borderRadius: 6, opacity: 0.92}} />
              <div style={{position: 'absolute', left, top: axisY - 64, width: w, height: 40,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: th.bg, fontWeight: 800, fontSize: 24, letterSpacing: '0.06em',
                textTransform: 'uppercase',
                opacity: (w >= e.label.length * 18 ? 1 : 0) * (g > 0.7 ? (g - 0.7) / 0.3 : 0),
                overflow: 'hidden', whiteSpace: 'nowrap'}}>{e.label}</div>
            </div>
          );
        })}

        {/* the axis + ticks */}
        <div style={{position: 'absolute', left: mx, top: axisY, height: 4,
          width: axisW * axisIn, background: th.fg, opacity: 0.85, borderRadius: 2}} />
        {(() => {
          const step = tickStep(span);
          const first = Math.ceil(start / step) * step;
          const ticks = [];
          for (let y = first; y <= end; y += step) ticks.push(y);
          return ticks.map((y, i) => (
            <div key={i} style={{opacity: axisIn * 0.9}}>
              <div style={{position: 'absolute', left: x(y) - 1, top: axisY, width: 2, height: 12,
                background: th.fg, opacity: 0.6}} />
              <div style={{position: 'absolute', left: x(y) - 40, top: axisY + 18, width: 80,
                textAlign: 'center', color: th.neutral, fontSize: 20, fontWeight: 600}}>
                {fmtYear(y)}</div>
            </div>
          ));
        })()}

        {/* accumulated markers: present from the start (the motif REMEMBERS) */}
        {oldMarkers.map((m, i) => (
          <MarkerPin key={`o${i}`} px={x(m.year)} axisY={axisY} m={m} th={th}
            appear={interpolate(frame, [20 + i * 3, 30 + i * 3], [0, 1], clamp)}
            lift={96 + (i % 2) * 50} fps={fps} pop={1} />
        ))}
        {/* THIS beat's delta: drops in, sequenced */}
        {newMarkers.map((m, i) => {
          const s = spring({frame: frame - newAt(i), fps, durationInFrames: 20, config: {damping: 14, stiffness: 160}});
          return (
            <MarkerPin key={`n${i}`} px={x(m.year)} axisY={axisY} m={m} th={th}
              appear={interpolate(frame, [newAt(i), newAt(i) + 8], [0, 1], clamp)}
              lift={96 + ((oldMarkers.length + i) % 2) * 50} fps={fps} pop={s} isNew />
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const MarkerPin: React.FC<{
  px: number; axisY: number; m: Marker; th: Theme; appear: number;
  lift: number; fps: number; pop: number; isNew?: boolean;
}> = ({px, axisY, m, th, appear, lift, pop, isNew}) => {
  const c = m.emphasis || isNew ? th.accent : th.neutral;
  return (
    <div style={{opacity: appear}}>
      <div style={{position: 'absolute', left: px - 1.5, top: axisY - lift + 22, width: 3,
        height: (lift - 22) * pop, background: c, opacity: 0.8,
        transformOrigin: 'bottom', bottom: undefined}} />
      <div style={{position: 'absolute', left: px - 7 * pop, top: axisY - 7 * pop,
        width: 14 * pop, height: 14 * pop, borderRadius: '50%', background: c,
        border: `3px solid ${th.bg}`}} />
      <div style={{position: 'absolute', left: px - 150, top: axisY - lift - 12,
        width: 300, textAlign: 'center', transform: `scale(${0.6 + 0.4 * pop})`}}>
        <span style={{display: 'inline-block', padding: '4px 12px', borderRadius: 6,
          background: isNew ? th.accent : `${th.neutral}33`,
          color: isNew ? th.bg : th.fg, fontSize: 22, fontWeight: 700,
          whiteSpace: 'nowrap', maxWidth: 300, overflow: 'hidden',
          textOverflow: 'ellipsis'}}>{m.label}</span>
      </div>
    </div>
  );
};
