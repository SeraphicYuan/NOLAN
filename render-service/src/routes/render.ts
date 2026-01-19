// render-service/src/routes/render.ts
import { Router } from 'express';
import { jobQueue } from '../jobs/queue.js';
import { RenderSpec } from '../jobs/types.js';
import { hasEffect, transformToEngineData } from '../effects/index.js';
import {
  resolveLayout,
  isLayoutTemplate,
  getLayoutTemplates,
  getTemplateRegions,
  TEMPLATES,
  type LayoutSpec,
} from '../layout/index.js';

const router = Router();

// POST /render - Submit a new render job
// Supports two formats:
// 1. Effect-based: { effect: "image-ken-burns", params: { ... }, layout?: "center" | {...} }
// 2. Direct engine: { engine: "remotion", data: { ... } }
router.post('/', (req, res) => {
  const body = req.body;

  // Check if this is an effect-based request
  if (body.effect) {
    const effectId = body.effect as string;
    const params = body.params || {};
    const layout = body.layout as LayoutSpec | undefined;

    if (!hasEffect(effectId)) {
      return res.status(400).json({ error: `Unknown effect: ${effectId}` });
    }

    const transformed = transformToEngineData(effectId, params);
    if (!transformed) {
      return res.status(500).json({ error: 'Failed to transform effect params' });
    }

    // Add layout to engine data if specified
    const engineData = {
      ...transformed.data,
      ...(layout ? { layout } : {}),
    };

    const spec: RenderSpec = {
      engine: transformed.engine as 'remotion' | 'motion-canvas' | 'infographic',
      data: engineData,
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
      layout: layout || 'center',
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

// GET /render/layouts - List available layout templates
router.get('/layouts', (req, res) => {
  const templates = getLayoutTemplates();

  res.json({
    templates: templates.map((name) => ({
      name,
      regions: getTemplateRegions(name),
      definition: TEMPLATES[name],
    })),
  });
});

export default router;
