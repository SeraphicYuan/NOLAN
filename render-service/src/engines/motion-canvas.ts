import * as fs from 'fs';
import * as path from 'path';
import puppeteer from 'puppeteer';
import type { RenderSpec } from '../jobs/types.js';
import { RenderEngine, RenderResult } from './types.js';
import { ensureDir, toNumber, toString } from './utils.js';
import { resolveBackgroundFromTheme } from '../themes.js';

type MotionCanvasPayload = {
  data: Record<string, unknown>;
  width: number;
  height: number;
  duration: number;
  fps: number;
  background: string;
  outputName: string;
  debug: boolean;
};

const DEFAULT_WIDTH = 1920;
const DEFAULT_HEIGHT = 1080;
const DEFAULT_DURATION = 6;
const DEFAULT_FPS = 30;
const DEFAULT_BACKGROUND = '#ffffff';

function resolveBackground(spec: RenderSpec): string {
  const data = spec.data ?? {};
  const direct = typeof (data as Record<string, unknown>).background === 'string'
    ? String((data as Record<string, unknown>).background)
    : '';
  if (direct.trim()) {
    return direct;
  }

  const theme =
    typeof spec.theme === 'string'
      ? spec.theme
      : typeof (data as Record<string, unknown>).theme === 'string'
        ? String((data as Record<string, unknown>).theme)
        : '';

  return resolveBackgroundFromTheme(theme, DEFAULT_BACKGROUND);
}

function resolveFps(spec: RenderSpec): number {
  const data = spec.data ?? {};
  const fps = (data as Record<string, unknown>).fps;
  return toNumber(fps, DEFAULT_FPS);
}

function resolveDuration(spec: RenderSpec): number {
  const data = spec.data ?? {};
  const duration = (data as Record<string, unknown>).duration;
  return toNumber(spec.duration ?? duration, DEFAULT_DURATION);
}

function buildPayload(spec: RenderSpec, outputName: string): MotionCanvasPayload {
  const data = spec.data ?? {};
  const debugFlag =
    process.env.MOTION_CANVAS_DEBUG === '1' ||
    (typeof (data as Record<string, unknown>).debug === 'boolean' &&
      (data as Record<string, unknown>).debug === true);
  return {
    data,
    width: toNumber(spec.width, DEFAULT_WIDTH),
    height: toNumber(spec.height, DEFAULT_HEIGHT),
    duration: resolveDuration(spec),
    fps: resolveFps(spec),
    background: resolveBackground(spec),
    outputName,
    debug: debugFlag,
  };
}

function createProjectFiles(root: string, payload: MotionCanvasPayload): void {
  const srcDir = path.join(root, 'src');
  const scenesDir = path.join(srcDir, 'scenes');
  ensureDir(scenesDir);

  const renderHtml = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Motion Canvas Render</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Georgia&family=Playfair+Display:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
      * { font-family: 'Inter', sans-serif; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/render.ts"></script>
  </body>
</html>
`;

  const projectTs = `import { makeProject } from '@motion-canvas/core';
import scene from './scenes/Main?scene';

export default makeProject({
  name: '${payload.outputName}',
  scenes: [scene],
});
`;

  const sceneTsx = `import { Circle, Layout, Line, Rect, Txt, makeScene2D } from '@motion-canvas/2d';
import { Vector2, all, createRef, waitFor, easeOutCubic, linear } from '@motion-canvas/core';
import spec from '../spec.json';

const data = (spec as any).data ?? {};
const rawTitle = typeof data.title === 'string' ? data.title : '';
const title = rawTitle.trim().length ? rawTitle : 'Infographic';
const subtitle = typeof data.subtitle === 'string' ? data.subtitle.trim() : '';
const items = Array.isArray(data.items) ? data.items : [];
const safeItems = items.length ? items : ['No items provided'];
const width = typeof (spec as any).width === 'number' ? (spec as any).width : ${DEFAULT_WIDTH};
const height = typeof (spec as any).height === 'number' ? (spec as any).height : ${DEFAULT_HEIGHT};
const background = typeof (spec as any).background === 'string' ? (spec as any).background : '${DEFAULT_BACKGROUND}';
const chart =
  typeof (data as any).chart === 'object' && (data as any).chart !== null
    ? (data as any).chart
    : null;
const chartType = chart && typeof chart.type === 'string' ? chart.type : '';
const chartItemsRaw = chart && Array.isArray(chart.items) ? chart.items : [];
const chartItems = chartItemsRaw.map((item: unknown, index: number) => {
  if (typeof item === 'number') {
    return { label: 'Item ' + (index + 1), value: item };
  }
  if (typeof item === 'object' && item !== null) {
    const record = item as Record<string, unknown>;
    const label =
      typeof record.label === 'string'
        ? record.label
        : typeof record.title === 'string'
          ? record.title
          : 'Item ' + (index + 1);
    const value = typeof record.value === 'number' ? record.value : Number(record.value);
    return { label, value: Number.isFinite(value) ? value : 0 };
  }
  return { label: 'Item ' + (index + 1), value: 0 };
});
const isProgressStaircase = chartType === 'progress-staircase';
const chartEnabled = (chartType === 'bar' || chartType === 'line' || chartType === 'pie' || isProgressStaircase) && chartItems.length > 0;
const isLineChart = chartType === 'line';
const isBarChart = chartType === 'bar';
const isPieChart = chartType === 'pie';
const chartAccent = chart && typeof chart.color === 'string' ? chart.color : '#2563eb';
const chartFill = chart && chart.fill !== false;
const chartShowPoints = chart && chart.show_points !== false;
const chartHeight = Math.min(420, height * 0.45);
const chartFontFamily = chart && typeof chart.fontFamily === 'string' ? chart.fontFamily : 'Inter';
const chartLabelColor = chart && typeof chart.labelColor === 'string' ? chart.labelColor : '#e5e5e5';
const barCount = chartItems.length || 1;
const barWidth = Math.max(48, Math.floor((width - 240) / barCount) - 12);
const maxValue = chart && typeof chart.max === 'number'
  ? Math.max(chart.max, 1)
  : Math.max(1, ...chartItems.map((item) => item.value));
const lineChartWidth = width - 240;
const lineChartHeight = chartHeight;
const linePointSpacing = chartItems.length > 1 ? lineChartWidth / (chartItems.length - 1) : lineChartWidth;
// Pie chart specific vars
const pieDonut = chart && chart.donut === true;
const pieShowPercentages = chart && chart.show_percentages !== false;
const pieRadius = Math.min(width, height) * 0.28;
const pieInnerRadius = pieDonut ? pieRadius * 0.55 : 0;
const pieTotalValue = chartItems.reduce((sum, item) => sum + Math.max(0, item.value), 0) || 1;
const pieItemsWithAngles = chartItems.map((item, index) => {
  const defaultColors = ['#0ea5e9', '#8b5cf6', '#f97316', '#10b981', '#ef4444', '#eab308', '#ec4899'];
  const color = (chartItemsRaw[index] as Record<string, unknown>)?.color as string || defaultColors[index % defaultColors.length];
  const percentage = (item.value / pieTotalValue) * 100;
  const angle = (item.value / pieTotalValue) * 360;
  return { ...item, color, percentage, angle };
});
// Progress staircase chart variables
const staircaseArrowColor = chart && typeof chart.arrowColor === 'string' ? chart.arrowColor : '#22c55e';
const staircaseCardBg = chart && typeof chart.cardBackground === 'string' ? chart.cardBackground : '#ffffff';
const staircaseLabelColor = chart && typeof chart.labelColor === 'string' ? chart.labelColor : '#1f2937';
const staircaseDescColor = chart && typeof chart.descColor === 'string' ? chart.descColor : '#6b7280';
const staircaseValueColor = chart && typeof chart.valueColor === 'string' ? chart.valueColor : '#22c55e';
const staircaseItems = isProgressStaircase ? chartItemsRaw.map((item: unknown, index: number) => {
  const record = item as Record<string, unknown>;
  return {
    label: typeof record.label === 'string' ? record.label : 'Step ' + (index + 1),
    desc: typeof record.desc === 'string' ? record.desc : '',
    value: typeof record.value === 'number' ? record.value : undefined,
    icon: typeof record.icon === 'string' ? record.icon : 'check',
  };
}) : [];
const staircaseStepCount = staircaseItems.length;
// Calculate staircase geometry - arrow goes from bottom-left to top-right
const staircaseMargin = 120;
const staircaseWidth = width - staircaseMargin * 2;
const staircaseHeight = height * 0.5;
const staircaseBaseY = height * 0.75;
const staircaseStepWidth = staircaseStepCount > 1 ? staircaseWidth / staircaseStepCount : staircaseWidth;
const staircaseStepHeight = staircaseStepCount > 1 ? staircaseHeight / staircaseStepCount : staircaseHeight;
// Generate staircase points (creates a step pattern going up-right)
const staircasePoints: Array<{x: number; y: number}> = [];
for (let i = 0; i <= staircaseStepCount; i++) {
  const x = staircaseMargin + i * staircaseStepWidth;
  const y = staircaseBaseY - i * staircaseStepHeight;
  // Add horizontal then vertical for step pattern
  if (i > 0) {
    staircasePoints.push({ x, y: staircaseBaseY - (i - 1) * staircaseStepHeight });
  }
  staircasePoints.push({ x, y });
}
// Card positions alternate above/below the steps
const staircaseCardPositions = staircaseItems.map((_, index) => {
  const x = staircaseMargin + (index + 0.5) * staircaseStepWidth;
  const stepY = staircaseBaseY - index * staircaseStepHeight - staircaseStepHeight / 2;
  const isAbove = index % 2 === 0;
  const cardY = isAbove ? stepY - 100 : stepY + 80;
  return { x, y: cardY, isAbove };
});
const kinetic =
  typeof (data as any).kinetic === 'object' && (data as any).kinetic !== null
    ? (data as any).kinetic
    : null;
const kineticPhrasesRaw = kinetic && Array.isArray(kinetic.phrases) ? kinetic.phrases : [];
const kineticPhrases = kineticPhrasesRaw.map((entry: unknown) => {
  if (typeof entry === 'string') {
    return { text: entry, hold: 0.6 };
  }
  if (typeof entry === 'object' && entry !== null) {
    const record = entry as Record<string, unknown>;
    const text = typeof record.text === 'string' ? record.text : '';
    const hold = typeof record.hold === 'number' ? Math.max(0.1, record.hold) : 0.6;
    return { text, hold };
  }
  return { text: '', hold: 0.6 };
});
const kineticEnabled = kineticPhrases.length > 0;
const kineticColor = kinetic && typeof kinetic.color === 'string' ? kinetic.color : '#0f172a';
const kineticSize = kinetic && typeof kinetic.size === 'number' ? kinetic.size : 96;
const kineticFontFamily = kinetic && typeof kinetic.fontFamily === 'string' ? kinetic.fontFamily : 'Inter';
const kineticFontWeight = kinetic && typeof kinetic.fontWeight === 'number' ? kinetic.fontWeight : 700;
const counter =
  typeof (data as any).counter === 'object' && (data as any).counter !== null
    ? (data as any).counter
    : null;
const counterEnabled = counter && typeof counter.value === 'number';
const counterValue = counter && typeof counter.value === 'number' ? counter.value : 0;
const counterPrefix = counter && typeof counter.prefix === 'string' ? counter.prefix : '';
const counterSuffix = counter && typeof counter.suffix === 'string' ? counter.suffix : '';
const counterLabel = counter && typeof counter.label === 'string' ? counter.label : '';
const counterColor = counter && typeof counter.color === 'string' ? counter.color : '#0ea5e9';
const counterSize = counter && typeof counter.size === 'number' ? counter.size : 120;
const counterFontFamily = counter && typeof counter.fontFamily === 'string' ? counter.fontFamily : 'Inter';
const counterLabelColor = counter && typeof counter.labelColor === 'string' ? counter.labelColor : '#a1a1aa';
const typewriter =
  typeof (data as any).typewriter === 'object' && (data as any).typewriter !== null
    ? (data as any).typewriter
    : null;
const typewriterEnabled = typewriter && typeof typewriter.text === 'string' && typewriter.text.length > 0;
const typewriterText = typewriter && typeof typewriter.text === 'string' ? typewriter.text : '';
const typewriterSpeed = typewriter && typeof typewriter.speed === 'number' ? typewriter.speed : 15;
const typewriterColor = typewriter && typeof typewriter.color === 'string' ? typewriter.color : '#ffffff';
const typewriterCursorColor = typewriter && typeof typewriter.cursor_color === 'string' ? typewriter.cursor_color : '#0ea5e9';
const typewriterFontSize = typewriter && typeof typewriter.font_size === 'number' ? typewriter.font_size : 48;
// Progress data
const progress =
  typeof (data as any).progress === 'object' && (data as any).progress !== null
    ? (data as any).progress
    : null;
const progressEnabled = progress && typeof progress.value === 'number';
const progressType = progress && typeof progress.type === 'string' ? progress.type : 'circular';
const progressValue = progress && typeof progress.value === 'number' ? Math.min(100, Math.max(0, progress.value)) : 0;
const progressLabel = progress && typeof progress.label === 'string' ? progress.label : '';
const progressColor = progress && typeof progress.color === 'string' ? progress.color : '#0ea5e9';
const progressTrackColor = progress && typeof progress.track_color === 'string' ? progress.track_color : '#e2e8f0';
const progressSize = progress && typeof progress.size === 'number' ? progress.size : 300;
const progressThickness = progress && typeof progress.thickness === 'number' ? progress.thickness : 24;
const progressBarWidth = progress && typeof progress.width === 'number' ? progress.width : 600;
const progressBarHeight = progress && typeof progress.height === 'number' ? progress.height : 32;
const progressTextColor = progress && typeof progress.textColor === 'string' ? progress.textColor : '#475569';
const progressFontFamily = progress && typeof progress.fontFamily === 'string' ? progress.fontFamily : 'Inter';
// Countdown data
const countdown =
  typeof (data as any).countdown === 'object' && (data as any).countdown !== null
    ? (data as any).countdown
    : null;
const countdownEnabled = countdown && typeof countdown.start === 'number';
const countdownStart = countdown && typeof countdown.start === 'number' ? Math.max(1, Math.min(10, countdown.start)) : 3;
const countdownEndText = countdown && typeof countdown.end_text === 'string' ? countdown.end_text : 'GO!';
const countdownColor = countdown && typeof countdown.color === 'string' ? countdown.color : '#0ea5e9';
const countdownEndColor = countdown && typeof countdown.end_color === 'string' ? countdown.end_color : '#10b981';
const countdownStyle = countdown && typeof countdown.style === 'string' ? countdown.style : 'scale-fade';
const countdownFontFamily = countdown && typeof countdown.fontFamily === 'string' ? countdown.fontFamily : 'Inter';
// Highlight data
const highlight =
  typeof (data as any).highlight === 'object' && (data as any).highlight !== null
    ? (data as any).highlight
    : null;
const highlightEnabled = highlight && typeof highlight.text === 'string' && highlight.text.length > 0;
const highlightText = highlight && typeof highlight.text === 'string' ? highlight.text : '';
const highlightStyle = highlight && typeof highlight.style === 'string' ? highlight.style : 'marker';
const highlightTextColor = highlight && typeof highlight.text_color === 'string' ? highlight.text_color : '#0f172a';
const highlightColor = highlight && typeof highlight.highlight_color === 'string' ? highlight.highlight_color : '#fef08a';
const highlightFontSize = highlight && typeof highlight.font_size === 'number' ? highlight.font_size : 64;
// Slide transition data
const slide =
  typeof (data as any).slide === 'object' && (data as any).slide !== null
    ? (data as any).slide
    : null;
const slideEnabled = slide && typeof slide.text === 'string' && slide.text.length > 0;
const slideText = slide && typeof slide.text === 'string' ? slide.text : '';
const slideDirection = slide && typeof slide.direction === 'string' ? slide.direction : 'left';
const slideColor = slide && typeof slide.color === 'string' ? slide.color : '#0f172a';
const slideFontSize = slide && typeof slide.font_size === 'number' ? slide.font_size : 72;
const slideWithFade = slide && slide.with_fade !== false;
// Wipe transition data
const wipe =
  typeof (data as any).wipe === 'object' && (data as any).wipe !== null
    ? (data as any).wipe
    : null;
const wipeEnabled = wipe !== null;
const wipeText = wipe && typeof wipe.text === 'string' ? wipe.text : '';
const wipeDirection = wipe && typeof wipe.direction === 'string' ? wipe.direction : 'right';
const wipeColor = wipe && typeof wipe.wipe_color === 'string' ? wipe.wipe_color : '#0ea5e9';
const wipeTextColor = wipe && typeof wipe.text_color === 'string' ? wipe.text_color : '#0f172a';
// Glitch effect data
const glitch =
  typeof (data as any).glitch === 'object' && (data as any).glitch !== null
    ? (data as any).glitch
    : null;
const glitchEnabled = glitch && typeof glitch.text === 'string' && glitch.text.length > 0;
const glitchText = glitch && typeof glitch.text === 'string' ? glitch.text : '';
const glitchIntensity = glitch && typeof glitch.intensity === 'string' ? glitch.intensity : 'medium';
const glitchColor = glitch && typeof glitch.color === 'string' ? glitch.color : '#ffffff';
const glitchFontSize = glitch && typeof glitch.font_size === 'number' ? glitch.font_size : 80;
// Bounce effect data
const bounce =
  typeof (data as any).bounce === 'object' && (data as any).bounce !== null
    ? (data as any).bounce
    : null;
const bounceEnabled = bounce && typeof bounce.text === 'string' && bounce.text.length > 0;
const bounceText = bounce && typeof bounce.text === 'string' ? bounce.text : '';
const bounceColor = bounce && typeof bounce.color === 'string' ? bounce.color : '#0f172a';
const bounceFontSize = bounce && typeof bounce.font_size === 'number' ? bounce.font_size : 80;
const bounceStyle = bounce && typeof bounce.style === 'string' ? bounce.style : 'drop';
// Timeline data
const timeline =
  typeof (data as any).timeline === 'object' && (data as any).timeline !== null
    ? (data as any).timeline
    : null;
const timelineItemsRaw = timeline && Array.isArray(timeline.items) ? timeline.items : [];
const timelineItems = timelineItemsRaw.map((item: unknown, index: number) => {
  if (typeof item === 'object' && item !== null) {
    const record = item as Record<string, unknown>;
    const defaultColors = ['#0ea5e9', '#8b5cf6', '#10b981', '#f97316', '#ef4444'];
    return {
      label: typeof record.label === 'string' ? record.label : 'Milestone ' + (index + 1),
      date: typeof record.date === 'string' ? record.date : '',
      color: typeof record.color === 'string' ? record.color : defaultColors[index % defaultColors.length],
    };
  }
  return { label: 'Milestone ' + (index + 1), date: '', color: '#0ea5e9' };
});
const timelineEnabled = timelineItems.length > 0;
const timelineLineColor = timeline && typeof timeline.line_color === 'string' ? timeline.line_color : '#cbd5e1';
const timelineTextColor = timeline && typeof timeline.textColor === 'string' ? timeline.textColor : '#0f172a';
const timelineFontFamily = timeline && typeof timeline.fontFamily === 'string' ? timeline.fontFamily : 'Inter';
const calloutsRaw = Array.isArray((data as any).callouts) ? (data as any).callouts : [];
const callouts = calloutsRaw.map((entry: unknown, index: number) => {
  if (typeof entry === 'object' && entry !== null) {
    const record = entry as Record<string, unknown>;
    const label = typeof record.label === 'string' ? record.label : 'Callout ' + (index + 1);
    const targetType = typeof record.target_type === 'string' ? record.target_type : '';
    const targetIndex = typeof record.target_index === 'number' ? record.target_index : -1;
    const x = typeof record.x === 'number' ? record.x : undefined;
    const y = typeof record.y === 'number' ? record.y : undefined;
    const dx = typeof record.dx === 'number' ? record.dx : 140;
    const dy = typeof record.dy === 'number' ? record.dy : -120;
    const color = typeof record.color === 'string' ? record.color : '#0f172a';
    return { label, targetType, targetIndex, x, y, dx, dy, color };
  }
  return { label: 'Callout ' + (index + 1), targetType: '', targetIndex: -1, x: undefined, y: undefined, dx: 140, dy: -120, color: '#0f172a' };
});

// Callout Line effect data
const calloutLine =
  typeof (data as any).calloutLine === 'object' && (data as any).calloutLine !== null
    ? (data as any).calloutLine
    : null;
const calloutLineEnabled = calloutLine && typeof calloutLine.label === 'string';
const calloutLineLabel = calloutLine?.label || '';
const calloutLineStartX = typeof calloutLine?.startX === 'number' ? calloutLine.startX : 0.2;
const calloutLineStartY = typeof calloutLine?.startY === 'number' ? calloutLine.startY : 0.8;
const calloutLineEndX = typeof calloutLine?.endX === 'number' ? calloutLine.endX : 0.7;
const calloutLineEndY = typeof calloutLine?.endY === 'number' ? calloutLine.endY : 0.3;
const calloutLineColor = calloutLine?.color || '#0ea5e9';
const calloutLineThickness = typeof calloutLine?.thickness === 'number' ? calloutLine.thickness : 3;
const calloutLineTextColor = calloutLine && typeof calloutLine.textColor === 'string' ? calloutLine.textColor : '#0f172a';
const calloutLineFontFamily = calloutLine && typeof calloutLine.fontFamily === 'string' ? calloutLine.fontFamily : 'Inter';

// Callout Box effect data
const calloutBox =
  typeof (data as any).calloutBox === 'object' && (data as any).calloutBox !== null
    ? (data as any).calloutBox
    : null;
const calloutBoxEnabled = calloutBox !== null;
const calloutBoxX = typeof calloutBox?.x === 'number' ? calloutBox.x : 0.5;
const calloutBoxY = typeof calloutBox?.y === 'number' ? calloutBox.y : 0.5;
const calloutBoxWidth = typeof calloutBox?.width === 'number' ? calloutBox.width : 0.3;
const calloutBoxHeight = typeof calloutBox?.height === 'number' ? calloutBox.height : 0.2;
const calloutBoxShape = calloutBox?.shape || 'rectangle';
const calloutBoxStyle = calloutBox?.style || 'stroke';
const calloutBoxColor = calloutBox?.color || '#ef4444';
const calloutBoxThickness = typeof calloutBox?.thickness === 'number' ? calloutBox.thickness : 4;

// Split Screen effect data
const splitScreen =
  typeof (data as any).splitScreen === 'object' && (data as any).splitScreen !== null
    ? (data as any).splitScreen
    : null;
const splitScreenPanelsRaw = splitScreen && Array.isArray(splitScreen.panels) ? splitScreen.panels : [];
const splitScreenPanels = splitScreenPanelsRaw.map((p: any, i: number) => ({
  title: p?.title || 'Panel ' + (i + 1),
  subtitle: p?.subtitle || '',
  color: p?.color || ['#0ea5e9', '#22c55e', '#eab308', '#ef4444'][i % 4],
}));
const splitScreenEnabled = splitScreenPanels.length >= 2;
const splitScreenLayout = splitScreen?.layout || 'horizontal';
const splitScreenGap = typeof splitScreen?.gap === 'number' ? splitScreen.gap : 4;
const splitScreenAnimation = splitScreen?.animation || 'slide';

// Picture in Picture effect data
const pip =
  typeof (data as any).pip === 'object' && (data as any).pip !== null
    ? (data as any).pip
    : null;
const pipEnabled = pip !== null;
const pipPosition = pip?.position || 'bottom-right';
const pipSize = typeof pip?.size === 'number' ? pip.size : 0.25;
const pipBorder = pip?.border !== false;
const pipBorderColor = pip?.borderColor || '#ffffff';
const pipBackground = pip?.background || '#1e293b';
const pipLabel = pip?.label || '';

// VHS Retro effect data
const vhs =
  typeof (data as any).vhs === 'object' && (data as any).vhs !== null
    ? (data as any).vhs
    : null;
const vhsEnabled = vhs !== null;
const vhsIntensity = typeof vhs?.intensity === 'number' ? vhs.intensity : 0.5;
const vhsScanlines = vhs?.scanlines !== false;
const vhsNoise = vhs?.noise !== false;
const vhsColorShift = vhs?.colorShift !== false;
const vhsText = vhs?.text || '';

// Film Grain effect data
const filmGrain =
  typeof (data as any).filmGrain === 'object' && (data as any).filmGrain !== null
    ? (data as any).filmGrain
    : null;
const filmGrainEnabled = filmGrain !== null;
const filmGrainIntensity = typeof filmGrain?.intensity === 'number' ? filmGrain.intensity : 0.3;
const filmGrainSize = typeof filmGrain?.size === 'number' ? filmGrain.size : 1;
const filmGrainText = filmGrain?.text || '';

// Photo Frame effect data
const photoFrame =
  typeof (data as any).photoFrame === 'object' && (data as any).photoFrame !== null
    ? (data as any).photoFrame
    : null;
const photoFrameEnabled = photoFrame !== null;
const photoFrameStyle = photoFrame?.style || 'polaroid';
const photoFrameTilt = typeof photoFrame?.tilt === 'number' ? photoFrame.tilt : 5;
const photoFrameCaption = photoFrame?.caption || '';
const photoFrameAnimation = photoFrame?.animation || 'drop';

// Document Reveal effect data
const docReveal =
  typeof (data as any).document === 'object' && (data as any).document !== null
    ? (data as any).document
    : null;
const docRevealEnabled = docReveal && typeof docReveal.content === 'string' && docReveal.content.length > 0;
const docRevealTitle = docReveal?.title || '';
const docRevealContent = docReveal?.content || '';
const docRevealStyle = docReveal?.style || 'paper';
const docRevealAnimation = docReveal?.animation || 'unfold';
const docRevealHighlight = docReveal?.highlight || '';

// Text Scramble effect data
const scramble =
  typeof (data as any).scramble === 'object' && (data as any).scramble !== null
    ? (data as any).scramble
    : null;
const scrambleEnabled = scramble && typeof scramble.text === 'string' && scramble.text.length > 0;
const scrambleText = scramble?.text || '';
const scrambleCharset = scramble?.charset || 'alphanumeric';
const scrambleColor = scramble?.color || '#22c55e';
const scrambleScrambleColor = scramble?.scrambleColor || '#0ea5e9';
const scrambleFontSize = typeof scramble?.font_size === 'number' ? scramble.font_size : 64;

// Gradient Text effect data
const gradientText =
  typeof (data as any).gradientText === 'object' && (data as any).gradientText !== null
    ? (data as any).gradientText
    : null;
const gradientTextEnabled = gradientText && typeof gradientText.text === 'string' && gradientText.text.length > 0;
const gradientTextValue = gradientText?.text || '';
const gradientTextColors = Array.isArray(gradientText?.colors) ? gradientText.colors : ['#0ea5e9', '#a855f7', '#ec4899'];
const gradientTextDirection = gradientText?.direction || 'horizontal';
const gradientTextSpeed = typeof gradientText?.speed === 'number' ? gradientText.speed : 1;
const gradientTextFontSize = typeof gradientText?.font_size === 'number' ? gradientText.font_size : 80;

// Dissolve Transition effect data
const dissolve =
  typeof (data as any).dissolve === 'object' && (data as any).dissolve !== null
    ? (data as any).dissolve
    : null;
const dissolveEnabled = dissolve !== null;
const dissolveText = dissolve?.text || '';
const dissolveEasing = dissolve?.easing || 'smooth';
const dissolveColor = dissolve?.color || '#ffffff';
const dissolveFontSize = typeof dissolve?.font_size === 'number' ? dissolve.font_size : 64;

// Zoom Transition effect data
const zoomTransition =
  typeof (data as any).zoom === 'object' && (data as any).zoom !== null
    ? (data as any).zoom
    : null;
const zoomEnabled = zoomTransition !== null;
const zoomText = zoomTransition?.text || '';
const zoomDirection = zoomTransition?.direction || 'in';
const zoomFocalX = typeof zoomTransition?.focal_x === 'number' ? zoomTransition.focal_x : 0.5;
const zoomFocalY = typeof zoomTransition?.focal_y === 'number' ? zoomTransition.focal_y : 0.5;
const zoomColor = zoomTransition?.color || '#ffffff';
const zoomFontSize = typeof zoomTransition?.font_size === 'number' ? zoomTransition.font_size : 64;

// Location Pin effect data
const locationPin =
  typeof (data as any).locationPin === 'object' && (data as any).locationPin !== null
    ? (data as any).locationPin
    : null;
const locationPinEnabled = locationPin !== null;
const locationPinX = typeof locationPin?.x === 'number' ? locationPin.x : 0.5;
const locationPinY = typeof locationPin?.y === 'number' ? locationPin.y : 0.5;
const locationPinLabel = locationPin?.label || '';
const locationPinColor = locationPin?.color || '#ef4444';
const locationPinPulse = locationPin?.pulse !== false;

// Light Leak effect data
const lightLeak =
  typeof (data as any).lightLeak === 'object' && (data as any).lightLeak !== null
    ? (data as any).lightLeak
    : null;
const lightLeakEnabled = lightLeak !== null;
const lightLeakStyle = lightLeak?.style || 'warm';
const lightLeakIntensity = typeof lightLeak?.intensity === 'number' ? lightLeak.intensity : 0.5;
const lightLeakPosition = lightLeak?.position || 'corner';
const lightLeakAnimated = lightLeak?.animated !== false;
const lightLeakColor = lightLeak?.color || '#ff6b35';

// Camera Shake effect data
const cameraShake =
  typeof (data as any).cameraShake === 'object' && (data as any).cameraShake !== null
    ? (data as any).cameraShake
    : null;
const cameraShakeEnabled = cameraShake !== null;
const cameraShakeIntensity = cameraShake?.intensity || 'subtle';
const cameraShakeStyle = cameraShake?.style || 'handheld';
const cameraShakeText = cameraShake?.text || '';
const cameraShakeBackground = cameraShake?.background || '#0f172a';

// Parallax effect data
const parallax =
  typeof (data as any).parallax === 'object' && (data as any).parallax !== null
    ? (data as any).parallax
    : null;
const parallaxEnabled = parallax !== null;
const parallaxLayers = typeof parallax?.layers === 'number' ? parallax.layers : 3;
const parallaxDirection = parallax?.direction || 'horizontal';
const parallaxIntensity = typeof parallax?.intensity === 'number' ? parallax.intensity : 1.0;

// Before/After effect data
const beforeAfter =
  typeof (data as any).beforeAfter === 'object' && (data as any).beforeAfter !== null
    ? (data as any).beforeAfter
    : null;
const beforeAfterEnabled = beforeAfter !== null;
const beforeAfterBeforeLabel = beforeAfter?.before_label || 'Before';
const beforeAfterAfterLabel = beforeAfter?.after_label || 'After';
const beforeAfterBeforeColor = beforeAfter?.before_color || '#64748b';
const beforeAfterAfterColor = beforeAfter?.after_color || '#22c55e';
const beforeAfterDirection = beforeAfter?.direction || 'horizontal';
const beforeAfterPauseMiddle = typeof beforeAfter?.pause_middle === 'number' ? beforeAfter.pause_middle : 1;
const beforeAfterShowSlider = beforeAfter?.show_slider !== false;

// Text Pop effect data
const textPop =
  typeof (data as any).textPop === 'object' && (data as any).textPop !== null
    ? (data as any).textPop
    : null;
const textPopEnabled = textPop && typeof textPop.text === 'string' && textPop.text.length > 0;
const textPopText = textPop?.text || '';
const textPopWords = textPopText.split(/\s+/).filter((w: string) => w.length > 0);
const textPopEmphasisWords = Array.isArray(textPop?.emphasis_words) ? textPop.emphasis_words : [];
const textPopStyle = textPop?.style || 'scale-up';
const textPopColor = textPop?.color || '#ffffff';
const textPopEmphasisColor = textPop?.emphasis_color || '#fbbf24';
const textPopFontSize = typeof textPop?.font_size === 'number' ? textPop.font_size : 72;

// Source Citation effect data
const sourceCitation =
  typeof (data as any).sourceCitation === 'object' && (data as any).sourceCitation !== null
    ? (data as any).sourceCitation
    : null;
const sourceCitationEnabled = sourceCitation && typeof sourceCitation.source === 'string';
const sourceCitationSource = sourceCitation?.source || '';
const sourceCitationTitle = sourceCitation?.title || '';
const sourceCitationDate = sourceCitation?.date || '';
const sourceCitationUrl = sourceCitation?.url || '';
const sourceCitationStyle = sourceCitation?.style || 'minimal';
const sourceCitationPosition = sourceCitation?.position || 'bottom-left';
const sourceCitationColor = sourceCitation?.color || '#94a3b8';

// Screen Frame effect data
const screenFrame =
  typeof (data as any).screenFrame === 'object' && (data as any).screenFrame !== null
    ? (data as any).screenFrame
    : null;
const screenFrameEnabled = screenFrame !== null;
const screenFrameDevice = screenFrame?.device || 'browser';
const screenFrameUrl = screenFrame?.url || '';
const screenFrameTitle = screenFrame?.title || '';
const screenFrameContentText = screenFrame?.content_text || '';
const screenFrameTheme = screenFrame?.theme || 'dark';
const screenFrameAnimation = screenFrame?.animation || 'scale';

// Audio Waveform effect data
const audioWaveform =
  typeof (data as any).audioWaveform === 'object' && (data as any).audioWaveform !== null
    ? (data as any).audioWaveform
    : null;
const audioWaveformEnabled = audioWaveform !== null;
const audioWaveformStyle = audioWaveform?.style || 'bars';
const audioWaveformColor = audioWaveform?.color || '#0ea5e9';
const audioWaveformSecondaryColor = audioWaveform?.secondary_color || '#a855f7';
const audioWaveformIntensity = typeof audioWaveform?.intensity === 'number' ? audioWaveform.intensity : 1.0;
const audioWaveformLabel = audioWaveform?.label || '';

// Zoom Blur effect data
const zoomBlur =
  typeof (data as any).zoomBlur === 'object' && (data as any).zoomBlur !== null
    ? (data as any).zoomBlur
    : null;
const zoomBlurEnabled = zoomBlur !== null;
const zoomBlurText = zoomBlur?.text || '';
const zoomBlurDirection = zoomBlur?.direction || 'in';
const zoomBlurIntensity = typeof zoomBlur?.intensity === 'number' ? zoomBlur.intensity : 0.7;
const zoomBlurSpeed = zoomBlur?.speed || 'medium';
const zoomBlurColor = zoomBlur?.color || '#ffffff';

// Glitch Transition effect data
const glitchEffect =
  typeof (data as any).glitch === 'object' && (data as any).glitch !== null
    ? (data as any).glitch
    : null;
const glitchEffectEnabled = glitchEffect !== null;
const glitchEffectText = glitchEffect?.text || '';
const glitchEffectIntensity = glitchEffect?.intensity || 'medium';
const glitchEffectStyle = glitchEffect?.style || 'digital';
const glitchEffectRgbSplit = glitchEffect?.rgb_split !== false;
const glitchEffectScanLines = glitchEffect?.scan_lines !== false;
const glitchEffectColor = glitchEffect?.color || '#00ff00';

// Data Ticker effect data
const dataTicker =
  typeof (data as any).dataTicker === 'object' && (data as any).dataTicker !== null
    ? (data as any).dataTicker
    : null;
const dataTickerEnabled = dataTicker !== null;
const dataTickerItems: { text: string; icon: string; color: string }[] = Array.isArray(dataTicker?.items)
  ? dataTicker.items.map((item: any) => ({
      text: item?.text || '',
      icon: item?.icon || '',
      color: item?.color || '#ffffff',
    }))
  : [
      { text: 'Breaking: Major announcement', icon: '', color: '#ffffff' },
      { text: 'Markets up 2.5%', icon: '', color: '#ffffff' },
    ];
const dataTickerPosition = dataTicker?.position || 'bottom';
const dataTickerSpeed = dataTicker?.speed || 'medium';
const dataTickerStyle = dataTicker?.style || 'news';
const dataTickerLabel = dataTicker?.label || '';
const dataTickerBackground = dataTicker?.background || '#1e3a5f';
const dataTickerTextColor = dataTicker?.text_color || '#ffffff';

// Social Media Post effect data
const socialPost =
  typeof (data as any).socialPost === 'object' && (data as any).socialPost !== null
    ? (data as any).socialPost
    : null;
const socialPostEnabled = socialPost !== null;
const socialPostPlatform = socialPost?.platform || 'twitter';
const socialPostUsername = socialPost?.username || '@user';
const socialPostHandle = socialPost?.handle || socialPostUsername;
const socialPostContent = socialPost?.content || '';
const socialPostVerified = socialPost?.verified === true;
const socialPostLikes = socialPost?.likes || '1.2K';
const socialPostRetweets = socialPost?.retweets || '234';
const socialPostComments = socialPost?.comments || '89';
const socialPostTimestamp = socialPost?.timestamp || '2h';
const socialPostAnimation = socialPost?.animation || 'scale';
const socialPostTheme = socialPost?.theme || 'dark';

// Video Frame Stack effect data
const frameStack =
  typeof (data as any).frameStack === 'object' && (data as any).frameStack !== null
    ? (data as any).frameStack
    : null;
const frameStackEnabled = frameStack !== null;
const frameStackFrames: { title: string; color: string }[] = Array.isArray(frameStack?.frames)
  ? frameStack.frames.map((f: any, i: number) => ({
      title: f?.title || 'Video ' + (i + 1),
      color: f?.color || ['#ef4444', '#f59e0b', '#22c55e', '#0ea5e9', '#8b5cf6', '#ec4899'][i % 6],
    }))
  : Array.from({ length: 6 }, (_, i) => ({
      title: 'Video ' + (i + 1),
      color: ['#ef4444', '#f59e0b', '#22c55e', '#0ea5e9', '#8b5cf6', '#ec4899'][i % 6],
    }));
const frameStackLayout = frameStack?.layout || 'grid';
const frameStackHighlight = typeof frameStack?.highlight === 'number' ? frameStack.highlight : 0;
const frameStackAnimation = frameStack?.animation || 'stagger';

// Style Texture data (grain, vignette, gradient)
const texture =
  typeof (data as any).texture === 'object' && (data as any).texture !== null
    ? (data as any).texture
    : null;
const textureEnabled = texture !== null;
const textureGrainOpacity = texture && typeof texture.grainOpacity === 'number' ? texture.grainOpacity : 0;
const textureVignette = texture && texture.vignette === true;
const textureGradient = texture && typeof texture.gradient === 'object' && texture.gradient !== null
  ? texture.gradient
  : null;
const textureGradientFrom = textureGradient?.from || '#000000';
const textureGradientTo = textureGradient?.to || '#000000';
const textureGradientAngle = typeof textureGradient?.angle === 'number' ? textureGradient.angle : 180;

const titleRef = createRef<Txt>();
const subtitleRef = createRef<Txt>();
const itemRefs = safeItems.map(() => createRef<Txt>());
const barRefs = chartItems.map(() => createRef<Rect>());
const lineRef = createRef<Line>();
const lineFillRef = createRef<Line>();
const linePointRefs = chartItems.map(() => createRef<Circle>());
const pieSegmentRefs = chartItems.map(() => createRef<Circle>());
const pieLabelRefs = chartItems.map(() => createRef<Txt>());
const kineticRef = createRef<Txt>();
const counterRef = createRef<Txt>();
const counterLabelRef = createRef<Txt>();
const typewriterRef = createRef<Txt>();
const cursorRef = createRef<Rect>();
const progressTrackRef = createRef<Circle>();
const progressArcRef = createRef<Circle>();
const progressPercentRef = createRef<Txt>();
const progressLabelRef = createRef<Txt>();
const progressBarTrackRef = createRef<Rect>();
const progressBarFillRef = createRef<Rect>();
const countdownRef = createRef<Txt>();
const highlightTextRef = createRef<Txt>();
const highlightMarkerRef = createRef<Rect>();
const highlightUnderlineRef = createRef<Line>();
const slideTextRef = createRef<Txt>();
const wipeBarRef = createRef<Rect>();
const wipeTextRef = createRef<Txt>();
const glitchMainRef = createRef<Txt>();
const glitchRedRef = createRef<Txt>();
const glitchBlueRef = createRef<Txt>();
const bounceLetterRefs: ReturnType<typeof createRef<Txt>>[] = [];
const timelineLineRef = createRef<Line>();
const timelineDotRefs = timelineItems.map(() => createRef<Circle>());
const timelineLabelRefs = timelineItems.map(() => createRef<Txt>());
const timelineDateRefs = timelineItems.map(() => createRef<Txt>());
const calloutGroupRefs = callouts.map(() => createRef<Layout>());
const calloutLineRefs = callouts.map(() => createRef<Line>());
const calloutLabelRefs = callouts.map(() => createRef<Txt>());

// New effect refs
const newCalloutLineRef = createRef<Line>();
const newCalloutLabelRef = createRef<Txt>();
const calloutBoxRef = createRef<Rect>();
const calloutBoxPulseRef = createRef<Circle>();
const splitScreenPanelRefs = splitScreenPanels.map(() => createRef<Rect>());
const splitScreenTitleRefs = splitScreenPanels.map(() => createRef<Txt>());
const splitScreenSubtitleRefs = splitScreenPanels.map(() => createRef<Txt>());
const pipContainerRef = createRef<Rect>();
const pipLabelRef = createRef<Txt>();
const vhsTextRef = createRef<Txt>();
const filmGrainTextRef = createRef<Txt>();
const photoFrameRef = createRef<Rect>();
const photoFrameCaptionRef = createRef<Txt>();
const docRevealRef = createRef<Rect>();
const docRevealTitleRef = createRef<Txt>();
const docRevealContentRef = createRef<Txt>();
const scrambleRef = createRef<Txt>();
const gradientTextRef = createRef<Txt>();
const dissolveTextRef = createRef<Txt>();
const zoomContainerRef = createRef<Layout>();
const zoomTextRef = createRef<Txt>();
const locationPinRef = createRef<Layout>();
const locationPinBodyRef = createRef<Circle>();
const locationPinPulseRef = createRef<Circle>();
const locationPinLabelRef = createRef<Txt>();
// Progress staircase refs
const staircaseArrowRef = createRef<Line>();
const staircaseCardRefs = staircaseItems.map(() => createRef<Layout>());
const staircaseValueRefs = staircaseItems.map(() => createRef<Txt>());

// New effect refs
const lightLeakRef = createRef<Rect>();
const cameraShakeContainerRef = createRef<Layout>();
const cameraShakeTextRef = createRef<Txt>();
const parallaxLayerRefs: ReturnType<typeof createRef<Rect>>[] = [];
for (let i = 0; i < 5; i++) parallaxLayerRefs.push(createRef<Rect>());
const beforeAfterBeforeRef = createRef<Rect>();
const beforeAfterAfterRef = createRef<Rect>();
const beforeAfterSliderRef = createRef<Rect>();
const beforeAfterBeforeLabelRef = createRef<Txt>();
const beforeAfterAfterLabelRef = createRef<Txt>();
const textPopWordRefs: ReturnType<typeof createRef<Txt>>[] = [];
for (let i = 0; i < 50; i++) textPopWordRefs.push(createRef<Txt>());
const sourceCitationRef = createRef<Layout>();
const sourceCitationSourceRef = createRef<Txt>();
const sourceCitationTitleRef = createRef<Txt>();
const screenFrameRef = createRef<Rect>();
const screenFrameTitleBarRef = createRef<Rect>();
const screenFrameContentRef = createRef<Txt>();
const audioWaveformBarRefs: ReturnType<typeof createRef<Rect>>[] = [];
for (let i = 0; i < 32; i++) audioWaveformBarRefs.push(createRef<Rect>());
const audioWaveformLabelRef = createRef<Txt>();

// Zoom Blur refs
const zoomBlurContainerRef = createRef<Layout>();
const zoomBlurTextRef = createRef<Txt>();
const zoomBlurRaysRefs: ReturnType<typeof createRef<Rect>>[] = [];
for (let i = 0; i < 12; i++) zoomBlurRaysRefs.push(createRef<Rect>());

// Glitch Effect refs
const glitchEffectContainerRef = createRef<Layout>();
const glitchEffectMainRef = createRef<Txt>();
const glitchEffectRedRef = createRef<Txt>();
const glitchEffectBlueRef = createRef<Txt>();
const glitchEffectScanLineRef = createRef<Rect>();

// Data Ticker refs
const dataTickerContainerRef = createRef<Rect>();
const dataTickerLabelRef = createRef<Txt>();
const dataTickerScrollRef = createRef<Layout>();
const dataTickerItemRefs: ReturnType<typeof createRef<Txt>>[] = [];
for (let i = 0; i < 10; i++) dataTickerItemRefs.push(createRef<Txt>());

// Social Post refs
const socialPostContainerRef = createRef<Rect>();
const socialPostUsernameRef = createRef<Txt>();
const socialPostContentRef = createRef<Txt>();
const socialPostStatsRef = createRef<Layout>();

// Frame Stack refs
const frameStackContainerRef = createRef<Layout>();
const frameStackItemRefs: ReturnType<typeof createRef<Rect>>[] = [];
for (let i = 0; i < 12; i++) frameStackItemRefs.push(createRef<Rect>());
const frameStackTitleRefs: ReturnType<typeof createRef<Txt>>[] = [];
for (let i = 0; i < 12; i++) frameStackTitleRefs.push(createRef<Txt>());

// Texture overlay refs
const textureGradientRef = createRef<Rect>();
const textureVignetteRef = createRef<Rect>();
const textureGrainRefs: ReturnType<typeof createRef<Circle>>[] = [];
for (let i = 0; i < 150; i++) textureGrainRefs.push(createRef<Circle>());

function formatItem(item: unknown, index: number): string {
  if (typeof item === 'string' || typeof item === 'number') {
    return String(item);
  }
  if (typeof item === 'object' && item !== null) {
    const record = item as Record<string, unknown>;
    const label =
      typeof record.label === 'string'
        ? record.label
        : typeof record.title === 'string'
          ? record.title
          : 'Item ' + (index + 1);
    const desc =
      typeof record.desc === 'string'
        ? record.desc
        : typeof record.description === 'string'
          ? record.description
          : '';
    const value =
      typeof record.value === 'string' || typeof record.value === 'number'
        ? ' (' + record.value + ')'
        : '';
    return desc ? label + ' - ' + desc + value : label + value;
  }
  return 'Item ' + (index + 1);
}

export default makeScene2D(function* (view) {
  view.add(<Rect width={width} height={height} fill={background} />);

  // Add gradient overlay if texture.gradient is defined
  if (textureGradient) {
    // Calculate gradient direction based on angle
    const angleRad = (textureGradientAngle * Math.PI) / 180;
    const cos = Math.cos(angleRad);
    const sin = Math.sin(angleRad);
    view.add(
      <Rect
        ref={textureGradientRef}
        width={width}
        height={height}
        opacity={0.4}
        fill={textureGradientFrom}
      >
        <Rect
          width={width}
          height={height}
          opacity={0.6}
          fill={textureGradientTo}
          y={sin > 0 ? -height * 0.5 : height * 0.5}
        />
      </Rect>
    );
  }

  // Add vignette overlay if enabled
  if (textureVignette) {
    view.add(
      <Rect
        ref={textureVignetteRef}
        width={width}
        height={height}
        radius={0}
        fill="transparent"
        shadowColor="#000000"
        shadowBlur={width * 0.4}
        shadowOffsetX={0}
        shadowOffsetY={0}
        opacity={0.7}
      />
    );
  }

  // Add grain overlay if grainOpacity > 0
  if (textureGrainOpacity > 0) {
    const grainCount = Math.floor(150 * textureGrainOpacity);
    const grainElements: JSX.Element[] = [];
    for (let i = 0; i < grainCount; i++) {
      const x = (Math.random() - 0.5) * width;
      const y = (Math.random() - 0.5) * height;
      const size = Math.random() * 2 + 1;
      const opacity = Math.random() * 0.3 * textureGrainOpacity;
      grainElements.push(
        <Circle
          key={i}
          ref={textureGrainRefs[i]}
          x={x}
          y={y}
          width={size}
          height={size}
          fill="#ffffff"
          opacity={opacity}
        />
      );
    }
    view.add(
      <Layout width={width} height={height}>
        {grainElements}
      </Layout>
    );
  }

  if (kineticEnabled) {
    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Txt
          ref={kineticRef}
          text=""
          fontSize={kineticSize}
          fontFamily={kineticFontFamily}
          fontWeight={kineticFontWeight}
          fill={kineticColor}
          opacity={0}
        />
      </Layout>
    );

    for (const phrase of kineticPhrases) {
      if (!phrase.text || !kineticRef()) continue;
      kineticRef().text(phrase.text);
      kineticRef().scale(0.95);
      kineticRef().opacity(0);
      yield* all(
        kineticRef().opacity(1, 0.25),
        kineticRef().scale(1, 0.35, easeOutCubic),
      );
      yield* waitFor(phrase.hold);
      yield* kineticRef().opacity(0, 0.2);
    }

    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    yield* waitFor(Math.max(0, duration - kineticPhrases.length * 0.8));
    return;
  }

  if (counterEnabled) {
    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center" direction="column" gap={24}>
        <Txt
          ref={counterRef}
          text={counterPrefix + '0' + counterSuffix}
          fontSize={counterSize}
          fontFamily={counterFontFamily}
          fontWeight={700}
          fill={counterColor}
          opacity={0}
        />
        {counterLabel ? (
          <Txt
            ref={counterLabelRef}
            text={counterLabel}
            fontSize={36}
            fontFamily={counterFontFamily}
            fontWeight={500}
            fill={counterLabelColor}
            opacity={0}
          />
        ) : null}
      </Layout>
    );

    // Fade in the counter
    yield* counterRef().opacity(1, 0.3);

    // Animate the counter rolling up
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const rollDuration = Math.min(duration * 0.6, 2.5);
    const steps = 60;
    const stepTime = rollDuration / steps;

    for (let i = 1; i <= steps; i++) {
      const progress = i / steps;
      // Ease out cubic for natural deceleration
      const eased = 1 - Math.pow(1 - progress, 3);
      const currentValue = Math.round(counterValue * eased);
      // Format with commas for large numbers
      const formatted = currentValue.toLocaleString();
      counterRef().text(counterPrefix + formatted + counterSuffix);
      yield* waitFor(stepTime);
    }

    // Ensure final value is exact
    counterRef().text(counterPrefix + counterValue.toLocaleString() + counterSuffix);

    // Show label after counter finishes
    if (counterLabelRef()) {
      yield* counterLabelRef().opacity(1, 0.4);
    }

    // Hold for remaining duration
    const elapsed = 0.3 + rollDuration + 0.4;
    yield* waitFor(Math.max(0.5, duration - elapsed));
    return;
  }

  if (typewriterEnabled) {
    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center" direction="row">
        <Txt
          ref={typewriterRef}
          text=""
          fontSize={typewriterFontSize}
          fontWeight={500}
          fontFamily="'SF Mono', 'Consolas', 'Monaco', monospace"
          fill={typewriterColor}
        />
        <Rect
          ref={cursorRef}
          width={3}
          height={typewriterFontSize * 1.1}
          fill={typewriterCursorColor}
          marginLeft={2}
          opacity={1}
        />
      </Layout>
    );

    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const chars = typewriterText.split('');
    const typeTime = chars.length / typewriterSpeed;
    const charDelay = 1 / typewriterSpeed;

    // Blink cursor before typing starts
    for (let i = 0; i < 3; i++) {
      yield* cursorRef().opacity(0, 0.25);
      yield* cursorRef().opacity(1, 0.25);
    }

    // Type each character
    let currentText = '';
    for (const char of chars) {
      currentText += char;
      typewriterRef().text(currentText);
      yield* waitFor(charDelay);
    }

    // Blink cursor after typing completes
    const holdTime = Math.max(0.5, duration - typeTime - 1.5);
    const blinks = Math.floor(holdTime / 0.5);
    for (let i = 0; i < blinks; i++) {
      yield* cursorRef().opacity(0, 0.25);
      yield* cursorRef().opacity(1, 0.25);
    }

    return;
  }

  if (progressEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    if (progressType === 'circular') {
      // Circular progress ring
      view.add(
        <Layout layout width={width} height={height} alignItems="center" justifyContent="center" direction="column" gap={24}>
          <Layout layout={false}>
            {/* Track (background ring) */}
            <Circle
              ref={progressTrackRef}
              size={progressSize}
              stroke={progressTrackColor}
              lineWidth={progressThickness}
              startAngle={-90}
              endAngle={270}
            />
            {/* Progress arc */}
            <Circle
              ref={progressArcRef}
              size={progressSize}
              stroke={progressColor}
              lineWidth={progressThickness}
              startAngle={-90}
              endAngle={-90}
              lineCap="round"
            />
            {/* Percentage in center */}
            <Txt
              ref={progressPercentRef}
              text="0%"
              fontSize={progressSize * 0.2}
              fontWeight={700}
              fill={progressColor}
            />
          </Layout>
          {progressLabel ? (
            <Txt
              ref={progressLabelRef}
              text={progressLabel}
              fontSize={32}
              fontWeight={600}
              fontFamily={progressFontFamily}
              fill={progressTextColor}
              opacity={0}
            />
          ) : null}
        </Layout>
      );

      // Animate progress
      const animDuration = Math.min(duration * 0.7, 2.5);
      const targetAngle = -90 + (progressValue / 100) * 360;
      const steps = 60;
      const stepTime = animDuration / steps;

      for (let i = 1; i <= steps; i++) {
        const progress = i / steps;
        const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
        const currentAngle = -90 + (progressValue / 100) * 360 * eased;
        const currentPercent = Math.round(progressValue * eased);

        if (progressArcRef()) {
          progressArcRef().endAngle(currentAngle);
        }
        if (progressPercentRef()) {
          progressPercentRef().text(currentPercent + '%');
        }
        yield* waitFor(stepTime);
      }

      // Ensure final values
      if (progressArcRef()) progressArcRef().endAngle(targetAngle);
      if (progressPercentRef()) progressPercentRef().text(progressValue + '%');

      // Show label
      if (progressLabelRef()) {
        yield* progressLabelRef().opacity(1, 0.4);
      }

      // Hold
      yield* waitFor(Math.max(0.5, duration - animDuration - 0.4));
    } else {
      // Progress bar
      view.add(
        <Layout layout width={width} height={height} alignItems="center" justifyContent="center" direction="column" gap={24}>
          {progressLabel ? (
            <Txt
              ref={progressLabelRef}
              text={progressLabel}
              fontSize={28}
              fontWeight={600}
              fontFamily={progressFontFamily}
              fill={progressTextColor}
              opacity={1}
            />
          ) : null}
          <Layout layout={false}>
            {/* Track */}
            <Rect
              ref={progressBarTrackRef}
              width={progressBarWidth}
              height={progressBarHeight}
              fill={progressTrackColor}
              radius={progressBarHeight / 2}
            />
            {/* Fill */}
            <Rect
              ref={progressBarFillRef}
              x={-(progressBarWidth / 2)}
              width={0}
              height={progressBarHeight}
              fill={progressColor}
              radius={progressBarHeight / 2}
              offsetX={-1}
            />
          </Layout>
          <Txt
            ref={progressPercentRef}
            text="0%"
            fontSize={36}
            fontWeight={700}
            fill={progressColor}
          />
        </Layout>
      );

      // Animate progress bar
      const animDuration = Math.min(duration * 0.7, 2);
      const targetWidth = (progressValue / 100) * progressBarWidth;
      const steps = 50;
      const stepTime = animDuration / steps;

      for (let i = 1; i <= steps; i++) {
        const progress = i / steps;
        const eased = 1 - Math.pow(1 - progress, 3);
        const currentWidth = targetWidth * eased;
        const currentPercent = Math.round(progressValue * eased);

        if (progressBarFillRef()) {
          progressBarFillRef().width(currentWidth);
        }
        if (progressPercentRef()) {
          progressPercentRef().text(currentPercent + '%');
        }
        yield* waitFor(stepTime);
      }

      // Ensure final values
      if (progressBarFillRef()) progressBarFillRef().width(targetWidth);
      if (progressPercentRef()) progressPercentRef().text(progressValue + '%');

      // Hold
      yield* waitFor(Math.max(0.5, duration - animDuration));
    }

    return;
  }

  if (countdownEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const timePerNumber = (duration - 1) / (countdownStart + 1); // Leave 1s for end text

    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Txt
          ref={countdownRef}
          text=""
          fontSize={180}
          fontWeight={700}
          fontFamily={countdownFontFamily}
          fill={countdownColor}
          opacity={0}
          scale={0.5}
        />
      </Layout>
    );

    // Animate each number
    for (let num = countdownStart; num >= 1; num--) {
      countdownRef().text(String(num));
      countdownRef().fill(countdownColor);
      countdownRef().scale(0.5);
      countdownRef().opacity(0);

      if (countdownStyle === 'bounce') {
        // Bounce in style
        yield* all(
          countdownRef().opacity(1, 0.15),
          countdownRef().scale(1.2, 0.2, easeOutCubic),
        );
        yield* countdownRef().scale(1, 0.15, easeOutCubic);
        yield* waitFor(timePerNumber - 0.5);
        yield* countdownRef().opacity(0, 0.15);
      } else if (countdownStyle === 'flip') {
        // Flip style (rotation)
        countdownRef().rotation(-90);
        yield* all(
          countdownRef().opacity(1, 0.2),
          countdownRef().rotation(0, 0.3, easeOutCubic),
          countdownRef().scale(1, 0.3, easeOutCubic),
        );
        yield* waitFor(timePerNumber - 0.5);
        yield* all(
          countdownRef().opacity(0, 0.15),
          countdownRef().rotation(90, 0.15),
        );
      } else {
        // Default scale-fade
        yield* all(
          countdownRef().opacity(1, 0.2),
          countdownRef().scale(1, 0.3, easeOutCubic),
        );
        yield* waitFor(timePerNumber - 0.5);
        yield* all(
          countdownRef().opacity(0, 0.2),
          countdownRef().scale(1.5, 0.2),
        );
      }
    }

    // Show end text
    if (countdownEndText) {
      countdownRef().text(countdownEndText);
      countdownRef().fill(countdownEndColor);
      countdownRef().scale(0.3);
      countdownRef().opacity(0);

      yield* all(
        countdownRef().opacity(1, 0.2),
        countdownRef().scale(1.1, 0.3, easeOutCubic),
      );
      yield* countdownRef().scale(1, 0.1);
      yield* waitFor(0.7);
    }

    return;
  }

  if (highlightEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    // Estimate text width based on character count and font size
    const estimatedTextWidth = highlightText.length * highlightFontSize * 0.55;

    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Layout layout={false}>
          {/* Highlight marker/underline behind text */}
          {highlightStyle === 'marker' ? (
            <Rect
              ref={highlightMarkerRef}
              width={0}
              height={highlightFontSize * 0.85}
              fill={highlightColor}
              y={highlightFontSize * 0.1}
              x={-estimatedTextWidth / 2}
              offsetX={-1}
              radius={4}
            />
          ) : highlightStyle === 'underline' ? (
            <Line
              ref={highlightUnderlineRef}
              points={[new Vector2(-estimatedTextWidth / 2, highlightFontSize * 0.45), new Vector2(-estimatedTextWidth / 2, highlightFontSize * 0.45)]}
              stroke={highlightColor}
              lineWidth={8}
              lineCap="round"
            />
          ) : (
            <Rect
              ref={highlightMarkerRef}
              width={0}
              height={highlightFontSize * 1.4}
              stroke={highlightColor}
              lineWidth={4}
              x={-estimatedTextWidth / 2}
              offsetX={-1}
              radius={8}
            />
          )}
          {/* Text */}
          <Txt
            ref={highlightTextRef}
            text={highlightText}
            fontSize={highlightFontSize}
            fontWeight={700}
            fill={highlightTextColor}
            opacity={0}
          />
        </Layout>
      </Layout>
    );

    // Show text first
    yield* highlightTextRef().opacity(1, 0.3);
    yield* waitFor(0.2);

    // Animate highlight
    const highlightDuration = Math.min(duration * 0.4, 1.2);
    if (highlightStyle === 'marker' && highlightMarkerRef()) {
      yield* highlightMarkerRef().width(estimatedTextWidth + 20, highlightDuration, easeOutCubic);
    } else if (highlightStyle === 'underline' && highlightUnderlineRef()) {
      yield* highlightUnderlineRef().points(
        [
          new Vector2(-estimatedTextWidth / 2, highlightFontSize * 0.45),
          new Vector2(estimatedTextWidth / 2, highlightFontSize * 0.45),
        ],
        highlightDuration,
        easeOutCubic
      );
    } else if (highlightStyle === 'box' && highlightMarkerRef()) {
      yield* highlightMarkerRef().width(estimatedTextWidth + 30, highlightDuration, easeOutCubic);
    }

    // Hold
    yield* waitFor(Math.max(0.5, duration - highlightDuration - 0.5));
    return;
  }

  if (slideEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    // Calculate starting position based on direction
    let startX = 0;
    let startY = 0;
    if (slideDirection === 'left') startX = -width;
    else if (slideDirection === 'right') startX = width;
    else if (slideDirection === 'top') startY = -height;
    else if (slideDirection === 'bottom') startY = height;

    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Txt
          ref={slideTextRef}
          text={slideText}
          fontSize={slideFontSize}
          fontWeight={700}
          fill={slideColor}
          x={startX}
          y={startY}
          opacity={slideWithFade ? 0 : 1}
        />
      </Layout>
    );

    // Animate slide in
    const slideDuration = Math.min(duration * 0.4, 1.2);
    if (slideWithFade) {
      yield* all(
        slideTextRef().x(0, slideDuration, easeOutCubic),
        slideTextRef().y(0, slideDuration, easeOutCubic),
        slideTextRef().opacity(1, slideDuration * 0.7),
      );
    } else {
      yield* all(
        slideTextRef().x(0, slideDuration, easeOutCubic),
        slideTextRef().y(0, slideDuration, easeOutCubic),
      );
    }

    // Hold
    yield* waitFor(Math.max(0.5, duration - slideDuration));
    return;
  }

  if (wipeEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    // Determine wipe bar properties based on direction
    const isHorizontal = wipeDirection === 'left' || wipeDirection === 'right';
    const barWidth = isHorizontal ? 0 : width;
    const barHeight = isHorizontal ? height : 0;
    const startX = wipeDirection === 'right' ? -width / 2 : wipeDirection === 'left' ? width / 2 : 0;
    const startY = wipeDirection === 'bottom' ? -height / 2 : wipeDirection === 'top' ? height / 2 : 0;

    const initialOffset = new Vector2(
      wipeDirection === 'right' ? -1 : wipeDirection === 'left' ? 1 : 0,
      wipeDirection === 'bottom' ? -1 : wipeDirection === 'top' ? 1 : 0
    );

    view.add(
      <Layout layout={false} width={width} height={height}>
        {/* Wipe bar */}
        <Rect
          ref={wipeBarRef}
          x={startX}
          y={startY}
          width={barWidth}
          height={barHeight}
          fill={wipeColor}
          offset={initialOffset}
        />
        {/* Text to reveal */}
        {wipeText ? (
          <Txt
            ref={wipeTextRef}
            x={width / 2}
            y={height / 2}
            text={wipeText}
            fontSize={72}
            fontWeight={700}
            fill={wipeTextColor}
            opacity={0}
          />
        ) : null}
      </Layout>
    );

    // Animate wipe
    const wipeDuration = Math.min(duration * 0.4, 1);

    if (isHorizontal) {
      yield* wipeBarRef().width(width, wipeDuration, easeOutCubic);
      yield* waitFor(0.1);
      if (wipeTextRef()) {
        yield* wipeTextRef().opacity(1, 0.3);
      }
      yield* waitFor(0.2);
      // Wipe exit - flip the offset to reverse direction
      const exitOffset = new Vector2(wipeDirection === 'right' ? 1 : -1, 0);
      wipeBarRef().offset(exitOffset);
      yield* wipeBarRef().width(0, wipeDuration * 0.8, easeOutCubic);
    } else {
      yield* wipeBarRef().height(height, wipeDuration, easeOutCubic);
      yield* waitFor(0.1);
      if (wipeTextRef()) {
        yield* wipeTextRef().opacity(1, 0.3);
      }
      yield* waitFor(0.2);
      const exitOffset = new Vector2(0, wipeDirection === 'bottom' ? 1 : -1);
      wipeBarRef().offset(exitOffset);
      yield* wipeBarRef().height(0, wipeDuration * 0.8, easeOutCubic);
    }

    // Hold
    yield* waitFor(Math.max(0.5, duration - wipeDuration * 2 - 0.6));
    return;
  }

  if (glitchEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const intensity = glitchIntensity === 'high' ? 12 : glitchIntensity === 'low' ? 3 : 6;

    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Layout layout={false}>
          {/* Red channel offset */}
          <Txt
            ref={glitchRedRef}
            text={glitchText}
            fontSize={glitchFontSize}
            fontWeight={700}
            fill="#ff0000"
            opacity={0.6}
            x={-intensity}
          />
          {/* Blue channel offset */}
          <Txt
            ref={glitchBlueRef}
            text={glitchText}
            fontSize={glitchFontSize}
            fontWeight={700}
            fill="#0000ff"
            opacity={0.6}
            x={intensity}
          />
          {/* Main text */}
          <Txt
            ref={glitchMainRef}
            text={glitchText}
            fontSize={glitchFontSize}
            fontWeight={700}
            fill={glitchColor}
          />
        </Layout>
      </Layout>
    );

    // Glitch animation loop
    const glitchCycles = Math.floor(duration * 2);
    for (let i = 0; i < glitchCycles; i++) {
      // Random offset for RGB split
      const offsetX = (Math.random() - 0.5) * intensity * 2;
      const offsetY = (Math.random() - 0.5) * intensity;

      // Rapid glitch
      glitchRedRef().x(-intensity + offsetX);
      glitchBlueRef().x(intensity - offsetX);
      glitchMainRef().y(offsetY);

      if (Math.random() > 0.7) {
        // Occasional clip/slice effect
        glitchMainRef().opacity(0.8);
      }
      yield* waitFor(0.05);

      // Reset
      glitchMainRef().opacity(1);
      glitchMainRef().y(0);

      // Hold stable
      yield* waitFor(0.35 + Math.random() * 0.2);
    }

    return;
  }

  if (bounceEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const letters = bounceText.split('');
    const letterWidth = bounceFontSize * 0.6;
    const totalWidth = letters.length * letterWidth;
    const startX = -totalWidth / 2 + letterWidth / 2;

    // Create refs for each letter
    for (let i = 0; i < letters.length; i++) {
      bounceLetterRefs.push(createRef<Txt>());
    }

    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Layout layout={false}>
          {letters.map((letter, index) => (
            <Txt
              ref={bounceLetterRefs[index]}
              text={letter}
              fontSize={bounceFontSize}
              fontWeight={700}
              fill={bounceColor}
              x={startX + index * letterWidth}
              y={bounceStyle === 'drop' ? -200 : 0}
              scale={bounceStyle === 'scale' ? 0 : 1}
              opacity={bounceStyle === 'wave' ? 1 : (bounceStyle === 'drop' ? 0 : 1)}
            />
          ))}
        </Layout>
      </Layout>
    );

    // Animate each letter
    const letterDelay = Math.min(0.1, (duration * 0.4) / letters.length);

    for (let i = 0; i < letters.length; i++) {
      const ref = bounceLetterRefs[i];
      if (!ref || !ref()) continue;

      if (bounceStyle === 'drop') {
        // Drop and bounce
        ref().opacity(1);
        yield* all(
          ref().y(20, 0.2, easeOutCubic),
        );
        yield* ref().y(0, 0.15, easeOutCubic);
      } else if (bounceStyle === 'scale') {
        // Scale bounce
        yield* all(
          ref().scale(1.3, 0.15, easeOutCubic),
        );
        yield* ref().scale(1, 0.1, easeOutCubic);
      } else {
        // Wave - letters bounce up and down
        yield* ref().y(-30, 0.15, easeOutCubic);
        yield* ref().y(0, 0.15, easeOutCubic);
      }

      if (i < letters.length - 1) {
        yield* waitFor(letterDelay);
      }
    }

    // Hold
    yield* waitFor(Math.max(0.5, duration - letters.length * (letterDelay + 0.3)));
    return;
  }

  if (timelineEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const itemCount = timelineItems.length;
    const timelineWidth = width - 200;
    const spacing = itemCount > 1 ? timelineWidth / (itemCount - 1) : timelineWidth;
    const startX = 100;
    const centerY = height / 2;

    // Build line points
    const lineStart = new Vector2(startX, centerY);
    const lineEnd = new Vector2(startX + timelineWidth, centerY);

    view.add(
      <Layout layout={false} width={width} height={height}>
        {/* Timeline line */}
        <Line
          ref={timelineLineRef}
          points={[lineStart, lineStart]}
          stroke={timelineLineColor}
          lineWidth={4}
          lineCap="round"
        />
        {/* Milestones */}
        {timelineItems.map((item, index) => {
          const x = startX + index * spacing;
          const isTop = index % 2 === 0;
          return (
            <>
              {/* Dot */}
              <Circle
                ref={timelineDotRefs[index]}
                x={x}
                y={centerY}
                size={0}
                fill={item.color}
                stroke="#ffffff"
                lineWidth={3}
              />
              {/* Label */}
              <Txt
                ref={timelineLabelRefs[index]}
                x={x}
                y={isTop ? centerY - 50 : centerY + 50}
                text={item.label}
                fontSize={24}
                fontWeight={600}
                fontFamily={timelineFontFamily}
                fill={item.color}
                opacity={0}
              />
              {/* Date */}
              {item.date ? (
                <Txt
                  ref={timelineDateRefs[index]}
                  x={x}
                  y={isTop ? centerY - 80 : centerY + 80}
                  text={item.date}
                  fontSize={18}
                  fontWeight={500}
                  fontFamily={timelineFontFamily}
                  fill={timelineTextColor}
                  opacity={0}
                />
              ) : null}
            </>
          );
        })}
      </Layout>
    );

    // Animate timeline line drawing
    yield* timelineLineRef().points([lineStart, lineEnd], 0.8, easeOutCubic);

    // Animate each milestone
    const milestoneDelay = Math.min(0.4, (duration * 0.5) / itemCount);

    for (let i = 0; i < itemCount; i++) {
      // Pop in dot
      if (timelineDotRefs[i] && timelineDotRefs[i]()) {
        yield* timelineDotRefs[i]().size(24, 0.2, easeOutCubic);
      }
      // Fade in label
      if (timelineLabelRefs[i] && timelineLabelRefs[i]()) {
        yield* timelineLabelRefs[i]().opacity(1, 0.2);
      }
      // Fade in date
      if (timelineDateRefs[i] && timelineDateRefs[i]()) {
        yield* timelineDateRefs[i]().opacity(1, 0.15);
      }

      if (i < itemCount - 1) {
        yield* waitFor(milestoneDelay);
      }
    }

    // Hold
    yield* waitFor(Math.max(0.5, duration - 0.8 - itemCount * (milestoneDelay + 0.35)));
    return;
  }

  // === NEW EFFECTS START ===

  // Callout Line effect
  if (calloutLineEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const startX = (calloutLineStartX - 0.5) * width;
    const startY = (calloutLineStartY - 0.5) * height;
    const endX = (calloutLineEndX - 0.5) * width;
    const endY = (calloutLineEndY - 0.5) * height;

    view.add(
      <Layout layout={false} width={width} height={height}>
        <Line
          ref={newCalloutLineRef}
          points={[new Vector2(startX, startY), new Vector2(startX, startY)]}
          stroke={calloutLineColor}
          lineWidth={calloutLineThickness}
          lineCap="round"
        />
        <Txt
          ref={newCalloutLabelRef}
          x={endX}
          y={endY - 30}
          text={calloutLineLabel}
          fontSize={28}
          fontWeight={600}
          fill={calloutLineColor}
          opacity={0}
        />
      </Layout>
    );

    // Animate line drawing
    yield* newCalloutLineRef().points([new Vector2(startX, startY), new Vector2(endX, endY)], 0.6, easeOutCubic);
    yield* newCalloutLabelRef().opacity(1, 0.3);
    yield* waitFor(Math.max(0.5, duration - 0.9));
    return;
  }

  // Callout Box effect
  if (calloutBoxEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const boxX = (calloutBoxX - 0.5) * width;
    const boxY = (calloutBoxY - 0.5) * height;
    const boxW = calloutBoxWidth * width;
    const boxH = calloutBoxHeight * height;
    const isCircle = calloutBoxShape === 'circle';
    const radius = isCircle ? Math.min(boxW, boxH) / 2 : (calloutBoxShape === 'rounded' ? 16 : 0);

    view.add(
      <Layout layout={false} width={width} height={height}>
        {calloutBoxStyle === 'pulse' ? (
          <Circle
            ref={calloutBoxPulseRef}
            x={boxX}
            y={boxY}
            size={0}
            fill={calloutBoxColor + '40'}
          />
        ) : null}
        {isCircle ? (
          <Circle
            ref={calloutBoxRef as any}
            x={boxX}
            y={boxY}
            size={0}
            stroke={calloutBoxStyle === 'stroke' ? calloutBoxColor : undefined}
            fill={calloutBoxStyle === 'fill' ? calloutBoxColor + '30' : undefined}
            lineWidth={calloutBoxThickness}
          />
        ) : (
          <Rect
            ref={calloutBoxRef}
            x={boxX}
            y={boxY}
            width={0}
            height={0}
            stroke={calloutBoxStyle === 'stroke' ? calloutBoxColor : undefined}
            fill={calloutBoxStyle === 'fill' ? calloutBoxColor + '30' : undefined}
            lineWidth={calloutBoxThickness}
            radius={radius}
          />
        )}
      </Layout>
    );

    // Animate box appearing
    if (isCircle) {
      yield* (calloutBoxRef() as any).size(Math.max(boxW, boxH), 0.4, easeOutCubic);
    } else {
      yield* all(
        calloutBoxRef().width(boxW, 0.4, easeOutCubic),
        calloutBoxRef().height(boxH, 0.4, easeOutCubic),
      );
    }

    // Pulse animation if enabled
    if (calloutBoxStyle === 'pulse' && calloutBoxPulseRef()) {
      for (let i = 0; i < 3; i++) {
        calloutBoxPulseRef().size(Math.max(boxW, boxH));
        calloutBoxPulseRef().opacity(0.6);
        yield* all(
          calloutBoxPulseRef().size(Math.max(boxW, boxH) * 1.5, 0.5),
          calloutBoxPulseRef().opacity(0, 0.5),
        );
      }
    }

    yield* waitFor(Math.max(0.5, duration - 1));
    return;
  }

  // Split Screen effect
  if (splitScreenEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const panelCount = splitScreenPanels.length;
    const isHorizontal = splitScreenLayout === 'horizontal';
    const panelWidth = isHorizontal ? (width - splitScreenGap * (panelCount - 1)) / panelCount : width;
    const panelHeight = isHorizontal ? height : (height - splitScreenGap * (panelCount - 1)) / panelCount;

    view.add(
      <Layout layout={false} width={width} height={height}>
        {splitScreenPanels.map((panel, index) => {
          const x = isHorizontal ? -width/2 + panelWidth/2 + index * (panelWidth + splitScreenGap) : 0;
          const y = isHorizontal ? 0 : -height/2 + panelHeight/2 + index * (panelHeight + splitScreenGap);
          const startX = splitScreenAnimation === 'slide' ? (isHorizontal ? (index % 2 === 0 ? -width : width) : 0) : x;
          const startY = splitScreenAnimation === 'slide' ? (isHorizontal ? 0 : (index % 2 === 0 ? -height : height)) : y;

          return (
            <Layout layout={false} key={index}>
              <Rect
                ref={splitScreenPanelRefs[index]}
                x={startX}
                y={startY}
                width={splitScreenAnimation === 'expand' ? 0 : panelWidth}
                height={splitScreenAnimation === 'expand' ? 0 : panelHeight}
                fill={panel.color}
                opacity={splitScreenAnimation === 'fade' ? 0 : 1}
              />
              <Txt
                ref={splitScreenTitleRefs[index]}
                x={x}
                y={y - (panel.subtitle ? 20 : 0)}
                text={panel.title}
                fontSize={48}
                fontWeight={700}
                fill="#ffffff"
                opacity={0}
              />
              {panel.subtitle ? (
                <Txt
                  ref={splitScreenSubtitleRefs[index]}
                  x={x}
                  y={y + 30}
                  text={panel.subtitle}
                  fontSize={24}
                  fontWeight={500}
                  fill="#ffffffcc"
                  opacity={0}
                />
              ) : null}
            </Layout>
          );
        })}
      </Layout>
    );

    // Animate panels in
    for (let i = 0; i < panelCount; i++) {
      const x = isHorizontal ? -width/2 + panelWidth/2 + i * (panelWidth + splitScreenGap) : 0;
      const y = isHorizontal ? 0 : -height/2 + panelHeight/2 + i * (panelHeight + splitScreenGap);

      if (splitScreenAnimation === 'slide') {
        yield* all(
          splitScreenPanelRefs[i]().x(x, 0.4, easeOutCubic),
          splitScreenPanelRefs[i]().y(y, 0.4, easeOutCubic),
        );
      } else if (splitScreenAnimation === 'expand') {
        splitScreenPanelRefs[i]().x(x);
        splitScreenPanelRefs[i]().y(y);
        yield* all(
          splitScreenPanelRefs[i]().width(panelWidth, 0.4, easeOutCubic),
          splitScreenPanelRefs[i]().height(panelHeight, 0.4, easeOutCubic),
        );
      } else {
        yield* splitScreenPanelRefs[i]().opacity(1, 0.3);
      }
      yield* splitScreenTitleRefs[i]().opacity(1, 0.2);
      if (splitScreenSubtitleRefs[i] && splitScreenSubtitleRefs[i]()) {
        yield* splitScreenSubtitleRefs[i]().opacity(1, 0.15);
      }
    }

    yield* waitFor(Math.max(0.5, duration - panelCount * 0.6));
    return;
  }

  // Picture in Picture effect
  if (pipEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const pipW = width * pipSize;
    const pipH = height * pipSize;
    const margin = 40;
    const pipX = pipPosition.includes('right') ? width/2 - pipW/2 - margin : -width/2 + pipW/2 + margin;
    const pipY = pipPosition.includes('bottom') ? height/2 - pipH/2 - margin : -height/2 + pipH/2 + margin;
    const startX = pipPosition.includes('right') ? width : -width;
    const startY = pipPosition.includes('bottom') ? height : -height;

    view.add(
      <Layout layout={false} width={width} height={height}>
        <Rect
          ref={pipContainerRef}
          x={startX}
          y={pipY}
          width={pipW}
          height={pipH}
          fill={pipBackground}
          stroke={pipBorder ? pipBorderColor : undefined}
          lineWidth={pipBorder ? 3 : 0}
          radius={8}
          shadowBlur={20}
          shadowColor="#00000040"
        />
        {pipLabel ? (
          <Txt
            ref={pipLabelRef}
            x={pipX}
            y={pipY}
            text={pipLabel}
            fontSize={24}
            fontWeight={600}
            fill="#ffffff"
            opacity={0}
          />
        ) : null}
      </Layout>
    );

    // Slide in
    yield* pipContainerRef().x(pipX, 0.5, easeOutCubic);
    if (pipLabelRef()) {
      yield* pipLabelRef().opacity(1, 0.3);
    }
    yield* waitFor(Math.max(0.5, duration - 0.8));
    return;
  }

  // VHS Retro effect
  if (vhsEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    view.add(
      <Layout layout={false} width={width} height={height}>
        {/* Scanlines overlay */}
        {vhsScanlines ? (
          <Rect width={width} height={height} opacity={vhsIntensity * 0.3}>
            {Array.from({ length: Math.floor(height / 4) }).map((_, i) => (
              <Rect
                key={i}
                y={-height/2 + i * 4 + 2}
                width={width}
                height={2}
                fill="#000000"
                opacity={0.3}
              />
            ))}
          </Rect>
        ) : null}
        {/* Text with color shift */}
        {vhsText ? (
          <>
            {vhsColorShift ? (
              <>
                <Txt x={-2 * vhsIntensity} text={vhsText} fontSize={64} fontWeight={700} fill="#ff000080" />
                <Txt x={2 * vhsIntensity} text={vhsText} fontSize={64} fontWeight={700} fill="#00ff0080" />
              </>
            ) : null}
            <Txt ref={vhsTextRef} text={vhsText} fontSize={64} fontWeight={700} fill="#ffffff" opacity={0} />
          </>
        ) : null}
      </Layout>
    );

    if (vhsTextRef()) {
      yield* vhsTextRef().opacity(1, 0.3);
    }
    yield* waitFor(Math.max(0.5, duration - 0.3));
    return;
  }

  // Film Grain effect
  if (filmGrainEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    view.add(
      <Layout layout={false} width={width} height={height}>
        {filmGrainText ? (
          <Txt ref={filmGrainTextRef} text={filmGrainText} fontSize={64} fontWeight={700} fill="#ffffff" opacity={0} />
        ) : null}
        {/* Grain texture simulated with dots */}
        <Rect width={width} height={height} opacity={filmGrainIntensity * 0.5}>
          {Array.from({ length: 100 }).map((_, i) => (
            <Circle
              key={i}
              x={Math.random() * width - width/2}
              y={Math.random() * height - height/2}
              size={filmGrainSize * 2}
              fill="#ffffff"
              opacity={Math.random() * 0.3}
            />
          ))}
        </Rect>
      </Layout>
    );

    if (filmGrainTextRef()) {
      yield* filmGrainTextRef().opacity(1, 0.3);
    }
    yield* waitFor(Math.max(0.5, duration - 0.3));
    return;
  }

  // Photo Frame effect
  if (photoFrameEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const frameW = width * 0.6;
    const frameH = height * 0.7;
    const isPolaroid = photoFrameStyle === 'polaroid';
    const captionHeight = isPolaroid ? 80 : 0;
    const framePadding = isPolaroid ? 20 : 10;
    const startY = photoFrameAnimation === 'drop' ? -height : 0;
    const startX = photoFrameAnimation === 'slide' ? -width : 0;

    view.add(
      <Layout layout={false} width={width} height={height}>
        <Rect
          ref={photoFrameRef}
          x={startX}
          y={startY}
          width={frameW}
          height={frameH + captionHeight}
          fill={isPolaroid ? '#ffffff' : '#1e293b'}
          radius={isPolaroid ? 4 : 8}
          rotation={photoFrameTilt}
          shadowBlur={30}
          shadowColor="#00000050"
          opacity={photoFrameAnimation === 'fade' ? 0 : 1}
        />
        {photoFrameCaption ? (
          <Txt
            ref={photoFrameCaptionRef}
            y={frameH/2 - captionHeight/2 + framePadding}
            text={photoFrameCaption}
            fontSize={24}
            fontWeight={500}
            fill={isPolaroid ? '#1e293b' : '#ffffff'}
            opacity={0}
          />
        ) : null}
      </Layout>
    );

    // Animate frame appearing
    if (photoFrameAnimation === 'drop') {
      yield* photoFrameRef().y(0, 0.5, easeOutCubic);
    } else if (photoFrameAnimation === 'slide') {
      yield* photoFrameRef().x(0, 0.5, easeOutCubic);
    } else {
      yield* photoFrameRef().opacity(1, 0.4);
    }
    if (photoFrameCaptionRef()) {
      yield* photoFrameCaptionRef().opacity(1, 0.3);
    }
    yield* waitFor(Math.max(0.5, duration - 0.8));
    return;
  }

  // Document Reveal effect
  if (docRevealEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const docW = width * 0.7;
    const docH = height * 0.8;
    const isNewspaper = docRevealStyle === 'newspaper';
    const isOfficial = docRevealStyle === 'official';
    const startScale = docRevealAnimation === 'unfold' ? 0.1 : 1;
    const startY = docRevealAnimation === 'drop' ? -height : 0;
    const startX = docRevealAnimation === 'slide' ? -width : 0;

    view.add(
      <Layout layout={false} width={width} height={height}>
        <Rect
          ref={docRevealRef}
          x={startX}
          y={startY}
          width={docW}
          height={docH}
          fill={isNewspaper ? '#f5f5dc' : '#ffffff'}
          radius={isOfficial ? 0 : 4}
          scale={startScale}
          shadowBlur={20}
          shadowColor="#00000030"
        />
        {docRevealTitle ? (
          <Txt
            ref={docRevealTitleRef}
            y={-docH/2 + 60}
            text={docRevealTitle}
            fontSize={isNewspaper ? 48 : 32}
            fontWeight={700}
            fill="#1e293b"
            opacity={0}
          />
        ) : null}
        <Txt
          ref={docRevealContentRef}
          y={docRevealTitle ? 20 : 0}
          text={docRevealContent.substring(0, 200)}
          fontSize={isNewspaper ? 18 : 20}
          fontWeight={400}
          fill="#334155"
          opacity={0}
          width={docW - 80}
        />
      </Layout>
    );

    // Animate document appearing
    if (docRevealAnimation === 'unfold') {
      yield* docRevealRef().scale(1, 0.5, easeOutCubic);
    } else if (docRevealAnimation === 'drop') {
      yield* docRevealRef().y(0, 0.4, easeOutCubic);
    } else {
      yield* docRevealRef().x(0, 0.4, easeOutCubic);
    }
    if (docRevealTitleRef()) {
      yield* docRevealTitleRef().opacity(1, 0.3);
    }
    yield* docRevealContentRef().opacity(1, 0.4);
    yield* waitFor(Math.max(0.5, duration - 1.2));
    return;
  }

  // Text Scramble effect
  if (scrambleEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const charsets: Record<string, string> = {
      alphanumeric: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
      binary: '01',
      symbols: '!@#$%^&*()[]{}|;:,.<>?',
      katakana: 'アイウエオカキクケコサシスセソタチツテト',
    };
    const charset = charsets[scrambleCharset] || charsets.alphanumeric;

    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Txt
          ref={scrambleRef}
          text={scrambleText.split('').map(() => charset[Math.floor(Math.random() * charset.length)]).join('')}
          fontSize={scrambleFontSize}
          fontWeight={700}
          fill={scrambleScrambleColor}
        />
      </Layout>
    );

    // Animate scramble decode
    const decodeTime = Math.min(duration * 0.7, 2);
    const steps = scrambleText.length;
    const stepTime = decodeTime / steps;

    for (let i = 0; i <= steps; i++) {
      const revealed = scrambleText.substring(0, i);
      const scrambled = scrambleText.substring(i).split('').map(() => charset[Math.floor(Math.random() * charset.length)]).join('');
      scrambleRef().text(revealed + scrambled);
      if (i === steps) {
        scrambleRef().fill(scrambleColor);
      }
      yield* waitFor(stepTime);
    }

    yield* waitFor(Math.max(0.5, duration - decodeTime));
    return;
  }

  // Gradient Text effect
  if (gradientTextEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Txt
          ref={gradientTextRef}
          text={gradientTextValue}
          fontSize={gradientTextFontSize}
          fontWeight={700}
          fill={gradientTextColors[0]}
          opacity={0}
        />
      </Layout>
    );

    yield* gradientTextRef().opacity(1, 0.3);

    // Animate color cycling
    const cycleTime = 1 / gradientTextSpeed;
    const cycles = Math.floor((duration - 0.3) / cycleTime);

    for (let i = 0; i < Math.min(cycles, 10); i++) {
      const colorIndex = i % gradientTextColors.length;
      const nextColorIndex = (i + 1) % gradientTextColors.length;
      yield* gradientTextRef().fill(gradientTextColors[nextColorIndex], cycleTime, linear);
    }

    yield* waitFor(Math.max(0.3, duration - 0.3 - cycles * cycleTime));
    return;
  }

  // Dissolve Transition effect
  if (dissolveEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Txt
          ref={dissolveTextRef}
          text={dissolveText || 'Dissolve'}
          fontSize={dissolveFontSize}
          fontWeight={700}
          fill={dissolveColor}
          opacity={0}
        />
      </Layout>
    );

    // Fade in
    const fadeTime = Math.min(duration * 0.3, 1);
    yield* dissolveTextRef().opacity(1, fadeTime);
    yield* waitFor(Math.max(0.5, duration - fadeTime * 2));
    // Fade out
    yield* dissolveTextRef().opacity(0, fadeTime);
    return;
  }

  // Zoom Transition effect
  if (zoomEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const focalX = (zoomFocalX - 0.5) * width;
    const focalY = (zoomFocalY - 0.5) * height;
    const isZoomIn = zoomDirection === 'in';

    view.add(
      <Layout
        ref={zoomContainerRef}
        layout
        width={width}
        height={height}
        alignItems="center"
        justifyContent="center"
        scale={isZoomIn ? 0.5 : 2}
        opacity={0}
        x={focalX * (isZoomIn ? 1 : -1)}
        y={focalY * (isZoomIn ? 1 : -1)}
      >
        <Txt
          ref={zoomTextRef}
          text={zoomText || 'Zoom'}
          fontSize={zoomFontSize}
          fontWeight={700}
          fill={zoomColor}
        />
      </Layout>
    );

    // Animate zoom
    const zoomTime = Math.min(duration * 0.4, 1.5);
    yield* all(
      zoomContainerRef().scale(1, zoomTime, easeOutCubic),
      zoomContainerRef().opacity(1, zoomTime * 0.5),
      zoomContainerRef().x(0, zoomTime, easeOutCubic),
      zoomContainerRef().y(0, zoomTime, easeOutCubic),
    );
    yield* waitFor(Math.max(0.5, duration - zoomTime));
    return;
  }

  // Location Pin effect
  if (locationPinEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const pinX = (locationPinX - 0.5) * width;
    const pinY = (locationPinY - 0.5) * height;
    const pinSize = 60;

    view.add(
      <Layout layout={false} width={width} height={height}>
        {/* Pulse circle */}
        {locationPinPulse ? (
          <Circle
            ref={locationPinPulseRef}
            x={pinX}
            y={pinY}
            size={0}
            fill={locationPinColor + '40'}
          />
        ) : null}
        {/* Pin body */}
        <Layout ref={locationPinRef} x={pinX} y={-height}>
          <Circle
            ref={locationPinBodyRef}
            size={pinSize}
            fill={locationPinColor}
          />
          {/* Pin point */}
          <Rect
            y={pinSize/2 + 10}
            width={20}
            height={20}
            fill={locationPinColor}
            rotation={45}
          />
          {/* Inner circle */}
          <Circle
            size={pinSize * 0.4}
            fill="#ffffff"
          />
        </Layout>
        {/* Label */}
        {locationPinLabel ? (
          <Txt
            ref={locationPinLabelRef}
            x={pinX}
            y={pinY + pinSize + 30}
            text={locationPinLabel}
            fontSize={24}
            fontWeight={600}
            fill={locationPinColor}
            opacity={0}
          />
        ) : null}
      </Layout>
    );

    // Drop animation with bounce
    yield* locationPinRef().y(pinY - pinSize/2, 0.4, easeOutCubic);

    // Pulse effect
    if (locationPinPulse && locationPinPulseRef()) {
      for (let i = 0; i < 2; i++) {
        locationPinPulseRef().size(pinSize);
        locationPinPulseRef().opacity(0.6);
        yield* all(
          locationPinPulseRef().size(pinSize * 3, 0.6),
          locationPinPulseRef().opacity(0, 0.6),
        );
      }
    }

    if (locationPinLabelRef()) {
      yield* locationPinLabelRef().opacity(1, 0.3);
    }

    yield* waitFor(Math.max(0.5, duration - 1.8));
    return;
  }

  // Light Leak effect
  if (lightLeakEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    // Get position offsets
    let startX = width * 0.3;
    let startY = -height * 0.3;
    if (lightLeakPosition === 'left') { startX = -width * 0.5; startY = 0; }
    else if (lightLeakPosition === 'right') { startX = width * 0.5; startY = 0; }
    else if (lightLeakPosition === 'top') { startX = 0; startY = -height * 0.5; }
    else if (lightLeakPosition === 'bottom') { startX = 0; startY = height * 0.5; }
    else if (lightLeakPosition === 'center') { startX = 0; startY = 0; }

    // Get colors based on style
    let colors = [lightLeakColor, '#fbbf24', '#ff6b35'];
    if (lightLeakStyle === 'cool') colors = ['#0ea5e9', '#a855f7', '#06b6d4'];
    else if (lightLeakStyle === 'rainbow') colors = ['#ef4444', '#fbbf24', '#22c55e', '#0ea5e9', '#a855f7'];
    else if (lightLeakStyle === 'burn') colors = ['#fff7ed', '#fed7aa', '#fdba74'];
    else if (lightLeakStyle === 'flare') colors = ['#ffffff', '#fef3c7', '#fde68a'];

    view.add(
      <Rect
        ref={lightLeakRef}
        x={startX}
        y={startY}
        width={width * 1.5}
        height={height * 1.5}
        fill={colors[0]}
        opacity={0}
        rotation={45}
      />
    );

    // Animate light leak
    yield* all(
      lightLeakRef().opacity(lightLeakIntensity * 0.6, duration * 0.3),
    );

    if (lightLeakAnimated) {
      yield* all(
        lightLeakRef().x(startX + 100, duration * 0.4),
        lightLeakRef().y(startY + 50, duration * 0.4),
      );
    }

    yield* waitFor(duration * 0.2);
    yield* lightLeakRef().opacity(0, duration * 0.1);
    return;
  }

  // Camera Shake effect
  if (cameraShakeEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    // Intensity values
    let shakeAmount = 5;
    if (cameraShakeIntensity === 'moderate') shakeAmount = 15;
    else if (cameraShakeIntensity === 'intense') shakeAmount = 30;
    else if (cameraShakeIntensity === 'earthquake') shakeAmount = 50;

    // Get shake text or show intensity indicator
    const displayText = cameraShakeText || (cameraShakeIntensity.toUpperCase() + ' SHAKE');

    view.add(
      <Layout ref={cameraShakeContainerRef} width={width} height={height}>
        <Rect width={width} height={height} fill={cameraShakeBackground} />
        <Txt
          ref={cameraShakeTextRef}
          text={displayText}
          fontSize={64}
          fontWeight={700}
          fill="#ffffff"
        />
      </Layout>
    );

    // Shake animation
    const shakeSteps = Math.floor(duration * 10);
    for (let i = 0; i < shakeSteps; i++) {
      const offsetX = (Math.random() - 0.5) * shakeAmount * 2;
      const offsetY = (Math.random() - 0.5) * shakeAmount * 2;
      const rotation = (Math.random() - 0.5) * (shakeAmount / 10);
      yield* all(
        cameraShakeContainerRef().x(offsetX, 0.05),
        cameraShakeContainerRef().y(offsetY, 0.05),
        cameraShakeContainerRef().rotation(rotation, 0.05),
      );
    }

    // Settle
    yield* all(
      cameraShakeContainerRef().x(0, 0.2),
      cameraShakeContainerRef().y(0, 0.2),
      cameraShakeContainerRef().rotation(0, 0.2),
    );
    return;
  }

  // Parallax effect
  if (parallaxEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const layerColors = ['#1e3a5f', '#2d5a4f', '#4d3a6f', '#5a4a3f', '#3d6a5f'];

    // Create layers with shapes for visual distinction
    for (let i = 0; i < parallaxLayers; i++) {
      const depth = (i + 1) / parallaxLayers;
      const layerWidth = width * (1.2 + depth * 0.3);
      const layerHeight = height * (1.2 + depth * 0.3);

      view.add(
        <Rect
          ref={parallaxLayerRefs[i]}
          width={layerWidth}
          height={layerHeight}
          fill={layerColors[i % layerColors.length]}
          opacity={0.5 + depth * 0.3}
          radius={20 + i * 30}
        >
          {/* Add visual elements to each layer */}
          <Txt
            text={'Layer ' + (i + 1)}
            fontSize={48 - i * 8}
            fontWeight={700}
            fill={'rgba(255, 255, 255, 0.3)'}
            y={-100 + i * 60}
          />
        </Rect>
      );
    }

    // Animate parallax movement
    const moveAmount = 100 * parallaxIntensity;
    const isHorizontal = parallaxDirection === 'horizontal';

    for (let i = 0; i < parallaxLayers; i++) {
      const depth = (i + 1) / parallaxLayers;
      const layerMove = moveAmount * depth;

      if (isHorizontal) {
        parallaxLayerRefs[i]().x(-layerMove);
      } else {
        parallaxLayerRefs[i]().y(-layerMove);
      }
    }

    yield* waitFor(0.3);

    const animations = [];
    for (let i = 0; i < parallaxLayers; i++) {
      const depth = (i + 1) / parallaxLayers;
      const layerMove = moveAmount * depth * 2;

      if (isHorizontal) {
        animations.push(parallaxLayerRefs[i]().x(layerMove, duration * 0.8, linear));
      } else {
        animations.push(parallaxLayerRefs[i]().y(layerMove, duration * 0.8, linear));
      }
    }

    yield* all(...animations);
    return;
  }

  // Before/After effect
  if (beforeAfterEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const isHorizontal = beforeAfterDirection === 'horizontal';

    view.add(
      <Layout layout={false} width={width} height={height}>
        {/* After (bottom layer) */}
        <Rect
          ref={beforeAfterAfterRef}
          width={width}
          height={height}
          fill={beforeAfterAfterColor}
        />
        <Txt
          ref={beforeAfterAfterLabelRef}
          x={isHorizontal ? width * 0.25 : 0}
          y={isHorizontal ? 0 : height * 0.25}
          text={beforeAfterAfterLabel}
          fontSize={48}
          fontWeight={700}
          fill="#ffffff"
        />
        {/* Before (top layer with clip) */}
        <Rect
          ref={beforeAfterBeforeRef}
          x={isHorizontal ? -width/2 : 0}
          y={isHorizontal ? 0 : -height/2}
          width={width}
          height={height}
          fill={beforeAfterBeforeColor}
          clip
        >
          <Txt
            text={beforeAfterBeforeLabel}
            x={isHorizontal ? width * 0.25 : 0}
            y={isHorizontal ? 0 : height * 0.25}
            fontSize={48}
            fontWeight={700}
            fill="#ffffff"
          />
        </Rect>
        {/* Slider line */}
        {beforeAfterShowSlider ? (
          <Rect
            ref={beforeAfterSliderRef}
            x={0}
            y={0}
            width={isHorizontal ? 6 : width}
            height={isHorizontal ? height : 6}
            fill="#ffffff"
          />
        ) : null}
      </Layout>
    );

    // Wipe animation
    const wipeTime = (duration - beforeAfterPauseMiddle) / 2;

    // Wipe to middle
    yield* all(
      beforeAfterBeforeRef().x(0, wipeTime, easeOutCubic),
      beforeAfterSliderRef ? beforeAfterSliderRef().x(0, wipeTime, easeOutCubic) : waitFor(0),
    );

    yield* waitFor(beforeAfterPauseMiddle);

    // Wipe to end
    yield* all(
      beforeAfterBeforeRef().x(isHorizontal ? width/2 : 0, wipeTime, easeOutCubic),
      beforeAfterBeforeRef().y(isHorizontal ? 0 : height/2, wipeTime, easeOutCubic),
      beforeAfterSliderRef ? beforeAfterSliderRef().x(isHorizontal ? width/2 : 0, wipeTime, easeOutCubic) : waitFor(0),
    );
    return;
  }

  // Text Pop effect
  if (textPopEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
    const words = textPopWords;
    const wordDelay = (duration * 0.8) / Math.max(words.length, 1);

    // Add all words
    const wordSpacing = textPopFontSize * 0.3;
    const totalWidth = words.length * textPopFontSize + (words.length - 1) * wordSpacing;
    let currentX = -totalWidth / 2;

    for (let i = 0; i < Math.min(words.length, 50); i++) {
      const word = words[i];
      const isEmphasis = textPopEmphasisWords.includes(word.toLowerCase());
      const wordWidth = word.length * textPopFontSize * 0.6;

      view.add(
        <Txt
          ref={textPopWordRefs[i]}
          x={currentX + wordWidth / 2}
          y={0}
          text={word}
          fontSize={textPopFontSize}
          fontWeight={700}
          fill={isEmphasis ? textPopEmphasisColor : textPopColor}
          opacity={0}
          scale={0.5}
        />
      );

      currentX += wordWidth + wordSpacing;
    }

    // Animate words popping in
    for (let i = 0; i < Math.min(words.length, 50); i++) {
      yield* all(
        textPopWordRefs[i]().opacity(1, 0.15),
        textPopWordRefs[i]().scale(1.2, 0.15, easeOutCubic),
      );
      yield* textPopWordRefs[i]().scale(1, 0.1, easeOutCubic);
      yield* waitFor(Math.max(0.05, wordDelay - 0.25));
    }

    yield* waitFor(duration * 0.1);
    return;
  }

  // Source Citation effect
  if (sourceCitationEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    // Position
    let posX = -width/2 + 100;
    let posY = height/2 - 80;
    if (sourceCitationPosition === 'bottom-right') { posX = width/2 - 100; }
    else if (sourceCitationPosition === 'bottom-center') { posX = 0; }
    else if (sourceCitationPosition === 'top-left') { posX = -width/2 + 100; posY = -height/2 + 80; }
    else if (sourceCitationPosition === 'top-right') { posX = width/2 - 100; posY = -height/2 + 80; }

    view.add(
      <Layout
        ref={sourceCitationRef}
        x={posX}
        y={posY}
        layout
        direction="column"
        gap={4}
        opacity={0}
      >
        <Txt
          ref={sourceCitationSourceRef}
          text={'Source: ' + sourceCitationSource}
          fontSize={20}
          fontWeight={600}
          fill={sourceCitationColor}
        />
        {sourceCitationTitle ? (
          <Txt
            ref={sourceCitationTitleRef}
            text={'"' + sourceCitationTitle + '"'}
            fontSize={16}
            fontStyle="italic"
            fill={sourceCitationColor}
          />
        ) : null}
        {sourceCitationDate ? (
          <Txt
            text={sourceCitationDate}
            fontSize={14}
            fill={sourceCitationColor}
            opacity={0.7}
          />
        ) : null}
      </Layout>
    );

    yield* sourceCitationRef().opacity(1, 0.4);
    yield* waitFor(duration - 0.8);
    yield* sourceCitationRef().opacity(0, 0.4);
    return;
  }

  // Screen Frame effect
  if (screenFrameEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    const frameWidth = width * 0.7;
    const frameHeight = height * 0.7;
    const titleBarHeight = 40;
    const isDark = screenFrameTheme === 'dark';
    const frameBg = isDark ? '#1e293b' : '#ffffff';
    const titleBg = isDark ? '#334155' : '#f1f5f9';
    const textColor = isDark ? '#e2e8f0' : '#1e293b';

    view.add(
      <Rect
        ref={screenFrameRef}
        width={frameWidth}
        height={frameHeight}
        fill={frameBg}
        radius={12}
        opacity={0}
        scale={screenFrameAnimation === 'scale' ? 0.8 : 1}
        y={screenFrameAnimation === 'slide-up' ? 100 : 0}
        clip
      >
        {/* Title bar */}
        <Rect
          ref={screenFrameTitleBarRef}
          y={-frameHeight/2 + titleBarHeight/2}
          width={frameWidth}
          height={titleBarHeight}
          fill={titleBg}
        >
          {/* Traffic lights */}
          <Layout x={-frameWidth/2 + 50} direction="row" gap={8}>
            <Circle size={12} fill="#ef4444" />
            <Circle size={12} fill="#fbbf24" />
            <Circle size={12} fill="#22c55e" />
          </Layout>
          {/* URL or title */}
          <Txt
            text={screenFrameUrl || screenFrameTitle || 'Browser'}
            fontSize={14}
            fill={textColor}
            opacity={0.6}
          />
        </Rect>
        {/* Content */}
        <Txt
          ref={screenFrameContentRef}
          y={titleBarHeight/2}
          text={screenFrameContentText || 'Content'}
          fontSize={24}
          fill={textColor}
          textWrap
          width={frameWidth - 60}
        />
      </Rect>
    );

    // Animate in
    yield* all(
      screenFrameRef().opacity(1, 0.4),
      screenFrameRef().scale(1, 0.4, easeOutCubic),
      screenFrameRef().y(0, 0.4, easeOutCubic),
    );

    yield* waitFor(duration - 0.8);
    yield* screenFrameRef().opacity(0, 0.4);
    return;
  }

  // Audio Waveform effect
  if (audioWaveformEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};

    const barCount = 32;
    const barWidth = 12;
    const barGap = 8;
    const maxBarHeight = 200;
    const totalWidth = barCount * (barWidth + barGap) - barGap;

    // Add bars
    for (let i = 0; i < barCount; i++) {
      const x = -totalWidth/2 + i * (barWidth + barGap) + barWidth/2;
      view.add(
        <Rect
          ref={audioWaveformBarRefs[i]}
          x={x}
          y={0}
          width={barWidth}
          height={20}
          fill={audioWaveformColor}
          radius={barWidth/2}
        />
      );
    }

    // Add label if present
    if (audioWaveformLabel) {
      view.add(
        <Txt
          ref={audioWaveformLabelRef}
          y={maxBarHeight/2 + 40}
          text={audioWaveformLabel}
          fontSize={24}
          fontWeight={600}
          fill={audioWaveformColor}
          opacity={0}
        />
      );
    }

    // Animate waveform
    const animationSteps = Math.floor(duration * 15);
    yield* audioWaveformLabelRef ? audioWaveformLabelRef().opacity(1, 0.3) : waitFor(0);

    for (let step = 0; step < animationSteps; step++) {
      const animations = [];
      for (let i = 0; i < barCount; i++) {
        const phase = (step * 0.3 + i * 0.2) % (Math.PI * 2);
        const height = 20 + Math.abs(Math.sin(phase)) * maxBarHeight * audioWaveformIntensity;
        animations.push(audioWaveformBarRefs[i]().height(height, 0.05));
      }
      yield* all(...animations);
    }

    // Fade out
    for (let i = 0; i < barCount; i++) {
      yield audioWaveformBarRefs[i]().height(20, 0.2);
    }
    yield* waitFor(0.2);
    return;
  }

  // Zoom Blur effect
  if (zoomBlurEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : 2;
    const speedMap: Record<string, number> = { slow: 1.5, medium: 1, fast: 0.5, instant: 0.2 };
    const zoomSpeed = speedMap[zoomBlurSpeed] || 1;

    // Add radial rays for blur effect
    const rayCount = 12;
    for (let i = 0; i < rayCount; i++) {
      const angle = (i / rayCount) * Math.PI * 2;
      const rayLength = width * 0.8;
      view.add(
        <Rect
          ref={zoomBlurRaysRefs[i]}
          x={0}
          y={0}
          width={rayLength}
          height={8 + zoomBlurIntensity * 20}
          fill={'rgba(255, 255, 255, ' + (zoomBlurIntensity * 0.3) + ')'}
          rotation={angle * (180 / Math.PI)}
          opacity={0}
          scale={0.1}
        />
      );
    }

    // Add text if present
    if (zoomBlurText) {
      view.add(
        <Txt
          ref={zoomBlurTextRef}
          text={zoomBlurText}
          fontSize={72}
          fontWeight={700}
          fill={zoomBlurColor}
          opacity={0}
          scale={zoomBlurDirection === 'in' ? 0.5 : 2}
        />
      );
    }

    // Animate zoom blur
    const rayAnimations = zoomBlurRaysRefs.slice(0, rayCount).map((ref, i) =>
      all(
        ref().opacity(zoomBlurIntensity, zoomSpeed * 0.3),
        ref().scale(zoomBlurDirection === 'in' ? 1.5 : 0.5, zoomSpeed, easeOutCubic),
      )
    );
    yield* all(...rayAnimations);

    if (zoomBlurTextRef()) {
      yield* all(
        zoomBlurTextRef().opacity(1, zoomSpeed * 0.5),
        zoomBlurTextRef().scale(1, zoomSpeed * 0.5, easeOutCubic),
      );
    }

    yield* waitFor(duration - zoomSpeed * 1.5);

    // Fade out
    const fadeAnimations = zoomBlurRaysRefs.slice(0, rayCount).map((ref) => ref().opacity(0, 0.3));
    if (zoomBlurTextRef()) fadeAnimations.push(zoomBlurTextRef().opacity(0, 0.3));
    yield* all(...fadeAnimations);
    return;
  }

  // Glitch Transition effect
  if (glitchEffectEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : 3;
    const intensityMap: Record<string, number> = { subtle: 0.3, medium: 0.6, intense: 0.9, chaos: 1.2 };
    const intensity = intensityMap[glitchEffectIntensity] || 0.6;

    // Main text
    view.add(
      <Layout ref={glitchEffectContainerRef} width={width} height={height}>
        {glitchEffectRgbSplit && (
          <>
            <Txt
              ref={glitchEffectRedRef}
              text={glitchEffectText || 'GLITCH'}
              fontSize={96}
              fontWeight={900}
              fill={'#ff0000'}
              opacity={0.7}
              x={-intensity * 5}
            />
            <Txt
              ref={glitchEffectBlueRef}
              text={glitchEffectText || 'GLITCH'}
              fontSize={96}
              fontWeight={900}
              fill={'#00ffff'}
              opacity={0.7}
              x={intensity * 5}
            />
          </>
        )}
        <Txt
          ref={glitchEffectMainRef}
          text={glitchEffectText || 'GLITCH'}
          fontSize={96}
          fontWeight={900}
          fill={glitchEffectColor}
          opacity={0}
        />
        {glitchEffectScanLines && (
          <Rect
            ref={glitchEffectScanLineRef}
            width={width}
            height={4}
            fill={'rgba(255, 255, 255, 0.1)'}
            y={-height/2}
          />
        )}
      </Layout>
    );

    // Animate glitch
    yield* glitchEffectMainRef().opacity(1, 0.1);

    const glitchSteps = Math.floor(duration * 10);
    for (let step = 0; step < glitchSteps; step++) {
      const offset = (Math.random() - 0.5) * intensity * 20;
      const skew = (Math.random() - 0.5) * intensity * 10;

      if (glitchEffectRgbSplit && glitchEffectRedRef() && glitchEffectBlueRef()) {
        yield* all(
          glitchEffectRedRef().x(-intensity * 5 + offset, 0.05),
          glitchEffectBlueRef().x(intensity * 5 - offset, 0.05),
          glitchEffectMainRef().skew([skew, 0], 0.05),
        );
      } else {
        yield* glitchEffectMainRef().x(offset, 0.05);
      }

      if (glitchEffectScanLines && glitchEffectScanLineRef()) {
        yield glitchEffectScanLineRef().y((Math.random() - 0.5) * height, 0.05);
      }

      if (Math.random() < 0.2) {
        yield* glitchEffectMainRef().opacity(0.5, 0.02);
        yield* glitchEffectMainRef().opacity(1, 0.02);
      }
    }

    yield* glitchEffectMainRef().opacity(0, 0.2);
    return;
  }

  // Data Ticker effect
  if (dataTickerEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : 8;
    const speedMap: Record<string, number> = { slow: 80, medium: 150, fast: 250 };
    const scrollSpeed = speedMap[dataTickerSpeed] || 150;
    const tickerHeight = 60;
    const yPos = dataTickerPosition === 'top' ? -height/2 + tickerHeight/2 + 20 : height/2 - tickerHeight/2 - 20;

    // Ticker background
    view.add(
      <Rect
        ref={dataTickerContainerRef}
        x={0}
        y={yPos}
        width={width}
        height={tickerHeight}
        fill={dataTickerBackground}
        opacity={0}
      >
        {dataTickerLabel && (
          <Rect
            x={-width/2 + 80}
            width={150}
            height={tickerHeight}
            fill={'#ef4444'}
          >
            <Txt
              ref={dataTickerLabelRef}
              text={dataTickerLabel}
              fontSize={20}
              fontWeight={700}
              fill={'#ffffff'}
            />
          </Rect>
        )}
        <Layout
          ref={dataTickerScrollRef}
          x={dataTickerLabel ? 100 : 0}
          layout
          direction="row"
          gap={60}
        >
          {dataTickerItems.map((item, i) => (
            <Txt
              key={i}
              ref={dataTickerItemRefs[i]}
              text={(item.icon ? item.icon + ' ' : '') + item.text}
              fontSize={22}
              fontWeight={500}
              fill={item.color || dataTickerTextColor}
            />
          ))}
        </Layout>
      </Rect>
    );

    // Slide in
    yield* dataTickerContainerRef().opacity(1, 0.3);

    // Scroll animation
    const scrollDistance = width * 1.5;
    const scrollDuration = scrollDistance / scrollSpeed;
    const totalScrolls = Math.ceil(duration / scrollDuration);

    for (let s = 0; s < totalScrolls; s++) {
      if (dataTickerScrollRef()) {
        dataTickerScrollRef().x(width/2);
        yield* dataTickerScrollRef().x(-scrollDistance, scrollDuration, linear);
      }
    }

    yield* dataTickerContainerRef().opacity(0, 0.3);
    return;
  }

  // Social Media Post effect
  if (socialPostEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : 5;
    const isDark = socialPostTheme === 'dark';
    const cardBg = isDark ? '#15202b' : '#ffffff';
    const textColor = isDark ? '#ffffff' : '#0f1419';
    const secondaryColor = isDark ? '#8899a6' : '#536471';
    const cardWidth = 500;
    const cardPadding = 20;

    // Twitter-style card
    view.add(
      <Rect
        ref={socialPostContainerRef}
        width={cardWidth}
        height={'auto'}
        fill={cardBg}
        radius={16}
        padding={cardPadding}
        opacity={0}
        scale={socialPostAnimation === 'scale' ? 0.8 : 1}
        y={socialPostAnimation === 'slide-up' ? 100 : 0}
        layout
        direction="column"
        gap={12}
      >
        {/* Header */}
        <Layout layout direction="row" gap={10} alignItems="center">
          <Circle width={48} height={48} fill={socialPostPlatform === 'twitter' ? '#1d9bf0' : '#e4405f'} />
          <Layout layout direction="column" gap={2}>
            <Layout layout direction="row" gap={6} alignItems="center">
              <Txt
                ref={socialPostUsernameRef}
                text={socialPostUsername}
                fontSize={16}
                fontWeight={700}
                fill={textColor}
              />
              {socialPostVerified && (
                <Circle width={16} height={16} fill={'#1d9bf0'} />
              )}
            </Layout>
            <Txt text={socialPostHandle} fontSize={14} fill={secondaryColor} />
          </Layout>
          <Txt text={socialPostTimestamp} fontSize={14} fill={secondaryColor} marginLeft={'auto'} />
        </Layout>

        {/* Content */}
        <Txt
          ref={socialPostContentRef}
          text={socialPostContent}
          fontSize={18}
          fill={textColor}
          width={cardWidth - cardPadding * 2}
          textWrap={true}
        />

        {/* Stats */}
        <Layout ref={socialPostStatsRef} layout direction="row" gap={30} marginTop={12}>
          <Txt text={'\\u{1F4AC} ' + socialPostComments} fontSize={14} fill={secondaryColor} />
          <Txt text={'\\u{1F501} ' + socialPostRetweets} fontSize={14} fill={secondaryColor} />
          <Txt text={'\\u{2764} ' + socialPostLikes} fontSize={14} fill={secondaryColor} />
        </Layout>
      </Rect>
    );

    // Animate in
    if (socialPostAnimation === 'fade') {
      yield* socialPostContainerRef().opacity(1, 0.5);
    } else if (socialPostAnimation === 'slide-up') {
      yield* all(
        socialPostContainerRef().opacity(1, 0.4),
        socialPostContainerRef().y(0, 0.4, easeOutCubic),
      );
    } else if (socialPostAnimation === 'scale') {
      yield* all(
        socialPostContainerRef().opacity(1, 0.4),
        socialPostContainerRef().scale(1, 0.4, easeOutCubic),
      );
    } else {
      socialPostContainerRef().opacity(1);
    }

    yield* waitFor(duration - 0.8);
    yield* socialPostContainerRef().opacity(0, 0.4);
    return;
  }

  // Video Frame Stack effect
  if (frameStackEnabled) {
    const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : 5;
    const frames = frameStackFrames;
    const frameCount = Math.min(frames.length, 12);

    // Calculate grid layout
    const cols = frameStackLayout === 'grid' ? Math.ceil(Math.sqrt(frameCount)) : 1;
    const rows = frameStackLayout === 'grid' ? Math.ceil(frameCount / cols) : frameCount;
    const frameWidth = frameStackLayout === 'grid' ? (width - 200) / cols : 280;
    const frameHeight = frameWidth * 0.5625; // 16:9 ratio
    const gapSize = 20;

    for (let i = 0; i < frameCount; i++) {
      const frame = frames[i];
      const col = i % cols;
      const row = Math.floor(i / cols);

      let xPos = 0, yPos = 0;
      if (frameStackLayout === 'grid') {
        xPos = -((cols - 1) * (frameWidth + gapSize)) / 2 + col * (frameWidth + gapSize);
        yPos = -((rows - 1) * (frameHeight + gapSize)) / 2 + row * (frameHeight + gapSize);
      } else if (frameStackLayout === 'stack') {
        xPos = i * 15;
        yPos = i * 15;
      } else if (frameStackLayout === 'cascade') {
        xPos = (i - frameCount/2) * 80;
        yPos = (i - frameCount/2) * 40;
      } else if (frameStackLayout === 'carousel') {
        const angle = (i / frameCount) * Math.PI * 0.5 - Math.PI * 0.25;
        xPos = Math.sin(angle) * 400;
        yPos = 0;
      }

      const isHighlighted = i === frameStackHighlight;

      view.add(
        <Rect
          ref={frameStackItemRefs[i]}
          x={xPos}
          y={yPos}
          width={frameWidth}
          height={frameHeight}
          fill={frame.color}
          radius={8}
          opacity={0}
          scale={1}
          stroke={isHighlighted ? '#ffffff' : undefined}
          lineWidth={isHighlighted ? 4 : 0}
        />
      );

      // Add title text separately
      view.add(
        <Txt
          ref={frameStackTitleRefs[i]}
          x={xPos}
          y={yPos}
          text={frame.title}
          fontSize={16}
          fontWeight={600}
          fill={'#ffffff'}
          opacity={0}
        />
      );
    }

    // Animate in with stagger
    const staggerDelay = 0.1;
    for (let i = 0; i < frameCount; i++) {
      const rectRef = frameStackItemRefs[i];
      const txtRef = frameStackTitleRefs[i];
      if (!rectRef()) continue;

      yield* all(
        rectRef().opacity(1, 0.3),
        txtRef ? txtRef().opacity(1, 0.3) : waitFor(0),
      );
      yield* waitFor(staggerDelay);
    }

    yield* waitFor(duration - frameCount * staggerDelay - 0.5);

    // Fade out all
    for (let i = 0; i < frameCount; i++) {
      const rectRef = frameStackItemRefs[i];
      const txtRef = frameStackTitleRefs[i];
      if (rectRef()) yield rectRef().opacity(0, 0.3);
      if (txtRef && txtRef()) yield txtRef().opacity(0, 0.3);
    }
    yield* waitFor(0.3);
    return;
  }

  // === NEW EFFECTS END ===

  view.add(
    <Layout
      layout
      width={width}
      height={height}
      padding={80}
      gap={24}
      direction="column"
      alignItems="start"
      justifyContent="start"
    >
      <Txt
        ref={titleRef}
        text={title}
        fontSize={64}
        fontWeight={700}
        fill="#0f172a"
        opacity={0}
      />
      {subtitle ? (
        <Txt
          ref={subtitleRef}
          text={subtitle}
          fontSize={32}
          fontWeight={500}
          fill="#475569"
          opacity={0}
        />
      ) : null}
      {isBarChart && chartEnabled ? (
        <Layout
          layout
          direction="row"
          gap={24}
          alignItems="end"
          justifyContent="start"
          height={chartHeight}
          width={width - 160}
        >
          {chartItems.map((item, index) => (
            <Layout layout direction="column" alignItems="center" gap={12}>
              <Rect
                ref={barRefs[index]}
                width={barWidth}
                height={0}
                fill={chartAccent}
                radius={8}
              />
              <Txt text={item.label} fontSize={24} fontWeight={600} fill="#0f172a" />
            </Layout>
          ))}
        </Layout>
      ) : isLineChart && chartEnabled ? (
        <Layout layout={false} width={lineChartWidth} height={lineChartHeight + 60}>
          {/* Area fill under line */}
          {chartFill ? (
            <Line
              ref={lineFillRef}
              points={[new Vector2(0, lineChartHeight)]}
              fill={chartAccent + '30'}
              closed
              lineWidth={0}
            />
          ) : null}
          {/* Main line */}
          <Line
            ref={lineRef}
            points={[new Vector2(0, lineChartHeight)]}
            stroke={chartAccent}
            lineWidth={4}
            lineCap="round"
            lineJoin="round"
          />
          {/* Data points */}
          {chartShowPoints ? chartItems.map((item, index) => (
            <Circle
              ref={linePointRefs[index]}
              x={index * linePointSpacing}
              y={lineChartHeight - (item.value / maxValue) * lineChartHeight}
              width={0}
              height={0}
              fill={chartAccent}
              stroke="#ffffff"
              lineWidth={3}
            />
          )) : null}
          {/* X-axis labels */}
          {chartItems.map((item, index) => (
            <Txt
              x={index * linePointSpacing}
              y={lineChartHeight + 30}
              text={item.label}
              fontSize={20}
              fontWeight={600}
              fill="#475569"
            />
          ))}
        </Layout>
      ) : isPieChart && chartEnabled ? null : (
        <Layout layout direction="column" gap={16}>
          {safeItems.map((item, index) => (
            <Txt
              ref={itemRefs[index]}
              text={formatItem(item, index)}
              fontSize={36}
              fontWeight={600}
              fill="#0f172a"
              opacity={0}
            />
          ))}
        </Layout>
      )}
    </Layout>
  );

  view.add(
    <Layout layout={false} width={width} height={height}>
      {callouts.map((callout, index) => (
        <Layout ref={calloutGroupRefs[index]} layout={false} opacity={0}>
          <Line
            ref={calloutLineRefs[index]}
            lineWidth={4}
            stroke={callout.color}
            endArrow
            points={[new Vector2(0, 0), new Vector2(0, 0)]}
          />
          <Txt
            ref={calloutLabelRefs[index]}
            text={callout.label}
            fontSize={28}
            fontWeight={600}
            fill={callout.color}
          />
        </Layout>
      ))}
    </Layout>
  );

  // Pie chart layout (separate centered view)
  if (isPieChart && chartEnabled) {
    let cumulativeAngle = -90; // Start from top
    view.add(
      <Layout layout={false} width={width} height={height}>
        {pieItemsWithAngles.map((item, index) => {
          const startAngle = cumulativeAngle;
          const endAngle = cumulativeAngle + item.angle;
          cumulativeAngle = endAngle;
          // Calculate label position at middle of arc
          const midAngle = (startAngle + endAngle) / 2;
          const labelRadius = pieDonut ? pieRadius * 0.78 : pieRadius * 0.65;
          const labelX = width / 2 + Math.cos(midAngle * Math.PI / 180) * labelRadius;
          const labelY = height / 2 + Math.sin(midAngle * Math.PI / 180) * labelRadius;
          return (
            <>
              <Circle
                ref={pieSegmentRefs[index]}
                x={width / 2}
                y={height / 2}
                size={pieRadius * 2}
                startAngle={startAngle}
                endAngle={startAngle}
                closed={!pieDonut}
                fill={pieDonut ? undefined : item.color}
                stroke={pieDonut ? item.color : undefined}
                lineWidth={pieDonut ? pieRadius - pieInnerRadius : 0}
              />
              {pieShowPercentages ? (
                <Txt
                  ref={pieLabelRefs[index]}
                  x={labelX}
                  y={labelY}
                  text={item.percentage.toFixed(1) + '%'}
                  fontSize={24}
                  fontWeight={700}
                  fill={pieDonut ? item.color : '#ffffff'}
                  opacity={0}
                />
              ) : null}
            </>
          );
        })}
      </Layout>
    );
  }

  // Progress staircase chart layout
  if (isProgressStaircase && chartEnabled) {
    // Convert staircase points to Vector2 array
    const arrowPoints = staircasePoints.map(p => new Vector2(p.x, p.y));

    view.add(
      <Layout layout={false} width={width} height={height}>
        {/* Staircase arrow - 3D effect with shadow and gradient */}
        <Line
          points={arrowPoints}
          stroke={staircaseArrowColor}
          lineWidth={50}
          lineCap="round"
          lineJoin="round"
          opacity={0.3}
          offsetY={8}
        />
        <Line
          ref={staircaseArrowRef}
          points={arrowPoints}
          stroke={staircaseArrowColor}
          lineWidth={50}
          lineCap="round"
          lineJoin="round"
          end={0}
        />
        {/* Arrow head at the end */}
        <Layout
          x={staircasePoints[staircasePoints.length - 1]?.x || 0}
          y={staircasePoints[staircasePoints.length - 1]?.y || 0}
          rotation={-45}
          opacity={0}
        >
          <Line
            points={[new Vector2(-30, 20), new Vector2(0, 0), new Vector2(-30, -20)]}
            stroke={staircaseArrowColor}
            lineWidth={50}
            lineCap="round"
            lineJoin="round"
          />
        </Layout>

        {/* Info cards at each step */}
        {staircaseItems.map((item, index) => {
          const pos = staircaseCardPositions[index];
          const cardWidth = 260;
          const cardHeight = item.desc ? 90 : 60;

          return (
            <Layout
              ref={staircaseCardRefs[index]}
              x={pos.x}
              y={pos.y}
              opacity={0}
              scale={0.8}
            >
              {/* Card background with shadow */}
              <Rect
                width={cardWidth}
                height={cardHeight}
                fill={staircaseCardBg}
                radius={12}
                shadowColor="rgba(0,0,0,0.15)"
                shadowBlur={20}
                shadowOffsetY={4}
              />
              {/* Icon circle */}
              <Circle
                x={-cardWidth / 2 + 35}
                y={0}
                size={36}
                fill={staircaseArrowColor + '20'}
                stroke={staircaseArrowColor}
                lineWidth={2}
              />
              {/* Label */}
              <Txt
                x={-cardWidth / 2 + 75}
                y={item.desc ? -15 : 0}
                text={item.label}
                fontSize={20}
                fontWeight={700}
                fill={staircaseLabelColor}
                fontFamily={chartFontFamily}
              />
              {/* Description */}
              {item.desc ? (
                <Txt
                  x={-cardWidth / 2 + 75}
                  y={15}
                  text={item.desc.length > 30 ? item.desc.substring(0, 30) + '...' : item.desc}
                  fontSize={14}
                  fill={staircaseDescColor}
                  fontFamily={chartFontFamily}
                />
              ) : null}
              {/* Value */}
              {item.value !== undefined ? (
                <Txt
                  ref={staircaseValueRefs[index]}
                  x={cardWidth / 2 - 35}
                  y={0}
                  text={'0'}
                  fontSize={28}
                  fontWeight={700}
                  fill={staircaseValueColor}
                  fontFamily={chartFontFamily}
                />
              ) : null}
            </Layout>
          );
        })}
      </Layout>
    );
  }

  if (titleRef()) {
    yield* titleRef().opacity(1, 0.6);
  }
  if (subtitleRef()) {
    yield* subtitleRef().opacity(1, 0.4);
  }
  if (isBarChart && chartEnabled) {
    for (let index = 0; index < barRefs.length; index += 1) {
      const ref = barRefs[index];
      const item = chartItems[index];
      if (ref()) {
        const targetHeight = Math.max(6, (item.value / maxValue) * chartHeight);
        yield* ref().height(targetHeight, 0.4, easeOutCubic);
      }
    }
  } else if (isLineChart && chartEnabled) {
    // Animate line chart: draw line progressively, then pop in points
    const linePoints: Vector2[] = [];
    const fillPoints: Vector2[] = [];
    const pointAnimTime = 0.3;
    const lineAnimTime = 0.25;

    for (let index = 0; index < chartItems.length; index++) {
      const item = chartItems[index];
      const x = index * linePointSpacing;
      const y = lineChartHeight - (item.value / maxValue) * lineChartHeight;
      const point = new Vector2(x, y);
      linePoints.push(point);

      // Update line with new point
      if (lineRef()) {
        yield* lineRef().points(linePoints, lineAnimTime, easeOutCubic);
      }

      // Update fill area (line to bottom and back to start)
      if (chartFill && lineFillRef()) {
        fillPoints.push(point);
        const fillPath = [
          new Vector2(0, lineChartHeight),
          ...fillPoints,
          new Vector2(fillPoints[fillPoints.length - 1].x, lineChartHeight),
        ];
        lineFillRef().points(fillPath);
      }

      // Pop in the data point
      if (chartShowPoints && linePointRefs[index] && linePointRefs[index]()) {
        yield* all(
          linePointRefs[index]().width(16, pointAnimTime, easeOutCubic),
          linePointRefs[index]().height(16, pointAnimTime, easeOutCubic),
        );
      }
    }
  } else if (isPieChart && chartEnabled) {
    // Animate pie chart: each segment grows from start angle to end angle
    let cumulativeAngle = -90; // Start from top
    const segmentAnimTime = 0.4;

    for (let index = 0; index < pieItemsWithAngles.length; index++) {
      const item = pieItemsWithAngles[index];
      const startAngle = cumulativeAngle;
      const endAngle = cumulativeAngle + item.angle;
      cumulativeAngle = endAngle;

      const ref = pieSegmentRefs[index];
      if (ref && ref()) {
        yield* ref().endAngle(endAngle, segmentAnimTime, easeOutCubic);
      }

      // Show percentage label after segment appears
      if (pieShowPercentages && pieLabelRefs[index] && pieLabelRefs[index]()) {
        yield* pieLabelRefs[index]().opacity(1, 0.2);
      }
    }
  } else if (isProgressStaircase && chartEnabled) {
    // Animate progress staircase: draw arrow progressively, reveal cards at each step
    const totalSteps = staircaseItems.length;
    const arrowDrawTime = 0.8; // Time to draw each step of the arrow
    const cardRevealTime = 0.4;
    const valueCountTime = 0.5;

    // Draw arrow progressively, revealing cards as arrow reaches each step
    if (staircaseArrowRef()) {
      for (let step = 0; step < totalSteps; step++) {
        // Calculate progress for this step (each step is a portion of the total path)
        const stepProgress = (step + 1) / totalSteps;

        // Draw arrow to this step
        yield* staircaseArrowRef().end(stepProgress, arrowDrawTime, easeOutCubic);

        // Reveal the card for this step
        const cardRef = staircaseCardRefs[step];
        if (cardRef && cardRef()) {
          yield* all(
            cardRef().opacity(1, cardRevealTime, easeOutCubic),
            cardRef().scale(1, cardRevealTime, easeOutCubic),
          );

          // Animate the value counter if present
          const valueRef = staircaseValueRefs[step];
          const item = staircaseItems[step];
          if (valueRef && valueRef() && item.value !== undefined) {
            const targetValue = item.value;
            // Counter animation
            const steps = 20;
            for (let i = 1; i <= steps; i++) {
              const currentValue = Math.round((i / steps) * targetValue);
              valueRef().text(String(currentValue));
              yield* waitFor(valueCountTime / steps);
            }
          }
        }
      }
    }
  } else {
    for (const ref of itemRefs) {
      if (ref()) {
        yield* ref().opacity(1, 0.25);
      }
    }
  }

  function resolveTargetPosition(callout: { targetType: string; targetIndex: number; x?: number; y?: number }): Vector2 {
    if (typeof callout.x === 'number' && typeof callout.y === 'number') {
      return new Vector2(callout.x, callout.y);
    }
    if (callout.targetType === 'bar' && barRefs[callout.targetIndex] && barRefs[callout.targetIndex]()) {
      return barRefs[callout.targetIndex]().absolutePosition();
    }
    if (callout.targetType === 'item' && itemRefs[callout.targetIndex] && itemRefs[callout.targetIndex]()) {
      return itemRefs[callout.targetIndex]().absolutePosition();
    }
    return new Vector2(0, 0);
  }

  for (let index = 0; index < callouts.length; index += 1) {
    const callout = callouts[index];
    const group = calloutGroupRefs[index]();
    const line = calloutLineRefs[index]();
    const label = calloutLabelRefs[index]();
    if (!group || !line || !label) continue;
    const targetPos = resolveTargetPosition(callout);
    const labelPos = new Vector2(
      typeof callout.x === 'number' ? callout.x + callout.dx : targetPos.x + callout.dx,
      typeof callout.y === 'number' ? callout.y + callout.dy : targetPos.y + callout.dy,
    );
    line.points([targetPos, targetPos]);
    label.position(labelPos);
    yield* all(
      group.opacity(1, 0.2),
      line.points([targetPos, labelPos], 0.45, easeOutCubic),
    );
  }

  const duration = typeof (spec as any).duration === 'number' ? (spec as any).duration : ${DEFAULT_DURATION};
  const intro = chartEnabled
    ? 0.6 + (subtitle ? 0.4 : 0) + chartItems.length * 0.4
    : 0.6 + (subtitle ? 0.4 : 0) + itemRefs.length * 0.25;
  const hold = Math.max(0.2, duration - intro);
  yield* waitFor(hold);
});
`;

  const renderTs = `import project from './project?project';
import { Renderer, Vector2 } from '@motion-canvas/core';
import spec from './spec.json';

const settings = {
  name: (spec as any).outputName || 'motion-canvas',
  range: [0, (spec as any).duration ?? ${DEFAULT_DURATION}],
  fps: (spec as any).fps ?? ${DEFAULT_FPS},
  size: new Vector2((spec as any).width ?? ${DEFAULT_WIDTH}, (spec as any).height ?? ${DEFAULT_HEIGHT}),
  resolutionScale: 1,
  colorSpace: 'srgb',
  background: (spec as any).background ?? '${DEFAULT_BACKGROUND}',
  exporter: {
    name: '@motion-canvas/ffmpeg',
    options: {
      fastStart: true,
      includeAudio: false,
    },
  },
};

const debug = Boolean((spec as any).debug);
const renderer = new Renderer(project);
let finishedResult = null;
renderer.onFinished.subscribe((result) => {
  finishedResult = result;
});

if (debug) {
  project.logger.onLogged.subscribe((entry: any) => {
    const payload = {
      level: entry?.level,
      message: entry?.message,
      stack: entry?.stack,
      remarks: entry?.remarks,
    };
    console.log('Motion Canvas log', payload);
  });

  const exporters = (project as any)?.meta?.rendering?.exporter?.exporters?.map((exp: any) => exp.id);
  console.log('Motion Canvas exporters', exporters);
  console.log('Motion Canvas HMR', Boolean(import.meta.hot));
}

window.addEventListener('error', (event) => {
  const message = event?.message || 'Unknown error';
  (window as any).__renderError = message;
  (window as any).__renderDone = true;
});

window.addEventListener('unhandledrejection', (event) => {
  const message = (event?.reason && event.reason.message) ? event.reason.message : String(event?.reason || 'Unhandled rejection');
  (window as any).__renderError = message;
  (window as any).__renderDone = true;
});

async function run() {
  try {
    if (debug) {
      console.log('Motion Canvas render start', settings);
    }
    await renderer.render(settings);
    (window as any).__renderResult = finishedResult;
    if (finishedResult !== 0) {
      (window as any).__renderError = 'Motion Canvas render failed with code ' + finishedResult;
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (debug) {
      console.error('Motion Canvas render error', message);
    }
    (window as any).__renderError = message;
  } finally {
    (window as any).__renderDone = true;
  }
}

if (!(window as any).__renderStarted) {
  (window as any).__renderStarted = true;
  run();
}
`;

  fs.writeFileSync(path.join(root, 'render.html'), renderHtml, 'utf8');
  fs.writeFileSync(path.join(srcDir, 'project.ts'), projectTs, 'utf8');
  fs.writeFileSync(path.join(scenesDir, 'Main.tsx'), sceneTsx, 'utf8');
  fs.writeFileSync(path.join(srcDir, 'render.ts'), renderTs, 'utf8');
  fs.writeFileSync(path.join(srcDir, 'spec.json'), JSON.stringify(payload, null, 2), 'utf8');
}

function resolveDefault<T>(module: T | { default: T }): T {
  const candidate = module as { default?: T | { default?: T } };
  if (candidate && typeof candidate === 'object' && 'default' in candidate) {
    const first = candidate.default;
    if (first && typeof first === 'object' && 'default' in first) {
      return (first as { default?: T }).default ?? (first as T);
    }
    return first as T;
  }
  return module as T;
}

async function withTimeout<T>(label: string, ms: number, task: Promise<T>): Promise<T> {
  let timeoutId: NodeJS.Timeout | null = null;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Motion Canvas ${label} timed out after ${ms}ms`));
    }, ms);
  });
  try {
    return await Promise.race([task, timeout]);
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
}

export class MotionCanvasEngine implements RenderEngine {
  name = 'motion-canvas';

  async render(spec: RenderSpec, outputDir: string): Promise<RenderResult> {
    const outputName = `motion_canvas_${Date.now()}`;
    const payload = buildPayload(spec, outputName);
    const cacheRoot = path.join(process.cwd(), '.cache', 'motion-canvas');
    ensureDir(cacheRoot);

    const tempRoot = fs.mkdtempSync(path.join(cacheRoot, 'job-'));
    createProjectFiles(tempRoot, payload);

    const outputPath = path.join(outputDir, `${payload.outputName}.mp4`);
    const debugEnabled = payload.debug;
    const debugLogPath = path.join(tempRoot, 'debug.log');
    const logDebug = (message: string): void => {
      if (!debugEnabled) return;
      const line = `[${new Date().toISOString()}] ${message}\n`;
      fs.appendFileSync(debugLogPath, line, 'utf8');
      console.log(`[MotionCanvasEngine] ${message}`);
    };

    let browser: puppeteer.Browser | null = null;
    let server: any = null;

    const consoleMessages: string[] = [];

    try {
      ensureDir(outputDir);
      logDebug(`start render ${outputName}`);
      const projectFile = path.join(tempRoot, 'src', 'project.ts');
      const projectFilePosix = projectFile.split(path.sep).join(path.posix.sep);

      if (debugEnabled) {
        console.log('[MotionCanvasEngine] Debug cache at:', tempRoot);
      }

      const { createServer } = await import('vite');
      const motionCanvas = resolveDefault(await import('@motion-canvas/vite-plugin')) as unknown as (config: {
        project: string;
        output: string;
      }) => unknown;
      const ffmpeg = resolveDefault(await import('@motion-canvas/ffmpeg')) as unknown as () => unknown;

      logDebug('creating vite server');
      server = await withTimeout(
        'vite server creation',
        20000,
        createServer({
        root: tempRoot,
        logLevel: 'error',
        plugins: [
          motionCanvas({
            project: projectFilePosix,
            output: outputDir,
          }) as never,
          ffmpeg() as never,
        ],
        server: {
          host: '127.0.0.1',
          port: 0,
          strictPort: false,
        },
      }),
      );
      await withTimeout('vite server listen', 20000, server.listen());
      logDebug('vite server ready');

      const address = server.httpServer?.address();
      const port =
        typeof address === 'object' && address && 'port' in address ? address.port : server.config.server.port;
      const url = `http://127.0.0.1:${port}/render.html`;

      logDebug('launching puppeteer');
      browser = await withTimeout(
        'puppeteer launch',
        30000,
        puppeteer.launch({
          headless: true,
          args: ['--no-sandbox', '--disable-setuid-sandbox'],
        }),
      );

      const page = await browser.newPage();
      page.on('console', async (msg) => {
        const args = [];
        for (const arg of msg.args()) {
          let value: unknown = '[unserializable]';
          try {
            value = await arg.jsonValue();
          } catch {
            value = '[unserializable]';
          }
          if (value && typeof value === 'object' && Object.keys(value).length === 0) {
            try {
              const messageHandle = await arg.getProperty('message');
              const messageValue = await messageHandle.jsonValue();
              if (typeof messageValue === 'string' && messageValue.trim()) {
                value = { ...value, message: messageValue };
              }
            } catch {
              // ignore message extraction failures
            }
          }
          args.push(value);
        }
        const suffix = args.length ? ` ${JSON.stringify(args)}` : '';
        consoleMessages.push(`[console.${msg.type()}] ${msg.text()}${suffix}`);
      });
      page.on('pageerror', (err) => {
        const message = err instanceof Error ? err.message : String(err);
        consoleMessages.push(`[pageerror] ${message}`);
      });
      page.on('response', (response) => {
        if (response.status() === 404) {
          consoleMessages.push(`[response.404] ${response.url()}`);
        }
      });
      page.on('requestfailed', (request) => {
        const failure = request.failure();
        const reason = failure ? failure.errorText : 'unknown';
        consoleMessages.push(`[requestfailed] ${request.url()} (${reason})`);
      });

      logDebug(`navigating ${url}`);
      await withTimeout('page navigation', 30000, page.goto(url, { waitUntil: 'domcontentloaded' }));
      logDebug('page loaded');
      const startTimeoutMs = 15000;
      try {
        await withTimeout(
          'render start',
          startTimeoutMs,
          page.waitForFunction(() => (window as any).__renderStarted === true, { timeout: 0 }),
        );
        logDebug('render started');
      } catch {
        const details = debugEnabled && consoleMessages.length ? `\n${consoleMessages.join('\n')}` : '';
        throw new Error(`Motion Canvas renderer did not start.${details}`);
      }

      const renderTimeoutMs = Math.max(60000, payload.duration * 1000 * 10);
      try {
        await withTimeout(
          'render completion',
          renderTimeoutMs,
          page.waitForFunction(() => (window as any).__renderDone === true, { timeout: 0 }),
        );
        logDebug('render completed');
      } catch {
        const details = debugEnabled && consoleMessages.length ? `\n${consoleMessages.join('\n')}` : '';
        throw new Error(`Motion Canvas render timed out after ${renderTimeoutMs}ms.${details}`);
      }

      const renderError = await page.evaluate(() => (window as any).__renderError);
      if (renderError) {
        const details = debugEnabled && consoleMessages.length ? `\n${consoleMessages.join('\n')}` : '';
        throw new Error(`${renderError}${details}`);
      }

      if (!fs.existsSync(outputPath)) {
        logDebug(`output missing at ${outputPath}`);
        throw new Error('Motion Canvas render did not produce an output file.');
      }

      logDebug(`output ready ${outputPath}`);
      return {
        success: true,
        outputPath,
      };
    } catch (error) {
      const debugDetails =
        debugEnabled && consoleMessages.length ? `\n${consoleMessages.join('\n')}` : '';
      const message = error instanceof Error ? error.message : 'Unknown error';
      return {
        success: false,
        error: `${message}${debugDetails}`,
      };
    } finally {
      if (browser) {
        await browser.close();
      }
      if (server) {
        await server.close();
      }
      if (!debugEnabled) {
        fs.rmSync(tempRoot, { recursive: true, force: true });
      }
    }
  }
}
