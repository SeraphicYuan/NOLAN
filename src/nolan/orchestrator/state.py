"""Director state persistence — `.orchestrator/director_state.json`."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_VERSION = 1


@dataclass
class StepRecord:
    step_num: int
    name: str
    started_at: str
    finished_at: str | None = None
    status: str = "in_progress"
    notes: str = ""


@dataclass
class TemplateProvenance:
    style_template_id: str | None = None
    style_template_version: int | None = None
    style_match_score: float | None = None
    style_was_fallback: bool = False
    scene_plan_template_id: str | None = None
    scene_plan_template_version: int | None = None
    scene_plan_match_score: float | None = None
    scene_plan_was_fallback: bool = False


@dataclass
class DirectorState:
    schema_version: int = STATE_VERSION
    project_slug: str = ""
    iteration_count: int = 0
    current_step: str = "init"
    status: str = "fresh"
    started_at: str = ""
    last_updated: str = ""
    step_history: list[StepRecord] = field(default_factory=list)
    template_provenance: TemplateProvenance = field(default_factory=TemplateProvenance)
    max_tokens_per_step: int = 200_000
    consumed_feedback: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DirectorState":
        history_raw = data.pop("step_history", [])
        provenance_raw = data.pop("template_provenance", {})
        consumed = data.pop("consumed_feedback", [])
        state = cls(**data)
        state.step_history = [StepRecord(**s) for s in history_raw]
        state.template_provenance = TemplateProvenance(**provenance_raw)
        state.consumed_feedback = list(consumed)
        return state


def state_path(project_path: Path) -> Path:
    return project_path / ".orchestrator" / "director_state.json"


def load_state(project_path: Path) -> DirectorState:
    path = state_path(project_path)
    if not path.exists():
        return DirectorState(
            project_slug=project_path.name,
            started_at=_now(),
            last_updated=_now(),
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return DirectorState.from_dict(data)


def save_state(project_path: Path, state: DirectorState) -> None:
    state.last_updated = _now()
    path = state_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def append_step(state: DirectorState, name: str) -> StepRecord:
    next_num = (
        max((s.step_num for s in state.step_history), default=0) + 1
    )
    record = StepRecord(
        step_num=next_num,
        name=name,
        started_at=_now(),
    )
    state.step_history.append(record)
    state.current_step = name
    return record


def finish_step(record: StepRecord, status: str = "completed", notes: str = "") -> None:
    record.finished_at = _now()
    record.status = status
    if notes:
        record.notes = notes


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
