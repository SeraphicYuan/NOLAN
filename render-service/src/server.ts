// render-service/src/server.ts
import express from 'express';
import cors from 'cors';
import healthRouter from './routes/health.js';
import renderRouter from './routes/render.js';
import effectsRouter from './routes/effects.js';
import stylesRouter from './routes/styles.js';
import { startProcessor } from './jobs/processor.js';

const app = express();
const PORT = process.env.PORT || 3010;

process.on('unhandledRejection', (reason) => {
  console.error('[RenderService] Unhandled rejection:', reason);
});

process.on('uncaughtException', (error) => {
  console.error('[RenderService] Uncaught exception:', error);
});

app.use(cors());
app.use(express.json());

// Routes
app.use('/health', healthRouter);
app.use('/render', renderRouter);
app.use('/effects', effectsRouter);
app.use('/styles', stylesRouter);

// Start job processor
startProcessor();
console.log('Job processor started');

app.listen(PORT, () => {
  console.log(`Render service running on http://localhost:${PORT}`);
});

export default app;
