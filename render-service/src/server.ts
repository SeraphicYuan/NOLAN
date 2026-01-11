// render-service/src/server.ts
import express from 'express';
import cors from 'cors';
import healthRouter from './routes/health';
import renderRouter from './routes/render';

const app = express();
const PORT = process.env.PORT || 3010;

app.use(cors());
app.use(express.json());

// Routes
app.use('/health', healthRouter);
app.use('/render', renderRouter);

app.listen(PORT, () => {
  console.log(`Render service running on http://localhost:${PORT}`);
});

export default app;
