// render-service/src/routes/render.ts
import { Router } from 'express';
import { jobQueue } from '../jobs/queue.js';
import { RenderSpec } from '../jobs/types.js';

const router = Router();

// POST /render - Submit a new render job
router.post('/', (req, res) => {
  const spec: RenderSpec = req.body;

  if (!spec.engine) {
    return res.status(400).json({ error: 'engine is required' });
  }

  if (!spec.data) {
    return res.status(400).json({ error: 'data is required' });
  }

  const job = jobQueue.createJob(spec);

  // TODO: Actually start rendering (Phase 2)
  // For now, just create the job

  res.status(202).json({
    job_id: job.id,
    status: job.status,
    poll_url: `/render/status/${job.id}`
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
