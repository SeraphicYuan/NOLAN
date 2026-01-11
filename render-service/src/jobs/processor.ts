// render-service/src/jobs/processor.ts
import * as path from 'path';
import { jobQueue } from './queue.js';
import { RenderJob } from './types.js';
import { InfographicEngine } from '../engines/infographic.js';
import { MotionCanvasEngine } from '../engines/motion-canvas.js';
import { RemotionEngine } from '../engines/remotion.js';
import { RenderEngine } from '../engines/types.js';

const OUTPUT_DIR = path.join(process.cwd(), 'output');

const engines: Record<string, RenderEngine> = {
  infographic: new InfographicEngine(),
  'motion-canvas': new MotionCanvasEngine(),
  remotion: new RemotionEngine(),
};

export async function processJob(job: RenderJob): Promise<void> {
  const { spec } = job;

  // Update status to rendering
  jobQueue.updateJob(job.id, { status: 'rendering', progress: 0.1 });

  const engine = engines[spec.engine];
  if (!engine) {
    jobQueue.updateJob(job.id, {
      status: 'error',
      error: `Unknown engine: ${spec.engine}`
    });
    return;
  }

  jobQueue.updateJob(job.id, { progress: 0.3 });

  console.log('[Processor] Calling engine.render() for engine:', engine.name);
  let result;
  try {
    result = await engine.render(spec, OUTPUT_DIR);
    console.log('[Processor] engine.render() returned:', result);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('[Processor] engine.render() threw:', message);
    jobQueue.updateJob(job.id, {
      status: 'error',
      error: message,
    });
    return;
  }

  if (result.success) {
    jobQueue.updateJob(job.id, {
      status: 'done',
      progress: 1.0,
      videoPath: result.outputPath,
      completedAt: new Date()
    });
  } else {
    jobQueue.updateJob(job.id, {
      status: 'error',
      error: result.error
    });
  }
}

export function startProcessor(): void {
  // Simple polling processor - check for pending jobs every second
  setInterval(async () => {
    const jobs = jobQueue.listJobs();
    const pending = jobs.filter(j => j.status === 'pending');

    for (const job of pending) {
      await processJob(job);
    }
  }, 1000);
}
