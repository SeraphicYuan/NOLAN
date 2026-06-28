// Shared position vocabulary — mirrors the Python `Position`/`POSITIONS` anchors
// (src/nolan/renderer/layout.py) so a scene spec's `position` means the same thing
// on both backends. `position` is a named anchor OR a normalized {x,y} in 0..1.

export type Anchor =
  | 'top-left' | 'top' | 'top-right'
  | 'left' | 'center' | 'right'
  | 'bottom-left' | 'bottom' | 'bottom-right'
  | 'upper-third' | 'lower-third';

const FRAC: Record<Anchor, [number, number]> = {
  'top-left': [0.2, 0.18], top: [0.5, 0.16], 'top-right': [0.8, 0.18],
  left: [0.2, 0.5], center: [0.5, 0.5], right: [0.8, 0.5],
  'bottom-left': [0.2, 0.82], bottom: [0.5, 0.84], 'bottom-right': [0.8, 0.82],
  'upper-third': [0.5, 0.3], 'lower-third': [0.5, 0.72],
};

export type Position = Anchor | {x: number; y: number} | undefined;

export const resolveAnchor = (position: Position, w: number, h: number) => {
  let fx = 0.5, fy = 0.5;
  if (position && typeof position === 'object') {
    fx = position.x; fy = position.y;
  } else if (typeof position === 'string' && FRAC[position as Anchor]) {
    [fx, fy] = FRAC[position as Anchor];
  }
  return {fx, fy, x: fx * w, y: fy * h};
};
