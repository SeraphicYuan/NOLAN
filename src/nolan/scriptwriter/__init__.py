"""Grounded script-writer for NOLAN.

Turns a *subject + a narrative style + context sources* into a Director-ready
``script.md`` inside a standard ``projects/<slug>/`` project. The actual writing
(fetch sources → ground facts → draft → fact-check) is performed by a dispatched
Claude agent following a generated task file; this package owns the file-backed
project workspace and the task brief.

Reuses, rather than duplicates, the rest of NOLAN:
- the voice spec comes from ``script_style.ScriptStyleStore.read_guide(style_id)``;
- the output is a normal project (``project.yaml`` + ``script.md``) consumed by
  the orchestrator Director (``script_to_scenes → … → render``);
- the agent dispatch mirrors ``webui.operations.analyze_style``.
"""

from .store import ScriptProjectStore
from .tasks import write_script_task, prep_task, draft_task, v3_task

__all__ = ["ScriptProjectStore", "write_script_task",
           "prep_task", "draft_task", "v3_task"]
