"""Render dispatcher for the orchestrator's `render` pipeline step.

Translates the orchestrator's `scene_plan.json` (with `matched_clip` +
`layout_spec`) into per-scene MP4 clips, then assembles a final video.

Routing per scene `visual_type`:

- `b-roll` with `matched_clip` → FFmpeg sub-clip extraction
- `text-overlay` / `graphic` with `layout_spec` → direct dispatch into the
  Python scene renderers (bypasses `PythonTemplateEngine`'s regex auto-detect,
  which is built for the legacy `visual_description`-based pipeline)
- `generated-image` (no ComfyUI integration yet) → skipped; assemble fills
  with a black frame
- `layout_spec.template == "custom"` → skipped; ditto

This module reuses NOLAN's existing scene renderers and assemble logic; it
does not re-implement video composition.
"""

from __future__ import annotations

import inspect
import json
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
    from nolan.renderer.scenes.counter import CountUp
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
        "counter": CountUp,
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


class RenderError(RuntimeError):
    pass


def render_b_roll(
    scene: dict,
    output_path: Path,
) -> Path:
    """Extract a sub-clip from the source video using FFmpeg."""
    mc = scene.get("matched_clip") or {}
    video_path = mc.get("video_path")
    clip_start = mc.get("clip_start")
    clip_end = mc.get("clip_end")
    if not (video_path and clip_start is not None and clip_end is not None):
        raise RenderError(
            f"scene {scene.get('id')} matched_clip is incomplete: {mc!r}"
        )
    duration = float(clip_end) - float(clip_start)
    if duration <= 0:
        raise RenderError(f"scene {scene.get('id')} matched_clip has non-positive duration")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(clip_start),
        "-i", str(video_path),
        "-t", f"{duration:.3f}",
    ]
    # Optional gentle fade in/out (seconds) so hard cuts breathe a little.
    fade = float(scene.get("fade", 0.0) or 0.0)
    if fade > 0:
        fade = min(fade, duration / 2)
        cmd += ["-vf", f"fade=t=in:st=0:d={fade},fade=t=out:st={duration - fade:.3f}:d={fade}"]
    cmd += [
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        "-loglevel", "error",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError(
            f"ffmpeg failed for {scene.get('id')}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return output_path


def render_layout(
    scene: dict,
    output_path: Path,
    duration: float,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path | None:
    """Render a text-overlay/graphic scene from its layout_spec.

    Returns None for `custom` templates or unknown templates — assembly will
    fill those slots with a black frame.
    """
    spec = scene.get("layout_spec") or {}
    template = spec.get("template")
    if not template:
        return None
    if template == "custom":
        return None

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
    """Dispatch a single scene to the right renderer."""
    scene_id = scene.get("id", "unknown")
    visual_type = scene.get("visual_type", "")
    duration = parse_duration(scene.get("duration", "5s"))
    target = output_dir / f"{scene_id}.mp4"

    spec_template = (scene.get("layout_spec") or {}).get("template")

    try:
        # Highest priority: an LLM-authored motion spec (nolan.motion, Python or Remotion).
        if scene.get("motion_spec"):
            from nolan.motion import render as render_motion
            render_motion(scene["motion_spec"], target)
            return RenderOutcome(
                scene_id=scene_id,
                rendered_clip=str(target.relative_to(project_path)).replace("\\", "/"),
                visual_type=visual_type,
                template=scene["motion_spec"].get("effect"),
                skipped_reason=None,
            )

        if visual_type == "b-roll":
            if scene.get("matched_clip"):
                render_b_roll(scene, target)
                return RenderOutcome(
                    scene_id=scene_id,
                    rendered_clip=str(target.relative_to(project_path)).replace("\\", "/"),
                    visual_type=visual_type,
                    template=None,
                    skipped_reason=None,
                )
            return RenderOutcome(
                scene_id, None, visual_type, None,
                "b-roll without matched_clip — assemble will use black frame",
            )

        if visual_type in ("text-overlay", "graphic"):
            if scene.get("layout_spec"):
                result = render_layout(scene, target, duration)
                if result is None:
                    return RenderOutcome(
                        scene_id, None, visual_type, spec_template,
                        f"template `{spec_template}` not renderable in v1 (custom or unknown)",
                    )
                return RenderOutcome(
                    scene_id=scene_id,
                    rendered_clip=str(target.relative_to(project_path)).replace("\\", "/"),
                    visual_type=visual_type,
                    template=spec_template,
                    skipped_reason=None,
                )
            return RenderOutcome(
                scene_id, None, visual_type, None,
                f"{visual_type} without layout_spec — assemble will use black frame",
            )

        if visual_type == "generated-image":
            return RenderOutcome(
                scene_id, None, visual_type, None,
                "generated-image: ComfyUI integration not implemented in v1",
            )

        return RenderOutcome(
            scene_id, None, visual_type, None,
            f"unknown visual_type `{visual_type}`",
        )
    except RenderError as exc:
        return RenderOutcome(
            scene_id, None, visual_type, spec_template,
            f"render error: {exc}",
        )


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

    Timecodes are derived from the existing `start` and `duration` fields so
    `nolan assemble` can place each clip on the timeline.

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
            duration = parse_duration(scene.get("duration", "5s"))
            scene["start_seconds"] = cursor
            scene["end_seconds"] = cursor + duration
            cursor += duration
    return cursor, rendered


def generate_silent_audio(duration_seconds: float, output_path: Path) -> Path:
    """Produce a silent WAV of the given duration via FFmpeg lavfi anullsrc."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t", f"{duration_seconds:.3f}",
        "-c:a", "pcm_s16le",
        "-loglevel", "error",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError(
            f"silent audio generation failed: {proc.stderr.strip()}"
        )
    return output_path


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
