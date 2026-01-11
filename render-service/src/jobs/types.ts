// Job status lifecycle: pending -> rendering -> done/error
export type JobStatus = 'pending' | 'rendering' | 'done' | 'error';

// Supported rendering engines
export type Engine = 'infographic' | 'motion-canvas' | 'remotion';

// Specification for a render job
export interface RenderSpec {
  engine: Engine;
  template?: string;
  data: Record<string, unknown>;
  duration?: number;
  audio?: string;
  style_prompt?: string;
}

// A render job with its current state
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
