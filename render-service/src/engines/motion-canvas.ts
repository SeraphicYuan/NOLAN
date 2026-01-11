import * as fs from 'fs';
import * as path from 'path';
import puppeteer from 'puppeteer';
import type { RenderSpec } from '../jobs/types.js';
import { RenderEngine, RenderResult } from './types.js';

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

function ensureDir(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
}

function toNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function toString(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim().length > 0 ? value : fallback;
}

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
  switch (theme.toLowerCase()) {
    case 'dark':
      return '#0b1120';
    case 'warm':
      return '#fff7ed';
    case 'cool':
      return '#f8fafc';
    default:
      return DEFAULT_BACKGROUND;
  }
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

  const sceneTsx = `import { Layout, Line, Rect, Txt, makeScene2D } from '@motion-canvas/2d';
import { Vector2, all, createRef, waitFor, easeOutCubic } from '@motion-canvas/core';
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
const chartEnabled = chartType === 'bar' && chartItems.length > 0;
const chartAccent = chart && typeof chart.color === 'string' ? chart.color : '#2563eb';
const chartHeight = Math.min(420, height * 0.45);
const barCount = chartItems.length || 1;
const barWidth = Math.max(48, Math.floor((width - 240) / barCount) - 12);
const maxValue = chart && typeof chart.max === 'number'
  ? Math.max(chart.max, 1)
  : Math.max(1, ...chartItems.map((item) => item.value));
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

const titleRef = createRef<Txt>();
const subtitleRef = createRef<Txt>();
const itemRefs = safeItems.map(() => createRef<Txt>());
const barRefs = chartItems.map(() => createRef<Rect>());
const kineticRef = createRef<Txt>();
const calloutGroupRefs = callouts.map(() => createRef<Layout>());
const calloutLineRefs = callouts.map(() => createRef<Line>());
const calloutLabelRefs = callouts.map(() => createRef<Txt>());

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

  if (kineticEnabled) {
    view.add(
      <Layout layout width={width} height={height} alignItems="center" justifyContent="center">
        <Txt
          ref={kineticRef}
          text=""
          fontSize={kineticSize}
          fontWeight={700}
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
      {chartEnabled ? (
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
      ) : (
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

  if (titleRef()) {
    yield* titleRef().opacity(1, 0.6);
  }
  if (subtitleRef()) {
    yield* subtitleRef().opacity(1, 0.4);
  }
  if (chartEnabled) {
    for (let index = 0; index < barRefs.length; index += 1) {
      const ref = barRefs[index];
      const item = chartItems[index];
      if (ref()) {
        const targetHeight = Math.max(6, (item.value / maxValue) * chartHeight);
        yield* ref().height(targetHeight, 0.4, easeOutCubic);
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
          }),
          ffmpeg(),
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
