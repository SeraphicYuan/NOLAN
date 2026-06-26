"""Aggregate orchestrator state across projects for the agents webUI page.

Reads `.orchestrator/` directories under `projects/` and shapes the data for
the FastAPI routes that drive the agents dashboard.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from nolan.orchestrator import state as state_mod


def _orchestrator_dir(project_path: Path) -> Path:
    return project_path / ".orchestrator"


def discover_projects(projects_root: Path) -> list[Path]:
    """Return project directories that have a `.orchestrator/` folder."""
    if not projects_root.exists():
        return []
    return sorted(
        p for p in projects_root.iterdir()
        if p.is_dir() and (p / ".orchestrator").exists()
    )


def latest_checkpoint(project_path: Path) -> str | None:
    cp = _orchestrator_dir(project_path) / "CHECKPOINT.md"
    if not cp.exists():
        return None
    return cp.read_text(encoding="utf-8")


def list_feedback(project_path: Path) -> list[dict[str, Any]]:
    folder = _orchestrator_dir(project_path) / "feedback"
    if not folder.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(folder.glob("review_*.md")):
        items.append({
            "name": path.name,
            "size": path.stat().st_size,
            "mtime": path.stat().st_mtime,
        })
    return items


_INLINE_KINDS = {"markdown"}
_MAX_INLINE_BYTES = 200_000


def _classify_artifact(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".json":
        return "json"
    if suffix in {".txt", ".log"}:
        return "text"
    return "other"


def list_history_snapshots(project_path: Path) -> list[dict[str, Any]]:
    folder = _orchestrator_dir(project_path) / "history"
    if not folder.exists():
        return []
    snapshots: list[dict[str, Any]] = []
    for snap_dir in sorted(folder.iterdir()):
        if not snap_dir.is_dir():
            continue
        files: list[dict[str, Any]] = []
        for fp in sorted(snap_dir.iterdir()):
            if not fp.is_file():
                continue
            size = fp.stat().st_size
            kind = _classify_artifact(fp)
            entry: dict[str, Any] = {
                "name": fp.name,
                "size_bytes": size,
                "kind": kind,
                "path": str(fp),
            }
            if kind in _INLINE_KINDS and size <= _MAX_INLINE_BYTES:
                try:
                    entry["content"] = fp.read_text(encoding="utf-8")
                except OSError:
                    entry["content"] = None
            files.append(entry)
        snapshots.append({
            "name": snap_dir.name,
            "files": files,
        })
    return snapshots


def project_summary(project_path: Path) -> dict[str, Any]:
    state = state_mod.load_state(project_path)
    style_guide_path = project_path / "style_guide.md"

    feedback_files = list_feedback(project_path)
    consumed = set(state.consumed_feedback)
    unconsumed = sum(1 for f in feedback_files if f["name"] not in consumed)

    return {
        "slug": state.project_slug or project_path.name,
        "path": str(project_path),
        "status": state.status,
        "current_step": state.current_step,
        "iteration_count": state.iteration_count,
        "started_at": state.started_at,
        "last_updated": state.last_updated,
        "step_history": [asdict(s) for s in state.step_history],
        "template_provenance": asdict(state.template_provenance),
        "has_style_guide": style_guide_path.exists(),
        "has_checkpoint": (_orchestrator_dir(project_path) / "CHECKPOINT.md").exists(),
        "feedback_files": feedback_files,
        "consumed_feedback": list(state.consumed_feedback),
        "unconsumed_feedback_count": unconsumed,
        "history_snapshots": list_history_snapshots(project_path),
    }


def list_all_projects(projects_root: Path) -> list[dict[str, Any]]:
    return [project_summary(p) for p in discover_projects(projects_root)]


def write_feedback(project_path: Path, body: str) -> Path:
    folder = _orchestrator_dir(project_path) / "feedback"
    folder.mkdir(parents=True, exist_ok=True)
    existing = sorted(folder.glob("review_*.md"))
    next_num = len(existing) + 1
    target = folder / f"review_{next_num}.md"
    target.write_text(body.strip() + "\n", encoding="utf-8")
    return target


def _stream_log_path(project_path: Path, agent_name: str) -> Path:
    return (
        project_path
        / ".orchestrator"
        / "modules"
        / agent_name
        / "last_run.stream.jsonl"
    )


def list_stream_modules(project_path: Path) -> list[str]:
    """Module names that have produced a stream log."""
    modules_dir = project_path / ".orchestrator" / "modules"
    if not modules_dir.exists():
        return []
    return sorted(
        d.name for d in modules_dir.iterdir()
        if d.is_dir() and (d / "last_run.stream.jsonl").exists()
    )


def _summarize_assistant(message: dict) -> list[dict]:
    """Extract renderable items from an `assistant` event's message.content."""
    items: list[dict] = []
    for block in message.get("content") or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text = block.get("text") or ""
            if text.strip():
                items.append({"kind": "text", "text": text})
        elif btype == "tool_use":
            items.append({
                "kind": "tool_use",
                "id": block.get("id"),
                "name": block.get("name"),
                "input": block.get("input") or {},
            })
        elif btype == "thinking":
            text = block.get("thinking") or block.get("text") or ""
            if text.strip():
                items.append({"kind": "thinking", "text": text})
    return items


def _summarize_tool_result(message: dict) -> list[dict]:
    """Extract tool_result content keyed by the matching tool_use_id."""
    out: list[dict] = []
    for block in message.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        content = block.get("content")
        if isinstance(content, list):
            text = " ".join(
                c.get("text", "") for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
        elif isinstance(content, str):
            text = content
        else:
            text = str(content) if content is not None else ""
        out.append({
            "kind": "tool_result",
            "tool_use_id": block.get("tool_use_id"),
            "is_error": bool(block.get("is_error")),
            "text": text,
        })
    return out


def read_stream_events(
    project_path: Path,
    agent_name: str,
    since_seq: int = 0,
) -> dict[str, Any]:
    """Read and filter the stream log for one module agent.

    Filters out high-volume `stream_event` deltas (which duplicate complete
    `assistant` events). Returns events in the shape the webUI renders.
    """
    log_path = _stream_log_path(project_path, agent_name)
    if not log_path.exists():
        return {
            "agent": agent_name,
            "events": [],
            "total_lines": 0,
            "finished": False,
            "log_size_bytes": 0,
        }

    events: list[dict] = []
    finished = False
    init_meta: dict | None = None
    total_lines = 0
    seq = 0

    with log_path.open(encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            line = line.rstrip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = e.get("type")
            esubtype = e.get("subtype")

            if etype == "stream_event":
                continue

            if etype == "system" and esubtype == "init":
                init_meta = {
                    "model": e.get("model"),
                    "cwd": e.get("cwd"),
                    "permission_mode": e.get("permissionMode"),
                    "claude_code_version": e.get("claude_code_version"),
                }
                seq += 1
                if seq > since_seq:
                    events.append({
                        "seq": seq,
                        "kind": "init",
                        "data": init_meta,
                    })
                continue

            if etype == "assistant":
                items = _summarize_assistant(e.get("message") or {})
                for item in items:
                    seq += 1
                    if seq > since_seq:
                        events.append({"seq": seq, **item})
                continue

            if etype == "user":
                results = _summarize_tool_result(e.get("message") or {})
                for item in results:
                    seq += 1
                    if seq > since_seq:
                        events.append({"seq": seq, **item})
                continue

            if etype == "result":
                finished = True
                seq += 1
                if seq > since_seq:
                    events.append({
                        "seq": seq,
                        "kind": "result",
                        "subtype": esubtype,
                        "duration_ms": e.get("duration_ms"),
                        "duration_api_ms": e.get("duration_api_ms"),
                        "num_turns": e.get("num_turns"),
                        "is_error": bool(e.get("is_error")),
                    })
                continue

    return {
        "agent": agent_name,
        "events": events,
        "total_lines": total_lines,
        "finished": finished,
        "log_size_bytes": log_path.stat().st_size,
        "init": init_meta,
    }


def read_all_streams(project_path: Path, since_seq: int = 0) -> list[dict[str, Any]]:
    """Read stream logs for every module that has one."""
    return [
        read_stream_events(project_path, name, since_seq=since_seq)
        for name in list_stream_modules(project_path)
    ]


def trigger_orchestrate(
    project_path: Path,
    repo_root: Path,
    refine_target: str | None = None,
) -> dict[str, Any]:
    """Spawn `nolan orchestrate <project>` as a detached background process.

    Default mode advances the pipeline by one step. If `refine_target` is
    given, runs `--refine --target <refine_target>` instead. The dashboard
    polls state files; no PID tracking needed for v1.
    """
    python_bin = sys.executable
    cmd = [python_bin, "-m", "nolan", "orchestrate", str(project_path)]
    if refine_target:
        cmd.extend(["--refine", "--target", refine_target])

    log_dir = _orchestrator_dir(project_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = log_dir / "last_run.stdout.log"
    stderr_log = log_dir / "last_run.stderr.log"

    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root),
        stdout=stdout_log.open("w", encoding="utf-8"),
        stderr=stderr_log.open("w", encoding="utf-8"),
        stdin=subprocess.DEVNULL,
        env=os.environ.copy(),
        start_new_session=True,
    )

    return {
        "pid": proc.pid,
        "command": " ".join(cmd),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "mode": "refine" if refine_target else "advance",
    }


def unconsumed_feedback_count(project_path: Path) -> int:
    """How many feedback files exist that haven't yet been consumed by a refine."""
    state = state_mod.load_state(project_path)
    consumed = set(state.consumed_feedback)
    folder = _orchestrator_dir(project_path) / "feedback"
    if not folder.exists():
        return 0
    return sum(1 for f in folder.glob("review_*.md") if f.name not in consumed)
