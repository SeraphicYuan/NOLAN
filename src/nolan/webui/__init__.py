"""Web UI support package: in-process job manager for hub-launched operations."""

from nolan.webui.jobs import JobManager, Job, get_job_manager

__all__ = ["JobManager", "Job", "get_job_manager"]
