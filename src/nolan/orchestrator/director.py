"""Director — Layer 2 orchestrator.

v1 scope: first-pass template matching → adapt or invent → write style_guide.md
→ checkpoint → exit. No specialists, no refine flow yet.

See docs/plans/2026-04-26-two-layer-orchestrator.md.
"""

from __future__ import annotations

import asyncio
import logging
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
logger = logging.getLogger(__name__)

PIPELINE_STEPS = [
    "match_and_adapt_style",
    "script_to_scenes",
    "tempo_enrich",
    "select_clips",
    "slide_designer",
    "motion_design",
    "generate_assets",
    "voiceover",
    "align_narration",
    "soundtrack",
    "render",
]

# infographic joined when the block library grew real chart/table/diagram
# templates (bar_chart, line_chart, data_table, loop_diagram, …) — before
# that, 7 infographic scenes in a premium plan had no layout path at all.
INFO_SCENE_TYPES = {"text-overlay", "graphic", "infographic"}


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


def _pinned_reference_template(project_path: Path,
                               repo_root: Path) -> TemplateCandidate | None:
    """The scene-plan template exported from this project's attached
    deconstruction (matched via template meta provenance), or None.

    A cloned/attached project names its intended structure explicitly, so the
    matcher's open scoring — which e.g. penalizes a duration mismatch with the
    SOURCE video's length — must not override it.
    """
    import json
    meta_path = project_path / "scriptgen" / "meta.json"
    if not meta_path.exists():
        return None
    try:
        dec = json.loads(meta_path.read_text(encoding="utf-8")).get(
            "cloned_from_deconstruction")
    except Exception:
        return None
    if not dec:
        return None
    root = repo_root / "assets" / "templates" / "scene_plans"
    if not root.exists():
        return None
    for tdir in sorted(root.iterdir()):
        mp = tdir / "meta.json"
        if not mp.exists():
            continue
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (m.get("provenance") or {}).get("derived_from_deconstruction") == dec:
            return TemplateCandidate(
                template_id=m.get("id", tdir.name),
                version=int(m.get("version", 1)),
                name=m.get("name", tdir.name), kind="scene_plan", score=1.0,
                score_breakdown={"pinned_by_reference": 1.0},
                template_dir=tdir, summary=m.get("summary", ""))
    return None


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
        if next_name == "motion_design":
            return await self._run_motion_design_step(ctx, state)
        if next_name == "generate_assets":
            return await self._run_generate_assets_step(ctx, state)
        if next_name == "voiceover":
            return await self._run_voiceover_step(ctx, state)
        if next_name == "align_narration":
            return await self._run_align_narration_step(ctx, state)
        if next_name == "soundtrack":
            return await self._run_soundtrack_step(ctx, state)
        if next_name == "render":
            return await self._run_render_step(ctx, state)
        raise DirectorError(f"unknown pipeline step: {next_name}")

    # Artifact-presence-gated steps: redoing one must also remove the artifact
    # that marks it "done", or the scheduler skips it. Steps absent here are
    # gated purely by step_history.
    _REDO_ARTIFACTS = {
        "match_and_adapt_style": ["style_guide.md", "brief.json"],
        "script_to_scenes": ["scene_plan.json"],
        "voiceover": ["assets/voiceover/voiceover.mp3"],
        "soundtrack": ["soundtrack.json"],
        "render": ["output/final.mp4"],
    }

    def redo_step(self, step: str) -> list:
        """Reset one step so the scheduler runs it again. Returns notes.

        Removes the step's history records and deletes its presence-gating
        artifact(s). DESTRUCTIVE for authoring steps: redoing
        script_to_scenes regenerates the plan from scratch (downstream
        enrichment on the old plan is gone); redoing the style step discards
        the current guide + brief. A locked artifact (e.g. final.mp4 open in
        a player) fails LOUDLY instead of leaving half-reset state."""
        if step not in PIPELINE_STEPS:
            raise DirectorError(
                f"unknown step {step!r} — one of {PIPELINE_STEPS}")
        notes = []
        # delete gating artifacts FIRST: if one is locked we abort before
        # touching history, so the state stays consistent
        for rel in self._REDO_ARTIFACTS.get(step, []):
            p = self.project_path / rel
            if p.exists():
                try:
                    p.unlink()
                except OSError as exc:
                    raise DirectorError(
                        f"cannot redo {step}: {rel} is locked ({exc}) — "
                        "close whatever holds it open and retry")
                notes.append(f"deleted {rel}")
        state = state_mod.load_state(self.project_path)
        before = len(state.step_history)
        state.step_history = [s for s in state.step_history if s.name != step]
        removed = before - len(state.step_history)
        state.status = "awaiting_review"
        state_mod.save_state(self.project_path, state)
        notes.append(f"removed {removed} history record(s) for '{step}'")
        return notes

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
        if ("motion_design" not in completed
                and (self.project_path / "scene_plan.json").exists()):
            return "motion_design"
        if ("generate_assets" not in completed
                and self._generated_scenes_missing_asset() > 0):
            return "generate_assets"
        voiceover_mp3 = (
            self.project_path / "assets" / "voiceover" / "voiceover.mp3"
        )
        # Artifact-presence: a hand-made (or webUI-made) voiceover is respected.
        if "voiceover" not in completed and not voiceover_mp3.exists():
            return "voiceover"
        if "align_narration" not in completed and voiceover_mp3.exists():
            return "align_narration"
        # Artifact-presence: a hand-authored/edited soundtrack.json is respected.
        if ("soundtrack" not in completed
                and not (self.project_path / "soundtrack.json").exists()):
            return "soundtrack"
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

    async def _run_soundtrack_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """AUTHOR the soundtrack (the reviewable decision, no audio touched).

        Writes soundtrack.json — chosen track, the runner-up candidates,
        gain/duck/fade parameters, and SFX event placements at the beat
        boundaries. Review/edit it (or swap `track` to an alternative) before
        the render step EXECUTES it. Skips with a note when project.yaml has
        no `music:` — the final simply carries narration only.
        """
        from nolan.audio_mix import author_soundtrack, resolve_music_config, save_soundtrack

        record = state_mod.append_step(state, "soundtrack")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        cfg = resolve_music_config(self.project_path)
        if not cfg["enabled"]:
            note = ("skipped — no music configured (set `music: auto` or a "
                    "track path in project.yaml); final will carry narration only.")
            state_mod.finish_step(record, status="completed", notes=note)
            state.status = "awaiting_review"
            state_mod.save_state(self.project_path, state)
            return _write_checkpoint(self.project_path, record.step_num, [note])

        try:
            plan = json.loads(
                (self.project_path / "scene_plan.json").read_text(encoding="utf-8"))
            spec = author_soundtrack(
                plan, music=cfg["music"], music_gain_db=cfg["gain"],
                sfx=cfg["sfx"], mood=cfg["mood"],
                sfx_provider=cfg.get("sfx_provider", "freesound"))
            spec_path = save_soundtrack(spec, self.project_path)
        except Exception as exc:
            err = f"soundtrack authoring failed: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err) from exc

        alts = ", ".join(a["file"] for a in spec.get("alternatives", [])) or "none"
        summary = [
            f"Soundtrack authored: **{spec['track']['file']}** "
            f"({spec['track']['source']}), {len(spec.get('sfx_events', []))} "
            f"transition sfx, gain {spec['music_gain_db']} dB.",
            f"Alternatives: {alts}.",
            f"Review/edit `{spec_path.name}` (swap track, drop sfx events, "
            "adjust gain/duck) — the render step executes it as written.",
        ]
        state_mod.finish_step(record, status="completed", notes=summary[0])
        state.status = "awaiting_review"
        state_mod.save_state(self.project_path, state)
        return _write_checkpoint(self.project_path, record.step_num, summary)

    def _mix_soundtrack_if_configured(self, final: Path, scene_plan: dict) -> str:
        """EXECUTE the authored soundtrack.json against the finished cut.

        Falls back to ad-hoc author+mix when a project opted into music but
        has no spec (pre-step projects). A failure is reported loudly in the
        step notes but never destroys the (already correct) narrated video.
        """
        from nolan.audio_mix import (
            load_soundtrack, measure_sfx_audibility, mix_from_spec,
            mix_soundtrack, resolve_music_config,
        )

        spec = load_soundtrack(self.project_path)
        cfg = resolve_music_config(self.project_path)
        if spec is None and not cfg["enabled"]:
            return ""
        try:
            if spec is not None:
                mix_from_spec(final, spec)
                # verify like an editor: measure that authored events are
                # actually audible in the mix, and SAY so in the checkpoint
                checks = measure_sfx_audibility(final, spec)
                dead = [c for c in checks if not c["audible"]]
                note = f" + soundtrack ({spec['track']['file']}"
                if checks:
                    note += (f"; sfx {len(checks) - len(dead)}/{len(checks)} audible"
                             + (f" — INAUDIBLE: "
                                + ", ".join(f"{c['kind']}@{c['t']}s" for c in dead[:4])
                                + " — raise volumes in soundtrack.json"
                                if dead else ""))
                return note + ")"
            mix_soundtrack(final, scene_plan, music=cfg["music"],
                           music_gain_db=cfg["gain"], sfx=cfg["sfx"],
                           mood=cfg["mood"],
                           sfx_provider=cfg.get("sfx_provider", "freesound"))
            return " + music/sfx soundtrack (ad-hoc — no soundtrack.json)"
        except Exception as exc:
            logger.warning("soundtrack mix failed: %s", exc)
            return f" (soundtrack mix FAILED: {exc})"

    def _generated_scenes_missing_asset(self) -> int:
        """Count 'generated' scenes whose ComfyUI image doesn't exist yet."""
        plan_path = self.project_path / "scene_plan.json"
        if not plan_path.exists():
            return 0
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return 0
        gen_dir = self.project_path / "assets" / "generated"
        count = 0
        for scenes in (plan.get("sections") or {}).values():
            if not isinstance(scenes, list):
                continue
            for s in scenes:
                if not isinstance(s, dict):
                    continue
                if s.get("visual_type") not in ("generated", "generated-image"):
                    continue
                if s.get("skip_generation"):
                    continue
                asset = s.get("generated_asset") or f"{s.get('id')}.png"
                if not (gen_dir / asset).exists():
                    count += 1
        return count

    def _write_idle_checkpoint(self, state: state_mod.DirectorState) -> Path:
        completed = [s.name for s in state.step_history if s.status == "completed"]
        summary = [
            f"All known pipeline steps already completed: {completed}",
            "To advance further, build/enable the next specialist or use "
            "`--redo <step>` to reset + re-run one step.",
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
        """Match a style template to the script and adapt it into the project style guide."""
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

        # Reference pin: a project cloned from / attached to a deconstruction
        # names its intended structure. If that deconstruction was exported as
        # a scene-plan template, PIN it — open scoring must not override an
        # explicit reference (e.g. on duration mismatch with the source video).
        pinned = _pinned_reference_template(self.project_path, self.repo_root)
        if pinned is not None:
            chosen_scene = pinned
            scene_reason = "pinned by the project's attached deconstruction reference"

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

        # Compile the brief: the guide is prose for humans/script agents; the
        # render side needs DECISIONS. brief.json carries theme (explainable
        # selector pick), accent, music mood, voice — validated, reviewable
        # in the Step Inspector, consumed by render/soundtrack/voiceover.
        try:
            from nolan.project_brief import compile_brief, save_brief
            from nolan.config import load_config
            from nolan.llm import create_text_llm
            _llm = None
            try:
                _llm = create_text_llm(load_config())
            except Exception:
                _llm = None
            _brief = await compile_brief(self.project_path, llm=_llm,
                                         style_guide=style_guide)
            save_brief(self.project_path, _brief)
            summary_lines.append(
                f"Brief compiled: theme **{_brief['theme']}** "
                f"({'; '.join(_brief['theme_why'][:4])}) · "
                f"mood '{_brief['music_mood']}' · voice "
                f"{_brief['voice_id'] or '(default)'} · accent "
                f"{_brief['accent'] or '(theme)'} — `brief.json` "
                f"(alternatives: "
                f"{', '.join(a['id'] for a in _brief['theme_alternatives'])})")
        except Exception as exc:
            # a failed compile must be VISIBLE but not sink the style step
            summary_lines.append(f"Brief compile FAILED: {exc} — render will "
                                 "fall back to defaults until re-run.")

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

    async def _run_generate_assets_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Generate ComfyUI imagery for every 'generated' scene missing its PNG.

        Reuses the proven CLI generator (`_generate_images`, registry-default
        workflow = krea2 + configured style) one scene at a time so partial
        progress persists and re-runs only fill gaps. Fails honestly when
        ComfyUI is unreachable — black-frame gaps must not ship silently.
        """
        from nolan.cli_legacy import _generate_images
        from nolan.comfyui import ComfyUIClient
        from nolan.config import load_config
        from nolan.scenes import ScenePlan

        record = state_mod.append_step(state, "generate_assets")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        config = load_config()
        plan_path = self.project_path / "scene_plan.json"
        plan = ScenePlan.load(str(plan_path))
        gen_dir = self.project_path / "assets" / "generated"
        pending = [
            s for s in plan.all_scenes
            if s.visual_type in ("generated", "generated-image")
            and not s.skip_generation
            and not (gen_dir / (s.generated_asset or f"{s.id}.png")).exists()
        ]

        if not pending:
            note = "no generated scenes pending — nothing to do"
            state_mod.finish_step(record, status="completed", notes=note)
            state.status = "awaiting_review"
            state_mod.save_state(self.project_path, state)
            return _write_checkpoint(self.project_path, record.step_num, [note])

        client = ComfyUIClient(host=config.comfyui.host, port=config.comfyui.port)
        if not await client.check_connection():
            err = (
                f"ComfyUI unreachable at {config.comfyui.host}:"
                f"{config.comfyui.port} with {len(pending)} scenes to generate "
                "— start ComfyUI and re-run, or set skip_generation on scenes."
            )
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        # Style cohesion: distilled style_guide suffix on every prompt (same
        # behavior as the webUI Generate op).
        style_suffix = ""
        try:
            from nolan.webui.operations import _distill_style_suffix
            style_suffix = await _distill_style_suffix(
                config, self.project_path / "style_guide.md")
        except Exception as exc:
            logger.warning("style suffix distillation failed: %s", exc)

        failures: list[str] = []
        for scene in pending:
            try:
                await _generate_images(
                    config, self.project_path, scene.id,
                    prompt_suffix=style_suffix)
            except Exception as exc:
                failures.append(f"{scene.id}: {exc}")
        still_missing = self._generated_scenes_missing_asset()

        summary = [
            f"Generated {len(pending) - still_missing}/{len(pending)} pending "
            f"scenes via ComfyUI (registry workflow"
            f"{' + style suffix' if style_suffix else ''}).",
        ]
        if failures:
            summary.append(f"Failures: {failures[:5]}")
        status = "completed" if still_missing == 0 else "error"
        state_mod.finish_step(
            record, status=status, notes=" | ".join(summary))
        state.status = "awaiting_review" if status == "completed" else "error"
        state_mod.save_state(self.project_path, state)
        if status == "error":
            raise DirectorError(
                f"{still_missing} generated scenes still missing images: "
                + "; ".join(failures[:5]))
        return _write_checkpoint(self.project_path, record.step_num, summary)

    async def _run_voiceover_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Narrate the script with local TTS (shared `nolan.voice_pipeline` core).

        Voice resolution: the SAME ladder every pipeline uses
        (`nolan.voiceover.resolve_voice_ref`): project.yaml `voice_id` →
        config `tts.default_voice` → skip with a clear note (final stays
        silent). Full mode leaves per-section anchors in
        assets/voiceover/_work/ which the align step uses for beat-exact sync.
        """
        from nolan.config import load_config
        from nolan.voiceover import resolve_voice_ref

        record = state_mod.append_step(state, "voiceover")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        config = load_config()
        ref_audio, ref_text, voice_id = resolve_voice_ref(
            self.project_path, config)

        if not config.tts.enabled or not voice_id:
            note = (
                "skipped — "
                + ("TTS disabled in nolan.yaml" if not config.tts.enabled
                   else "no voice resolved (set voice_id: in project.yaml "
                        "or tts.default_voice in nolan.yaml; the voice must "
                        "exist in the voice library)")
                + "; final video will be silent."
            )
            state_mod.finish_step(record, status="completed", notes=note)
            state.status = "awaiting_review"
            state_mod.save_state(self.project_path, state)
            return _write_checkpoint(self.project_path, record.step_num, [note])

        from nolan.voice_pipeline import synthesize_voiceover

        kind = ("script_project"
                if (self.project_path / "script.md").exists() else "project")
        try:
            result = await synthesize_voiceover(
                config=config,
                project_dir=self.project_path,
                log=lambda msg: logger.info("voiceover: %s", msg),
                ref_audio=ref_audio,
                ref_text=ref_text,
                **{kind: ctx.slug},
            )
        except Exception as exc:
            err = f"voiceover synthesis failed: {type(exc).__name__}: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err) from exc

        summary = [
            f"Voiceover ready: {result.get('sections')} sections, voice "
            f"'{voice_id}' → {result.get('voiceover')}",
        ]
        if result.get("missing"):
            summary.append(f"Sections with no audio: {result['missing']}")
        state_mod.finish_step(record, status="completed",
                              notes=" | ".join(summary))
        state.status = "awaiting_review"
        state_mod.save_state(self.project_path, state)
        return _write_checkpoint(self.project_path, record.step_num, summary)

    async def _run_align_narration_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Beat-anchor scene timings to the narration (`nolan align`).

        Shells out to the proven aligner: per-section wavs in
        assets/voiceover/_work/ pin each section's exact audio span; whisper
        refines scene boundaries within them; windows are tiled gap-free so
        video ≡ narration and sync errors cannot cross beats.
        """
        import subprocess
        import sys

        record = state_mod.append_step(state, "align_narration")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        plan_path = self.project_path / "scene_plan.json"
        audio_path = self.project_path / "assets" / "voiceover" / "voiceover.mp3"
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "nolan", "align",
             str(plan_path), str(audio_path)],
            cwd=str(self.repo_root), capture_output=True, text=True,
        )
        if proc.returncode != 0:
            err = ("`nolan align` failed (rc=%d): %s" % (
                proc.returncode, (proc.stderr or proc.stdout).strip()[:800]))
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        tail = (proc.stdout or "").strip().splitlines()[-6:]
        summary = ["Scene timings aligned to narration (beat-anchored)."] + tail
        state_mod.finish_step(record, status="completed",
                              notes=summary[0])
        state.status = "awaiting_review"
        state_mod.save_state(self.project_path, state)
        return _write_checkpoint(self.project_path, record.step_num, summary)

    async def _run_render_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Render every scene to per-scene MP4s and assemble a final video.

        Assembles WITH the project narration (assets/voiceover/voiceover.mp3,
        produced by the voiceover step and beat-aligned by align_narration)
        when it exists; falls back to silent audio for voice-less projects.
        See `src/nolan/orchestrator/render.py`.
        """
        from nolan.orchestrator import render as render_mod

        record = state_mod.append_step(state, "render")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        # Retention lint (SOTA #4): the plan is final here — measure it for
        # attention rot (treatment monotony, energy plateaus, pacing vs the
        # brief) and REPORT. Findings never block the render.
        lint_note = ""
        try:
            from nolan.retention import lint_project, render_report
            lint = lint_project(self.project_path)
            rp = (_orchestrator_dir(self.project_path)
                  / "modules" / "retention" / "last_report.md")
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(render_report(lint, title=f"Retention lint — {ctx.slug}"),
                          encoding="utf-8")
            st = lint["stats"]
            lint_note = (f" · retention lint: {st.get('warn', 0)} warn / "
                         f"{st.get('info', 0)} info "
                         f"(`.orchestrator/modules/retention/last_report.md`)")
        except Exception as exc:
            lint_note = f" · retention lint FAILED: {exc}"

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

        # Premium render mode (project.yaml: render_mode: premium): every beat
        # renders as ONE Remotion Chapter with baked per-scene VO — FLOW's
        # driver fed from the scene plan. Explicit opt-in fails honestly when
        # a scene can't map to a Chapter block (no silent fallback).
        render_mode = None
        try:
            _meta = yaml.safe_load(
                (self.project_path / "project.yaml").read_text(encoding="utf-8"))
            if isinstance(_meta, dict):
                render_mode = _meta.get("render_mode")
        except Exception:
            pass
        if render_mode == "premium":
            from nolan.premium_render import PremiumIneligible, render_premium
            try:
                final = render_premium(self.project_path, output=final_video_path)
            except PremiumIneligible as exc:
                err = f"premium render not possible: {exc}"
                state_mod.finish_step(record, status="error", notes=err)
                state.status = "error"
                state_mod.save_state(self.project_path, state)
                raise DirectorError(err) from exc
            except Exception as exc:
                err = f"premium render failed: {type(exc).__name__}: {exc}"
                state_mod.finish_step(record, status="error", notes=err)
                state.status = "error"
                state_mod.save_state(self.project_path, state)
                raise DirectorError(err) from exc
            size_mb = final.stat().st_size / (1024 * 1024)
            note = (f"premium render: {len(scene_plan.get('sections') or {})} "
                    f"beat Chapters -> {final.name} ({size_mb:.1f} MB)")
            try:                       # beat-cache honesty: reuse is REPORTED
                stats = json.loads((self.project_path / "assets" / "premium"
                                    / "beats" / "last_run.json")
                                   .read_text(encoding="utf-8"))
                if stats.get("draft"):
                    note += " [DRAFT — half-res, no word-sync, no gate]"
                elif stats.get("reused"):
                    note += (f" [beats: {stats['rendered']} rendered, "
                             f"{stats['reused']} reused from cache]")
            except Exception:
                pass
            note += self._mix_soundtrack_if_configured(final, scene_plan)
            note += lint_note
            state_mod.finish_step(record, status="completed", notes=note)
            state.status = "awaiting_review"
            state_mod.save_state(self.project_path, state)
            return _write_checkpoint(self.project_path, record.step_num, [note])

        scratch = _orchestrator_dir(self.project_path) / "modules" / "render"
        scratch.mkdir(parents=True, exist_ok=True)
        silent_audio_path = scratch / "silent.wav"
        report_path = scratch / "last_report.md"

        # 0. Tempo→motion: give image-backed stills a still-motion spec driven
        # by their authored (reference-blended) energy, so they render as
        # motion clips at the planned rhythm instead of assemble's generic
        # Ken Burns.
        try:
            stamped = render_mod.stamp_tempo_motions(scene_plan, self.project_path)
        except Exception as stamp_exc:
            stamped = 0
            logger.warning("tempo-motion stamping failed: %s", stamp_exc)

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

        # 3. Pick the audio track: real narration when it exists, else silence.
        voiceover_path = (
            self.project_path / "assets" / "voiceover" / "voiceover.mp3"
        )
        if voiceover_path.exists():
            audio_path = voiceover_path
            audio_note = f"narration ({voiceover_path.name})"
        else:
            try:
                render_mod.generate_silent_audio(total_duration, silent_audio_path)
            except render_mod.RenderError as exc:
                err = f"silent audio generation failed: {exc}"
                state_mod.finish_step(record, status="error", notes=err)
                state.status = "error"
                state_mod.save_state(self.project_path, state)
                raise DirectorError(err) from exc
            audio_path = silent_audio_path
            audio_note = "silent (no voiceover generated)"

        # 4. Shell out to `nolan assemble` for the final stitch.
        try:
            render_mod.call_assemble(
                project_path=self.project_path,
                scene_plan_path=scene_plan_path,
                audio_path=audio_path,
                output_path=final_video_path,
                repo_root=self.repo_root,
            )
        except render_mod.RenderError as exc:
            err = f"assemble failed: {exc}"
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err) from exc

        # 4b. Sound design (project.yaml `music:`): ducked music bed +
        # transition sfx laid under the finished cut, in place.
        audio_note += self._mix_soundtrack_if_configured(
            final_video_path, scene_plan)

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
                    f"- Audio: {audio_note}\n"
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
        """Turn script.md into the sectioned scene plan (the central artifact)."""
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
            + self._taste_guidance("scenes", state)
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

        # visual_type is matched by exact string downstream (scheduler,
        # slide_designer, asset engine, premium) — normalize LLM-invented
        # synonyms LOUDLY and fail on unmappable values, or every consumer
        # silently sees 0 eligible scenes (the silent-cascade bug class).
        from nolan.scenes import normalize_plan_visual_types
        vt_mapped, vt_unknown = normalize_plan_visual_types(plan_data)
        if vt_unknown:
            err = ("script_to_scenes used visual_type values outside the "
                   "canonical vocabulary and they can't be auto-mapped: "
                   + ", ".join(vt_unknown[:8]))
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)
        if vt_mapped:
            target_path.write_text(json.dumps(plan_data, indent=2,
                                              ensure_ascii=False),
                                   encoding="utf-8")

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
        if vt_mapped:
            summary_lines.insert(3, "Normalized non-canonical visual_type "
                                    f"values: {vt_mapped}")
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    async def _run_slide_designer_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Author layout_specs (the 23 templates) for info scenes."""
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
            + self._taste_guidance("slides", state)
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

    def _taste_guidance(self, stage: str, state=None) -> str:
        """Prompt block of learned channel taste for one authoring stage.

        video_type = the matched style template (the natural video-type key)
        when one matched, else the genre hint. Empty string when no rules —
        prompts stay clean until taste exists."""
        try:
            from nolan.taste import guidance_for
            vtype = ""
            if state is not None:
                vtype = (getattr(state.template_provenance,
                                 "style_template_id", None) or "")
            g = guidance_for(stage, vtype)
            return f"\n# Taste guidance\n{g}\n" if g else ""
        except Exception:
            return ""

    @staticmethod
    def _hostable_motion_catalog() -> str:
        """The motion umbrella as compact JSON — hostable effects only, with
        when_to_use + params. This is the motion_design agent's whole legal
        vocabulary (module contract: the authoring pass consumes the catalog)."""
        from nolan.motion.executor import _CHAPTER_TARGETS
        from nolan.motion.registry import REGISTRY

        def _params(plist):
            return {p.name: (p.doc or p.type) +
                    (f" [{'|'.join(map(str, p.values))}]" if p.values else "")
                    for p in plist}

        effects = []
        for e in REGISTRY:
            if e.backend == "block" or (e.backend == "remotion"
                                        and e.target in _CHAPTER_TARGETS):
                effects.append({
                    "effect": e.id, "purpose": e.purpose,
                    "when_to_use": e.when_to_use,
                    "content_params": _params(e.content),
                    "style_params": _params(e.style)})
        return json.dumps(effects, ensure_ascii=False, indent=1)

    def _validate_plan_motion_specs(self) -> tuple[dict, list[str]]:
        """(effect_counts, problems) for every motion_spec in the plan —
        the deterministic gate behind the motion_design agent."""
        from nolan.motion import chapter_step_for_spec
        counts: dict[str, int] = {}
        problems: list[str] = []
        try:
            plan = json.loads((self.project_path / "scene_plan.json")
                              .read_text(encoding="utf-8"))
        except Exception as exc:
            return {}, [f"scene_plan.json unreadable: {exc}"]
        for scenes in (plan.get("sections") or {}).values():
            if not isinstance(scenes, list):
                continue
            for s in scenes:
                ms = s.get("motion_spec") if isinstance(s, dict) else None
                if not (isinstance(ms, dict) and ms.get("effect")):
                    continue
                counts[ms["effect"]] = counts.get(ms["effect"], 0) + 1
                try:
                    hosted = chapter_step_for_spec(ms, self.project_path)
                except ValueError as exc:
                    problems.append(f"{s.get('id')}: {exc}")
                    continue
                if hosted is None:
                    problems.append(f"{s.get('id')}: effect "
                                    f"{ms['effect']!r} is not premium-hostable")
        return counts, problems

    def _human_directives(self) -> str:
        """Per-scene human notes (shortlist notes / pin notes) as a prompt
        section for the design passes. Human words carry HUMAN provenance:
        the agent follows them, it does not overrule them."""
        try:
            plan = json.loads((self.project_path / "scene_plan.json")
                              .read_text(encoding="utf-8"))
        except Exception:
            return ""
        lines = []
        for scenes in (plan.get("sections") or {}).values():
            if not isinstance(scenes, list):
                continue
            for s in scenes:
                note = (s.get("human_note") or
                        (s.get("pinned_asset") or {}).get("note") or "").strip()
                if note:
                    lines.append(f"- {s.get('id')}: {note}")
        if not lines:
            return ""
        return ("\n# Human directives (from the editor — FOLLOW these; they "
                "outrank your own judgment for the named scenes)\n"
                + "\n".join(lines) + "\n")

    async def _run_motion_design_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Author motion_specs from the catalog (the pass that SPENDS the motion library)."""
        record = state_mod.append_step(state, "motion_design")
        state.status = "running"
        state_mod.save_state(self.project_path, state)

        scene_plan_path = self.project_path / "scene_plan.json"
        style_guide_path = self.project_path / "style_guide.md"
        target_report_path = (
            _orchestrator_dir(self.project_path)
            / "modules" / "motion_design" / "last_report.md")
        target_report_path.parent.mkdir(parents=True, exist_ok=True)
        if target_report_path.exists():
            target_report_path.unlink()

        system = handoff("orchestrator.motion-designer")
        user = (
            f"# scene_plan_path\n`{path_for_agent(scene_plan_path)}`\n\n"
            f"# style_guide_path\n`{path_for_agent(style_guide_path)}`\n\n"
            f"# target_report_path\n`{path_for_agent(target_report_path)}`\n\n"
            f"# catalog_json (your whole legal vocabulary)\n"
            f"```json\n{self._hostable_motion_catalog()}\n```\n\n"
            f"# Project metadata\n- slug: {ctx.slug}\n- name: {ctx.name}\n"
            + self._human_directives()
            + self._taste_guidance("motion", state)
        )

        try:
            result = await run_one_shot(
                system_prompt=system,
                user_prompt=user,
                cwd=self.project_path,
                permission_mode="bypassPermissions",
                stream_log_path=_stream_log_path(self.project_path, "motion_design"),
            )
        except ClaudeRunnerError as exc:
            state_mod.finish_step(record, status="error", notes=str(exc))
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(f"motion_design failed: {exc}") from exc

        # Deterministic gate: every authored spec must validate AND be
        # premium-hostable; bad authoring fails the step by scene id.
        counts, problems = self._validate_plan_motion_specs()
        if problems:
            err = (f"motion_design authored {len(problems)} invalid spec(s): "
                   + "; ".join(problems[:6]))
            state_mod.finish_step(record, status="error", notes=err)
            state.status = "error"
            state_mod.save_state(self.project_path, state)
            raise DirectorError(err)

        report_body = (target_report_path.read_text(encoding="utf-8")
                       if target_report_path.exists() else "(no report written)")
        _snapshot_history(
            self.project_path,
            record.step_num,
            "motion_design",
            {
                "scene_plan.json": scene_plan_path.read_text(encoding="utf-8"),
                "report.md": report_body,
                "reasoning.md": (
                    f"# Step {record.step_num}: motion_design\n\n"
                    f"- Claude CLI elapsed: {result.elapsed_seconds:.1f}s\n"
                    f"- Motion specs authored (by effect): {counts}\n"
                ),
            },
        )

        state_mod.finish_step(record, status="completed")
        state.status = "awaiting_review"
        state.current_step = "checkpoint_after_motion_design"
        state_mod.save_state(self.project_path, state)

        summary_lines = [
            f"motion_design ran in {result.elapsed_seconds:.1f}s.",
            (f"Motion specs authored: {sum(counts.values())} ({counts}) — "
             "all validated + premium-hostable."
             if counts else
             "No motion specs authored — the agent judged the default "
             "treatments sufficient (restraint is allowed)."),
            f"Report at `.orchestrator/modules/motion_design/last_report.md`.",
        ]
        return _write_checkpoint(self.project_path, record.step_num, summary_lines)

    async def _run_select_clips_step(
        self,
        ctx: ProjectContext,
        state: state_mod.DirectorState,
    ) -> Path:
        """Resolve footage + archival-art scenes through the asset engine."""
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

        # Consolidated clip selection: ONE asset engine (nolan.asset_engine)
        # resolves footage scenes (library vector search → picture-library
        # stills) and archival-art scenes (exact-title museum pass → semantic
        # fallback). Every touched scene gets an auditable resolved_source.
        try:
            from nolan.asset_engine import (
                ART_TYPES, FOOTAGE_TYPES, AssetEngine, EngineConfig,
            )
            from nolan.config import load_config
            from nolan.scenes import ScenePlan as _ScenePlan

            _nolan_cfg = load_config()
            engine = AssetEngine.from_config(
                _nolan_cfg,
                # Selection only: no generation tags, no motion authoring —
                # slide_designer and generate_assets own those stages.
                # External stock (vision-gated images + materialized video) is
                # a full pipeline tier since the asset-ladder completion.
                config=EngineConfig(enable_generation=False,
                                    enable_motion=False,
                                    enable_external=True),
                project_path=self.project_path,
                # Scope the clip search to THIS project's associated sources.
                # The old global search let 0.5-cosine matches from unrelated
                # library videos beat the vision-gated stock tier (the 2-beat
                # rerun matched lecture footage to aerial queries — twice).
                # No associated sources → empty tier → honest escalation.
                project_id=ctx.slug,
            )
            _plan = _ScenePlan.load(str(scene_plan_path))
            _scenes = _plan.all_scenes
            _targets = [
                s for s in _scenes
                if (s.visual_type or "").lower().strip()
                in (FOOTAGE_TYPES | ART_TYPES)
            ]
            counts = engine.resolve_all(_targets)
            # tempo's shot cadence: fetch the extra stills shot-listed scenes need
            _shot_lines: list[str] = []
            _shots_done = AssetEngine.fulfill_shots_wanted(
                _targets, nolan_config=_nolan_cfg, project_path=self.project_path,
                log=_shot_lines.append)
            # Review tray: record the runner-up library candidates per matched
            # scene so the /scenes drawer can offer one-click swaps — the human
            # reviews what matching CONSIDERED, not just what it chose.
            AssetEngine.record_candidates(_targets, project_id=ctx.slug)
            _plan.save(str(scene_plan_path))
            _matched = sum(1 for s in _scenes if getattr(s, "matched_clip", None))
            _art_hits = sum(
                1 for s in _targets
                if str(getattr(s, "resolved_source", "")).startswith("art"))
            _stills = sum(
                1 for s in _targets
                if str(getattr(s, "resolved_source", "")).startswith("library"))
            _external = sum(
                1 for s in _targets
                if str(getattr(s, "resolved_source", "")).startswith("external"))

            report_path.write_text(
                "# Clip Selection Report (asset engine)\n\n"
                f"Resolved **{len(_targets)}** footage/art scenes via the unified "
                f"asset engine: {_matched} video matches, {_art_hits} "
                f"archival artworks, {_stills} picture-library stills, "
                f"{_external} external stock hits; shot lists authored for "
                f"{_shots_done} scene(s).\n\n"
                f"By source: "
                f"{', '.join(f'{k}: {v}' for k, v in sorted(counts.items()))}\n\n"
                "Ladder: footage → vector clip search (gate 0.5, no-reuse) → "
                "picture-library stills → external stock (vision gate 4; video "
                "materialized locally); archival-art → exact-title museum pass → "
                "semantic fallback. Operator bridge (tonal/conceptual) re-probes "
                "on literal misses. Unresolved scenes report `none(<reason>)` — "
                "no silent gaps.\n"
                + ("\n## Shot lists\n" + "\n".join(f"- {ln}" for ln in _shot_lines) + "\n"
                   if _shot_lines else ""),
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
