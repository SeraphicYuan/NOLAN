"""Director — Layer 2 orchestrator.

v1 scope: first-pass template matching → adapt or invent → write style_guide.md
→ checkpoint → exit. No specialists, no refine flow yet.

See docs/plans/2026-04-26-two-layer-orchestrator.md.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from nolan.skills import handoff
from nolan.orchestrator import state as state_mod
from nolan.orchestrator.claude_runner import (
    ClaudeRunnerError,
    path_for_agent,
    run_one_shot,
)
from nolan.orchestrator.template_match import (
    TemplateCandidate,
    match_scene_plan_template,
    match_style_template,
)


MATCH_THRESHOLD = 0.6

# Order matters — Director runs the first not-yet-completed step on each
# invocation. Add new specialists here.
PIPELINE_STEPS = [
    "match_and_adapt_style",
    "script_to_scenes",
    "tempo_enrich",
    "select_clips",
    "slide_designer",
    "render",
]

INFO_SCENE_TYPES = {"text-overlay", "graphic"}


@dataclass
class ProjectContext:
    project_path: Path
    slug: str
    name: str
    description: str
    script: str
    duration_seconds: int | None
    genre_hint: str | None


class DirectorError(Exception):
    pass


def _load_project_context(project_path: Path) -> ProjectContext:
    project_yaml = project_path / "project.yaml"
    script_md = project_path / "script.md"
    if not project_yaml.exists():
        raise DirectorError(f"missing project.yaml at {project_yaml}")
    if not script_md.exists():
        raise DirectorError(f"missing script.md at {script_md}")

    meta = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    script = script_md.read_text(encoding="utf-8")
    duration = _extract_duration_seconds(script)

    return ProjectContext(
        project_path=project_path,
        slug=meta.get("slug", project_path.name),
        name=meta.get("name", project_path.name),
        description=meta.get("description", ""),
        script=script,
        duration_seconds=duration,
        genre_hint=_infer_genre_hint(meta.get("description", ""), script),
    )


def _extract_duration_seconds(script: str) -> int | None:
    match = re.search(r"\*\*Total Duration:\*\*\s*(\d+):(\d+)", script)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _infer_genre_hint(description: str, script: str) -> str | None:
    blob = (description + " " + script[:2000]).lower()
    if any(w in blob for w in ("documentary", "history", "historical")):
        return "documentary"
    if any(w in blob for w in ("explainer", "explain", "tutorial")):
        return "explainer"
    if any(w in blob for w in ("essay", "analysis", "argument")):
        return "explainer"
    return None


def _orchestrator_dir(project_path: Path) -> Path:
    return project_path / ".orchestrator"


def _build_match_free_text(ctx: ProjectContext) -> str:
    return f"{ctx.name}\n{ctx.description}\n\n{ctx.script[:3000]}"


def _select_match(
    candidates: list[TemplateCandidate], threshold: float
) -> tuple[TemplateCandidate | None, str]:
    if not candidates:
        return None, "no templates in library"
    top = candidates[0]
    if top.score >= threshold:
        return top, f"matched {top.template_id} score={top.score:.2f}"
    return None, (
        f"best candidate {top.template_id} score={top.score:.2f} "
        f"below threshold {threshold}"
    )


def _stream_log_path(project_path: Path, agent_name: str) -> Path:
    return (
        project_path
        / ".orchestrator"
        / "modules"
        / agent_name
        / "last_run.stream.jsonl"
    )


async def _run_style_agent(
    ctx: ProjectContext,
    system_prompt: str,
    user_prompt: str,
    target_path: Path,
) -> tuple[str, float]:
    """Invoke Claude in agent mode; expect it to Write the style guide to target_path."""
    if target_path.exists():
        target_path.unlink()

    result = await run_one_shot(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cwd=ctx.project_path,
        permission_mode="bypassPermissions",
        stream_log_path=_stream_log_path(ctx.project_path, "director"),
    )

    if not target_path.exists():
        raise DirectorError(
            f"Agent did not write the expected file at {target_path}. "
            f"Final assistant text was: {result.text[:300]!r}"
        )

    content = target_path.read_text(encoding="utf-8")
    return content, result.elapsed_seconds


async def _adapt_style_template(
    candidate: TemplateCandidate, ctx: ProjectContext
) -> tuple[str, float]:
    system = handoff("orchestrator.adapt-style")
    template_md = candidate.template_md_path().read_text(encoding="utf-8")
    target_path = ctx.project_path / "style_guide.md"

    user = (
        f"# target_path\n`{path_for_agent(target_path)}`\n\n"
        f"# Matched template metadata\n"
        f"- id: {candidate.template_id}\n"
        f"- version: {candidate.version}\n"
        f"- name: {candidate.name}\n"
        f"- match_score: {candidate.score:.3f}\n"
        f"- score_breakdown: {candidate.score_breakdown}\n\n"
        f"# Template content (`template.md`)\n\n{template_md}\n\n"
        f"# Project metadata\n"
        f"- slug: {ctx.slug}\n"
        f"- name: {ctx.name}\n"
        f"- description: {ctx.description}\n"
        f"- duration_seconds: {ctx.duration_seconds}\n"
        f"- genre_hint: {ctx.genre_hint}\n\n"
        f"# Project script (`script.md`)\n\n{ctx.script}\n"
    )

    return await _run_style_agent(ctx, system, user, target_path)


async def _invent_style(
    ctx: ProjectContext, miss_reason: str
) -> tuple[str, float]:
    system = handoff("orchestrator.invent-style")
    target_path = ctx.project_path / "style_guide.md"

    user = (
        f"# target_path\n`{path_for_agent(target_path)}`\n\n"
        f"# Why fallback fired\n{miss_reason}\n\n"
        f"# Project metadata\n"
        f"- slug: {ctx.slug}\n"
        f"- name: {ctx.name}\n"
        f"- description: {ctx.description}\n"
        f"- duration_seconds: {ctx.duration_seconds}\n"
        f"- genre_hint: {ctx.genre_hint}\n\n"
        f"# Project script (`script.md`)\n\n{ctx.script}\n"
    )

    return await _run_style_agent(ctx, system, user, target_path)


def _snapshot_history(
    project_path: Path,
    step_num: int,
    step_name: str,
    artifacts: dict[str, str | bytes],
) -> Path:
    folder = (
        _orchestrator_dir(project_path)
        / "history"
        / f"step_{step_num:02d}_{step_name}"
    )
    folder.mkdir(parents=True, exist_ok=True)
    for filename, content in artifacts.items():
        path = folder / filename
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return folder


def _write_checkpoint(
    project_path: Path,
    step_num: int,
    summary_lines: list[str],
) -> Path:
    checkpoint = _orchestrator_dir(project_path) / "CHECKPOINT.md"
    body = (
        f"# Checkpoint after step {step_num}\n\n"
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n\n"
        f"## What just happened\n\n"
    )
    for line in summary_lines:
        body += f"- {line}\n"
    body += (
        "\n## Your turn\n\n"
        "Review the artifacts listed above. When ready:\n"
        "- Accept as-is and re-run `nolan orchestrate <project> --resume` to advance.\n"
        "- Or edit the artifacts directly (style_guide.md, scene_plan.json, etc.) "
        "and then resume.\n"
        "- Or write feedback into `.orchestrator/feedback/review_<n>.md` and "
        "re-run with `--refine` (refine flow lands in a later build).\n"
    )
    checkpoint.write_text(body, encoding="utf-8")
    return checkpoint


class Director:
    def __init__(self, project_path: Path, repo_root: Path | None = None):
        self.project_path = project_path.resolve()
        self.repo_root = (repo_root or _find_repo_root(self.project_path)).resolve()

    async def run_auto(self, max_steps: int = 12) -> list[Path]:
        """Run all pending pipeline steps in sequence until none remain or one errors.

        Each step still writes its own checkpoint and snapshot — `--auto` is
        purely an automation convenience over repeated `run_next_step` calls.
        Stops on:
        - no more pending steps (writes idle checkpoint and returns)
        - any step entering `error` status
        - max_steps cap (safety net against infinite loops)
        """
        checkpoints: list[Path] = []
        for _ in range(max_steps):
            cp = await self.run_next_step()
            checkpoints.append(cp)
            state = state_mod.load_state(self.project_path)
            if state.status == "error":
                break
            if self._next_step_name(state) is None:
                break
        return checkpoints

    async def run_next_step(self) -> Path:
        """Run the first not-yet-completed pipeline step, then exit at checkpoint.

        Use the same Director invocation repeatedly to advance the pipeline:
        first run → style_guide; second run → clip selection; etc. State is
        derived from `state.step_history` so re-running is idempotent.
        """
        if not self.project_path.exists():
            raise DirectorError(f"project not found: {self.project_path}")

        ctx = _load_project_context(self.project_path)
        state = state_mod.load_state(self.project_path)
        state.project_slug = ctx.slug

        next_name = self._next_step_name(state)
        if next_name is None:
            return self._write_idle_checkpoint(state)

        if next_name == "match_and_adapt_style":
            return await self._run_match_and_adapt_style_step(ctx, state)
        if next_name == "script_to_scenes":
            return await self._run_script_to_scenes_step(ctx, state)
        if next_name == "tempo_enrich":
            return await self._run_tempo_enrich_step(ctx, state)
        if next_name == "select_clips":
            return await self._run_select_clips_step(ctx, state)
        if next_name == "slide_designer":
            return await self._run_slide_designer_step(ctx, state)
        if next_name == "render":
            return await self._run_render_step(ctx, state)
        raise DirectorError(f"unknown pipeline step: {next_name}")

    def _next_step_name(self, state: state_mod.DirectorState) -> str | None:
        """Pick the next step. Mixed strategy:

        - Steps that *produce* a top-level artifact use artifact-presence so
          hand-authored files are respected (skip the step, don't overwrite).
        - Steps that *mutate* an existing artifact in place can only be
          detected via step_history.
        """
        completed = {
            s.name for s in state.step_history if s.status == "completed"
        }
        if not (self.project_path / "style_guide.md").exists():
            return "match_and_adapt_style"
        if not (self.project_path / "scene_plan.json").exists():
            return "script_to_scenes"
        if "tempo_enrich" not in completed:
            return "tempo_enrich"
        if "select_clips" not in completed:
            return "select_clips"
        if self._info_scenes_missing_layout() > 0:
            return "slide_designer"
        final_video = self.project_path / "output" / "final.mp4"
        if not final_video.exists():
            return "render"
        return None

    def _info_scenes_missing_layout(self) -> int:
        plan_path = self.project_path / "scene_plan.json"
        if not plan_path.exists():
            return 0
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return 0
        count = 0
        for scenes in (plan.get("sections") or {}).values():
            if not isinstance(scenes, list):
                continue
            for s in scenes:
                if not isinstance(s, dict):
                    continue
                if s.get("visual_type") in INFO_SCENE_TYPES and not s.get("layout_spec"):
                    count += 1
        return count

    def _write_idle_checkpoint(self, state: state_mod.DirectorState) -> Path:
        completed = [s.name for s in state.step_history if s.status == "completed"]
        summary = [
            f"All known pipeline steps already completed: {completed}",
            "To advance further, build/enable the next specialist or use "
            "`--redo <step>` (not yet implemented).",
        ]
        state.status = "awaiting_review"
        state.current_step = "idle"
        state_mod.save_state(self.project_path, state)
        last_step_num = len(state.step_history)
        return _write_checkpoint(self.project_path, last_step_num, summary)

    async def _run_match_and_adapt_style_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        record = state_mod.append_step(state, "match_and_adapt_style")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        free_text = _build_match_free_text(ctx)
        style_candidates = match_style_template(
            project_genre=ctx.genre_hint,
            duration_seconds=ctx.duration_seconds,
            free_text=free_text,
            repo_root=self.repo_root,
            top_k=3,
        )
        scene_candidates = match_scene_plan_template(
            project_genre=ctx.genre_hint,
            duration_seconds=ctx.duration_seconds,
            free_text=free_text,
            repo_root=self.repo_root,
            top_k=3,
        )

        chosen_style, style_reason = _select_match(style_candidates, MATCH_THRESHOLD)
        chosen_scene, scene_reason = _select_match(scene_candidates, MATCH_THRESHOLD)

        summary_lines: list[str] = []

        try:
            if chosen_style is not None:
                summary_lines.append(
                    f"Style template matched: **{chosen_style.template_id}** "
                    f"v{chosen_style.version} (score {chosen_style.score:.2f}). "
                    f"Adapting to this project."
                )
                style_guide, llm_elapsed = await _adapt_style_template(
                    chosen_style, ctx
                )
                state.template_provenance.style_template_id = chosen_style.template_id
                state.template_provenance.style_template_version = chosen_style.version
                state.template_provenance.style_match_score = round(
                    chosen_style.score, 3
                )
                state.template_provenance.style_was_fallback = False
            else:
                summary_lines.append(
                    f"Style template **fallback**: {style_reason}. Inventing fresh."
                )
                style_guide, llm_elapsed = await _invent_style(ctx, style_reason)
                state.template_provenance.style_was_fallback = True
        except (ClaudeRunnerError, DirectorError) as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"Style-agent step failed: {exc}") from exc

        summary_lines.append(f"Claude CLI elapsed: {llm_elapsed:.1f}s")

        if chosen_scene is not None:
            summary_lines.append(
                f"Scene-plan structure template matched: "
                f"**{chosen_scene.template_id}** v{chosen_scene.version} "
                f"(score {chosen_scene.score:.2f}). "
                f"Will be used by `script_to_scenes` when that module ships."
            )
            state.template_provenance.scene_plan_template_id = chosen_scene.template_id
            state.template_provenance.scene_plan_template_version = chosen_scene.version
            state.template_provenance.scene_plan_match_score = round(
                chosen_scene.score, 3
            )
            state.template_provenance.scene_plan_was_fallback = False
        else:
            summary_lines.append(
                f"Scene-plan structure **fallback**: {scene_reason}. "
                f"`script_to_scenes` will design from scratch when invoked."
            )
            state.template_provenance.scene_plan_was_fallback = True

        candidate_lines = ["Top style-template candidates:"]
        for c in style_candidates:
            candidate_lines.append(
                f"  - {c.template_id} score={c.score:.2f} {c.score_breakdown}"
            )
        candidate_lines.append("Top scene-plan candidates:")
        for c in scene_candidates:
            candidate_lines.append(
                f"  - {c.template_id} score={c.score:.2f} {c.score_breakdown}"
            )
        reasoning = "\n".join(candidate_lines)

        _snapshot_history(
            self.project_path,
            record.step_num,
            "match_and_adapt_style",
            {
                "style_guide.md": style_guide,
                "reasoning.md": (
                    f"# Step {record.step_num}: match_and_adapt_style\n\n"
                    f"## Style match\n{style_reason}\n\n"
                    f"## Scene-plan match\n{scene_reason}\n\n"
                    f"## Candidate scores\n{reasoning}\n"
                ),
            },
        )

        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = "checkpoint_after_match_and_adapt_style"
        state_mod.save_state(self.project_path, state)

        summary_lines.append(
            "Wrote `style_guide.md` to project root. "
            "Snapshot in `.orchestrator/history/step_01_match_and_adapt_style/`."
        )
        summary_lines.append(
            "State saved to `.orchestrator/director_state.json`."
        )

        return _write_checkpoint(self.project_path, record.step_num, summary_lines)


    async def run_refine_step(self, target_step: str) -> Path:
        """Run a refine pass on a previously-completed step using the latest unconsumed feedback file."""
        if not self.project_path.exists():
            raise DirectorError(f"project not found: {self.project_path}")

        refine_dispatch = {
            "match_and_adapt_style": self._run_match_and_adapt_style_refine,
            "select_clips": self._run_select_clips_refine,
            "slide_designer": self._run_slide_designer_refine,
        }
        if target_step not in refine_dispatch:
            raise DirectorError(
                f"refine for step '{target_step}' is not yet implemented "
                f"(supported: {sorted(refine_dispatch)})"
            )

        ctx = _load_project_context(self.project_path)
        state = state_mod.load_state(self.project_path)
        state.project_slug = ctx.slug

        feedback_dir = _orchestrator_dir(self.project_path) / "feedback"
        if not feedback_dir.exists():
            raise DirectorError(
                "no `.orchestrator/feedback/` folder; nothing to refine against"
            )
        feedback_files = sorted(feedback_dir.glob("review_*.md"))
        consumed = set(state.consumed_feedback)
        unconsumed = [f for f in feedback_files if f.name not in consumed]
        if not unconsumed:
            raise DirectorError(
                "no unconsumed feedback files; write feedback into "
                "`.orchestrator/feedback/review_<n>.md` before refining"
            )
        feedback_path = unconsumed[-1]
        feedback_text = feedback_path.read_text(encoding="utf-8").strip()
        if not feedback_text:
            raise DirectorError(f"feedback file {feedback_path.name} is empty")

        # Feedback ledger: a human correction at this gate is a signal about the skill that
        # AUTHORED the artifact being refined — record it against that producer's version.
        producer = {
            "match_and_adapt_style": "orchestrator.adapt-style",
            "select_clips": "orchestrator.select-clips",
            "slide_designer": "orchestrator.slide-designer",
        }.get(target_step)
        if producer:
            from nolan.skills import record_feedback
            record_feedback(producer, feedback_text,
                            ctx={"project": ctx.slug, "step": target_step, "file": feedback_path.name})

        return await refine_dispatch[target_step](
            ctx, state, feedback_path, feedback_text,
        )

    async def _run_match_and_adapt_style_refine(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
        feedback_path: Path,
        feedback_text: str,
    ) -> Path:
        prior_refines = sum(
            1 for s in state.step_history
            if s.name.startswith("match_and_adapt_style_refine_")
        )
        refine_num = prior_refines + 1
        step_name = f"match_and_adapt_style_refine_{refine_num}"

        record = state_mod.append_step(state, step_name)
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        target_path = self.project_path / "style_guide.md"
        if not target_path.exists():
            err = (
                f"style_guide.md missing at {target_path}; "
                f"run match_and_adapt_style first"
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        current_content = target_path.read_text(encoding="utf-8")
        prior_reasoning = self._latest_step_reasoning("match_and_adapt_style") or "(no prior reasoning available)"

        system = handoff("orchestrator.refine-style")
        user = (
            f"# target_path\n`{path_for_agent(target_path)}`\n\n"
            f"# iteration_number\n{refine_num}\n\n"
            f"# Project metadata\n"
            f"- slug: {ctx.slug}\n"
            f"- name: {ctx.name}\n"
            f"- description: {ctx.description}\n"
            f"- duration_seconds: {ctx.duration_seconds}\n\n"
            f"# Current style guide content (`style_guide.md`)\n\n"
            f"{current_content}\n\n"
            f"# Prior reasoning\n\n{prior_reasoning}\n\n"
            f"# User feedback (verbatim from `{feedback_path.name}`)\n\n"
            f"{feedback_text}\n"
        )

        try:
            result = await run_one_shot(
                system_prompt=system,
                user_prompt=user,
                cwd=self.project_path,
                permission_mode="bypassPermissions",
                stream_log_path=_stream_log_path(self.project_path, "director"),
            )
        except ClaudeRunnerError as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"refine failed: {exc}") from exc

        new_content = target_path.read_text(encoding="utf-8")
        if new_content == current_content:
            note = (
                "Agent did not modify style_guide.md. "
                "Either the feedback was a no-op or the model declined to edit."
            )
        else:
            note = ""

        _snapshot_history(
            self.project_path,
            record.step_num,
            step_name,
            {
                "style_guide.md": new_content,
                "feedback_consumed.md": (
                    f"# Feedback file: {feedback_path.name}\n\n"
                    f"Consumed by refine pass {refine_num} at "
                    f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}.\n\n"
                    f"---\n\n{feedback_text}\n"
                ),
                "reasoning.md": (
                    f"# Step {record.step_num}: {step_name}\n\n"
                    f"- Refine pass: {refine_num}\n"
                    f"- Feedback file: {feedback_path.name}\n"
                    f"- Claude CLI elapsed: {result.elapsed_seconds:.1f}s\n"
                    f"- Stream events: {result.event_count}\n"
                    f"- Note: {note or 'style_guide.md changed in place.'}\n"
                ),
            },
        )

        if feedback_path.name not in state.consumed_feedback:
            state.consumed_feedback.append(feedback_path.name)

        state.iteration_count += 1
        state_mod.finish_step(record, status="completed", notes=note)
        state.status = "awaiting_review"
        state.current_step = f"checkpoint_after_{step_name}"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            f"Refine pass {refine_num} on `match_and_adapt_style` complete.",
            f"Feedback consumed: `{feedback_path.name}`.",
            f"Claude CLI elapsed: {result.elapsed_seconds:.1f}s "
            f"({result.event_count} stream events).",
        ]
        if note:
            summary_lines.append(f"⚠ {note}")
        else:
            summary_lines.append(
                f"`style_guide.md` updated in place; "
                f"snapshot in `.orchestrator/history/step_{record.step_num:02d}_{step_name}/`."
            )
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    async def _run_select_clips_refine(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
        feedback_path: Path,
        feedback_text: str,
    ) -> Path:
        prior_refines = sum(
            1 for s in state.step_history
            if s.name.startswith("select_clips_refine_")
        )
        refine_num = prior_refines + 1
        step_name = f"select_clips_refine_{refine_num}"

        record = state_mod.append_step(state, step_name)
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        scene_plan_path = self.project_path / "scene_plan.json"
        style_guide_path = self.project_path / "style_guide.md"
        prior_report_path = (
            _orchestrator_dir(self.project_path)
            / "modules" / "clip_selector" / "last_report.md"
        )
        target_report_path = prior_report_path  # overwritten by agent

        if not scene_plan_path.exists():
            err = f"scene_plan.json missing at {scene_plan_path}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)
        if not prior_report_path.exists():
            err = (
                f"prior clip_selector report missing at {prior_report_path}; "
                f"run select_clips first before refining it"
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        # Stash the prior report before the agent overwrites it, so we snapshot
        # the BEFORE/AFTER as separate artifacts.
        prior_report_text = prior_report_path.read_text(encoding="utf-8")

        system = handoff("orchestrator.refine-clips")
        user = (
            f"# target_scene_plan_path\n`{path_for_agent(scene_plan_path)}`\n\n"
            f"# target_report_path\n`{path_for_agent(target_report_path)}`\n\n"
            f"# style_guide_path\n`{path_for_agent(style_guide_path)}`\n\n"
            f"# prior_report_path\n`{path_for_agent(prior_report_path)}`\n\n"
            f"# project_slug\n`{ctx.slug}`\n\n"
            f"# iteration_number\n{refine_num}\n\n"
            f"# Project metadata\n"
            f"- name: {ctx.name}\n"
            f"- description: {ctx.description}\n"
            f"- duration_seconds: {ctx.duration_seconds}\n\n"
            f"# User feedback (verbatim from `{feedback_path.name}`)\n\n"
            f"{feedback_text}\n"
        )

        try:
            result = await run_one_shot(
                system_prompt=system,
                user_prompt=user,
                cwd=self.project_path,
                permission_mode="bypassPermissions",
                stream_log_path=_stream_log_path(self.project_path, "clip_selector"),
            )
        except ClaudeRunnerError as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"select_clips refine failed: {exc}") from exc

        if not target_report_path.exists():
            err = (
                f"clip_selector refine did not write the report at "
                f"{target_report_path}. Final assistant text was: {result.text[:300]!r}"
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        new_report_text = target_report_path.read_text(encoding="utf-8")
        new_scene_plan_text = scene_plan_path.read_text(encoding="utf-8")

        _snapshot_history(
            self.project_path,
            record.step_num,
            step_name,
            {
                "scene_plan.json": new_scene_plan_text,
                "report.md": new_report_text,
                "prior_report.md": prior_report_text,
                "feedback_consumed.md": (
                    f"# Feedback file: {feedback_path.name}\n\n"
                    f"Consumed by clip_selector refine pass {refine_num} at "
                    f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}.\n\n"
                    f"---\n\n{feedback_text}\n"
                ),
                "reasoning.md": (
                    f"# Step {record.step_num}: {step_name}\n\n"
                    f"- Refine pass: {refine_num}\n"
                    f"- Feedback file: {feedback_path.name}\n"
                    f"- Claude CLI elapsed: {result.elapsed_seconds:.1f}s\n"
                    f"- Stream events: {result.event_count}\n"
                ),
            },
        )

        if feedback_path.name not in state.consumed_feedback:
            state.consumed_feedback.append(feedback_path.name)

        state.iteration_count += 1
        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = f"checkpoint_after_{step_name}"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            f"clip_selector refine pass {refine_num} complete.",
            f"Feedback consumed: `{feedback_path.name}`.",
            f"Claude CLI elapsed: {result.elapsed_seconds:.1f}s "
            f"({result.event_count} stream events).",
            f"`scene_plan.json` updated in place; "
            f"new report at `.orchestrator/modules/clip_selector/last_report.md`. "
            f"Snapshot in `.orchestrator/history/step_{record.step_num:02d}_{step_name}/`.",
        ]
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    async def _run_slide_designer_refine(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
        feedback_path: Path,
        feedback_text: str,
    ) -> Path:
        prior_refines = sum(
            1 for s in state.step_history
            if s.name.startswith("slide_designer_refine_")
        )
        refine_num = prior_refines + 1
        step_name = f"slide_designer_refine_{refine_num}"

        record = state_mod.append_step(state, step_name)
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        scene_plan_path = self.project_path / "scene_plan.json"
        style_guide_path = self.project_path / "style_guide.md"
        prior_report_path = (
            _orchestrator_dir(self.project_path)
            / "modules" / "slide_designer" / "last_report.md"
        )
        target_report_path = prior_report_path  # overwritten by agent

        if not scene_plan_path.exists():
            err = f"scene_plan.json missing at {scene_plan_path}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)
        if not prior_report_path.exists():
            err = (
                f"prior slide_designer report missing at {prior_report_path}; "
                f"run slide_designer first before refining it"
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        prior_report_text = prior_report_path.read_text(encoding="utf-8")

        system = handoff("orchestrator.refine-slides")
        user = (
            f"# scene_plan_path\n`{path_for_agent(scene_plan_path)}`\n\n"
            f"# target_report_path\n`{path_for_agent(target_report_path)}`\n\n"
            f"# style_guide_path\n`{path_for_agent(style_guide_path)}`\n\n"
            f"# prior_report_path\n`{path_for_agent(prior_report_path)}`\n\n"
            f"# iteration_number\n{refine_num}\n\n"
            f"# Project metadata\n"
            f"- slug: {ctx.slug}\n"
            f"- name: {ctx.name}\n"
            f"- description: {ctx.description}\n\n"
            f"# User feedback (verbatim from `{feedback_path.name}`)\n\n"
            f"{feedback_text}\n"
        )

        try:
            result = await run_one_shot(
                system_prompt=system,
                user_prompt=user,
                cwd=self.project_path,
                permission_mode="bypassPermissions",
                stream_log_path=_stream_log_path(self.project_path, "slide_designer"),
            )
        except ClaudeRunnerError as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"slide_designer refine failed: {exc}") from exc

        if not target_report_path.exists():
            err = (
                f"slide_designer refine did not write report at "
                f"{target_report_path}. Final assistant text was: {result.text[:300]!r}"
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        new_report_text = target_report_path.read_text(encoding="utf-8")
        new_scene_plan_text = scene_plan_path.read_text(encoding="utf-8")

        _snapshot_history(
            self.project_path,
            record.step_num,
            step_name,
            {
                "scene_plan.json": new_scene_plan_text,
                "report.md": new_report_text,
                "prior_report.md": prior_report_text,
                "feedback_consumed.md": (
                    f"# Feedback file: {feedback_path.name}\n\n"
                    f"Consumed by slide_designer refine pass {refine_num} at "
                    f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}.\n\n"
                    f"---\n\n{feedback_text}\n"
                ),
                "reasoning.md": (
                    f"# Step {record.step_num}: {step_name}\n\n"
                    f"- Refine pass: {refine_num}\n"
                    f"- Feedback file: {feedback_path.name}\n"
                    f"- Claude CLI elapsed: {result.elapsed_seconds:.1f}s\n"
                    f"- Stream events: {result.event_count}\n"
                ),
            },
        )

        if feedback_path.name not in state.consumed_feedback:
            state.consumed_feedback.append(feedback_path.name)

        state.iteration_count += 1
        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = f"checkpoint_after_{step_name}"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            f"slide_designer refine pass {refine_num} complete.",
            f"Feedback consumed: `{feedback_path.name}`.",
            f"Claude CLI elapsed: {result.elapsed_seconds:.1f}s "
            f"({result.event_count} stream events).",
            f"`scene_plan.json` updated in place; "
            f"new report at `.orchestrator/modules/slide_designer/last_report.md`. "
            f"Snapshot in `.orchestrator/history/step_{record.step_num:02d}_{step_name}/`.",
        ]
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    async def _run_render_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Render every scene to per-scene MP4s and assemble a final video.

        v1: silent audio (no TTS yet), generated-image scenes skipped (assemble
        fills with black frames). See `src/nolan/orchestrator/render.py`.
        """
        from nolan.orchestrator import render as render_mod

        record = state_mod.append_step(state, "render")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        scene_plan_path = self.project_path / "scene_plan.json"
        if not scene_plan_path.exists():
            err = "scene_plan.json missing — render needs scenes."
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        try:
            scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            err = f"scene_plan.json is invalid JSON: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        rendered_dir = self.project_path / "assets" / "rendered"
        rendered_dir.mkdir(parents=True, exist_ok=True)
        output_dir = self.project_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_video_path = output_dir / "final.mp4"

        scratch = _orchestrator_dir(self.project_path) / "modules" / "render"
        scratch.mkdir(parents=True, exist_ok=True)
        silent_audio_path = scratch / "silent.wav"
        report_path = scratch / "last_report.md"

        # 1. Render every scene that we know how to render.
        try:
            outcomes = render_mod.render_all(
                scene_plan, self.project_path, rendered_dir
            )
        except Exception as exc:
            err = f"render_all failed: {type(exc).__name__}: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err) from exc

        # 2. Annotate scene_plan with rendered_clip + start_seconds/end_seconds
        #    so `nolan assemble` places each clip on the timeline.
        total_duration, rendered_count = render_mod.annotate_scene_plan(
            scene_plan, outcomes
        )
        scene_plan_path.write_text(
            json.dumps(scene_plan, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 3. Generate a silent audio track of the right length.
        try:
            render_mod.generate_silent_audio(total_duration, silent_audio_path)
        except render_mod.RenderError as exc:
            err = f"silent audio generation failed: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err) from exc

        # 4. Shell out to `nolan assemble` for the final stitch.
        try:
            render_mod.call_assemble(
                project_path=self.project_path,
                scene_plan_path=scene_plan_path,
                audio_path=silent_audio_path,
                output_path=final_video_path,
                repo_root=self.repo_root,
            )
        except render_mod.RenderError as exc:
            err = f"assemble failed: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err) from exc

        # 5. Write the report + snapshot.
        report_body = render_mod.render_summary_report(outcomes, total_duration)
        report_path.write_text(report_body, encoding="utf-8")

        skipped_count = sum(1 for o in outcomes if not o.rendered_clip)
        final_size_mb = (
            final_video_path.stat().st_size / (1024 * 1024)
            if final_video_path.exists() else 0
        )

        _snapshot_history(
            self.project_path,
            record.step_num,
            "render",
            {
                "report.md": report_body,
                "scene_plan.json": scene_plan_path.read_text(encoding="utf-8"),
                "reasoning.md": (
                    f"# Step {record.step_num}: render\n\n"
                    f"- Total scenes: {len(outcomes)}\n"
                    f"- Rendered: {rendered_count}\n"
                    f"- Skipped: {skipped_count}\n"
                    f"- Total runtime: {total_duration:.1f}s\n"
                    f"- Final video: `output/final.mp4` "
                    f"({final_size_mb:.1f} MB)\n"
                    f"- Audio: silent (TTS not yet integrated)\n"
                ),
            },
        )

        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = "checkpoint_after_render"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            f"render step complete.",
            f"Rendered {rendered_count}/{len(outcomes)} scenes; "
            f"{skipped_count} filled with black frames at assembly.",
            f"Total runtime: {total_duration:.1f}s "
            f"({int(total_duration//60)}:{int(total_duration%60):02d}).",
            f"Final video: `output/final.mp4` ({final_size_mb:.1f} MB) — silent.",
            f"Per-scene report: `.orchestrator/modules/render/last_report.md`.",
            f"Snapshot in `.orchestrator/history/step_{record.step_num:02d}_render/`.",
        ]
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    def _latest_step_reasoning(self, step_name: str) -> str | None:
        """Return the reasoning.md from the most recent snapshot of `step_name` (incl. refines)."""
        history = _orchestrator_dir(self.project_path) / "history"
        if not history.exists():
            return None
        candidates = sorted(
            p for p in history.glob(f"step_*_{step_name}*/reasoning.md")
        )
        if not candidates:
            return None
        return candidates[-1].read_text(encoding="utf-8")

    async def _run_script_to_scenes_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        record = state_mod.append_step(state, "script_to_scenes")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        target_path = self.project_path / "scene_plan.json"
        script_path = self.project_path / "script.md"
        style_guide_path = self.project_path / "style_guide.md"
        if not script_path.exists():
            err = "script.md missing — script_to_scenes needs the narration."
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)
        if not style_guide_path.exists():
            err = (
                "style_guide.md missing — match_and_adapt_style must complete "
                "first so the visual_type vocabulary and pacing rules are defined."
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        # Locate the matched scene-plan structure template's skeleton, if one
        # was matched during step 1. Fallback if missing.
        skeleton_path: Path | None = None
        sp_id = state.template_provenance.scene_plan_template_id
        if sp_id:
            candidate = (
                self.repo_root / "assets" / "templates" / "scene_plans"
                / sp_id / "skeleton.json"
            )
            if candidate.exists():
                skeleton_path = candidate

        skeleton_arg = (
            path_for_agent(skeleton_path) if skeleton_path else "none"
        )

        if target_path.exists():
            target_path.unlink()

        # Context-injection: hand the agent the scriptgen grounding it doesn't otherwise see —
        # facts.md (anchor visuals to real, specific subjects) + beatmap.md (per-beat pace tags).
        _sg = self.project_path / "scriptgen"
        grounding = ""
        if (_sg / "facts.md").exists():
            grounding += ("# facts_path (grounded fact sheet — anchor visuals to these; prefer NAMING "
                          "the specific real subject, e.g. a titled artwork/artifact/place, over generic "
                          f"stock)\n`{path_for_agent(_sg / 'facts.md')}`\n\n")
        if (_sg / "beatmap.md").exists():
            grounding += ("# beatmap_path (retention/pacing plan — each beat is tagged pace:accelerate|"
                          f"decelerate; honor that rhythm)\n`{path_for_agent(_sg / 'beatmap.md')}`\n\n")
        if (_sg / "reference_structure.json").exists():
            grounding += ("# reference_structure_path (a REAL video's recovered editorial plan this "
                          "project was cloned from / references — per beat: pairing `operator` (how "
                          "the reference relates visuals to narration: literal/tonal/conceptual/…), "
                          "`dominant_treatment` (its motion grammar), `asset_types`, and measured "
                          "energy. Use it to CHOOSE visual_type + visual treatment per section like "
                          "the reference does; it complements, never overrides, the style guide's "
                          f"visual vocabulary)\n`{path_for_agent(_sg / 'reference_structure.json')}`\n\n")

        system = handoff("orchestrator.script-to-scenes")
        user = (
            f"# target_path\n`{path_for_agent(target_path)}`\n\n"
            f"# script_path\n`{path_for_agent(script_path)}`\n\n"
            f"# style_guide_path\n`{path_for_agent(style_guide_path)}`\n\n"
            f"# structure_skeleton_path\n`{skeleton_arg}`\n\n"
            f"{grounding}"
            f"# Project metadata\n"
            f"- slug: {ctx.slug}\n"
            f"- name: {ctx.name}\n"
            f"- description: {ctx.description}\n"
            f"- duration_seconds: {ctx.duration_seconds}\n"
            f"- genre_hint: {ctx.genre_hint}\n"
        )

        try:
            result = await run_one_shot(
                system_prompt=system,
                user_prompt=user,
                cwd=self.project_path,
                permission_mode="bypassPermissions",
                stream_log_path=_stream_log_path(self.project_path, "script_to_scenes"),
            )
        except ClaudeRunnerError as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"script_to_scenes failed: {exc}") from exc

        if not target_path.exists():
            err = (
                f"script_to_scenes did not write {target_path}. "
                f"Final assistant text was: {result.text[:300]!r}"
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        # Validate JSON parseability + collect summary stats for the snapshot.
        try:
            plan_data = json.loads(target_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            err = f"script_to_scenes wrote invalid JSON: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        sections = plan_data.get("sections", {}) or {}
        section_count = len(sections)
        scene_count = sum(len(v) for v in sections.values() if isinstance(v, list))
        type_counts: dict[str, int] = {}
        for scenes in sections.values():
            if not isinstance(scenes, list):
                continue
            for s in scenes:
                t = s.get("visual_type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

        scene_plan_text = target_path.read_text(encoding="utf-8")

        _snapshot_history(
            self.project_path,
            record.step_num,
            "script_to_scenes",
            {
                "scene_plan.json": scene_plan_text,
                "reasoning.md": (
                    f"# Step {record.step_num}: script_to_scenes\n\n"
                    f"- Claude CLI elapsed: {result.elapsed_seconds:.1f}s\n"
                    f"- Stream events: {result.event_count}\n"
                    f"- Sections: {section_count}\n"
                    f"- Total scenes: {scene_count}\n"
                    f"- Visual-type distribution: {type_counts}\n"
                    f"- Structure template used: "
                    f"{sp_id or '(none — fallback invention)'}\n"
                ),
            },
        )

        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = "checkpoint_after_script_to_scenes"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            f"script_to_scenes ran in {result.elapsed_seconds:.1f}s "
            f"({result.event_count} stream events).",
            f"Produced {scene_count} scenes across {section_count} sections.",
            f"Visual-type distribution: {type_counts}",
            f"`scene_plan.json` saved to project root; "
            f"snapshot in `.orchestrator/history/step_{record.step_num:02d}_script_to_scenes/`.",
        ]
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    async def _run_slide_designer_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        record = state_mod.append_step(state, "slide_designer")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        scene_plan_path = self.project_path / "scene_plan.json"
        style_guide_path = self.project_path / "style_guide.md"
        renderer_scenes_dir = self.repo_root / "src" / "nolan" / "renderer" / "scenes"
        target_report_path = (
            _orchestrator_dir(self.project_path)
            / "modules" / "slide_designer" / "last_report.md"
        )
        target_report_path.parent.mkdir(parents=True, exist_ok=True)
        if target_report_path.exists():
            target_report_path.unlink()

        if not scene_plan_path.exists():
            err = "scene_plan.json missing — slide_designer needs scenes to design."
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)
        if not style_guide_path.exists():
            err = "style_guide.md missing — slide_designer needs style context."
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        # Snapshot the count of info-scenes needing layout BEFORE the run, so
        # we can confirm afterward that the agent processed them.
        before_missing = self._info_scenes_missing_layout()

        system = handoff("orchestrator.slide-designer")
        user = (
            f"# scene_plan_path\n`{path_for_agent(scene_plan_path)}`\n\n"
            f"# style_guide_path\n`{path_for_agent(style_guide_path)}`\n\n"
            f"# target_report_path\n`{path_for_agent(target_report_path)}`\n\n"
            f"# renderer_scenes_dir\n`{path_for_agent(renderer_scenes_dir)}`\n\n"
            f"# Project metadata\n"
            f"- slug: {ctx.slug}\n"
            f"- name: {ctx.name}\n"
            f"- description: {ctx.description}\n"
            f"- duration_seconds: {ctx.duration_seconds}\n\n"
            f"# Pre-run summary\n"
            f"- info-scenes missing layout_spec: {before_missing}\n"
        )

        try:
            result = await run_one_shot(
                system_prompt=system,
                user_prompt=user,
                cwd=self.project_path,
                permission_mode="bypassPermissions",
                stream_log_path=_stream_log_path(self.project_path, "slide_designer"),
            )
        except ClaudeRunnerError as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"slide_designer failed: {exc}") from exc

        if not target_report_path.exists():
            err = (
                f"slide_designer did not write report at {target_report_path}. "
                f"Final assistant text was: {result.text[:300]!r}"
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        # Recount + capture per-template stats from the updated scene_plan.
        after_missing = self._info_scenes_missing_layout()
        template_counts: dict[str, int] = {}
        try:
            updated_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
            for scenes in (updated_plan.get("sections") or {}).values():
                if not isinstance(scenes, list):
                    continue
                for s in scenes:
                    if not isinstance(s, dict):
                        continue
                    spec = s.get("layout_spec") or {}
                    if isinstance(spec, dict) and spec.get("template"):
                        t = spec["template"]
                        template_counts[t] = template_counts.get(t, 0) + 1
        except json.JSONDecodeError as exc:
            err = f"slide_designer wrote invalid JSON to scene_plan.json: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        report_body = target_report_path.read_text(encoding="utf-8")
        scene_plan_text = scene_plan_path.read_text(encoding="utf-8")

        _snapshot_history(
            self.project_path,
            record.step_num,
            "slide_designer",
            {
                "scene_plan.json": scene_plan_text,
                "report.md": report_body,
                "reasoning.md": (
                    f"# Step {record.step_num}: slide_designer\n\n"
                    f"- Claude CLI elapsed: {result.elapsed_seconds:.1f}s\n"
                    f"- Stream events: {result.event_count}\n"
                    f"- Info-scenes missing layout before: {before_missing}\n"
                    f"- Info-scenes missing layout after: {after_missing}\n"
                    f"- Templates assigned (counts): {template_counts}\n"
                ),
            },
        )

        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = "checkpoint_after_slide_designer"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            f"slide_designer ran in {result.elapsed_seconds:.1f}s "
            f"({result.event_count} stream events).",
            f"Layout specs assigned: {before_missing - after_missing}; "
            f"still missing: {after_missing}.",
            f"Template distribution: {template_counts}",
            f"Report at `.orchestrator/modules/slide_designer/last_report.md`.",
            f"Snapshot in `.orchestrator/history/step_{record.step_num:02d}_slide_designer/`.",
        ]
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    async def _run_select_clips_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        record = state_mod.append_step(state, "select_clips")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        scene_plan_path = self.project_path / "scene_plan.json"
        style_guide_path = self.project_path / "style_guide.md"
        if not scene_plan_path.exists():
            err = "scene_plan.json missing — script_to_scenes must run first."
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)
        if not style_guide_path.exists():
            err = "style_guide.md missing — match_and_adapt_style must complete first."
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        report_path = (
            _orchestrator_dir(self.project_path)
            / "modules"
            / "clip_selector"
            / "last_report.md"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if report_path.exists():
            report_path.unlink()

        # Consolidated clip selection: use the fast semantic vector matcher instead
        # of a full LLM re-selection pass. The vector matcher reads the same
        # embeddings an LLM would, is ~free and near-instant, and writes
        # matched_clip into scene_plan.json directly. (Was a ~12-min Claude pass.)
        try:
            from nolan.config import load_config
            from nolan.cli_legacy import _match_clips
            from nolan.scenes import ScenePlan as _ScenePlan

            await _match_clips(
                load_config(), str(scene_plan_path),
                candidates=None, min_similarity=None, project=None,
                skip_existing=False, dry_run=False, search_level=None, concurrency=8,
            )
            _plan = _ScenePlan.load(str(scene_plan_path))
            _scenes = _plan.all_scenes
            _matched = sum(1 for s in _scenes if getattr(s, "matched_clip", None))
            report_path.write_text(
                "# Clip Selection Report (vector matcher)\n\n"
                f"Matched **{_matched}/{len(_scenes)}** scenes to library clips via semantic "
                "vector search.\n\n"
                "Consolidated step: this replaces the previous LLM clip-selection pass "
                "(~12 min) with the fast vector matcher (seconds, no token cost). The "
                "vector matcher ranks by embedding similarity over the same segment "
                "descriptions an LLM would read.\n",
                encoding="utf-8",
            )
        except Exception as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"clip selection (vector) failed: {exc}") from exc

        report_body = report_path.read_text(encoding="utf-8")
        scene_plan_after = scene_plan_path.read_text(encoding="utf-8")

        _snapshot_history(
            self.project_path,
            record.step_num,
            "select_clips",
            {
                "report.md": report_body,
                "scene_plan.json": scene_plan_after,
                "reasoning.md": (
                    f"# Step {record.step_num}: select_clips\n\n"
                    f"Matched via fast semantic vector search (no Claude pass).\n\n"
                    f"## Report\n\n{report_body}\n"
                ),
            },
        )

        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = "checkpoint_after_select_clips"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            "clip_selector matched scenes via fast semantic vector search.",
            f"Report at `.orchestrator/modules/clip_selector/last_report.md`.",
            f"`scene_plan.json` updated in place; snapshot in "
            f"`.orchestrator/history/step_{record.step_num:02d}_select_clips/`.",
        ]
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    async def _run_tempo_enrich_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Editorial Arc post-pass: annotate the scene plan with rhythm (energy/transition/
        motion_speed) using WHOLE-SCRIPT context. Deterministic, no agent — runs after
        script_to_scenes so downstream motion/asset choices can read the arc. See
        nolan.tempo_plan / nolan.script_context."""
        record = state_mod.append_step(state, "tempo_enrich")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        scene_plan_path = self.project_path / "scene_plan.json"
        if not scene_plan_path.exists():
            err = "scene_plan.json missing — script_to_scenes must run first."
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        def _enrich() -> dict:
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            from nolan.scenes import ScenePlan
            from nolan.script_context import ScriptContext
            from nolan.tempo_plan import design_tempo, apply_to_plan, profile_for

            sctx = ScriptContext.load(self.project_path)
            plan = ScenePlan.load(str(scene_plan_path))
            profile = profile_for(sctx)
            if not sctx.beats:
                return {"beats": 0, "profile": profile, "source": "skipped",
                        "applied": {"sections": 0, "scenes": 0, "matched": 0}, "tempo": None}
            try:
                llm = create_text_llm(load_config())
            except Exception:
                llm = None
            tempo = design_tempo(sctx, llm=llm)
            # Tempo cloning: when the project carries an attached/cloned
            # deconstruction (reference_structure.json), blend the reference
            # video's MEASURED energy curve with the script-derived one.
            ref_path = self.project_path / "scriptgen" / "reference_structure.json"
            if ref_path.exists():
                try:
                    import json as _json
                    from nolan.tempo_plan import blend_with_reference
                    tempo = blend_with_reference(
                        tempo, _json.loads(ref_path.read_text(encoding="utf-8")))
                except Exception:
                    pass  # the reference is an enhancement, never a blocker
            applied = apply_to_plan(plan, tempo)
            plan.save(str(scene_plan_path))
            return {"beats": len(sctx.beats), "profile": profile, "source": tempo.source,
                    "applied": applied, "tempo": tempo.to_dict()}

        try:
            result = await asyncio.to_thread(_enrich)
        except Exception as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"tempo_enrich failed: {exc}") from exc

        applied = result["applied"]
        # human-readable report of the arc
        lines = [f"# Tempo Enrich Report", "",
                 f"Profile **{result['profile']}** · arc source **{result['source']}** · "
                 f"annotated **{applied['matched']}/{applied['scenes']}** scenes across "
                 f"{applied['sections']} sections.", ""]
        if result["tempo"]:
            lines.append("| beat | energy | pace | transition | motion |")
            lines.append("|---|---|---|---|---|")
            for b in result["tempo"]["beats"]:
                lines.append(f"| {b['title'][:40]} | {b['energy']:.2f} | {b['pace_dir']} | "
                             f"{b['transition']} | {b['motion_speed']} |")
        else:
            lines.append("_No script beats found (no script.md headings) — tempo skipped._")
        report_body = "\n".join(lines) + "\n"
        report_path = (_orchestrator_dir(self.project_path) / "modules" / "tempo_enrich"
                       / "last_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_body, encoding="utf-8")

        _snapshot_history(
            self.project_path, record.step_num, "tempo_enrich",
            {"report.md": report_body,
             "scene_plan.json": scene_plan_path.read_text(encoding="utf-8"),
             "reasoning.md": (f"# Step {record.step_num}: tempo_enrich\n\n"
                              "Whole-script Editorial Arc pass — wrote per-scene energy / "
                              "transition / motion_speed (the levers script_to_scenes leaves "
                              f"flat).\n\n{report_body}")},
        )

        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = "checkpoint_after_tempo_enrich"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            f"tempo_enrich annotated {applied['matched']}/{applied['scenes']} scenes with the "
            f"editorial arc ({result['profile']} profile, {result['source']}).",
            "`scene_plan.json` gained per-scene `energy` / `transition` / `motion_speed`.",
            f"Report at `.orchestrator/modules/tempo_enrich/last_report.md`.",
        ]
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)


def _find_repo_root(start: Path) -> Path:
    current = start
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "src" / "nolan").exists():
            return current
        current = current.parent
    return start


async def run(project_path: Path, repo_root: Path | None = None) -> Path:
    director = Director(project_path, repo_root=repo_root)
    return await director.run_next_step()


def run_sync(project_path: Path, repo_root: Path | None = None) -> Path:
    return asyncio.run(run(project_path, repo_root))


async def run_refine(
    project_path: Path,
    target_step: str,
    repo_root: Path | None = None,
) -> Path:
    director = Director(project_path, repo_root=repo_root)
    return await director.run_refine_step(target_step)


def run_refine_sync(
    project_path: Path,
    target_step: str,
    repo_root: Path | None = None,
) -> Path:
    return asyncio.run(run_refine(project_path, target_step, repo_root))


async def run_auto(
    project_path: Path,
    repo_root: Path | None = None,
) -> list[Path]:
    director = Director(project_path, repo_root=repo_root)
    return await director.run_auto()


def run_auto_sync(
    project_path: Path,
    repo_root: Path | None = None,
) -> list[Path]:
    return asyncio.run(run_auto(project_path, repo_root))
