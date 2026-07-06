import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {Theme, resolveTheme} from './theme';

// Procedural photo GRID with a 3-step choreography (sibling of PhotoMontage):
//   1. N images fly in to fill a cols×rows grid — sequenced one-by-one, by row, or by col.
//   2. one image zooms to fill the center while the rest of the grid peters out.
//   3. that image zooms back to its cell and the grid comes back in.
// Everything is computed from the grid shape + a few timings, so 40 images is just data.

export type GridImage = {src: string; caption?: string};

export type PhotoGridProps = {
  cards: GridImage[];
  cols: number;
  rows: number;
  order?: 'one-by-one' | 'row' | 'col';     // fly-in sequencing
  flyFrom?: 'edges' | 'bottom' | 'scale';   // where cells fly in from
  // timing (seconds)
  fillStart?: number;   // when the fly-in begins (default 0.2)
  stagger?: number;     // delay between successive units (cell/row/col) (default 0.08)
  flyDur?: number;      // each cell's fly-in duration (default 0.6)
  // focus step
  focusIndex?: number;  // which image zooms to center (default the middle one)
  focusAt?: number;     // when the zoom-in starts (default after fill + 0.5s)
  focusMove?: number;   // zoom in/out duration (default 0.7)
  focusHold?: number;   // how long it stays centered (default 1.6)
  focusScale?: number;  // centered height as a fraction of frame height (default 0.8)
  // look
  gap?: number;         // unused placeholder for future cell gap tuning
  margin?: number;      // outer margin, fraction of frame (default 0.05)
  frame?: 'polaroid' | 'plain' | 'cutout';
  background?: string;
  vignette?: number;
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const isColor = (s?: string) => !!s && /^(#|rgb|hsl|[a-z]+$)/i.test(s);
const easeOut = Easing.out(Easing.cubic);
const easeInOut = Easing.inOut(Easing.cubic);

const Framed: React.FC<{src: string; h: number; frame: string; caption?: string; captionOp: number}> = ({
  src, h, frame, caption, captionOp,
}) => {
  const img = <Img src={staticFile(src)} style={{height: h, width: 'auto', display: 'block'}} />;
  if (frame === 'cutout') return <div style={{filter: `drop-shadow(0 ${0.02 * h}px ${0.03 * h}px rgba(0,0,0,0.55))`}}>{img}</div>;
  if (frame === 'plain') return <div style={{border: '2px solid #f4f2ec', boxShadow: `0 ${0.03 * h}px ${0.05 * h}px rgba(0,0,0,0.5)`, lineHeight: 0}}>{img}</div>;
  const mat = Math.max(6, h * 0.05);
  return (
    <div style={{background: '#faf9f4', padding: `${mat}px ${mat}px ${caption ? mat * 2.4 : mat * 1.3}px`, boxShadow: `0 ${0.035 * h}px ${0.06 * h}px rgba(0,0,0,0.5)`, position: 'relative'}}>
      {img}
      {caption && captionOp > 0.01 && (
        <div style={{position: 'absolute', left: 0, right: 0, bottom: mat * 0.5, textAlign: 'center', opacity: captionOp}}>
          <span style={{fontFamily: `'Segoe Script', 'Bradley Hand', cursive`, fontSize: h * 0.08, color: '#2e2a30'}}>{caption}</span>
        </div>
      )}
    </div>
  );
};

export const PhotoGrid: React.FC<PhotoGridProps> = ({
  cards = [], cols, rows, order = 'one-by-one', flyFrom = 'edges',
  fillStart = 0.2, stagger = 0.08, flyDur = 0.6,
  focusIndex, focusAt, focusMove = 0.7, focusHold = 1.6, focusScale = 0.8,
  margin = 0.05, frame = 'polaroid', background = '#241016', vignette = 0.5, theme,
  durationInFrames,
}) => {
  const f = useCurrentFrame();
  const {fps, width, height, durationInFrames: cfgDur} = useVideoConfig();
  const th = resolveTheme(theme);
  const durSec = Math.max(1, durationInFrames || cfgDur) / fps;

  const n = Math.min(cards.length, cols * rows);
  const mx = margin * width;
  const my = margin * height;
  const cw = (width - 2 * mx) / cols;
  const ch = (height - 2 * my) / rows;
  const baseH = ch * 0.82;          // card height inside a cell
  const focusH = focusScale * height;

  const units = order === 'row' ? rows : order === 'col' ? cols : n;
  // Adaptive choreography (bench audit): the default schedule assumes a long
  // beat — on a short step the grid never finished filling and the focus
  // phase never ran. Compress the fill to <=45% of the step; give the focus
  // whatever honestly fits, or skip it (fill-only) when it can't.
  const naturalFill = fillStart + (units - 1) * stagger + flyDur;
  const k = Math.min(1, (durSec * 0.45) / Math.max(0.001, naturalFill));
  const stg = stagger * k;
  const fd = Math.max(0.2, flyDur * k);
  const fillEnd = fillStart * Math.min(1, k * 2) + (units - 1) * stg + fd;
  const focusFits = durSec - fillEnd - 0.3 >= 2 * focusMove + 0.4;
  const fStart = focusFits ? (focusAt ?? fillEnd + 0.3) : durSec + 99;
  const hold = focusFits
    ? Math.max(0.4, Math.min(focusHold, durSec - fStart - 2 * focusMove - 0.2))
    : focusHold;
  const rStart = fStart + focusMove + hold;
  const fIdx = focusIndex == null ? Math.floor(n / 2) : focusIndex;

  const bgIsColor = isColor(background);
  const vig = `radial-gradient(ellipse at center, transparent 42%, rgba(0,0,0,${vignette}) 100%)`;

  return (
    <AbsoluteFill style={{backgroundColor: bgIsColor ? background : th.bg, fontFamily: th.fontFamily}}>
      {background && !bgIsColor && <Img src={staticFile(background)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />}
      {cards.slice(0, n).map((card, i) => {
        const r = Math.floor(i / cols);
        const c = i % cols;
        const cellX = mx + (c + 0.5) * cw;
        const cellY = my + (r + 0.5) * ch;

        // --- phase 1: fly in ---
        const unit = order === 'row' ? r : order === 'col' ? c : i;
        const ti = fillStart * Math.min(1, k * 2) + unit * stg;
        const flyP = interpolate(f, [ti * fps, (ti + fd) * fps], [0, 1], {...clamp, easing: easeOut});
        let sx: number;
        let sy: number;
        let fromScale: number;
        if (flyFrom === 'bottom') {
          sx = cellX; sy = height * 1.35; fromScale = 1.1;
        } else if (flyFrom === 'scale') {
          sx = cellX; sy = cellY; fromScale = 1.8;
        } else {
          // radial: starts off-screen along the cell's direction from center, flies inward
          sx = width * 0.5 + (cellX - width * 0.5) * 2.5;
          sy = height * 0.5 + (cellY - height * 0.5) * 2.5;
          fromScale = 1.2;
        }
        let px = interpolate(flyP, [0, 1], [sx, cellX]);
        let py = interpolate(flyP, [0, 1], [sy, cellY]);
        let h = baseH * interpolate(flyP, [0, 1], [fromScale, 1]);
        let op = flyP;
        let z = i;
        let captionOp = 0;

        // --- phases 2 & 3: focus zoom in, then return ---
        const fP = interpolate(f, [fStart * fps, (fStart + focusMove) * fps], [0, 1], {...clamp, easing: easeInOut});
        const rP = interpolate(f, [rStart * fps, (rStart + focusMove) * fps], [0, 1], {...clamp, easing: easeInOut});
        const amt = Math.max(0, Math.min(1, fP - rP)); // 0 = in grid, 1 = centered

        if (i === fIdx) {
          px = interpolate(amt, [0, 1], [cellX, width * 0.5]);
          py = interpolate(amt, [0, 1], [cellY, height * 0.5]);
          h = interpolate(amt, [0, 1], [baseH, focusH]);
          z = amt > 0.001 ? 9999 : i;
          captionOp = amt;
        } else {
          op = op * (1 - amt); // the rest of the grid peters out, then comes back
        }

        if (op <= 0.001) return null;
        return (
          <div key={i} style={{position: 'absolute', left: px, top: py, opacity: op, zIndex: z, transform: `translate(-50%,-50%) scale(${h / baseH})`, transformOrigin: 'center center'}}>
            <Framed src={card.src} h={baseH} frame={frame} caption={card.caption} captionOp={captionOp} />
          </div>
        );
      })}
      {vignette > 0 && <AbsoluteFill style={{backgroundImage: vig, pointerEvents: 'none'}} />}
    </AbsoluteFill>
  );
};
