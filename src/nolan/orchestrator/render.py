"""Render thunks for the orchestrator's `render` pipeline step.

`render_scene` delegates per-scene routing to the shared `render_dispatch.render_one`
(motion → matched_clip → layout_spec → comfyui → card) and keeps the orchestrator's
`RenderOutcome` + project-relative path convention. `render_layout` (the layout_spec →
scene-renderer dispatch) is also used by `render_dispatch`. Assembly is shelled out to
`nolan assemble`.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RenderOutcome:
    scene_id: str
    rendered_clip: str | None  # path relative to project root, or None if skipped
    visual_type: str
    template: str | None
    skipped_reason: str | None  # populated when rendered_clip is None


def parse_duration(spec: str | int | float) -> float:
    """Convert '5s' / '12s' / 5 / 5.0 → seconds (float)."""
    if isinstance(spec, (int, float)):
        return float(spec)
    s = str(spec).strip().lower().rstrip("s")
    try:
        return float(s)
    except ValueError:
        return 5.0


def parse_timecode(tc: str) -> float:
    """Convert 'M:SS' / 'H:MM:SS' / '0:00' → seconds (float)."""
    parts = str(tc).split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0.0


def _build_renderer_registry():
    """Lazy-imported map: layout_spec.template → renderer class.

    Imports are local to avoid loading the renderer at orchestrator import time.
    """
    from nolan.renderer.scenes.chapter_card import ChapterCardRenderer
    from nolan.renderer.scenes.comparison import ComparisonRenderer
    from nolan.renderer.scenes.counter import CounterRenderer
    from nolan.renderer.scenes.definition import DefinitionRenderer
    from nolan.renderer.scenes.document_highlight import DocumentHighlightRenderer
    from nolan.renderer.scenes.list import ListRenderer
    from nolan.renderer.scenes.location_stamp import LocationStampRenderer
    from nolan.renderer.scenes.lower_third import LowerThirdRenderer
    from nolan.renderer.scenes.news_headline import NewsHeadlineRenderer
    from nolan.renderer.scenes.percentage_bar import PercentageBarRenderer
    from nolan.renderer.scenes.progress_bar import ProgressBarRenderer
    from nolan.renderer.scenes.pull_quote import PullQuoteRenderer
    from nolan.renderer.scenes.question import QuestionRenderer
    from nolan.renderer.scenes.quote import QuoteRenderer
    from nolan.renderer.scenes.ranking import RankingRenderer
    from nolan.renderer.scenes.section_divider import SectionDividerRenderer
    from nolan.renderer.scenes.source_citation import SourceCitationRenderer
    from nolan.renderer.scenes.stat_comparison import StatComparisonRenderer
    from nolan.renderer.scenes.statistic import StatisticRenderer
    from nolan.renderer.scenes.timeline import TimelineRenderer, TimelineEvent
    from nolan.renderer.scenes.title import TitleRenderer
    from nolan.renderer.scenes.tweet_card import TweetCardRenderer
    from nolan.renderer.scenes.verdict import VerdictRenderer

    return {
        "chapter_card": ChapterCardRenderer,
        "comparison": ComparisonRenderer,
        "counter": CounterRenderer,
        "definition": DefinitionRenderer,
        "document_highlight": DocumentHighlightRenderer,
        "list": ListRenderer,
        "location_stamp": LocationStampRenderer,
        "lower_third": LowerThirdRenderer,
        "news_headline": NewsHeadlineRenderer,
        "percentage_bar": PercentageBarRenderer,
        "progress_bar": ProgressBarRenderer,
        "pull_quote": PullQuoteRenderer,
        "question": QuestionRenderer,
        "quote": QuoteRenderer,
        "ranking": RankingRenderer,
        "section_divider": SectionDividerRenderer,
        "source_citation": SourceCitationRenderer,
        "stat_comparison": StatComparisonRenderer,
        "statistic": StatisticRenderer,
        "timeline": TimelineRenderer,
        "title": TitleRenderer,
        "tweet_card": TweetCardRenderer,
        "verdict": VerdictRenderer,
    }


def _filter_params_for_renderer(cls, params: dict) -> dict:
    """Keep only params the renderer's __init__ accepts.

    Layout specs may include extra keys we don't need; renderers may have
    accumulated parameters over time. Filter to the intersection so we don't
    raise on unexpected kwargs.
    """
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return params
    accepted = set(sig.parameters.keys())
    return {k: v for k, v in params.items() if k in accepted}


def _adapt_special_params(template: str, params: dict) -> dict:
    """Per-template fixup for params that need conversion before instantiation."""
    out = dict(params)
    if template == "timeline":
        events_raw = out.get("events") or []
        from nolan.renderer.scenes.timeline import TimelineEvent
        events = []
        for e in events_raw:
            if isinstance(e, dict):
                events.append(TimelineEvent(
                    year=str(e.get("year", "")),
                    label=str(e.get("label", "")),
                ))
            else:
                events.append(e)
        out["events"] = events
    if template == "ranking":
        items_raw = out.get("items") or []
        # Spec is list of [label, value] pairs; renderer likely accepts list of tuples.
        items: list = []
        for it in items_raw:
            if isinstance(it, (list, tuple)) and len(it) >= 2:
                items.append((str(it[0]), str(it[1])))
            elif isinstance(it, dict):
                items.append((str(it.get("label", "")), str(it.get("value", ""))))
            else:
                items.append((str(it), ""))
        out["items"] = items
    if template == "list":
        items_raw = out.get("items") or []
        out["items"] = [str(x) for x in items_raw]
    return out


logger = logging.getLogger(__name__)


class RenderError(RuntimeError):
    pass


# (render_b_roll removed in P4 — b-roll extraction now lives in the shared
#  render_dispatch.render_one → ffmpeg_utils.extract_subclip.)


def render_layout(
    scene: dict,
    output_path: Path,
    duration: float,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path | None:
    """Render a text-overlay/graphic scene from its layout_spec.

    Remotion-first (Phase 3): templates render through the curated blocks
    library via a one-step Chapter job; the legacy Python renderers remain the
    automatic fallback (and the only path under NOLAN_LEGACY_RENDER=1).

    Returns None for `custom` templates or unknown templates — assembly will
    fill those slots with a black frame.
    """
    import os

    spec = scene.get("layout_spec") or {}
    template = spec.get("template")
    if not template:
        return None
    if template == "custom":
        return None

    if os.environ.get("NOLAN_LEGACY_RENDER") != "1":
        try:
            from nolan.layout_blocks import render_layout_block
            clip = render_layout_block(
                template, spec.get("params") or {}, duration,
                output_path, fps=fps, scene_id=str(scene.get("id") or ""))
            if clip:
                return clip
        except Exception as exc:
            logger.warning(
                "remotion layout render failed for %s (%s) — python fallback: %s",
                scene.get("id"), template, exc)

    registry = _build_renderer_registry()
    cls = registry.get(template)
    if cls is None:
        return None

    raw_params = spec.get("params") or {}
    params = _adapt_special_params(template, raw_params)
    params.setdefault("width", width)
    params.setdefault("height", height)
    params.setdefault("fps", fps)

    valid = _filter_params_for_renderer(cls, params)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        renderer = cls(**valid)
        renderer.render(str(output_path), duration=duration)
    except Exception as exc:
        raise RenderError(
            f"renderer {template} failed for {scene.get('id')}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return output_path


def render_scene(
    scene: dict,
    project_path: Path,
    output_dir: Path,
) -> RenderOutcome:
    """Dispatch a single scene to the right renderer via the shared router.

    Routing (motion → b-roll → layout → generated/card) lives in
    `render_dispatch.render_one`; this keeps the orchestrator's `RenderOutcome` +
    project-relative path convention. No `gen_fn` is passed, so `generated-image`
    scenes render a title card instead of a black frame.
    """
    from nolan.render_dispatch import render_one

    scene_id = scene.get("id", "unknown")
    visual_type = scene.get("visual_type", "")
    # Prefer the ALIGNED window (`nolan align`) over the planner's estimate —
    # the narration owns duration; the plan string is only a fallback.
    _ss, _es = scene.get("start_seconds"), scene.get("end_seconds")
    if _ss is not None and _es is not None and float(_es) > float(_ss):
        duration = float(_es) - float(_ss)
    else:
        duration = parse_duration(scene.get("duration", "5s"))
    target = output_dir / f"{scene_id}.mp4"
    _ls = scene.get("layout_spec")
    if isinstance(_ls, str):           # both shapes exist in the wild
        try:
            _ls = json.loads(_ls)
        except Exception:
            _ls = {}
    spec_template = (_ls or {}).get("template")

    try:
        kind = render_one(scene, target, duration=duration)
    except Exception as exc:  # noqa: BLE001 - one bad scene shouldn't abort the render
        return RenderOutcome(scene_id, None, visual_type, spec_template, f"render error: {exc}")

    if kind is None:
        return RenderOutcome(scene_id, None, visual_type, spec_template,
                             _skip_reason(scene, visual_type, spec_template))
    return RenderOutcome(
        scene_id=scene_id,
        rendered_clip=str(target.relative_to(project_path)).replace("\\", "/"),
        visual_type=visual_type,
        template=spec_template or kind,
        skipped_reason=None,
    )


def _skip_reason(scene: dict, visual_type: str, spec_template: str | None) -> str:
    if visual_type == "b-roll" and not scene.get("matched_clip"):
        return "b-roll without matched_clip — assemble will use black frame"
    if visual_type in ("text-overlay", "graphic") and not scene.get("layout_spec"):
        return f"{visual_type} without layout_spec — assemble will use black frame"
    if spec_template:
        return f"template `{spec_template}` not renderable (custom or unknown)"
    return f"no renderable asset for visual_type `{visual_type}`"


def stamp_tempo_motions(scene_plan: dict, project_path: Path) -> int:
    """Give image-backed scenes a tempo-driven still-motion spec (in place).

    matched_asset/generated_asset stills otherwise fall through to assemble's
    generic Ken Burns. This maps each scene's authored/recovered ``energy``
    (stamped by tempo_enrich, reference-blended when the project carries a
    deconstruction) to the motion library's treatment via ``motion_for_tempo``
    — so a calm museum beat holds/breathes and a driving beat pushes in,
    at the planned rhythm. Returns the number of scenes stamped.
    """
    from nolan.motion.spec import validate
    from nolan.tempo_plan import BeatTempo, motion_for_tempo

    stamped = 0
    for scenes in (scene_plan.get("sections") or {}).values():
        if not isinstance(scenes, list):
            continue
        for scene in scenes:
            if not isinstance(scene, dict) or scene.get("motion_spec"):
                continue
            img = scene.get("matched_asset") or (
                f"assets/generated/{scene['generated_asset']}"
                if scene.get("generated_asset") else None)
            if not img or scene.get("energy") is None:
                continue
            bt = BeatTempo(idx=0, title=scene.get("id") or "",
                           energy=float(scene["energy"]),
                           motion_speed=scene.get("motion_speed") or "medium")
            treatment, dur = motion_for_tempo(bt, kind="image")
            # narration owns DURATION (aligned window); tempo owns TREATMENT
            _ss, _es = scene.get("start_seconds"), scene.get("end_seconds")
            if _ss is not None and _es is not None and float(_es) > float(_ss):
                dur = float(_es) - float(_ss)
            raw = {"effect": "still-motion", "duration": dur,
                   "content": {"image": str(project_path / img),
                               "treatment": treatment}}
            spec, _errors = validate(raw)
            if spec:
                scene["motion_spec"] = spec
                stamped += 1
    return stamped


def render_all(
    scene_plan: dict,
    project_path: Path,
    output_dir: Path,
) -> list[RenderOutcome]:
    """Render every scene in the plan; return per-scene outcomes."""
    outcomes: list[RenderOutcome] = []
    for section_name, scenes in (scene_plan.get("sections") or {}).items():
        if not isinstance(scenes, list):
            continue
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            outcomes.append(render_scene(scene, project_path, output_dir))
    return outcomes


def annotate_scene_plan(
    scene_plan: dict,
    outcomes: list[RenderOutcome],
) -> tuple[float, int]:
    """Apply rendered_clip + start_seconds/end_seconds onto scene_plan in place.

    Beat-aligned windows are the timing authority: scenes that already carry
    a valid start/end keep it VERBATIM (re-tiling them from planner durations
    is what once stretched an aligned beat from 76.5s to 127.5s). Only scenes
    WITHOUT a valid window are placed after their predecessor using the
    planner's duration estimate — so unaligned plans still tile sequentially
    from 0, exactly as before.

    Returns (total_seconds, rendered_count).
    """
    by_id = {o.scene_id: o for o in outcomes}
    rendered = 0
    cursor = 0.0
    for section_name, scenes in (scene_plan.get("sections") or {}).items():
        if not isinstance(scenes, list):
            continue
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            outcome = by_id.get(scene.get("id"))
            if outcome and outcome.rendered_clip:
                scene["rendered_clip"] = outcome.rendered_clip
                rendered += 1
            _ss, _es = scene.get("start_seconds"), scene.get("end_seconds")
            if _ss is not None and _es is not None and float(_es) > float(_ss):
                cursor = max(cursor, float(_es))     # aligned window kept as-is
            else:
                duration = parse_duration(scene.get("duration", "5s"))
                scene["start_seconds"] = cursor
                scene["end_seconds"] = cursor + duration
                cursor += duration
    return cursor, rendered


def generate_silent_audio(duration_seconds: float, output_path: Path) -> Path:
    """Produce a silent WAV of the given duration (shared bundled-ffmpeg helper)."""
    from nolan.ffmpeg_utils import silent_audio
    try:
        return silent_audio(duration_seconds, output_path)
    except Exception as exc:
        raise RenderError(f"silent audio generation failed: {exc}") from exc


def call_assemble(
    project_path: Path,
    scene_plan_path: Path,
    audio_path: Path,
    output_path: Path,
    repo_root: Path,
) -> None:
    """Shell out to `nolan assemble` to stitch rendered clips + silent audio."""
    import os
    import sys

    cmd = [
        sys.executable, "-m", "nolan", "assemble",
        str(scene_plan_path),
        str(audio_path),
        "-o", str(output_path),
    ]
    env = os.environ.copy()
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RenderError(
            f"`nolan assemble` failed (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:1000]}"
        )


def render_summary_report(outcomes: list[RenderOutcome], total_duration: float) -> str:
    """Markdown summary of the render pass."""
    rendered = [o for o in outcomes if o.rendered_clip]
    skipped = [o for o in outcomes if not o.rendered_clip]
    by_template: dict[str, int] = {}
    for o in rendered:
        key = o.template or o.visual_type
        by_template[key] = by_template.get(key, 0) + 1
    skip_reasons: dict[str, int] = {}
    for o in skipped:
        reason = (o.skipped_reason or "?").split(" — ")[0]
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    lines = [
        f"# Render Report",
        "",
        f"## Summary",
        f"- Total scenes: {len(outcomes)}",
        f"- Rendered: {len(rendered)}",
        f"- Skipped: {len(skipped)} (assemble fills with black frames)",
        f"- Total runtime: {total_duration:.1f}s ({int(total_duration//60)}:{int(total_duration%60):02d})",
        "",
        f"## Rendered by template / type",
    ]
    for k, n in sorted(by_template.items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{k}`: {n}")
    if skipped:
        lines.append("")
        lines.append(f"## Skipped reasons")
        for reason, n in sorted(skip_reasons.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {reason}: {n}")
        lines.append("")
        lines.append(f"## Skipped scenes (per-scene)")
        for o in skipped[:30]:
            lines.append(f"- `{o.scene_id}` ({o.visual_type}{', '+o.template if o.template else ''}) — {o.skipped_reason}")
        if len(skipped) > 30:
            lines.append(f"- … and {len(skipped) - 30} more")
    return "\n".join(lines) + "\n"
