// render-service/src/routes/render.ts
import { Router } from 'express';
import { jobQueue } from '../jobs/queue.js';
import { RenderSpec } from '../jobs/types.js';
import { hasEffect, transformToEngineData } from '../effects/index.js';

const router = Router();

// POST /render - Submit a new render job
// Supports two formats:
// 1. Effect-based: { effect: "image-ken-burns", params: { ... } }
// 2. Direct engine: { engine: "remotion", data: { ... } }
router.post('/', (req, res) => {
  const body = req.body;

  // Check if this is an effect-based request
  if (body.effect) {
    const effectId = body.effect as string;
    const params = body.params || {};

    if (!hasEffect(effectId)) {
      return res.status(400).json({ error: `Unknown effect: ${effectId}` });
    }

    const transformed = transformToEngineData(effectId, params);
    if (!transformed) {
      return res.status(500).json({ error: 'Failed to transform effect params' });
    }

    const spec: RenderSpec = {
      engine: transformed.engine as 'remotion' | 'motion-canvas' | 'infographic',
      data: transformed.data,
      width: body.width,
      height: body.height,
      duration: body.duration,
    };

    const job = jobQueue.createJob(spec);

    return res.status(202).json({
      job_id: job.id,
      status: job.status,
      effect: effectId,
      engine: transformed.engine,
      poll_url: `/render/status/${job.id}`,
    });
  }

  // Direct engine format (original behavior)
  const spec: RenderSpec = body;

  if (!spec.engine) {
    return res.status(400).json({ error: 'engine is required' });
  }

  if (!spec.data) {
    return res.status(400).json({ error: 'data is required' });
  }

  const job = jobQueue.createJob(spec);

  res.status(202).json({
    job_id: job.id,
    status: job.status,
    poll_url: `/render/status/${job.id}`,
  });
});

// GET /render/status/:id - Check job status
router.get('/status/:id', (req, res) => {
  const job = jobQueue.getJob(req.params.id);

  if (!job) {
    return res.status(404).json({ error: 'Job not found' });
  }

  res.json({
    job_id: job.id,
    status: job.status,
    progress: job.progress,
    error: job.error
  });
});

// GET /render/result/:id - Get completed video
router.get('/result/:id', (req, res) => {
  const job = jobQueue.getJob(req.params.id);

  if (!job) {
    return res.status(404).json({ error: 'Job not found' });
  }

  if (job.status !== 'done') {
    return res.status(400).json({
      error: 'Job not complete',
      status: job.status
    });
  }

  res.json({
    job_id: job.id,
    video_path: job.videoPath
  });
});

// DELETE /render/job/:id - Cancel/cleanup job
router.delete('/job/:id', (req, res) => {
  const deleted = jobQueue.deleteJob(req.params.id);

  if (!deleted) {
    return res.status(404).json({ error: 'Job not found' });
  }

  res.json({ deleted: true });
});

export default router;
