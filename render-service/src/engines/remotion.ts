import * as fs from 'fs';
import * as path from 'path';
import { spawn } from 'child_process';
import ffmpegInstaller from '@ffmpeg-installer/ffmpeg';
import ffprobeInstaller from '@ffprobe-installer/ffprobe';
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import type { RenderSpec } from '../jobs/types.js';
import { RenderEngine, RenderResult } from './types.js';
import { ensureDir, toNumber, toString } from './utils.js';
import { THEMES } from '../themes.js';

type RemotionPayload = {
  data: Record<string, unknown>;
  width: number;
  height: number;
  duration: number;
  fps: number;
  theme: string;
  outputName: string;
  debug: boolean;
  imageName?: string;
  mapImageName?: string;
};

const DEFAULT_WIDTH = 1920;
const DEFAULT_HEIGHT = 1080;
const DEFAULT_DURATION = 6;
const DEFAULT_FPS = 30;

function resolveDuration(spec: RenderSpec): number {
  const data = spec.data ?? {};
  const duration = (data as Record<string, unknown>).duration;
  return toNumber(spec.duration ?? duration, DEFAULT_DURATION);
}

function resolveFps(spec: RenderSpec): number {
  const data = spec.data ?? {};
  const fps = (data as Record<string, unknown>).fps;
  return toNumber(fps, DEFAULT_FPS);
}

function buildPayload(spec: RenderSpec, outputName: string): RemotionPayload {
  const data = spec.data ?? {};
  const theme = toString(
    spec.theme ?? (data as Record<string, unknown>).theme,
    'default'
  );
  return {
    data,
    width: toNumber(spec.width, DEFAULT_WIDTH),
    height: toNumber(spec.height, DEFAULT_HEIGHT),
    duration: resolveDuration(spec),
    fps: resolveFps(spec),
    theme,
    outputName,
    debug: process.env.REMOTION_DEBUG === '1',
  };
}

function resolveImagePath(spec: RenderSpec): string | null {
  const data = spec.data ?? {};
  const dataRecord = data as Record<string, unknown>;
  const specAny = spec as unknown as Record<string, unknown>;
  // Check nested image_focus.image_path (used by Ken Burns preset)
  const imageFocus = dataRecord.image_focus as Record<string, unknown> | undefined;
  const candidate =
    (typeof dataRecord.image_path === 'string' && dataRecord.image_path) ||
    (typeof dataRecord.image === 'string' && dataRecord.image) ||
    (typeof specAny.image_path === 'string' && specAny.image_path) ||
    (imageFocus && typeof imageFocus.image_path === 'string' && imageFocus.image_path) ||
    '';
  return candidate ? String(candidate) : null;
}

function resolveMapImagePath(spec: RenderSpec): string | null {
  const data = spec.data ?? {};
  const dataRecord = data as Record<string, unknown>;
  const specAny = spec as unknown as Record<string, unknown>;
  const candidate =
    (typeof dataRecord.map_image_path === 'string' && dataRecord.map_image_path) ||
    (typeof dataRecord.map_image === 'string' && dataRecord.map_image) ||
    (typeof specAny.map_image_path === 'string' && specAny.map_image_path) ||
    '';
  return candidate ? String(candidate) : null;
}

type CsvTable = {
  headers: string[];
  rows: string[][];
};

function parseCsvContent(content: string): CsvTable | null {
  const rows: string[][] = [];
  let current: string[] = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < content.length; i += 1) {
    const char = content[i];
    if (char === '"') {
      const next = content[i + 1];
      if (inQuotes && next === '"') {
        field += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (!inQuotes && (char === ',' || char === '\n')) {
      current.push(field);
      field = '';
      if (char === '\n') {
        rows.push(current);
        current = [];
      }
      continue;
    }
    if (char !== '\r') {
      field += char;
    }
  }
  if (field.length > 0 || current.length > 0) {
    current.push(field);
    rows.push(current);
  }
  const cleaned = rows.filter((row) => row.some((cell) => cell.trim().length > 0));
  if (!cleaned.length) {
    return null;
  }
  const headers = cleaned[0].map((cell) => cell.trim());
  const body = cleaned.slice(1).map((row) => row.map((cell) => cell.trim()));
  return { headers, rows: body };
}

function attachCsvTable(payload: RemotionPayload): void {
  const data = payload.data as Record<string, unknown>;
  const csvPath =
    typeof data.csv_path === 'string'
      ? data.csv_path
      : typeof data.csv === 'string'
        ? data.csv
        : '';
  if (!csvPath || !fs.existsSync(csvPath)) {
    return;
  }
  const raw = fs.readFileSync(csvPath, 'utf8');
  const parsed = parseCsvContent(raw);
  if (!parsed) {
    return;
  }
  payload.data = { ...data, csv_table: parsed };
}

function createProjectFiles(
  root: string,
  payload: RemotionPayload,
  imagePath: string | null,
  mapImagePath: string | null
): void {
  const srcDir = path.join(root, 'src');
  const publicDir = path.join(root, 'public');
  ensureDir(srcDir);
  ensureDir(publicDir);

  if (imagePath) {
    const imageName = path.basename(imagePath);
    const targetPath = path.join(publicDir, imageName);
    fs.copyFileSync(imagePath, targetPath);
    payload.imageName = imageName;
  }

  if (mapImagePath) {
    const mapImageName = path.basename(mapImagePath);
    const targetPath = path.join(publicDir, mapImageName);
    fs.copyFileSync(mapImagePath, targetPath);
    payload.mapImageName = mapImageName;
  }

  const specJson = JSON.stringify(payload, null, 2);

  const indexTsx = `import { registerRoot } from 'remotion';
import { RemotionRoot } from './Root';

registerRoot(RemotionRoot);
`;

  const infographicTsx = `import React from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring } from 'remotion';

type Item = {
  label?: string;
  desc?: string;
  description?: string;
  value?: string | number;
  title?: string;
};

type Theme = {
  background: string;
  primary: string;
  secondary: string;
  text: string;
  muted: string;
};

const themes: Record<string, Theme> = {
  // Legacy themes for backward compatibility
  default: {
    background: '#f8fafc',
    primary: '#1d4ed8',
    secondary: '#0f766e',
    text: '#0f172a',
    muted: '#475569',
  },
  dark: {
    background: '#0b1120',
    primary: '#38bdf8',
    secondary: '#f472b6',
    text: '#e2e8f0',
    muted: '#94a3b8',
  },
  warm: {
    background: '#fff7ed',
    primary: '#ea580c',
    secondary: '#d97706',
    text: '#431407',
    muted: '#78350f',
  },
  cool: {
    background: '#f0f9ff',
    primary: '#0284c7',
    secondary: '#0f766e',
    text: '#0f172a',
    muted: '#475569',
  },
  // Essay Style themes - mapped from EssayStyle definitions
  'noir-essay': {
    background: '#0f0f0f',
    primary: '#ffffff',
    secondary: '#a3a3a3',
    text: '#ffffff',
    muted: '#737373',
  },
  'cold-data': {
    background: '#0a1628',
    primary: '#38bdf8',
    secondary: '#06b6d4',
    text: '#e2e8f0',
    muted: '#64748b',
  },
  'modern-creator': {
    background: '#18181b',
    primary: '#f472b6',
    secondary: '#a855f7',
    text: '#fafafa',
    muted: '#a1a1aa',
  },
  'academic-paper': {
    background: '#fffbf5',
    primary: '#1e3a5f',
    secondary: '#8b4513',
    text: '#1a1a1a',
    muted: '#6b7280',
  },
  'documentary': {
    background: '#1c1917',
    primary: '#fbbf24',
    secondary: '#f59e0b',
    text: '#f5f5f4',
    muted: '#a8a29e',
  },
  'podcast-visual': {
    background: '#581c87',
    primary: '#e879f9',
    secondary: '#c084fc',
    text: '#faf5ff',
    muted: '#d8b4fe',
  },
  'retro-synthwave': {
    background: '#0c0a1d',
    primary: '#f472b6',
    secondary: '#22d3ee',
    text: '#fdf4ff',
    muted: '#c084fc',
  },
  'breaking-news': {
    background: '#dc2626',
    primary: '#ffffff',
    secondary: '#fef08a',
    text: '#ffffff',
    muted: '#fecaca',
  },
  'minimalist-white': {
    background: '#ffffff',
    primary: '#171717',
    secondary: '#525252',
    text: '#171717',
    muted: '#737373',
  },
  'true-crime': {
    background: '#1a0a0a',
    primary: '#991b1b',
    secondary: '#b91c1c',
    text: '#fef2f2',
    muted: '#a1a1aa',
  },
  'nature-documentary': {
    background: '#022c22',
    primary: '#34d399',
    secondary: '#10b981',
    text: '#ecfdf5',
    muted: '#6ee7b7',
  },
};

const normalizeItems = (items: unknown): Item[] => {
  if (!Array.isArray(items)) {
    return [];
  }
  return items.map((item) => {
    if (typeof item === 'string' || typeof item === 'number') {
      return { label: String(item) };
    }
    if (typeof item === 'object' && item !== null) {
      return item as Item;
    }
    return {};
  });
};

type TitleCard = {
  title?: string;
  subtitle?: string;
  duration?: number;
  background?: string;
  color?: string;
};

type LowerThird = {
  name?: string;
  role?: string;
  show_from?: number;
  show_to?: number;
  position?: 'left' | 'center' | 'right';
  color?: string;
};

type Chapter = {
  title?: string;
  subtitle?: string;
  start?: number;
  duration?: number;
};

type Quote = {
  text?: string;
  author?: string;
  start?: number;
  duration?: number;
};

type ProgressBar = {
  show?: boolean;
  color?: string;
  track?: string;
  height?: number;
  margin?: number;
};

const OverlayElements: React.FC<{
  data: Record<string, unknown>;
  theme: string;
}> = ({ data, theme }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const colors = themes[theme] ?? themes.default;
  const titleCard = (data as any).title_card as TitleCard | undefined;
  const lowerThird = (data as any).lower_third as LowerThird | undefined;
  const chapters = Array.isArray((data as any).chapters) ? (data as any).chapters as Chapter[] : [];
  const quotes = Array.isArray((data as any).quotes) ? (data as any).quotes as Quote[] : [];
  const progressBar = ((data as any).progress_bar ?? {}) as ProgressBar;

  const titleCardDurationSeconds =
    typeof titleCard?.duration === 'number' ? titleCard.duration : 2.5;
  const titleCardFrames = Math.max(1, Math.round(titleCardDurationSeconds * fps));
  const titleFade = Math.max(6, Math.round(titleCardFrames * 0.2));
  const titleOpacity = interpolate(
    frame,
    [0, titleFade, titleCardFrames - titleFade, titleCardFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const lowerFrom = Math.max(
    0,
    Math.round((typeof lowerThird?.show_from === 'number' ? lowerThird.show_from : 0.2) * fps)
  );
  const lowerTo = Math.min(
    durationInFrames,
    Math.round(
      (typeof lowerThird?.show_to === 'number' ? lowerThird.show_to : durationInFrames / fps) * fps
    )
  );
  const lowerOpacity = interpolate(
    frame,
    [lowerFrom, lowerFrom + 10, lowerTo - 10, lowerTo],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );
  const lowerOffset = interpolate(
    frame,
    [lowerFrom, lowerFrom + 12],
    [24, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const timeSeconds = frame / fps;
  const activeChapter = chapters.find((chapter) => {
    const start = typeof chapter.start === 'number' ? chapter.start : 0;
    const duration = typeof chapter.duration === 'number' ? chapter.duration : 2.5;
    return timeSeconds >= start && timeSeconds <= start + duration;
  });
  const activeQuote = quotes.find((quote) => {
    const start = typeof quote.start === 'number' ? quote.start : 0;
    const duration = typeof quote.duration === 'number' ? quote.duration : 2.5;
    return timeSeconds >= start && timeSeconds <= start + duration;
  });
  const chapterOpacity = activeChapter
    ? interpolate(
        frame,
        [Math.round((activeChapter.start ?? 0) * fps), Math.round((activeChapter.start ?? 0) * fps) + 10],
        [0, 1],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
      )
    : 0;
  const quoteOpacity = activeQuote
    ? interpolate(
        frame,
        [Math.round((activeQuote.start ?? 0) * fps), Math.round((activeQuote.start ?? 0) * fps) + 10],
        [0, 1],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
      )
    : 0;
  const progressEnabled = progressBar.show !== false;
  const progress = interpolate(frame, [0, durationInFrames - 1], [0, 1], {
    extrapolateRight: 'clamp',
  });
  const progressColor = progressBar.color ?? colors.primary;
  const progressTrack = progressBar.track ?? 'rgba(15, 23, 42, 0.2)';
  const progressHeight = typeof progressBar.height === 'number' ? progressBar.height : 6;
  const progressMargin = typeof progressBar.margin === 'number' ? progressBar.margin : 32;

  return (
    <AbsoluteFill>
      {titleCard?.title ? (
        <AbsoluteFill
          style={{
            alignItems: 'center',
            justifyContent: 'center',
            textAlign: 'center',
            opacity: titleOpacity,
            background: (titleCard as any).background || 'transparent',
          }}
        >
          {/* Render accented text segments if available */}
          {(titleCard as any).titleSegments ? (
            <div style={{
              fontSize: (titleCard as any).fontSize || 64,
              fontWeight: (titleCard as any).fontWeight || 700,
              fontFamily: (titleCard as any).fontFamily || 'Inter, sans-serif',
            }}>
              {((titleCard as any).titleSegments as Array<{text: string; color: string}>).map((seg, i) => (
                <span key={i} style={{ color: seg.color }}>{seg.text}</span>
              ))}
            </div>
          ) : (
            <div style={{
              fontSize: (titleCard as any).fontSize || 64,
              fontWeight: (titleCard as any).fontWeight || 700,
              fontFamily: (titleCard as any).fontFamily || 'Inter, sans-serif',
              color: titleCard.color || colors.text,
            }}>
              {titleCard.title}
            </div>
          )}
          {titleCard.subtitle ? (
            <div style={{
              marginTop: 12,
              fontSize: (titleCard as any).subtitleSize || 30,
              fontFamily: (titleCard as any).fontFamily || 'Inter, sans-serif',
              color: (titleCard as any).subtitleColor || titleCard.color || colors.muted,
              opacity: 0.8,
            }}>
              {titleCard.subtitle}
            </div>
          ) : null}
        </AbsoluteFill>
      ) : null}
      {lowerThird?.name ? (
        <AbsoluteFill style={{
          alignItems: lowerThird.position === 'center' ? 'center' : lowerThird.position === 'right' ? 'flex-end' : 'flex-start',
          justifyContent: 'flex-end'
        }}>
          <div
            style={{
              marginLeft: lowerThird.position === 'right' ? 0 : 60,
              marginRight: lowerThird.position === 'right' ? 60 : 0,
              marginBottom: 60,
              padding: '16px 22px',
              borderRadius: 14,
              background: (lowerThird as any).background || 'rgba(15, 23, 42, 0.8)',
              color: (lowerThird as any).nameColor || '#f8fafc',
              opacity: lowerOpacity,
              transform: 'translateY(' + lowerOffset + 'px)',
              borderLeft: lowerThird.position !== 'right' ? '4px solid ' + ((lowerThird as any).accentColor || lowerThird.color || colors.primary) : 'none',
              borderRight: lowerThird.position === 'right' ? '4px solid ' + ((lowerThird as any).accentColor || lowerThird.color || colors.primary) : 'none',
            }}
          >
            <div style={{
              fontSize: (lowerThird as any).fontSize || 28,
              fontWeight: 700,
              fontFamily: (lowerThird as any).fontFamily || 'Inter, sans-serif',
            }}>{lowerThird.name}</div>
            {lowerThird.role ? (
              <div style={{
                marginTop: 4,
                fontSize: (lowerThird as any).roleSize || 18,
                fontFamily: (lowerThird as any).fontFamily || 'Inter, sans-serif',
                color: (lowerThird as any).roleColor || '#cbd5e1',
              }}>{lowerThird.role}</div>
            ) : null}
          </div>
        </AbsoluteFill>
      ) : null}
      {activeChapter?.title ? (
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: chapterOpacity }}>
          <div
            style={{
              padding: '28px 36px',
              borderRadius: 18,
              background: 'rgba(15, 23, 42, 0.85)',
              color: '#f8fafc',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 44, fontWeight: 700 }}>{activeChapter.title}</div>
            {activeChapter.subtitle ? (
              <div style={{ marginTop: 8, fontSize: 22, color: '#e2e8f0' }}>
                {activeChapter.subtitle}
              </div>
            ) : null}
          </div>
        </AbsoluteFill>
      ) : null}
      {activeQuote?.text ? (
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: quoteOpacity }}>
          <div
            style={{
              maxWidth: 1000,
              padding: '32px 40px',
              borderRadius: 20,
              background: 'rgba(248, 250, 252, 0.9)',
              color: colors.text,
              textAlign: 'center',
              boxShadow: '0 18px 40px rgba(15, 23, 42, 0.2)',
            }}
          >
            <div style={{ fontSize: 36, fontWeight: 600, lineHeight: 1.3 }}>
              “{activeQuote.text}”
            </div>
            {activeQuote.author ? (
              <div style={{ marginTop: 12, fontSize: 20, color: colors.muted }}>
                — {activeQuote.author}
              </div>
            ) : null}
          </div>
        </AbsoluteFill>
      ) : null}
      {progressEnabled ? (
        <AbsoluteFill style={{ alignItems: 'stretch', justifyContent: 'flex-end' }}>
          <div
            style={{
              margin: '0 ' + progressMargin + 'px ' + progressMargin + 'px',
              height: progressHeight,
              borderRadius: progressHeight,
              background: progressTrack,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: Math.max(0, Math.min(1, progress)) * 100 + '%',
                height: '100%',
                background: progressColor,
              }}
            />
          </div>
        </AbsoluteFill>
      ) : null}
      {/* Texture overlays - grain, vignette */}
      {(() => {
        const texture = (data as any).texture;
        if (!texture) return null;
        const grainOpacity = typeof texture.grainOpacity === 'number' ? texture.grainOpacity : 0;
        const vignette = texture.vignette === true;
        return (
          <>
            {vignette ? (
              <AbsoluteFill
                style={{
                  background: 'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.7) 100%)',
                  pointerEvents: 'none',
                }}
              />
            ) : null}
            {grainOpacity > 0 ? (
              <AbsoluteFill
                style={{
                  backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\\'0 0 200 200\\' xmlns=\\'http://www.w3.org/2000/svg\\'%3E%3Cfilter id=\\'noise\\'%3E%3CfeTurbulence type=\\'fractalNoise\\' baseFrequency=\\'0.65\\' numOctaves=\\'3\\' stitchTiles=\\'stitch\\'/%3E%3C/filter%3E%3Crect width=\\'100%25\\' height=\\'100%25\\' filter=\\'url(%23noise)\\'/%3E%3C/svg%3E")',
                  opacity: grainOpacity,
                  mixBlendMode: 'overlay',
                  pointerEvents: 'none',
                }}
              />
            ) : null}
          </>
        );
      })()}
    </AbsoluteFill>
  );
};

export const Infographic: React.FC<{
  data: Record<string, unknown>;
  theme: string;
}> = ({ data, theme }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const colors = themes[theme] ?? themes.default;

  const title = typeof data.title === 'string' && data.title.trim()
    ? data.title
    : 'Infographic';
  const subtitle = typeof data.subtitle === 'string' ? data.subtitle : '';
  const items = normalizeItems(data.items);
  const safeItems = items.length ? items : [{ label: 'No items provided' }];
  const csvTable = (data as any).csv_table as { headers?: string[]; rows?: string[][] } | undefined;
  const csvHeaders = Array.isArray(csvTable?.headers) ? csvTable?.headers : [];
  const csvRows = Array.isArray(csvTable?.rows) ? csvTable?.rows : [];

  const titleOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: 'clamp',
  });
  const subtitleOpacity = interpolate(frame, [8, 26], [0, 1], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ backgroundColor: colors.background, padding: 80 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 64, fontWeight: 700, color: colors.text, opacity: titleOpacity }}>
          {title}
        </div>
        {subtitle ? (
          <div style={{ fontSize: 32, fontWeight: 500, color: colors.muted, opacity: subtitleOpacity }}>
            {subtitle}
          </div>
        ) : null}
      </div>
      <div style={{ marginTop: 48, display: 'flex', flexDirection: 'column', gap: 20 }}>
        {safeItems.map((item, index) => {
          const delay = index * 8;
          const appear = spring({
            frame: frame - delay,
            fps,
            config: { damping: 200 },
          });
          const y = interpolate(appear, [0, 1], [20, 0]);
          const opacity = interpolate(appear, [0, 1], [0, 1]);
          const label =
            typeof item.label === 'string'
              ? item.label
              : typeof item.title === 'string'
                ? item.title
                : 'Item ' + (index + 1);
          const desc =
            typeof item.desc === 'string'
              ? item.desc
              : typeof item.description === 'string'
                ? item.description
                : '';
          const value =
            typeof item.value === 'string' || typeof item.value === 'number'
              ? String(item.value)
              : '';
          const detail = desc ? desc : value ? value : '';
          return (
            <div
              key={index}
              style={{
                transform: \`translateY(\${y}px)\`,
                opacity,
                borderRadius: 16,
                padding: '18px 24px',
                background: '#ffffff',
                boxShadow: '0 10px 30px rgba(15, 23, 42, 0.08)',
                maxWidth: Math.min(900, width - 160),
              }}
            >
              <div style={{ fontSize: 30, fontWeight: 700, color: colors.text }}>
                {label}
              </div>
              {detail ? (
                <div style={{ marginTop: 6, fontSize: 20, color: colors.muted }}>
                  {detail}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      {csvHeaders.length > 0 ? (
        <div
          style={{
            marginTop: 48,
            padding: 24,
            borderRadius: 16,
            background: '#ffffff',
            boxShadow: '0 10px 30px rgba(15, 23, 42, 0.08)',
            maxWidth: Math.min(1100, width - 160),
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(' + csvHeaders.length + ', 1fr)', gap: 12 }}>
            {csvHeaders.map((header, index) => (
              <div
                key={'header-' + index}
                style={{ fontSize: 18, fontWeight: 700, color: colors.text }}
              >
                {header}
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, display: 'grid', gap: 10 }}>
            {csvRows.slice(0, 6).map((row, rowIndex) => (
              <div
                key={'row-' + rowIndex}
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(' + csvHeaders.length + ', 1fr)',
                  gap: 12,
                  fontSize: 16,
                  color: colors.muted,
                }}
              >
                {row.map((cell, cellIndex) => (
                  <div key={'cell-' + rowIndex + '-' + cellIndex}>{cell}</div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <OverlayElements data={data} theme={theme} />
    </AbsoluteFill>
  );
};

export const ZoomImage: React.FC<{
  imageName: string;
  focusX?: number;
  focusY?: number;
  zoomFrom?: number;
  zoomTo?: number;
  data?: Record<string, unknown>;
  theme?: string;
}> = ({ imageName, focusX, focusY, zoomFrom, zoomTo, data, theme }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const progress = interpolate(frame, [0, durationInFrames - 1], [0, 1], {
    extrapolateRight: 'clamp',
  });
  const startZoom = typeof zoomFrom === 'number' ? zoomFrom : 1;
  const endZoom = typeof zoomTo === 'number' ? zoomTo : 1.08;
  const scale = interpolate(progress, [0, 1], [startZoom, endZoom]);
  const originX =
    typeof focusX === 'number' && Number.isFinite(focusX) ? Math.min(1, Math.max(0, focusX)) : 0.5;
  const originY =
    typeof focusY === 'number' && Number.isFinite(focusY) ? Math.min(1, Math.max(0, focusY)) : 0.5;
  const transformOrigin =
    Math.round(originX * 100) + '% ' + Math.round(originY * 100) + '%';
  const transform = 'scale(' + scale + ')';

  return (
    <AbsoluteFill style={{ backgroundColor: '#000000' }}>
      <AbsoluteFill style={{ transform, transformOrigin }}>
        <Img
          src={staticFile(imageName)}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </AbsoluteFill>
      <OverlayElements data={data ?? {}} theme={theme ?? 'default'} />
    </AbsoluteFill>
  );
};

type MapPoint = {
  x: number;
  y: number;
  zoom?: number;
};

type MapPointWithLabel = MapPoint & { label?: string };

export const MapFlyover: React.FC<{
  mapImageName: string;
  data?: Record<string, unknown>;
  theme?: string;
}> = ({ mapImageName, data, theme }) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps, width, height } = useVideoConfig();
  const points = Array.isArray((data as any)?.map_points) ? (data as any).map_points as MapPointWithLabel[] : [];
  const showLabels = (data as any)?.show_map_labels !== false;
  const showMarker = (data as any)?.show_marker !== false;
  const showTrail = (data as any)?.show_trail !== false;
  const markerColor = typeof (data as any)?.marker_color === 'string' ? (data as any).marker_color : '#ef4444';
  const safePoints = points.length >= 2 ? points : [
    { x: 0.4, y: 0.5, zoom: 1.05 },
    { x: 0.6, y: 0.5, zoom: 1.15 },
  ];
  const segments = Math.max(1, safePoints.length - 1);
  const progress = interpolate(frame, [0, durationInFrames - 1], [0, 1], {
    extrapolateRight: 'clamp',
  });
  const position = progress * segments;
  const index = Math.min(segments - 1, Math.floor(position));
  const local = position - index;
  const from = safePoints[index];
  const to = safePoints[index + 1] ?? from;
  const x = interpolate(local, [0, 1], [from.x, to.x]);
  const y = interpolate(local, [0, 1], [from.y, to.y]);
  const zoomFrom = typeof from.zoom === 'number' ? from.zoom : 1;
  const zoomTo = typeof to.zoom === 'number' ? to.zoom : zoomFrom;
  const scale = interpolate(local, [0, 1], [zoomFrom, zoomTo]);
  const transformOrigin = Math.round(x * 100) + '% ' + Math.round(y * 100) + '%';

  // Calculate marker position in screen coordinates
  // The marker follows the path on the map image
  const markerX = x * width;
  const markerY = y * height;

  // Build trail path - all points up to current position
  const trailPoints: string[] = [];
  for (let i = 0; i <= index; i++) {
    const pt = safePoints[i];
    trailPoints.push((pt.x * width) + ',' + (pt.y * height));
  }
  // Add current interpolated position
  trailPoints.push(markerX + ',' + markerY);
  const trailPath = trailPoints.join(' ');

  // Pulsing effect for marker
  const pulse = Math.sin(frame * 0.3) * 0.3 + 1;

  // Calculate which point's label to show and its opacity
  const framesPerPoint = durationInFrames / safePoints.length;
  const currentPointIndex = Math.min(safePoints.length - 1, Math.floor(frame / framesPerPoint));
  const currentPoint = safePoints[currentPointIndex];
  const pointStartFrame = currentPointIndex * framesPerPoint;
  const pointEndFrame = (currentPointIndex + 1) * framesPerPoint;
  const fadeFrames = Math.min(10, framesPerPoint * 0.15);
  const labelOpacity = showLabels && currentPoint?.label
    ? interpolate(
        frame,
        [pointStartFrame, pointStartFrame + fadeFrames, pointEndFrame - fadeFrames, pointEndFrame],
        [0, 1, 1, 0],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
      )
    : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: '#000000' }}>
      <AbsoluteFill style={{ transform: 'scale(' + scale + ')', transformOrigin }}>
        <Img
          src={staticFile(mapImageName)}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
        {/* Trail line */}
        {showTrail && trailPoints.length >= 2 ? (
          <svg width={width} height={height} style={{ position: 'absolute', top: 0, left: 0 }}>
            <polyline
              points={trailPath}
              fill="none"
              stroke={markerColor}
              strokeWidth={4}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.8}
            />
            {/* Draw dots at visited points */}
            {safePoints.slice(0, index + 1).map((pt, i) => (
              <circle
                key={i}
                cx={pt.x * width}
                cy={pt.y * height}
                r={8}
                fill={markerColor}
                opacity={0.9}
              />
            ))}
          </svg>
        ) : null}
        {/* Animated marker */}
        {showMarker ? (
          <div
            style={{
              position: 'absolute',
              left: markerX,
              top: markerY,
              transform: 'translate(-50%, -50%) scale(' + pulse + ')',
            }}
          >
            {/* Outer glow */}
            <div
              style={{
                position: 'absolute',
                width: 40,
                height: 40,
                borderRadius: '50%',
                background: markerColor,
                opacity: 0.3,
                transform: 'translate(-50%, -50%)',
                left: '50%',
                top: '50%',
              }}
            />
            {/* Inner dot */}
            <div
              style={{
                width: 20,
                height: 20,
                borderRadius: '50%',
                background: markerColor,
                border: '3px solid white',
                boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
              }}
            />
          </div>
        ) : null}
      </AbsoluteFill>
      {showLabels && currentPoint?.label ? (
        <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'flex-end', paddingBottom: 80 }}>
          <div
            style={{
              padding: '16px 32px',
              background: 'rgba(15, 23, 42, 0.85)',
              borderRadius: 12,
              opacity: labelOpacity,
              transform: 'translateY(' + interpolate(labelOpacity, [0, 1], [20, 0]) + 'px)',
            }}
          >
            <div style={{ fontSize: 36, fontWeight: 600, color: '#ffffff' }}>
              {currentPoint.label}
            </div>
          </div>
        </AbsoluteFill>
      ) : null}
      <OverlayElements data={data ?? {}} theme={theme ?? 'default'} />
    </AbsoluteFill>
  );
};

// Generic overlay-only component for title cards, lower thirds, chapters, etc.
// Just renders a background with OverlayElements - no infographic content
export const OverlayOnly: React.FC<{
  data?: Record<string, unknown>;
  theme?: string;
}> = ({ data, theme }) => {
  const colors = themes[theme ?? 'default'] ?? themes.default;
  const titleCard = (data as any)?.title_card;
  // Use title_card background if available, otherwise use theme background
  const bgColor = titleCard?.background || colors.background;

  return (
    <AbsoluteFill style={{ backgroundColor: bgColor }}>
      <OverlayElements data={data ?? {}} theme={theme ?? 'default'} />
    </AbsoluteFill>
  );
};
`;

  const rootTsx = `import React from 'react';
import { Composition } from 'remotion';
import spec from './spec.json';
import { Infographic, MapFlyover, ZoomImage, OverlayOnly } from './Infographic';

const width = typeof (spec as any).width === 'number' ? (spec as any).width : ${DEFAULT_WIDTH};
const height = typeof (spec as any).height === 'number' ? (spec as any).height : ${DEFAULT_HEIGHT};
const fps = typeof (spec as any).fps === 'number' ? (spec as any).fps : ${DEFAULT_FPS};
const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
const durationInFrames = Math.max(1, Math.round(duration * fps));
const data = (spec as any).data ?? {};
const theme = typeof (spec as any).theme === 'string' ? (spec as any).theme : 'default';
const imageName = typeof (spec as any).imageName === 'string' ? (spec as any).imageName : '';
const mapImageName = typeof (spec as any).mapImageName === 'string' ? (spec as any).mapImageName : '';
const focus = (spec as any).data?.image_focus ?? {};
const bbox = Array.isArray(focus.bbox) ? focus.bbox : null;
const bboxX = bbox && typeof bbox[0] === 'number' ? bbox[0] : undefined;
const bboxY = bbox && typeof bbox[1] === 'number' ? bbox[1] : undefined;
const bboxW = bbox && typeof bbox[2] === 'number' ? bbox[2] : undefined;
const bboxH = bbox && typeof bbox[3] === 'number' ? bbox[3] : undefined;
const bboxCenterX =
  typeof bboxX === 'number' && typeof bboxW === 'number' ? bboxX + bboxW / 2 : undefined;
const bboxCenterY =
  typeof bboxY === 'number' && typeof bboxH === 'number' ? bboxY + bboxH / 2 : undefined;
const bboxScaleCandidate =
  typeof bboxW === 'number' && typeof bboxH === 'number' && bboxW > 0 && bboxH > 0
    ? 1 / Math.max(bboxW, bboxH)
    : undefined;
const bboxScale = typeof bboxScaleCandidate === 'number' && Number.isFinite(bboxScaleCandidate)
  ? Math.max(1, bboxScaleCandidate)
  : undefined;
const focusX = typeof focus.x === 'number' ? focus.x : (typeof bboxCenterX === 'number' ? bboxCenterX : 0.5);
const focusY = typeof focus.y === 'number' ? focus.y : (typeof bboxCenterY === 'number' ? bboxCenterY : 0.5);
const zoomFrom =
  typeof focus.zoom_from === 'number'
    ? focus.zoom_from
    : typeof bboxScale === 'number'
      ? Math.max(1, bboxScale * 0.9)
      : undefined;
const zoomTo =
  typeof focus.zoom_to === 'number'
    ? focus.zoom_to
    : typeof bboxScale === 'number'
      ? bboxScale
      : undefined;
const useMap = mapImageName.length > 0;
const useImage = imageName.length > 0;
// Detect overlay-only effects (no base infographic content needed)
const useOverlayOnly = !!(
  (data as any)?.title_card ||
  (data as any)?.lower_third ||
  (Array.isArray((data as any)?.chapters) && (data as any).chapters.length > 0) ||
  (Array.isArray((data as any)?.quotes) && (data as any).quotes.length > 0)
);

export const RemotionRoot: React.FC = () => {
  const Component = useMap ? MapFlyover : useImage ? ZoomImage : useOverlayOnly ? OverlayOnly : Infographic;
  return (
    <Composition
      id="NolanInfographic"
      component={Component}
      durationInFrames={durationInFrames}
      fps={fps}
      width={width}
      height={height}
      defaultProps={{ data, theme, imageName, mapImageName, focusX, focusY, zoomFrom, zoomTo }}
    />
  );
};
`;

  fs.writeFileSync(path.join(root, 'src', 'spec.json'), specJson, 'utf8');
  fs.writeFileSync(path.join(root, 'src', 'index.tsx'), indexTsx, 'utf8');
  fs.writeFileSync(path.join(root, 'src', 'Infographic.tsx'), infographicTsx, 'utf8');
  fs.writeFileSync(path.join(root, 'src', 'Root.tsx'), rootTsx, 'utf8');
}

type SilenceMarkerOptions = {
  thresholdDb: number;
  minSilenceMs: number;
};

type SilenceMarkerResult = {
  durationSeconds: number;
  silences: Array<{ start: number; end: number; duration: number }>;
  markers: number[];
};

function runProcess(command: string, args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const proc = spawn(command, args, { windowsHide: true });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    proc.on('close', (code) => {
      resolve({ code: code ?? 0, stdout, stderr });
    });
  });
}

async function getAudioDurationSeconds(audioPath: string): Promise<number> {
  const args = [
    '-v',
    'error',
    '-show_entries',
    'format=duration',
    '-of',
    'default=nk=1:nw=1',
    audioPath,
  ];
  const result = await runProcess(ffprobeInstaller.path, args);
  const value = result.stdout.trim();
  const duration = Number.parseFloat(value);
  return Number.isFinite(duration) ? duration : 0;
}

async function detectSilences(
  audioPath: string,
  options: SilenceMarkerOptions
): Promise<SilenceMarkerResult> {
  const silenceFilter = `silencedetect=noise=${options.thresholdDb}dB:d=${options.minSilenceMs / 1000}`;
  const args = ['-i', audioPath, '-af', silenceFilter, '-f', 'null', '-'];
  const result = await runProcess(ffmpegInstaller.path, args);

  const silences: Array<{ start: number; end: number; duration: number }> = [];
  let currentStart: number | null = null;

  const lines = result.stderr.split(/\r?\n/);
  for (const line of lines) {
    if (line.includes('silence_start')) {
      const match = line.match(/silence_start:\s*([0-9.]+)/);
      if (match) {
        currentStart = Number.parseFloat(match[1]);
      }
    } else if (line.includes('silence_end')) {
      const match = line.match(/silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)/);
      if (match) {
        const end = Number.parseFloat(match[1]);
        const duration = Number.parseFloat(match[2]);
        const start = currentStart ?? Math.max(0, end - duration);
        silences.push({ start, end, duration });
        currentStart = null;
      }
    }
  }

  const durationSeconds = await getAudioDurationSeconds(audioPath);
  const markers = [0, ...silences.map((s) => s.end).filter((value) => value > 0)];
  if (durationSeconds > 0) {
    markers.push(durationSeconds);
  }

  const uniqueMarkers = Array.from(new Set(markers.map((value) => Number(value.toFixed(3)))))
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);

  return { durationSeconds, silences, markers: uniqueMarkers };
}

async function generateSilenceMarkers(
  audioPath: string,
  outputDir: string,
  options: SilenceMarkerOptions
): Promise<RenderResult> {
  if (!fs.existsSync(audioPath)) {
    return { success: false, error: `Audio file not found: ${audioPath}` };
  }

  const result = await detectSilences(audioPath, options);
  ensureDir(outputDir);
  const outputPath = path.join(outputDir, `audio_markers_${Date.now()}.json`);
  const payload = {
    audio_path: audioPath,
    threshold_db: options.thresholdDb,
    min_silence_ms: options.minSilenceMs,
    duration_seconds: result.durationSeconds,
    silences: result.silences,
    markers_seconds: result.markers,
  };
  fs.writeFileSync(outputPath, JSON.stringify(payload, null, 2), 'utf8');

  return { success: true, outputPath };
}

export class RemotionEngine implements RenderEngine {
  name = 'remotion';

  async render(spec: RenderSpec, outputDir: string): Promise<RenderResult> {
    const outputName = `remotion_${Date.now()}`;
    const payload = buildPayload(spec, outputName);
    const specAny = spec as unknown as Record<string, unknown>;
    const imagePath = resolveImagePath(spec);
    const mapImagePath = resolveMapImagePath(spec);
    const audioPath = (spec.data as Record<string, unknown>)?.audio_path;
    const markersOnly =
      (spec.data as Record<string, unknown>)?.audio_markers_only === true ||
      specAny.audio_markers_only === true;
    if (markersOnly && typeof audioPath === 'string') {
      const thresholdDb =
        typeof (spec.data as Record<string, unknown>)?.silence_threshold_db === 'number'
          ? ((spec.data as Record<string, unknown>)?.silence_threshold_db as number)
          : -35;
      const minSilenceMs =
        typeof (spec.data as Record<string, unknown>)?.min_silence_ms === 'number'
          ? ((spec.data as Record<string, unknown>)?.min_silence_ms as number)
          : 400;
      return generateSilenceMarkers(audioPath, outputDir, {
        thresholdDb,
        minSilenceMs,
      });
    }
    const cacheRoot = path.join(process.cwd(), '.cache', 'remotion');
    ensureDir(cacheRoot);

    attachCsvTable(payload);
    const tempRoot = fs.mkdtempSync(path.join(cacheRoot, 'job-'));
    createProjectFiles(tempRoot, payload, imagePath, mapImagePath);

    const outputPath = path.join(outputDir, `${payload.outputName}.mp4`);
    const entryPoint = path.join(tempRoot, 'src', 'index.tsx');
    const bundleOut = path.join(tempRoot, 'dist');
    const publicDir = path.join(tempRoot, 'public');

    try {
      ensureDir(outputDir);
      const bundleLocation = await bundle({
        entryPoint,
        outDir: bundleOut,
        publicDir,
        onProgress: () => undefined,
      });

      const composition = await selectComposition({
        serveUrl: bundleLocation,
        id: 'NolanInfographic',
        chromiumOptions: {},
      });

      await renderMedia({
        serveUrl: bundleLocation,
        composition,
        codec: 'h264',
        outputLocation: outputPath,
        chromiumOptions: {},
      });

      return {
        success: true,
        outputPath,
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      const detail = payload.debug ? ` (cache: ${tempRoot})` : '';
      return {
        success: false,
        error: `${message}${detail}`,
      };
    } finally {
      if (!payload.debug) {
        fs.rmSync(tempRoot, { recursive: true, force: true });
      }
    }
  }
}
