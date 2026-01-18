// render-service/src/routes/effects.ts
import { Router } from 'express';
import {
  getAllEffects,
  getEffectsByCategory,
  getEffectInfo,
  categories,
  transformToEngineData,
  hasEffect,
} from '../effects/index.js';
import type { EffectCategory } from '../effects/index.js';
import { jobQueue } from '../jobs/queue.js';

const router = Router();

// GET /effects - List all effects
router.get('/', (req, res) => {
  const categoryFilter = req.query.category as string | undefined;

  let effects;
  if (categoryFilter && categories.includes(categoryFilter as EffectCategory)) {
    effects = getEffectsByCategory(categoryFilter as EffectCategory);
  } else {
    effects = getAllEffects();
  }

  res.json({
    effects,
    categories,
  });
});

// GET /effects/categories - List all categories
router.get('/categories', (_req, res) => {
  res.json({ categories });
});

// GET /effects/:id - Get specific effect details
router.get('/:id', (req, res) => {
  const effect = getEffectInfo(req.params.id);

  if (!effect) {
    return res.status(404).json({ error: 'Effect not found' });
  }

  res.json(effect);
});

// POST /effects/:id/render - Render using a specific effect
router.post('/:id/render', (req, res) => {
  const effectId = req.params.id;
  const params = req.body.params || req.body;

  if (!hasEffect(effectId)) {
    return res.status(404).json({ error: `Effect not found: ${effectId}` });
  }

  // Transform effect params to engine data
  const transformed = transformToEngineData(effectId, params);
  if (!transformed) {
    return res.status(500).json({ error: 'Failed to transform effect params' });
  }

  // Create render job with transformed data
  const job = jobQueue.createJob({
    engine: transformed.engine as 'remotion' | 'motion-canvas' | 'infographic',
    data: transformed.data,
    // Pass through optional fields if provided
    width: params.width,
    height: params.height,
    duration: params.duration,
  });

  res.status(202).json({
    job_id: job.id,
    status: job.status,
    effect: effectId,
    engine: transformed.engine,
    poll_url: `/render/status/${job.id}`,
  });
});

export default router;
