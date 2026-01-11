// render-service/src/routes/health.ts
import { Router } from 'express';

const router = Router();

router.get('/', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    engines: ['infographic', 'motion-canvas', 'remotion']
  });
});

export default router;
