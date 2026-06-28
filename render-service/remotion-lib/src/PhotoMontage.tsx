import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring, Easing} from 'remotion';
import {Theme, resolveTheme} from './theme';

// "Photos on a table" montage with a well-defined per-card motion system.
//
// Each card declares WHERE it rests (x,y,scale,rotation) and HOW it arrives
// (`from` edge + timing + easing) independently — so "come in from the bottom and
// settle in the middle", "slide in from the left and rest on the left", etc. are all
// just data. A slow Ken Burns camera drifts over the whole arrangement.
//
// Extend by adding: new `from` modes, exit tracks, motion paths, blend modes, frame
// styles. The schema below is the contract the Python registry mirrors.

export type CardSpec = {
  src: string;                 // image basename staged into public/
  // resting transform
  x: number;                   // 0..1 center on frame
  y: number;                   // 0..1 center on frame
  scale?: number;              // card height as a fraction of frame height (default 0.42)
  rotation?: number;           // settle rotation IN-PLANE (rotateZ), degrees (default 0)
  rotX?: number;               // 3D tilt about the horizontal axis (rotateX), degrees
  rotY?: number;               // 3D pan about the vertical axis (rotateY), degrees
  perspective?: number;        // 3D perspective depth in px (default 1400; lower = stronger)
  // entrance
  from?: 'left' | 'right' | 'top' | 'bottom' | 'center' | 'none'; // travel-in edge
  enterAt?: number;            // seconds before the entrance starts (default 0)
  enterDur?: number;           // seconds the entrance takes (default 0.7)
  distance?: number;           // how far out it starts, fraction of frame dim (default 0.55)
  ease?: 'out' | 'inOut' | 'spring';  // entrance easing (default 'out')
  fade?: boolean;              // fade alpha 0->1 on entry (default true unless from='none')
  fromScale?: number;          // start scale multiplier (default 0.92)
  fromRotation?: number;       // extra start rotation, degrees (default 0)
  // style
  frame?: 'polaroid' | 'plain' | 'cutout';  // polaroid mat | thin border | bare alpha cutout
  caption?: string;            // handwritten caption (polaroid mat)
  captionAt?: number;          // seconds the caption starts writing (default enterAt+enterDur)
  captionDur?: number;         // seconds to finish writing (default 0.5)
  shadow?: number;             // 0..1 drop-shadow strength (default 0.5)
  // Advanced: an explicit keyframe track. When present it FULLY drives the card's
  // transform (the `from`/`enter*` sugar is ignored) — each property tweens through
  // only the keys that define it. Enables appear-then-tilt, fade-in-then-fade-out,
  // and arbitrary multi-step paths. Times are absolute seconds on the timeline.
  keys?: Array<{
    at: number;
    x?: number; y?: number;      // 0..1 center
    scale?: number;              // height fraction
    rotation?: number;           // in-plane rotateZ, degrees
    rotX?: number;               // 3D tilt (rotateX), degrees
    rotY?: number;               // 3D pan (rotateY), degrees
    opacity?: number;            // 0..1
    ease?: 'linear' | 'in' | 'out' | 'inOut' | 'spring';  // easing INTO this key
  }>;
};

export type PhotoMontageProps = {
  cards: CardSpec[];
  background?: string;         // a CSS color (#.., rgb(..)) OR a staged image basename
  vignette?: number;           // 0..1 edge darkening (default 0.5)
  zoomStart?: number;          // Ken Burns camera zoom at t=0 (default 1.05)
  zoomEnd?: number;            // camera zoom at end (default 1.16)
  panX?: number;               // total camera pan, fraction of frame width (default -0.04)
  panY?: number;               // total camera pan, fraction of frame height (default 0)
  theme?: string | Partial<Theme>;
  durationInFrames: number;
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const isColor = (s?: string) => !!s && /^(#|rgb|hsl|[a-z]+$)/i.test(s);

const easeOf = (e?: string) =>
  e === 'in' ? Easing.in(Easing.cubic)
    : e === 'inOut' ? Easing.inOut(Easing.cubic)
    : e === 'linear' ? Easing.linear
    : Easing.out(Easing.cubic);   // 'out' (default) and 'spring' approximated as out-cubic

// Sample one property of a keyframe track at `frame`. Only the keys that define the
// field participate, so x/y/scale/rotation/opacity each have independent tracks. Holds
// the first/last value outside the range; eases INTO each key with that key's `ease`.
const sample = (keys: any[], field: string, def: number, frame: number, fps: number): number => {
  const pts = keys.filter((k) => k[field] !== undefined).map((k) => ({f: k.at * fps, v: k[field] as number, e: k.ease}));
  if (!pts.length) return def;
  if (frame <= pts[0].f) return pts[0].v;
  const last = pts[pts.length - 1];
  if (frame >= last.f) return last.v;
  for (let i = 0; i < pts.length - 1; i++) {
    if (frame >= pts[i].f && frame <= pts[i + 1].f) {
      return interpolate(frame, [pts[i].f, pts[i + 1].f], [pts[i].v, pts[i + 1].v], {...clamp, easing: easeOf(pts[i + 1].e)});
    }
  }
  return last.v;
};

const Card: React.FC<{card: CardSpec; fps: number}> = ({card, fps}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();

  const baseScale = card.scale ?? 0.42;
  const cardH = baseScale * height;

  let cx: number;
  let cy: number;
  let grow: number;
  let rot: number;
  let alpha: number;
  // 3D pan/tilt (rotateX/rotateY) — default to the card's resting values
  let rotX = card.rotX ?? 0;
  let rotY = card.rotY ?? 0;

  if (card.keys && card.keys.length) {
    // explicit keyframe track fully drives the transform
    cx = sample(card.keys, 'x', card.x, frame, fps) * width;
    cy = sample(card.keys, 'y', card.y, frame, fps) * height;
    grow = sample(card.keys, 'scale', baseScale, frame, fps) / baseScale;
    rot = sample(card.keys, 'rotation', card.rotation ?? 0, frame, fps);
    rotX = sample(card.keys, 'rotX', card.rotX ?? 0, frame, fps);
    rotY = sample(card.keys, 'rotY', card.rotY ?? 0, frame, fps);
    alpha = sample(card.keys, 'opacity', 1, frame, fps);
  } else {
    // simple sugar: one entrance from an edge, settling to the rest transform
    const from = card.from ?? 'none';
    const startF = (card.enterAt ?? 0) * fps;
    const durF = Math.max(1, Math.round((card.enterDur ?? 0.7) * fps));
    let p: number;
    if (from === 'none') p = 1;
    else if ((card.ease ?? 'out') === 'spring')
      p = spring({frame: frame - startF, fps, durationInFrames: durF, config: {damping: 18, stiffness: 90}});
    else {
      const ez = card.ease === 'inOut' ? Easing.inOut(Easing.cubic) : Easing.out(Easing.cubic);
      p = interpolate(frame, [startF, startF + durF], [0, 1], {...clamp, easing: ez});
    }
    const dist = card.distance ?? 0.55;
    let offX = 0;
    let offY = 0;
    if (from === 'left') offX = -(1 - p) * dist * width;
    else if (from === 'right') offX = (1 - p) * dist * width;
    else if (from === 'top') offY = -(1 - p) * dist * height;
    else if (from === 'bottom') offY = (1 - p) * dist * height;
    const fade = card.fade ?? from !== 'none';
    alpha = fade ? interpolate(p, [0, 1], [0, 1], clamp) : 1;
    grow = interpolate(p, [0, 1], [card.fromScale ?? 0.92, 1]);
    const restRot = card.rotation ?? 0;
    rot = interpolate(p, [0, 1], [restRot + (card.fromRotation ?? 0), restRot]);
    cx = card.x * width + offX;
    cy = card.y * height + offY;
  }
  const sh = card.shadow ?? 0.5;
  const style = card.frame ?? 'polaroid';

  // caption type-on (left -> right reveal)
  const capStart = (card.captionAt ?? (card.enterAt ?? 0) + (card.enterDur ?? 0.7)) * fps;
  const capDur = Math.max(1, (card.captionDur ?? 0.5) * fps);
  const capP = interpolate(frame, [capStart, capStart + capDur], [0, 1], clamp);

  const img = (
    <Img src={staticFile(card.src)} style={{height: cardH, width: 'auto', display: 'block'}} />
  );

  let inner: React.ReactNode;
  if (style === 'cutout') {
    // bare alpha silhouette — drop-shadow follows the PNG's transparency
    inner = <div style={{filter: `drop-shadow(0 ${18 * sh}px ${26 * sh}px rgba(0,0,0,${0.55 * sh}))`}}>{img}</div>;
  } else if (style === 'plain') {
    inner = (
      <div style={{border: '3px solid #f4f2ec', boxShadow: `0 ${20 * sh}px ${44 * sh}px rgba(0,0,0,${0.5 * sh})`, lineHeight: 0}}>
        {img}
      </div>
    );
  } else {
    const mat = Math.max(12, cardH * 0.05);
    inner = (
      <div style={{background: '#faf9f4', padding: `${mat}px ${mat}px ${mat * 2.6}px`, boxShadow: `0 ${22 * sh}px ${48 * sh}px rgba(0,0,0,${0.5 * sh})`, position: 'relative'}}>
        {img}
        {card.caption && (
          <div style={{position: 'absolute', left: 0, right: 0, bottom: mat * 0.7, textAlign: 'center', clipPath: `inset(0 ${(1 - capP) * 100}% 0 0)`}}>
            <span style={{fontFamily: `'Segoe Script', 'Bradley Hand', 'Comic Sans MS', cursive`, fontSize: cardH * 0.085, color: '#2e2a30'}}>
              {card.caption}
            </span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{position: 'absolute', left: cx, top: cy, opacity: alpha, transformStyle: 'preserve-3d', transform: `translate(-50%,-50%) perspective(${card.perspective ?? 1400}px) rotateX(${rotX}deg) rotateY(${rotY}deg) rotateZ(${rot}deg) scale(${grow})`, transformOrigin: 'center center'}}>
      {inner}
    </div>
  );
};

export const PhotoMontage: React.FC<PhotoMontageProps> = ({
  cards = [], background, vignette = 0.5, zoomStart = 1.05, zoomEnd = 1.16,
  panX = -0.04, panY = 0, theme,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const th = resolveTheme(theme);

  // Ken Burns camera over the whole arrangement.
  const z = interpolate(frame, [0, durationInFrames], [zoomStart, zoomEnd]);
  const tx = interpolate(frame, [0, durationInFrames], [0, panX * width]);
  const ty = interpolate(frame, [0, durationInFrames], [0, panY * height]);

  const bgIsColor = isColor(background);
  const vig = `radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,${vignette}) 100%)`;

  return (
    <AbsoluteFill style={{backgroundColor: bgIsColor ? (background as string) : th.bg, fontFamily: th.fontFamily}}>
      <AbsoluteFill style={{transform: `scale(${z}) translate(${tx}px, ${ty}px)`, transformOrigin: 'center center'}}>
        {background && !bgIsColor && (
          <Img src={staticFile(background)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        )}
        {cards.map((c, i) => (
          <Card key={i} card={c} fps={fps} />
        ))}
      </AbsoluteFill>
      {vignette > 0 && <AbsoluteFill style={{backgroundImage: vig}} />}
    </AbsoluteFill>
  );
};
