# Infographic & Animation Render Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a TypeScript microservice that renders animated infographics and returns MP4 videos, callable from NOLAN via HTTP API.

**Architecture:** Express server with async job queue. Three rendering engines (@antv/infographic, Motion Canvas, Remotion) unified under a single API. NOLAN submits render jobs, polls for status, retrieves completed videos.

**Tech Stack:** Node.js 18+, TypeScript, Express, @antv/infographic, @motion-canvas/core, Remotion, JSDOM (for infographic DOM), Bull (job queue), Redis (optional, can use in-memory)

---

## Progress Notes (2026-01-11)

- Motion Canvas and Remotion engines implemented and working (full render paths, not placeholders).
- Remotion gained a "audio_markers_only" mode: run FFmpeg `silencedetect` + FFprobe to output JSON markers without rendering video.
- Audio markers JSON generated for `D:\Animation\Proj4_YT_Vid3\voiceover.mp3` at `render-service\output\audio_markers_1768150924904.json`.
  - Parameters used: `silence_threshold_db=-35`, `min_silence_ms=400`.
  - Output contains `duration_seconds`, `silences`, and `markers_seconds` arrays.
- Motion Canvas chart build implemented (bar chart). `data.chart` now supports `{ type: "bar", color, items[] }` and animates bars.
  - Output: `render-service\output\motion_canvas_1768153937368.mp4`.
  - Fixed Vite/esbuild mismatch by pinning `esbuild@0.25.0` and adding overrides in `render-service\package.json`.
- Motion Canvas kinetic typography + callout annotations added.
  - Kinetic example output: `render-service\output\motion_canvas_1768154528121.mp4`.
  - Callout example output: `render-service\output\motion_canvas_1768154570146.mp4`.
- Remotion image focus now supports `image_focus.bbox` in addition to `x/y` and `zoom_from/zoom_to`.
- Infographic engine gained template inference, theme packs (`brand-*`, `docu-*`), and SVG+PNG export.
  - SVG+PNG example: `render-service\output\infographic_1768155117266.svg` and `render-service\output\infographic_1768155117266.png`.
- Added theme preset support via `theme_config_ref` (example: `docu-dark-minimal`) to avoid embedding full theme config in `scene_plan.json`.
- `render-infographics` now requests SVG+PNG and stores `infographic_asset_png` for viewer previews.
- Added a high-value AntV template registry to the scene design prompt so Gemini picks from a curated list.
- Added optional AntV icon resolution (items can include `icon_keyword`; resolver maps to icon names at render time).
- Added comparison item shaping for AntV compare templates (flat items -> left/right children buckets).
- Added `docu-warm-soft` theme preset and theme config refs (`theme_config_ref`) in scene specs.
- Added PNG preview support and viewer uses PNG when available (avoids SVG foreignObject text issues).
- Motion Canvas explainer references: `https://motioncanvas.io/showcase` and `https://motioncanvas.io/docs` (examples repo: `https://github.com/motion-canvas/examples`).
- Remotion overlays extended for chapters + progress bar + quotes.
  - Chapter/progress output: `render-service\output\remotion_1768156194897.mp4`.
  - Quote callout output: `render-service\output\remotion_1768156234688.mp4`.
- Remotion CSV overlay (data table) + map flyover scenes added.
  - CSV overlay output: `render-service\output\remotion_1768156281696.mp4` (CSV at `render-service\output\sample_data.csv`).
  - Map flyover output: `render-service\output\remotion_1768156338176.mp4` (map asset `render-service\output\map_stub.svg`).

---

## Implementation Notes (Current State)

### Motion Canvas
- Bar chart build via `data.chart` with animated heights.
- Kinetic typography via `data.kinetic` (phrases, size, color).
- Callout annotations via `data.callouts` (arrow + label pointing to bars/items or explicit x/y).

### Remotion
- Chapter cards + progress bar overlay via `data.chapters` and `data.progress_bar`.
- Quote callouts via `data.quotes`.
- CSV overlay via `data.csv_path` → parsed into `data.csv_table`.
- Map flyover via `data.map_image_path` + `data.map_points` (pan/zoom).
- Image focus supports `image_focus.bbox` (normalized [x,y,w,h]) or `image_focus.x/y`.

### Infographic
- Template inference from data shape or `template_type`.
- Theme packs (`brand-*`, `docu-*`, plus default/warm/cool/dark).
- Export formats: SVG (default) and PNG with `output_formats` or `export_png`.

### Build Fixes
- Motion Canvas/Vite esbuild mismatch fixed by pinning `esbuild@0.25.0` and overrides in `render-service/package.json`.

---

## Usage Cheatsheet

### Motion Canvas: bar chart
```
{
  "engine": "motion-canvas",
  "data": {
    "title": "Funding Growth",
    "subtitle": "Quarterly revenue",
    "duration": 6,
    "chart": {
      "type": "bar",
      "color": "#0ea5e9",
      "items": [
        {"label": "Q1", "value": 12},
        {"label": "Q2", "value": 24}
      ]
    }
  }
}
```

### Motion Canvas: kinetic typography
```
{
  "engine": "motion-canvas",
  "data": {
    "duration": 6,
    "kinetic": {
      "color": "#0f172a",
      "size": 96,
      "phrases": [
        {"text": "The real story", "hold": 0.7},
        {"text": "is in the data", "hold": 0.7}
      ]
    }
  }
}
```

### Motion Canvas: callouts
```
{
  "engine": "motion-canvas",
  "data": {
    "title": "Funding Growth",
    "chart": {
      "type": "bar",
      "items": [
        {"label": "Q1", "value": 12},
        {"label": "Q2", "value": 24}
      ]
    },
    "callouts": [
      {"label": "Peak quarter", "target_type": "bar", "target_index": 1, "dx": 160, "dy": -140, "color": "#ef4444"}
    ]
  }
}
```

### Remotion: chapters + progress bar
```
{
  "engine": "remotion",
  "data": {
    "duration": 6,
    "chapters": [
      {"title": "Chapter 1", "subtitle": "Context", "start": 0, "duration": 2.4},
      {"title": "Chapter 2", "subtitle": "Evidence", "start": 2.4, "duration": 2.4}
    ],
    "progress_bar": {"show": true, "color": "#0ea5e9", "height": 8, "margin": 40}
  }
}
```

### Remotion: quote callout
```
{
  "engine": "remotion",
  "data": {
    "duration": 6,
    "quotes": [
      {"text": "The real risk is the second-order effect.", "author": "Analyst", "start": 1.2, "duration": 2.5}
    ]
  }
}
```

### Remotion: CSV overlay
```
{
  "engine": "remotion",
  "data": {
    "duration": 6,
    "csv_path": "D:\\\\ClaudeProjects\\\\NOLAN\\\\render-service\\\\output\\\\sample_data.csv"
  }
}
```

### Remotion: map flyover
```
{
  "engine": "remotion",
  "data": {
    "duration": 6,
    "map_image_path": "D:\\\\ClaudeProjects\\\\NOLAN\\\\render-service\\\\output\\\\map_stub.svg",
    "map_points": [
      {"x": 0.35, "y": 0.35, "zoom": 1.05},
      {"x": 0.55, "y": 0.45, "zoom": 1.2}
    ]
  }
}
```

### Infographic: template inference + SVG/PNG
```
{
  "engine": "infographic",
  "data": {
    "title": "Roadmap",
    "template_type": "timeline",
    "palette": "docu-amber",
    "output_formats": ["svg", "png"],
    "items": [
      {"label": "Research", "desc": "Collect sources"},
      {"label": "Analysis", "desc": "Extract insights"}
    ]
  }
}
```

### TODO (next)
- Add a rerun path that lets us tweak `silence_threshold_db` / `min_silence_ms` quickly and regenerate markers.
- Use audio markers to auto-split a Remotion timeline into segments.
- Add scene timing from script beats.

### Current list (video essay additions)
- Chapter cards + progress bar (Remotion overlay)
- Quote callouts (Remotion overlay)
- CSV data overlays (Remotion)
- Maps/geo flyovers (Remotion, image-based)

---

## Phase 1: Project Setup & Basic Server

### Task 1: Initialize TypeScript Project

**Files:**
- Create: `render-service/package.json`
- Create: `render-service/tsconfig.json`
- Create: `render-service/.gitignore`

**Step 1: Create render-service directory and initialize npm**

```bash
cd D:\ClaudeProjects\NOLAN
mkdir render-service
cd render-service
npm init -y
```

**Step 2: Install core dependencies**

```bash
npm install express cors uuid
npm install -D typescript @types/node @types/express @types/cors @types/uuid ts-node nodemon
```

**Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

**Step 4: Create .gitignore**

```
node_modules/
dist/
*.log
.env
output/
```

**Step 5: Update package.json scripts**

```json
{
  "scripts": {
    "dev": "nodemon --exec ts-node src/server.ts",
    "build": "tsc",
    "start": "node dist/server.js",
    "test": "jest"
  }
}
```

**Step 6: Commit**

```bash
git add render-service/
git commit -m "feat(render-service): initialize TypeScript project"
```

---

### Task 2: Create Basic Express Server with Health Check

**Files:**
- Create: `render-service/src/server.ts`
- Create: `render-service/src/routes/health.ts`

**Step 1: Create health route**

```typescript
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
```

**Step 2: Create main server file**

```typescript
// render-service/src/server.ts
import express from 'express';
import cors from 'cors';
import healthRouter from './routes/health';

const app = express();
const PORT = process.env.PORT || 3010;

app.use(cors());
app.use(express.json());

// Routes
app.use('/health', healthRouter);

app.listen(PORT, () => {
  console.log(`Render service running on http://localhost:${PORT}`);
});

export default app;
```

**Step 3: Test manually**

```bash
cd render-service
npm run dev
# In another terminal:
curl http://localhost:3010/health
# Expected: {"status":"ok","timestamp":"...","engines":["infographic","motion-canvas","remotion"]}
```

**Step 4: Commit**

```bash
git add render-service/src/
git commit -m "feat(render-service): add Express server with health endpoint"
```

---

### Task 3: Implement Job Queue (In-Memory)

**Files:**
- Create: `render-service/src/jobs/queue.ts`
- Create: `render-service/src/jobs/types.ts`

**Step 1: Define job types**

```typescript
// render-service/src/jobs/types.ts
export type JobStatus = 'pending' | 'rendering' | 'done' | 'error';

export type Engine = 'infographic' | 'motion-canvas' | 'remotion';

export interface RenderSpec {
  engine: Engine;
  template?: string;
  data: Record<string, unknown>;
  duration?: number;
  audio?: string;
  style_prompt?: string;
}

export interface RenderJob {
  id: string;
  spec: RenderSpec;
  status: JobStatus;
  progress: number;
  createdAt: Date;
  completedAt?: Date;
  videoPath?: string;
  error?: string;
}
```

**Step 2: Create job queue manager**

```typescript
// render-service/src/jobs/queue.ts
import { v4 as uuidv4 } from 'uuid';
import { RenderJob, RenderSpec, JobStatus } from './types';

class JobQueue {
  private jobs: Map<string, RenderJob> = new Map();

  createJob(spec: RenderSpec): RenderJob {
    const job: RenderJob = {
      id: uuidv4(),
      spec,
      status: 'pending',
      progress: 0,
      createdAt: new Date(),
    };
    this.jobs.set(job.id, job);
    return job;
  }

  getJob(id: string): RenderJob | undefined {
    return this.jobs.get(id);
  }

  updateJob(id: string, updates: Partial<RenderJob>): RenderJob | undefined {
    const job = this.jobs.get(id);
    if (!job) return undefined;

    const updated = { ...job, ...updates };
    this.jobs.set(id, updated);
    return updated;
  }

  deleteJob(id: string): boolean {
    return this.jobs.delete(id);
  }

  listJobs(): RenderJob[] {
    return Array.from(this.jobs.values());
  }
}

export const jobQueue = new JobQueue();
```

**Step 3: Commit**

```bash
git add render-service/src/jobs/
git commit -m "feat(render-service): add in-memory job queue"
```

---

### Task 4: Implement Render API Routes

**Files:**
- Create: `render-service/src/routes/render.ts`
- Modify: `render-service/src/server.ts`

**Step 1: Create render routes**

```typescript
// render-service/src/routes/render.ts
import { Router } from 'express';
import { jobQueue } from '../jobs/queue';
import { RenderSpec } from '../jobs/types';

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
```

**Step 2: Add route to server**

```typescript
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
```

**Step 3: Test API manually**

```bash
# Submit job
curl -X POST http://localhost:3010/render \
  -H "Content-Type: application/json" \
  -d '{"engine":"infographic","data":{"items":[1,2,3]}}'
# Expected: {"job_id":"...","status":"pending","poll_url":"/render/status/..."}

# Check status
curl http://localhost:3010/render/status/<job_id>
# Expected: {"job_id":"...","status":"pending","progress":0}
```

**Step 4: Commit**

```bash
git add render-service/src/
git commit -m "feat(render-service): add render API routes (submit, status, result, delete)"
```

---

## Phase 2: Python Client in NOLAN

### Task 5: Create InfographicClient in NOLAN

**Files:**
- Create: `src/nolan/infographic_client.py`

**Step 1: Create the client**

```python
# src/nolan/infographic_client.py
"""Client for the Infographic & Animation Render Service."""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import httpx


class Engine(str, Enum):
    INFOGRAPHIC = "infographic"
    MOTION_CANVAS = "motion-canvas"
    REMOTION = "remotion"


class JobStatus(str, Enum):
    PENDING = "pending"
    RENDERING = "rendering"
    DONE = "done"
    ERROR = "error"


@dataclass
class RenderJob:
    """Represents a render job."""
    job_id: str
    status: JobStatus
    progress: float = 0.0
    video_path: Optional[str] = None
    error: Optional[str] = None


class InfographicClient:
    """Client for the Infographic & Animation Render Service."""

    def __init__(self, host: str = "127.0.0.1", port: int = 3010):
        """Initialize client.

        Args:
            host: Service host.
            port: Service port.
        """
        self.base_url = f"http://{host}:{port}"
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def health_check(self) -> bool:
        """Check if service is running."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def submit(
        self,
        engine: Engine,
        data: Dict[str, Any],
        template: Optional[str] = None,
        duration: Optional[float] = None,
        audio: Optional[str] = None,
        style_prompt: Optional[str] = None,
    ) -> RenderJob:
        """Submit a render job.

        Args:
            engine: Rendering engine to use.
            data: Data for the infographic.
            template: Template name (optional, LLM selects if not provided).
            duration: Duration in seconds.
            audio: Path to audio file for sync.
            style_prompt: Style customization prompt.

        Returns:
            RenderJob with job_id and initial status.
        """
        payload = {
            "engine": engine.value,
            "data": data,
        }
        if template:
            payload["template"] = template
        if duration:
            payload["duration"] = duration
        if audio:
            payload["audio"] = audio
        if style_prompt:
            payload["style_prompt"] = style_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/render",
                json=payload
            )
            response.raise_for_status()
            result = response.json()

        return RenderJob(
            job_id=result["job_id"],
            status=JobStatus(result["status"])
        )

    async def get_status(self, job_id: str) -> RenderJob:
        """Get job status.

        Args:
            job_id: The job ID.

        Returns:
            RenderJob with current status.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/render/status/{job_id}")
            response.raise_for_status()
            result = response.json()

        return RenderJob(
            job_id=result["job_id"],
            status=JobStatus(result["status"]),
            progress=result.get("progress", 0.0),
            error=result.get("error")
        )

    async def get_result(self, job_id: str) -> RenderJob:
        """Get completed job result.

        Args:
            job_id: The job ID.

        Returns:
            RenderJob with video_path.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/render/result/{job_id}")
            response.raise_for_status()
            result = response.json()

        return RenderJob(
            job_id=result["job_id"],
            status=JobStatus.DONE,
            video_path=result.get("video_path")
        )

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
        progress_callback: Optional[callable] = None
    ) -> RenderJob:
        """Wait for job to complete.

        Args:
            job_id: The job ID.
            poll_interval: Seconds between status checks.
            timeout: Maximum wait time in seconds.
            progress_callback: Optional callback(progress: float).

        Returns:
            Completed RenderJob.

        Raises:
            TimeoutError: If job doesn't complete in time.
            RuntimeError: If job fails.
        """
        elapsed = 0.0

        while elapsed < timeout:
            job = await self.get_status(job_id)

            if progress_callback:
                progress_callback(job.progress)

            if job.status == JobStatus.DONE:
                return await self.get_result(job_id)

            if job.status == JobStatus.ERROR:
                raise RuntimeError(f"Render failed: {job.error}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    async def render(
        self,
        engine: Engine,
        data: Dict[str, Any],
        **kwargs
    ) -> Path:
        """Submit job and wait for completion.

        Convenience method that combines submit + wait.

        Returns:
            Path to the rendered video.
        """
        job = await self.submit(engine, data, **kwargs)
        completed = await self.wait_for_completion(
            job.job_id,
            progress_callback=kwargs.get("progress_callback")
        )
        return Path(completed.video_path)
```

**Step 2: Commit**

```bash
git add src/nolan/infographic_client.py
git commit -m "feat: add InfographicClient for render service"
```

---

### Task 6: Add Client Tests

**Files:**
- Create: `tests/test_infographic_client.py`

**Step 1: Create tests**

```python
# tests/test_infographic_client.py
"""Tests for InfographicClient."""

import pytest
from unittest.mock import AsyncMock, patch

from nolan.infographic_client import (
    InfographicClient,
    Engine,
    JobStatus,
    RenderJob,
)


@pytest.fixture
def client():
    return InfographicClient(host="127.0.0.1", port=3010)


class TestInfographicClient:
    """Test InfographicClient."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        """Test health check when service is running."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(status_code=200)
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client):
        """Test health check when service is down."""
        with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_submit_job(self, client):
        """Test submitting a render job."""
        mock_response = AsyncMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "job_id": "test-123",
            "status": "pending"
        }
        mock_response.raise_for_status = lambda: None

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            job = await client.submit(
                engine=Engine.INFOGRAPHIC,
                data={"items": [1, 2, 3]}
            )
            assert job.job_id == "test-123"
            assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_status(self, client):
        """Test getting job status."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "job_id": "test-123",
            "status": "rendering",
            "progress": 0.5
        }
        mock_response.raise_for_status = lambda: None

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            job = await client.get_status("test-123")
            assert job.status == JobStatus.RENDERING
            assert job.progress == 0.5
```

**Step 2: Run tests**

```bash
cd D:\ClaudeProjects\NOLAN
D:\env\nolan\python.exe -m pytest tests/test_infographic_client.py -v
```

**Step 3: Commit**

```bash
git add tests/test_infographic_client.py
git commit -m "test: add InfographicClient tests"
```

---

## Phase 3: Infographic Engine (Basic)

### Task 7: Install Infographic Dependencies

**Files:**
- Modify: `render-service/package.json`

**Step 1: Install @antv/infographic and JSDOM**

```bash
cd render-service
npm install @anthropic-ai/sdk jsdom
npm install -D @types/jsdom
```

Note: @antv/infographic may need browser environment. We'll use JSDOM.

**Step 2: Commit**

```bash
git add render-service/package.json render-service/package-lock.json
git commit -m "feat(render-service): add infographic dependencies"
```

---

### Task 8: Create Infographic Engine Wrapper

**Files:**
- Create: `render-service/src/engines/infographic.ts`
- Create: `render-service/src/engines/types.ts`

**Step 1: Create engine types**

```typescript
// render-service/src/engines/types.ts
export interface RenderResult {
  success: boolean;
  outputPath?: string;
  error?: string;
}

export interface RenderEngine {
  name: string;
  render(spec: Record<string, unknown>, outputDir: string): Promise<RenderResult>;
}
```

**Step 2: Create infographic engine**

```typescript
// render-service/src/engines/infographic.ts
import { JSDOM } from 'jsdom';
import * as fs from 'fs';
import * as path from 'path';
import { RenderEngine, RenderResult } from './types';

export class InfographicEngine implements RenderEngine {
  name = 'infographic';

  async render(spec: Record<string, unknown>, outputDir: string): Promise<RenderResult> {
    try {
      // Setup JSDOM environment
      const dom = new JSDOM('<!DOCTYPE html><div id="container"></div>', {
        pretendToBeVisual: true,
      });

      // Set globals for @antv/infographic
      (global as any).window = dom.window;
      (global as any).document = dom.window.document;

      // Dynamic import after setting up globals
      const { Infographic } = await import('@antv/infographic');

      const container = dom.window.document.getElementById('container');

      const infographic = new Infographic({
        container: container as any,
        width: spec.width as number || 1920,
        height: spec.height as number || 1080,
      });

      // Build infographic markup from spec
      const markup = this.buildMarkup(spec);
      infographic.render(markup);

      // Extract SVG
      const svg = container?.querySelector('svg');
      if (!svg) {
        throw new Error('No SVG generated');
      }

      const svgString = svg.outerHTML;

      // Save SVG (for now - later convert to MP4)
      const outputPath = path.join(outputDir, `infographic_${Date.now()}.svg`);
      fs.mkdirSync(outputDir, { recursive: true });
      fs.writeFileSync(outputPath, svgString);

      // Cleanup
      dom.window.close();

      return {
        success: true,
        outputPath,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  private buildMarkup(spec: Record<string, unknown>): string {
    const template = spec.template as string || 'list-row-simple';
    const data = spec.data as Record<string, unknown>;

    // Build simple markup - expand this based on templates
    let markup = `infographic ${template}\n`;
    markup += 'data\n';

    if (data.items && Array.isArray(data.items)) {
      markup += '  items\n';
      for (const item of data.items) {
        if (typeof item === 'object' && item !== null) {
          const obj = item as Record<string, unknown>;
          markup += `    - label ${obj.label || ''}\n`;
          if (obj.desc) markup += `      desc ${obj.desc}\n`;
          if (obj.value) markup += `      value ${obj.value}\n`;
        } else {
          markup += `    - label ${item}\n`;
        }
      }
    }

    return markup;
  }
}
```

**Step 3: Commit**

```bash
git add render-service/src/engines/
git commit -m "feat(render-service): add infographic engine with JSDOM"
```

---

### Task 9: Connect Engine to Job Queue

**Files:**
- Create: `render-service/src/jobs/processor.ts`
- Modify: `render-service/src/routes/render.ts`

**Step 1: Create job processor**

```typescript
// render-service/src/jobs/processor.ts
import * as path from 'path';
import { jobQueue } from './queue';
import { RenderJob } from './types';
import { InfographicEngine } from '../engines/infographic';
import { RenderEngine } from '../engines/types';

const OUTPUT_DIR = path.join(process.cwd(), 'output');

const engines: Record<string, RenderEngine> = {
  infographic: new InfographicEngine(),
  // TODO: Add motion-canvas and remotion engines
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

  const result = await engine.render(spec.data as Record<string, unknown>, OUTPUT_DIR);

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
```

**Step 2: Start processor in server**

```typescript
// render-service/src/server.ts
import express from 'express';
import cors from 'cors';
import healthRouter from './routes/health';
import renderRouter from './routes/render';
import { startProcessor } from './jobs/processor';

const app = express();
const PORT = process.env.PORT || 3010;

app.use(cors());
app.use(express.json());

// Routes
app.use('/health', healthRouter);
app.use('/render', renderRouter);

// Start job processor
startProcessor();
console.log('Job processor started');

app.listen(PORT, () => {
  console.log(`Render service running on http://localhost:${PORT}`);
});

export default app;
```

**Step 3: Test end-to-end**

```bash
# Start server
cd render-service
npm run dev

# Submit job
curl -X POST http://localhost:3010/render \
  -H "Content-Type: application/json" \
  -d '{"engine":"infographic","data":{"items":[{"label":"Step 1","desc":"First step"},{"label":"Step 2","desc":"Second step"}]}}'

# Check status (use job_id from response)
curl http://localhost:3010/render/status/<job_id>

# Get result when done
curl http://localhost:3010/render/result/<job_id>
```

**Step 4: Commit**

```bash
git add render-service/src/
git commit -m "feat(render-service): connect infographic engine to job processor"
```

---

## Phase 4: Motion Canvas & Remotion (Future Tasks)

### Task 10: Add Motion Canvas Engine (Placeholder)

**Files:**
- Create: `render-service/src/engines/motion-canvas.ts`

*Implementation details to be added after Phase 3 is complete and tested.*

---

### Task 11: Add Remotion Engine (Placeholder)

**Files:**
- Create: `render-service/src/engines/remotion.ts`
- Create: `render-service/remotion/` directory structure

*Implementation details to be added after Motion Canvas is integrated.*

---

## Phase 5: NOLAN Integration

### Task 12: Add CLI Command for Infographic Rendering

**Files:**
- Modify: `src/nolan/cli.py`

*Add `nolan render-infographic` command that uses InfographicClient.*

---

### Task 13: Integrate with Scene Designer

**Files:**
- Modify: `src/nolan/scenes.py`

*Add infographic detection and suggestion generation.*

---

### Task 14: Add Infographic Review UI

**Files:**
- Modify: `src/nolan/library_viewer.py`
- Modify: `src/nolan/templates/library.html`

*Add UI for reviewing and approving infographic suggestions.*

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1-4 | Project setup, Express server, job queue, API routes |
| 2 | 5-6 | Python client in NOLAN |
| 3 | 7-9 | Infographic engine with JSDOM |
| 4 | 10-11 | Motion Canvas & Remotion (future) |
| 5 | 12-14 | Full NOLAN integration |

Start with Phase 1-3 to get a working MVP, then iterate.
