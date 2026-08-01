"""Compile typed mathematical screenplay beats into deterministic Manim scenes."""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass
from pathlib import Path

from math_animation.blocks import compile_block
from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    CustomSceneBlock,
    ProjectSpec,
    TimelineArtifact,
    TimelineClip,
)
from math_animation.scene_compiler import compile_scene_program
from math_animation.safety import validate_custom_scene_source
from math_animation.style import StyleTokens
from math_animation.timing import ResolvedBeat, resolve_anchor, resolve_beats
from math_animation.version import __version__



@dataclass(frozen=True)
class CompilationResult:
    timeline: TimelineArtifact
    source_files: tuple[Path, ...]
    visual_ir_files: tuple[Path, ...]


def _pascal(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    result = "".join(word[:1].upper() + word[1:] for word in words)
    if not result or result[0].isdigit():
        result = "Beat" + result
    return result + "Scene"


def _indent(lines: list[str], spaces: int = 8) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else "" for line in lines)


def _generated_scene_source(
    project: ProjectSpec,
    style: StyleTokens,
    *,
    scene_class: str,
    scene_base: str,
    body: list[str],
) -> str:
    settings = project.render
    return (
        '"""Generated deterministically by math-animation '
        f'{__version__}; edit the screenplay or SceneProgram, not this file."""\n\n'
        "from manim import *\n"
        "import numpy as np\n\n"
        f"config.pixel_width = {settings.pixel_width}\n"
        f"config.pixel_height = {settings.pixel_height}\n"
        "config.frame_height = 8.0\n"
        f"config.frame_width = {8.0 * settings.pixel_width / settings.pixel_height!r}\n"
        f"config.frame_rate = {settings.frame_rate}\n"
        f"config.background_color = {style.background!r}\n\n\n"
        f"class {scene_class}({scene_base}):\n"
        "    def construct(self):\n"
        f"{_indent(body)}\n"
    )


class ManimCompiler:
    def __init__(self, *, allow_custom_python: bool = False):
        self.allow_custom_python = allow_custom_python

    def compile(
        self,
        project: ProjectSpec,
        style: StyleTokens,
        run_dir: Path,
    ) -> CompilationResult:
        source_dir = Path(run_dir) / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        visual_ir_dir = Path(run_dir) / "visual_ir"
        visual_ir_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = Path(run_dir) / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        clips: list[TimelineClip] = []
        source_files: list[Path] = []
        visual_ir_files: list[Path] = []
        for resolved in resolve_beats(project):
            scene_class = _pascal(resolved.beat.id)
            source_path = source_dir / f"{resolved.beat.id}.py"
            if resolved.beat.scene_program is not None:
                visual_ir_path = visual_ir_dir / f"{resolved.beat.id}.scene.json"
                write_json_atomic(visual_ir_path, resolved.beat.scene_program)
                visual_ir_files.append(visual_ir_path)
            source = self._compile_beat(
                resolved, project, style, scene_class=scene_class
            )
            source_path.write_text(source, encoding="utf-8")
            builtins.compile(source, str(source_path), "exec")
            source_files.append(source_path)
            extension = ".mov" if project.render.transparent else ".mp4"
            clips.append(
                TimelineClip(
                    beat_id=resolved.beat.id,
                    scene_class=scene_class,
                    source_path=source_path.relative_to(run_dir).as_posix(),
                    expected_media_path=f"clips/{resolved.beat.id}{extension}",
                    start_seconds=resolved.start_seconds,
                    end_seconds=resolved.end_seconds,
                    duration_seconds=resolved.duration_seconds,
                    alpha=project.render.transparent,
                )
            )

        duration = max((clip.end_seconds for clip in clips), default=0.0)
        timeline = TimelineArtifact(
            project_id=project.project_id,
            frame_rate=project.render.frame_rate,
            pixel_width=project.render.pixel_width,
            pixel_height=project.render.pixel_height,
            audio_path=project.narration.audio_path,
            clips=clips,
            duration_seconds=duration,
        )
        return CompilationResult(
            timeline=timeline,
            source_files=tuple(source_files),
            visual_ir_files=tuple(visual_ir_files),
        )

    def _compile_beat(
        self,
        resolved: ResolvedBeat,
        project: ProjectSpec,
        style: StyleTokens,
        *,
        scene_class: str,
    ) -> str:
        if resolved.beat.scene_program is not None:
            compiled_program = compile_scene_program(
                resolved.beat.scene_program,
                style,
                resolved,
                pixel_width=project.render.pixel_width,
                pixel_height=project.render.pixel_height,
            )
            return _generated_scene_source(
                project,
                style,
                scene_class=scene_class,
                scene_base=compiled_program.scene_base,
                body=compiled_program.lines,
            )

        custom = [
            block
            for block in resolved.beat.blocks
            if isinstance(block, CustomSceneBlock)
        ]
        if custom:
            if len(resolved.beat.blocks) != 1:
                raise ValueError("custom_scene cannot be mixed with deterministic blocks")
            if not self.allow_custom_python:
                raise ValueError(
                    "custom_scene is disabled; explicitly enable allow_custom_python "
                    "and render it in an isolated worker"
                )
            block = custom[0]
            if block.scene_class != scene_class:
                raise ValueError(
                    f"custom scene class must be {scene_class!r} for beat "
                    f"{resolved.beat.id!r}"
                )
            validate_custom_scene_source(block.source, block.scene_class)
            return block.source.rstrip() + "\n"

        body: list[str] = [
            f"self.camera.background_color = {style.background!r}",
            f"self.next_section({resolved.beat.id!r})",
        ]
        cursor = 0.0
        for block in resolved.beat.blocks:
            start = resolve_anchor(block.start_at, resolved) if block.start_at else cursor
            if start < cursor - 1e-6:
                raise ValueError(
                    f"block {block.id!r} starts at {start:.3f}s, before the "
                    f"previous block ends at {cursor:.3f}s; overlapping blocks "
                    "need a dedicated composite block"
                )
            if start > cursor:
                body.append(f"self.wait({start - cursor!r})")
            compiled = compile_block(block, style)
            body.extend(compiled.lines)
            cursor = start + compiled.duration_seconds

        if cursor > resolved.duration_seconds + 1e-6:
            raise ValueError(
                f"beat {resolved.beat.id!r} needs {cursor:.3f}s of animation but "
                f"its narration/timeline allows {resolved.duration_seconds:.3f}s"
            )
        if resolved.duration_seconds > cursor:
            body.append(f"self.wait({resolved.duration_seconds - cursor!r})")

        return _generated_scene_source(
            project,
            style,
            scene_class=scene_class,
            scene_base="Scene",
            body=body,
        )
