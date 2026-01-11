import { v4 as uuidv4 } from 'uuid';
import { RenderJob, RenderSpec } from './types.js';

/**
 * In-memory job queue for managing render jobs.
 * Jobs are stored in a Map for O(1) lookup by ID.
 */
class JobQueue {
  private jobs: Map<string, RenderJob> = new Map();

  /**
   * Create a new render job with the given specification.
   * The job starts in 'pending' status with 0% progress.
   */
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

  /**
   * Retrieve a job by its ID.
   * Returns undefined if the job doesn't exist.
   */
  getJob(id: string): RenderJob | undefined {
    return this.jobs.get(id);
  }

  /**
   * Update a job with partial data.
   * Returns the updated job, or undefined if not found.
   */
  updateJob(id: string, updates: Partial<RenderJob>): RenderJob | undefined {
    const job = this.jobs.get(id);
    if (!job) return undefined;

    const updated = { ...job, ...updates };
    this.jobs.set(id, updated);
    return updated;
  }

  /**
   * Delete a job from the queue.
   * Returns true if the job was deleted, false if it didn't exist.
   */
  deleteJob(id: string): boolean {
    return this.jobs.delete(id);
  }

  /**
   * List all jobs in the queue.
   * Returns jobs in insertion order.
   */
  listJobs(): RenderJob[] {
    return Array.from(this.jobs.values());
  }

  /**
   * Get the count of jobs in the queue.
   */
  get size(): number {
    return this.jobs.size;
  }

  /**
   * Clear all jobs from the queue.
   * Useful for testing or resetting state.
   */
  clear(): void {
    this.jobs.clear();
  }
}

// Export a singleton instance for use across the application
export const jobQueue = new JobQueue();

// Also export the class for testing purposes
export { JobQueue };
