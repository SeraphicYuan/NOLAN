"""Deterministic post-render probes and lightweight visual QA."""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageStat

from math_animation.blocks import compile_block
from math_animation.bundle import sha256_json, write_json_atomic
from math_animation.contracts import (
    AnnotationVisualObject,
    ApplyMatrixAction,
    CreateAction,
    EquationTransformBlock,
    FadeInAction,
    FadeOutAction,
    GroupVisualObject,
    MathTexVisualObject,
    MoveAction,
    ProjectSpec,
    RotateAction,
    ScaleAction,
    SecantToTangentBlock,
    TextVisualObject,
    TimelineArtifact,
    TransformMathAction,
)
from math_animation.style import normalize_style
from math_animation.timing import resolve_anchor, resolve_beats
from math_animation.toolchain import executable_path, subprocess_environment
from math_animation.repair import Diagnostic


class ReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class _LayoutBox:
    object_id: str
    left: float
    right: float
    bottom: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center(self) -> tuple[float, float]:
        return (
            (self.left + self.right) / 2,
            (self.bottom + self.top) / 2,
        )

    def moved(self, position: tuple[float, float, float]) -> "_LayoutBox":
        center_x, center_y = self.center
        return replace(
            self,
            left=self.left + position[0] - center_x,
            right=self.right + position[0] - center_x,
            bottom=self.bottom + position[1] - center_y,
            top=self.top + position[1] - center_y,
        )

    def scaled(
        self,
        factor: float,
        *,
        about: tuple[float, float] | None = None,
    ) -> "_LayoutBox":
        about_x, about_y = about or self.center
        return replace(
            self,
            left=about_x + (self.left - about_x) * factor,
            right=about_x + (self.right - about_x) * factor,
            bottom=about_y + (self.bottom - about_y) * factor,
            top=about_y + (self.top - about_y) * factor,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "bounds": [self.left, self.bottom, self.right, self.top],
            "center": list(self.center),
            "width": self.width,
            "height": self.height,
        }


def _aspect_class(project: ProjectSpec) -> str:
    ratio = project.render.pixel_width / project.render.pixel_height
    return "landscape" if ratio > 1.15 else "portrait" if ratio < 0.87 else "square"


def _latex_visual_length(parts: list[str]) -> int:
    value = " ".join(parts)
    value = re.sub(r"\\(?:begin|end)\{[^}]+\}", "", value)
    value = re.sub(r"\\text\{([^}]*)\}", r"\1", value)
    value = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"\1/\2", value)
    value = re.sub(r"\\(?:det|sin|cos|tan|log|ln|exp)", "xxx", value)
    value = re.sub(r"\\[A-Za-z]+", "x", value)
    value = value.replace(r"\\", " ")
    return max(1, len(re.sub(r"[\s{}_^]", "", value)))


def _effective_item(item, aspect: str):
    override = item.responsive.get(aspect)
    if override is None:
        return item, 1.0
    updates: dict[str, Any] = {}
    if override.position is not None:
        updates["position"] = override.position
    if override.layout is not None:
        updates["layout"] = override.layout
    return (
        item.model_copy(update=updates) if updates else item,
        override.scale,
    )


def _label_box(
    item,
    *,
    style,
    aspect: str,
    latex_parts: list[str] | None = None,
) -> _LayoutBox | None:
    item, responsive_scale = _effective_item(item, aspect)
    if isinstance(item, TextVisualObject):
        lines = item.text.splitlines() or [item.text]
        font_size = item.font_size or style.typography.body_size
        width = max(len(line) for line in lines) * font_size * 0.0036
        height = len(lines) * font_size * 0.014
        max_width = item.max_width
        position = item.position
    elif isinstance(item, MathTexVisualObject):
        parts = latex_parts or item.latex_parts
        font_size = item.font_size or style.typography.math_size
        # MathTex glyphs are materially wider than Pango Text at the same
        # nominal font size. This coefficient is calibrated against the
        # rendered comparison and matrix fixtures checked into the project.
        width = _latex_visual_length(parts) * font_size * 0.0072
        height = font_size * 0.0125
        max_width = item.max_width
        position = item.position
    elif isinstance(item, AnnotationVisualObject):
        lines = item.text.splitlines() or [item.text]
        font_size = item.font_size or style.typography.body_size
        width = max(len(line) for line in lines) * font_size * 0.0036
        height = len(lines) * font_size * 0.014
        max_width = item.max_width
        position = tuple(
            left + right
            for left, right in zip(
                item.position,
                item.label_position,
                strict=True,
            )
        )
    else:
        return None
    width *= responsive_scale
    height *= responsive_scale
    if max_width is not None:
        width = min(width, max_width * responsive_scale)
    width = max(0.28, width)
    height = max(0.2, height)
    return _LayoutBox(
        object_id=item.id,
        left=position[0] - width / 2,
        right=position[0] + width / 2,
        bottom=position[1] - height / 2,
        top=position[1] + height / 2,
    )


def _apply_relative_layout(
    box: _LayoutBox,
    item,
    boxes: dict[str, _LayoutBox],
) -> _LayoutBox:
    layout = item.layout
    if layout is None or layout.relative_to not in boxes:
        return box
    reference = boxes[layout.relative_to]
    center_x, center_y = reference.center
    if layout.direction == "up":
        position = (
            center_x,
            reference.top + layout.buffer + box.height / 2,
            0.0,
        )
    elif layout.direction == "down":
        position = (
            center_x,
            reference.bottom - layout.buffer - box.height / 2,
            0.0,
        )
    elif layout.direction == "left":
        position = (
            reference.left - layout.buffer - box.width / 2,
            center_y,
            0.0,
        )
    else:
        position = (
            reference.right + layout.buffer + box.width / 2,
            center_y,
            0.0,
        )
    return box.moved(position)


def _group_members(
    target: str,
    objects: dict[str, Any],
) -> set[str]:
    item = objects[target]
    if not isinstance(item, GroupVisualObject):
        return {target}
    members: set[str] = set()
    for member in item.members:
        members.update(_group_members(member, objects))
    return members


def _union_center(
    object_ids: set[str],
    boxes: dict[str, _LayoutBox],
) -> tuple[float, float]:
    selected = [boxes[item] for item in object_ids if item in boxes]
    if not selected:
        return 0.0, 0.0
    return (
        (min(item.left for item in selected) + max(item.right for item in selected))
        / 2,
        (
            min(item.bottom for item in selected)
            + max(item.top for item in selected)
        )
        / 2,
    )


def _layout_snapshots(project: ProjectSpec) -> dict[str, dict[str, list[_LayoutBox]]]:
    """Project label boxes into each rendered stable probe."""

    style = normalize_style(project.style)
    aspect = _aspect_class(project)
    result: dict[str, dict[str, list[_LayoutBox]]] = {}
    for beat in project.beats:
        program = beat.scene_program
        if program is None:
            continue
        objects = {item.id: item for item in program.objects}
        boxes: dict[str, _LayoutBox] = {}
        for original in program.objects:
            item, _ = _effective_item(original, aspect)
            box = _label_box(original, style=style, aspect=aspect)
            if box is not None:
                boxes[original.id] = _apply_relative_layout(box, item, boxes)
        visible: set[str] = set()
        snapshots: dict[str, list[_LayoutBox]] = {}
        for cue in program.cues:
            for action in cue.actions:
                if not hasattr(action, "target"):
                    continue
                target_ids = _group_members(action.target, objects)
                if isinstance(action, (CreateAction, FadeInAction)):
                    visible.update(target_ids)
                elif isinstance(action, FadeOutAction):
                    visible.difference_update(target_ids)
                elif isinstance(action, MoveAction):
                    center = _union_center(target_ids, boxes)
                    delta = (
                        action.position[0] - center[0],
                        action.position[1] - center[1],
                    )
                    for object_id in target_ids & boxes.keys():
                        box = boxes[object_id]
                        boxes[object_id] = replace(
                            box,
                            left=box.left + delta[0],
                            right=box.right + delta[0],
                            bottom=box.bottom + delta[1],
                            top=box.top + delta[1],
                        )
                elif isinstance(action, ScaleAction):
                    center = _union_center(target_ids, boxes)
                    for object_id in target_ids & boxes.keys():
                        boxes[object_id] = boxes[object_id].scaled(
                            action.factor,
                            about=center,
                        )
                elif isinstance(action, ApplyMatrixAction):
                    matrix = action.matrix
                    for object_id in target_ids & boxes.keys():
                        box = boxes[object_id]
                        corners = [
                            (box.left, box.bottom),
                            (box.left, box.top),
                            (box.right, box.bottom),
                            (box.right, box.top),
                        ]
                        transformed = [
                            (
                                matrix[0][0] * x + matrix[0][1] * y,
                                matrix[1][0] * x + matrix[1][1] * y,
                            )
                            for x, y in corners
                        ]
                        boxes[object_id] = _LayoutBox(
                            object_id=object_id,
                            left=min(item[0] for item in transformed),
                            right=max(item[0] for item in transformed),
                            bottom=min(item[1] for item in transformed),
                            top=max(item[1] for item in transformed),
                        )
                elif isinstance(action, RotateAction):
                    # A conservative axis-aligned box after a planar rotation.
                    angle = math.radians(action.angle_degrees)
                    center = action.about_point[:2] if action.about_point else (
                        _union_center(target_ids, boxes)
                    )
                    for object_id in target_ids & boxes.keys():
                        box = boxes[object_id]
                        corners = [
                            (box.left, box.bottom),
                            (box.left, box.top),
                            (box.right, box.bottom),
                            (box.right, box.top),
                        ]
                        rotated = []
                        for x, y in corners:
                            relative_x, relative_y = x - center[0], y - center[1]
                            rotated.append(
                                (
                                    center[0]
                                    + relative_x * math.cos(angle)
                                    - relative_y * math.sin(angle),
                                    center[1]
                                    + relative_x * math.sin(angle)
                                    + relative_y * math.cos(angle),
                                )
                            )
                        boxes[object_id] = _LayoutBox(
                            object_id=object_id,
                            left=min(item[0] for item in rotated),
                            right=max(item[0] for item in rotated),
                            bottom=min(item[1] for item in rotated),
                            top=max(item[1] for item in rotated),
                        )
                elif isinstance(action, TransformMathAction):
                    item = objects[action.target]
                    transformed = _label_box(
                        item,
                        style=style,
                        aspect=aspect,
                        latex_parts=action.latex_parts,
                    )
                    if transformed is not None and action.target in boxes:
                        center = boxes[action.target].center
                        boxes[action.target] = transformed.moved(
                            (center[0], center[1], 0.0)
                        )
            snapshots[f"{cue.id}.stable"] = [
                boxes[object_id]
                for object_id in sorted(visible)
                if object_id in boxes
            ]
        snapshots["closing"] = [
            boxes[object_id]
            for object_id in sorted(visible)
            if object_id in boxes
        ]
        result[beat.id] = snapshots
    return result


def _box_collisions(
    boxes: list[_LayoutBox],
    *,
    horizontal_gap_floor: float = 0.6,
    vertical_gap_floor: float = 0.12,
) -> list[dict[str, Any]]:
    collisions: list[dict[str, Any]] = []
    for index, left in enumerate(boxes):
        for right in boxes[index + 1 :]:
            raw_overlap_width = min(left.right, right.right) - max(
                left.left,
                right.left,
            )
            raw_overlap_height = min(left.top, right.top) - max(
                left.bottom,
                right.bottom,
            )
            horizontal_gap = max(
                0.0,
                max(left.left, right.left) - min(left.right, right.right),
            )
            vertical_gap = max(
                0.0,
                max(left.bottom, right.bottom) - min(left.top, right.top),
            )
            collision_type: str | None = None
            overlap_width = max(0.0, raw_overlap_width)
            overlap_height = max(0.0, raw_overlap_height)
            if raw_overlap_width > 0 and raw_overlap_height > 0:
                collision_type = "projected_overlap"
            elif (
                raw_overlap_height
                >= 0.45 * min(left.height, right.height)
                and horizontal_gap < horizontal_gap_floor
            ):
                collision_type = "insufficient_horizontal_separation"
                overlap_width = horizontal_gap_floor - horizontal_gap
                overlap_height = raw_overlap_height
            elif (
                raw_overlap_width
                >= 0.3 * min(left.width, right.width)
                and vertical_gap < vertical_gap_floor
            ):
                collision_type = "insufficient_vertical_separation"
                overlap_width = raw_overlap_width
                overlap_height = vertical_gap_floor - vertical_gap
            if collision_type is None:
                continue
            overlap_area = overlap_width * overlap_height
            minimum_area = min(
                left.width * left.height,
                right.width * right.height,
            )
            overlap_ratio = overlap_area / max(1e-9, minimum_area)
            if overlap_ratio < 0.02:
                continue
            collisions.append(
                {
                    "object_ids": [left.object_id, right.object_id],
                    "collision_type": collision_type,
                    "overlap_ratio": overlap_ratio,
                    "horizontal_gap": horizontal_gap,
                    "vertical_gap": vertical_gap,
                    "intersection": [
                        max(left.left, right.left),
                        max(left.bottom, right.bottom),
                        min(left.right, right.right),
                        min(left.top, right.top),
                    ],
                    "first_box": left.as_dict(),
                    "second_box": right.as_dict(),
                }
            )
    return collisions


def _intersection_foreground_fraction(
    image_path: Path,
    intersection: list[float],
    *,
    background: tuple[int, int, int],
    frame_width: float,
    frame_height: float = 8.0,
) -> float:
    left, bottom, right, top = intersection
    if right <= left or top <= bottom:
        return 0.0
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        pixel_box = (
            round((left + frame_width / 2) / frame_width * image.width),
            round((frame_height / 2 - top) / frame_height * image.height),
            round((right + frame_width / 2) / frame_width * image.width),
            round((frame_height / 2 - bottom) / frame_height * image.height),
        )
        pixel_box = (
            max(0, min(image.width, pixel_box[0])),
            max(0, min(image.height, pixel_box[1])),
            max(0, min(image.width, pixel_box[2])),
            max(0, min(image.height, pixel_box[3])),
        )
        if pixel_box[2] <= pixel_box[0] or pixel_box[3] <= pixel_box[1]:
            return 0.0
        region = image.crop(pixel_box)
        foreground = 0
        for red, green, blue in region.getdata():
            distance = math.sqrt(
                (red - background[0]) ** 2
                + (green - background[1]) ** 2
                + (blue - background[2]) ** 2
            )
            if distance > 18:
                foreground += 1
        return foreground / max(1, region.width * region.height)


def _record_diagnostic(
    report: dict[str, Any],
    *,
    code: str,
    severity: str,
    message: str,
    beat_id: str | None = None,
    object_id: str | None = None,
    cue_id: str | None = None,
    evidence: dict[str, Any] | None = None,
    suggested_repairs: list[str] | None = None,
    repairable: bool = False,
) -> None:
    identity = {
        "code": code,
        "stage": "review",
        "beat_id": beat_id,
        "object_id": object_id,
        "cue_id": cue_id,
        "message": message,
    }
    diagnostic = Diagnostic(
        id=f"diag-{sha256_json(identity)[:12]}",
        code=code,
        severity=severity,
        stage="review",
        message=message,
        beat_id=beat_id,
        object_id=object_id,
        cue_id=cue_id,
        evidence=evidence or {},
        suggested_repairs=suggested_repairs or [],
        repairable=repairable,
    )
    report["diagnostics"].append(diagnostic.model_dump(mode="json"))
    destination = "warnings" if severity == "warning" else "errors"
    report[destination].append(message)


def _hex_rgb(value: str) -> tuple[int, int, int]:
    stripped = value.removeprefix("#")
    if len(stripped) != 6:
        raise ValueError(f"review requires a six-digit RGB color, got {value!r}")
    return tuple(int(stripped[index : index + 2], 16) for index in (0, 2, 4))


def _cue_times(project: ProjectSpec) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for resolved in resolve_beats(project):
        probes: list[dict[str, Any]] = [
            {"id": "opening", "time_seconds": min(0.1, resolved.duration_seconds / 2)}
        ]
        program = resolved.beat.scene_program
        if program is not None:
            cursor = 0.0
            for cue in program.cues:
                start = (
                    resolve_anchor(cue.start_at, resolved)
                    if cue.start_at is not None
                    else cursor
                )
                end = start + cue.duration_seconds
                stable = min(
                    max(0.0, resolved.duration_seconds - 0.05),
                    end + 0.05,
                )
                probes.append(
                    {
                        "id": f"{cue.id}.stable",
                        "time_seconds": stable,
                        "kind": "stable",
                    }
                )
                if cue.duration_seconds >= 0.4:
                    probes.extend(
                        [
                            {
                                "id": f"{cue.id}.motion-a",
                                "time_seconds": start + 0.25 * cue.duration_seconds,
                                "kind": "motion-a",
                                "motion_group": cue.id,
                            },
                            {
                                "id": f"{cue.id}.motion-b",
                                "time_seconds": start + 0.75 * cue.duration_seconds,
                                "kind": "motion-b",
                                "motion_group": cue.id,
                            },
                        ]
                    )
                cursor = end
        else:
            style = normalize_style(project.style)
            cursor = 0.0
            for block in resolved.beat.blocks:
                start = (
                    resolve_anchor(block.start_at, resolved)
                    if block.start_at is not None
                    else cursor
                )
                compiled = compile_block(block, style)
                caption_reveal = (
                    0.25
                    if isinstance(
                        block,
                        (EquationTransformBlock, SecantToTangentBlock),
                    )
                    and block.caption
                    else 0.0
                )
                stable = min(
                    resolved.duration_seconds - 0.05,
                    start
                    + block.run_time
                    + caption_reveal
                    + min(0.15, block.hold_seconds * 0.5),
                )
                probes.append(
                    {
                        "id": f"{block.id}.stable",
                        "time_seconds": max(start + 0.05, stable),
                        "kind": "stable",
                    }
                )
                if block.run_time >= 0.4:
                    probes.extend(
                        [
                            {
                                "id": f"{block.id}.motion-a",
                                "time_seconds": start + 0.25 * block.run_time,
                                "kind": "motion-a",
                                "motion_group": block.id,
                            },
                            {
                                "id": f"{block.id}.motion-b",
                                "time_seconds": start + 0.75 * block.run_time,
                                "kind": "motion-b",
                                "motion_group": block.id,
                            },
                        ]
                    )
                cursor = start + compiled.duration_seconds
        probes.append(
            {
                "id": "closing",
                "time_seconds": max(0.0, resolved.duration_seconds - 0.1),
                "expect_blank": program is None,
            }
        )
        result[resolved.beat.id] = probes
    return result


def _timing_quantization(
    project: ProjectSpec,
    frame_rate: int,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    frame_seconds = 1 / frame_rate
    for resolved in resolve_beats(project):
        records: list[dict[str, Any]] = []
        program = resolved.beat.scene_program
        if program is None:
            continue
        cursor = 0.0
        for cue in program.cues:
            desired = (
                resolve_anchor(cue.start_at, resolved)
                if cue.start_at is not None
                else cursor
            )
            output_frame = round(desired * frame_rate)
            quantized = output_frame / frame_rate
            records.append(
                {
                    "cue_id": cue.id,
                    "desired_seconds": desired,
                    "output_frame": output_frame,
                    "quantized_seconds": quantized,
                    "absolute_error_seconds": abs(quantized - desired),
                    "within_one_frame": (
                        abs(quantized - desired) <= frame_seconds + 1e-12
                    ),
                }
            )
            cursor = desired + cue.duration_seconds
        result[resolved.beat.id] = records
    return result


def _extract_frame(
    ffmpeg: str,
    video: Path,
    destination: Path,
    time_seconds: float,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{time_seconds:.6f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(destination),
        ],
        env=subprocess_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode or not destination.is_file():
        raise ReviewError(
            f"could not extract review frame at {time_seconds:.3f}s from "
            f"{video}: {completed.stderr[-2000:]}"
        )


def _frame_metrics(
    path: Path,
    background: tuple[int, int, int],
) -> dict[str, float]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        thumbnail = image.copy()
        thumbnail.thumbnail((320, 180))
    statistics = ImageStat.Stat(thumbnail)
    pixel_count = thumbnail.width * thumbnail.height
    foreground = 0
    for red, green, blue in thumbnail.getdata():
        distance = math.sqrt(
            (red - background[0]) ** 2
            + (green - background[1]) ** 2
            + (blue - background[2]) ** 2
        )
        if distance > 18:
            foreground += 1
    return {
        "luma_stddev": sum(statistics.stddev) / 3,
        "foreground_fraction": foreground / max(1, pixel_count),
    }


def _difference(first: Path, second: Path) -> float:
    with Image.open(first) as first_image, Image.open(second) as second_image:
        left = first_image.convert("RGB")
        right = second_image.convert("RGB")
        left.thumbnail((320, 180))
        right.thumbnail((320, 180))
        difference = ImageChops.difference(left, right)
        return sum(ImageStat.Stat(difference).rms) / 3


def _contact_sheet(frames: list[dict[str, Any]], destination: Path) -> None:
    if not frames:
        return
    cell_width = 400
    cell_height = 250
    columns = min(4, len(frames))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, probe in enumerate(frames):
        with Image.open(probe["path"]) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width, cell_height - 24))
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        sheet.paste(image, (x, y + 20))
        draw.text((x + 4, y + 3), probe["id"], fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)


def _decode_check(ffmpeg: str, video: Path) -> str | None:
    completed = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(video), "-f", "null", "-"],
        env=subprocess_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        return completed.stderr[-3000:] or "FFmpeg decoder returned a failure"
    return None


def _media_duration(video: Path) -> float:
    return float(_media_info(video)["duration_seconds"])


def _media_info(video: Path) -> dict[str, Any]:
    ffprobe = executable_path("ffprobe")
    if not ffprobe:
        raise ReviewError("ffprobe is required for frame-accurate review")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            (
                "stream=codec_type,codec_name,width,height,r_frame_rate,"
                "nb_frames,pix_fmt,sample_rate,channels"
            ),
            "-of",
            "json",
            str(video),
        ],
        env=subprocess_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
        duration = float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ReviewError(f"could not inspect media metadata for {video}") from exc
    if completed.returncode or duration <= 0:
        raise ReviewError(f"could not measure duration of {video}")
    streams = payload.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    audio_streams = [
        stream for stream in streams if stream.get("codec_type") == "audio"
    ]
    if video_stream is None:
        raise ReviewError(f"{video} contains no video stream")
    rate_text = str(video_stream.get("r_frame_rate", "0/1"))
    try:
        numerator, denominator = rate_text.split("/", 1)
        frame_rate = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        frame_rate = 0.0
    frames_text = video_stream.get("nb_frames")
    try:
        frame_count = int(frames_text)
    except (TypeError, ValueError):
        frame_count = round(duration * frame_rate) if frame_rate > 0 else None
    return {
        "duration_seconds": duration,
        "video_codec": video_stream.get("codec_name"),
        "pixel_format": video_stream.get("pix_fmt"),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "frame_rate": frame_rate,
        "frame_count": frame_count,
        "audio_streams": [
            {
                "codec": stream.get("codec_name"),
                "sample_rate": stream.get("sample_rate"),
                "channels": stream.get("channels"),
            }
            for stream in audio_streams
        ],
    }


def review_rendered_project(
    project: ProjectSpec,
    timeline: TimelineArtifact,
    run_dir: Path,
    *,
    final_video: Path | None = None,
) -> dict[str, Any]:
    """Extract authored probes, measure them, and verify every video decodes."""

    ffmpeg = executable_path("ffmpeg")
    if not ffmpeg:
        raise ReviewError("ffmpeg is required for rendered-frame review")
    style = normalize_style(project.style)
    background = _hex_rgb(style.background)
    requested = _cue_times(project)
    quantization = _timing_quantization(project, timeline.frame_rate)
    layout_snapshots = _layout_snapshots(project)
    frame_width = (
        8.0 * project.render.pixel_width / project.render.pixel_height
    )
    reported_collision_pairs: set[tuple[str, str, str]] = set()
    report: dict[str, Any] = {
        "schema_version": "math-animation.review.v2",
        "status": "passed",
        "clips": [],
        "warnings": [],
        "errors": [],
        "diagnostics": [],
    }
    review_root = run_dir / "review"

    for clip in timeline.clips:
        video = run_dir / clip.expected_media_path
        decoder_error = _decode_check(ffmpeg, video)
        if decoder_error:
            _record_diagnostic(
                report,
                code="media_mismatch",
                severity="error",
                beat_id=clip.beat_id,
                message=(
                    f"clip {clip.beat_id!r} failed decoder check: "
                    f"{decoder_error}"
                ),
                evidence={"decoder_error": decoder_error},
            )
            continue
        media = _media_info(video)
        media_duration = float(media["duration_seconds"])
        if (
            media["width"] != timeline.pixel_width
            or media["height"] != timeline.pixel_height
        ):
            _record_diagnostic(
                report,
                code="media_mismatch",
                severity="error",
                beat_id=clip.beat_id,
                message=(
                    f"clip {clip.beat_id!r} resolution is "
                    f"{media['width']}x{media['height']}, expected "
                    f"{timeline.pixel_width}x{timeline.pixel_height}"
                ),
                evidence={
                    "actual": [media["width"], media["height"]],
                    "expected": [timeline.pixel_width, timeline.pixel_height],
                },
            )
        if abs(float(media["frame_rate"]) - timeline.frame_rate) > 0.01:
            _record_diagnostic(
                report,
                code="media_mismatch",
                severity="error",
                beat_id=clip.beat_id,
                message=(
                    f"clip {clip.beat_id!r} frame rate is "
                    f"{media['frame_rate']}, expected {timeline.frame_rate}"
                ),
                evidence={
                    "actual": media["frame_rate"],
                    "expected": timeline.frame_rate,
                },
            )
        if project.render.transparent:
            pixel_format = str(media["pixel_format"] or "")
            if not (
                pixel_format.startswith("yuva")
                or pixel_format in {"argb", "rgba", "abgr", "bgra"}
            ):
                _record_diagnostic(
                    report,
                    code="media_mismatch",
                    severity="error",
                    beat_id=clip.beat_id,
                    message=(
                        f"transparent clip {clip.beat_id!r} uses pixel format "
                        f"{pixel_format!r} without an alpha channel"
                    ),
                    evidence={"pixel_format": pixel_format},
                )
        duration_tolerance = max(0.15, 2 / timeline.frame_rate)
        if abs(media_duration - clip.duration_seconds) > duration_tolerance:
            _record_diagnostic(
                report,
                code="timing_drift",
                severity="error",
                beat_id=clip.beat_id,
                message=(
                    f"clip {clip.beat_id!r} duration is {media_duration:.3f}s, "
                    f"expected {clip.duration_seconds:.3f}s"
                ),
                evidence={
                    "actual_seconds": media_duration,
                    "expected_seconds": clip.duration_seconds,
                },
            )
        clip_frames: list[dict[str, Any]] = []
        by_motion_group: dict[str, dict[str, Path]] = {}
        for index, probe in enumerate(requested[clip.beat_id]):
            time_seconds = min(
                max(0.0, float(probe["time_seconds"])),
                max(0.0, media_duration - 2 / timeline.frame_rate),
            )
            destination = (
                review_root
                / "frames"
                / clip.beat_id
                / f"{index:03d}-{probe['id']}.png"
            )
            _extract_frame(ffmpeg, video, destination, time_seconds)
            metrics = _frame_metrics(destination, background)
            record = {
                **probe,
                "time_seconds": time_seconds,
                "path": destination.relative_to(run_dir).as_posix(),
                "metrics": metrics,
            }
            snapshot_boxes = layout_snapshots.get(clip.beat_id, {}).get(
                probe["id"],
                [],
            )
            if snapshot_boxes and (
                probe.get("kind") == "stable" or probe["id"] == "closing"
            ):
                candidates = _box_collisions(snapshot_boxes)
                confirmed: list[dict[str, Any]] = []
                for candidate in candidates:
                    foreground_fraction = _intersection_foreground_fraction(
                        destination,
                        candidate["intersection"],
                        background=background,
                        frame_width=frame_width,
                    )
                    candidate["intersection_foreground_fraction"] = (
                        foreground_fraction
                    )
                    # Strong projected overlap is sufficient. Marginal
                    # overlap additionally needs foreground evidence from the
                    # actual rendered probe.
                    is_proximity = candidate["collision_type"].startswith(
                        "insufficient_"
                    )
                    if (
                        not is_proximity
                        and candidate["overlap_ratio"] < 0.18
                        and foreground_fraction < 0.01
                    ):
                        continue
                    confirmed.append(candidate)
                    object_ids = sorted(candidate["object_ids"])
                    identity = (
                        clip.beat_id,
                        object_ids[0],
                        object_ids[1],
                    )
                    if identity in reported_collision_pairs:
                        continue
                    reported_collision_pairs.add(identity)
                    _record_diagnostic(
                        report,
                        code="text_overflow",
                        severity="warning",
                        beat_id=clip.beat_id,
                        object_id=object_ids[0],
                        cue_id=probe["id"],
                        message=(
                            f"rendered probe {clip.beat_id}/{probe['id']} "
                            f"shows a likely visual collision between "
                            f"{object_ids[0]!r} and {object_ids[1]!r}"
                        ),
                        evidence={
                            "kind": "visual_collision",
                            "object_ids": object_ids,
                            "frame_path": (
                                destination.relative_to(run_dir).as_posix()
                            ),
                            **candidate,
                        },
                        suggested_repairs=[
                            "reposition_object",
                            "set_max_width",
                        ],
                    )
                record["layout"] = {
                    "projected_boxes": [
                        item.as_dict() for item in snapshot_boxes
                    ],
                    "collision_candidates": candidates,
                    "confirmed_collisions": confirmed,
                }
            clip_frames.append(record)
            # Opening and early-motion probes may legitimately be empty while
            # a Create/Write animation is entering. Blankness is actionable
            # only once the cue should be stable, or at a non-blank closing.
            blank_probe_is_actionable = (
                probe.get("kind") == "stable"
                or probe["id"] == "closing"
            )
            if (
                metrics["luma_stddev"] < 0.8
                and blank_probe_is_actionable
                and not probe.get("expect_blank")
            ):
                _record_diagnostic(
                    report,
                    code="blank_frame",
                    severity="warning",
                    beat_id=clip.beat_id,
                    cue_id=probe["id"],
                    message=(
                        f"probe {clip.beat_id}/{probe['id']} is nearly blank"
                    ),
                    evidence=metrics,
                    suggested_repairs=["regenerate_beat"],
                )
            if (
                probe.get("kind") == "stable"
                and metrics["foreground_fraction"] < 0.0005
            ):
                _record_diagnostic(
                    report,
                    code="blank_frame",
                    severity="warning",
                    beat_id=clip.beat_id,
                    cue_id=probe["id"],
                    message=(
                        f"stable probe {clip.beat_id}/{probe['id']} contains "
                        "almost no foreground content"
                    ),
                    evidence=metrics,
                    suggested_repairs=["regenerate_beat"],
                )
            if "motion_group" in probe:
                by_motion_group.setdefault(probe["motion_group"], {})[
                    probe["kind"]
                ] = destination

        for cue_id, pair in by_motion_group.items():
            if "motion-a" in pair and "motion-b" in pair:
                rms = _difference(pair["motion-a"], pair["motion-b"])
                if rms < 0.35:
                    _record_diagnostic(
                        report,
                        code="frozen_motion",
                        severity="warning",
                        beat_id=clip.beat_id,
                        cue_id=cue_id,
                        message=(
                            f"cue {clip.beat_id}/{cue_id} expected motion but "
                            f"frame difference was only {rms:.3f}"
                        ),
                        evidence={"frame_difference_rms": rms},
                        suggested_repairs=["regenerate_beat"],
                    )
                elif rms > 115:
                    _record_diagnostic(
                        report,
                        code="abrupt_discontinuity",
                        severity="warning",
                        beat_id=clip.beat_id,
                        cue_id=cue_id,
                        message=(
                            f"cue {clip.beat_id}/{cue_id} has an unusually "
                            f"abrupt frame difference of {rms:.3f}"
                        ),
                        evidence={"frame_difference_rms": rms},
                        suggested_repairs=["scale_timing", "regenerate_beat"],
                    )

        sheet = review_root / f"{clip.beat_id}.contact-sheet.png"
        _contact_sheet(
            [
                {
                    **frame,
                    "path": run_dir / frame["path"],
                }
                for frame in clip_frames
                if frame.get("kind") != "motion-a"
            ],
            sheet,
        )
        report["clips"].append(
            {
                "beat_id": clip.beat_id,
                "decoder": "passed",
                "declared_duration_seconds": clip.duration_seconds,
                "media_duration_seconds": media_duration,
                "media": media,
                "cue_timing": quantization.get(clip.beat_id, []),
                "frames": clip_frames,
                "contact_sheet": sheet.relative_to(run_dir).as_posix(),
            }
        )

    if final_video is not None:
        decoder_error = _decode_check(ffmpeg, final_video)
        report["final_video_decoder"] = (
            {"status": "failed", "error": decoder_error}
            if decoder_error
            else {"status": "passed"}
        )
        if decoder_error:
            _record_diagnostic(
                report,
                code="media_mismatch",
                severity="error",
                message=f"final video failed decoder check: {decoder_error}",
                evidence={"decoder_error": decoder_error},
            )
        else:
            final_media = _media_info(final_video)
            report["final_video_media"] = final_media
            if (
                final_media["width"] != timeline.pixel_width
                or final_media["height"] != timeline.pixel_height
            ):
                _record_diagnostic(
                    report,
                    code="media_mismatch",
                    severity="error",
                    message="final video resolution does not match the timeline",
                    evidence={
                        "actual": [
                            final_media["width"],
                            final_media["height"],
                        ],
                        "expected": [
                            timeline.pixel_width,
                            timeline.pixel_height,
                        ],
                    },
                )
            if project.narration.audio_path and not final_media["audio_streams"]:
                _record_diagnostic(
                    report,
                    code="media_mismatch",
                    severity="error",
                    message=(
                        "final video is missing the declared narration audio "
                        "stream"
                    ),
                    evidence={"audio_path": project.narration.audio_path},
                )

    if report["errors"]:
        report["status"] = "failed"
    elif report["warnings"]:
        report["status"] = "passed_with_warnings"
    write_json_atomic(review_root / "report.json", report)
    if report["errors"]:
        raise ReviewError("; ".join(report["errors"]))
    return report
