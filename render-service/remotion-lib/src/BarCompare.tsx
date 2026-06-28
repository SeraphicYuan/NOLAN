import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import {Theme, resolveTheme} from './theme';

type Bar = {label: string; value: number; color?: string};
export type BarCompareProps = {
  title: string;
  bars: Bar[];
  suffix: string;
  prefix?: string;
  theme?: string | Partial<Theme>;            // SHARED
  barStyle?: 'flat' | 'gradient' | 'glass';   // effect-specific
  durationInFrames: number;
};

const barBackground = (style: string, color: string) => {
  if (style === 'flat') return color;
  if (style === 'glass') return `${color}33`; // translucent fill; border/blur added below
  return `linear-gradient(180deg, ${color}, ${color}99)`; // gradient (default)
};

export const BarCompare: React.FC<BarCompareProps> = ({
  title, bars, suffix, prefix = '', theme, barStyle = 'gradient',
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const th = resolveTheme(theme);
  const maxV = Math.max(...bars.map((b) => b.value), 1);
  const chartH = 600;
  return (
    <AbsoluteFill style={{backgroundColor: th.bg, fontFamily: th.fontFamily}}>
      <div style={{position: 'absolute', top: 90, width: '100%', textAlign: 'center', color: th.fg, fontSize: 62, fontWeight: 800, letterSpacing: '-0.02em'}}>
        {title}
      </div>
      <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 130}}>
        <div style={{display: 'flex', gap: 180, alignItems: 'flex-end', height: chartH}}>
          {bars.map((b, i) => {
            const color = b.color || (i === bars.length - 1 ? th.up : th.neutral);
            const s = spring({frame: frame - i * 9, fps, durationInFrames: 26, config: {damping: 200}});
            const h = interpolate(s, [0, 1], [0, (b.value / maxV) * chartH]);
            const val = Math.round(interpolate(s, [0, 1], [0, b.value]));
            return (
              <div key={i} style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
                <div style={{color, fontSize: 58, fontWeight: 800, marginBottom: 16, opacity: s}}>
                  {prefix}{val.toLocaleString()}{suffix}
                </div>
                <div style={{
                  width: 220, height: h, borderRadius: '14px 14px 0 0',
                  background: barBackground(barStyle, color),
                  boxShadow: barStyle === 'glass' ? `inset 0 0 0 2px ${color}aa` : `0 0 40px ${color}55`,
                  backdropFilter: barStyle === 'glass' ? 'blur(6px)' : undefined,
                }} />
                <div style={{color: th.muted, fontSize: 36, fontWeight: 600, marginTop: 24, maxWidth: 300, textAlign: 'center', lineHeight: 1.2}}>
                  {b.label}
                </div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
