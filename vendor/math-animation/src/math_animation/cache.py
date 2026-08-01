"""Content-addressed beat render cache metadata and reuse."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from math_animation.bundle import sha256_json, write_json_atomic
from math_animation.compiler import CompilationResult
from math_animation.contracts import ProjectSpec
from math_animation.style import StyleTokens
from math_animation.version import __version__


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prior_reports(runs_dir: Path, current_run: Path) -> list[tuple[Path, dict]]:
    reports: list[tuple[Path, dict]] = []
    if not runs_dir.is_dir():
        return reports
    for candidate in sorted(runs_dir.iterdir(), reverse=True):
        if not candidate.is_dir() or candidate == current_run:
            continue
        report_path = candidate / "cache.json"
        if not report_path.is_file():
            continue
        try:
            reports.append(
                (
                    candidate,
                    json.loads(report_path.read_text(encoding="utf-8")),
                )
            )
        except (OSError, json.JSONDecodeError):
            continue
    return reports


def build_cache_report(
    project: ProjectSpec,
    style: StyleTokens,
    compilation: CompilationResult,
    run_dir: Path,
    runs_dir: Path,
) -> dict[str, Any]:
    utterances = {item.id: item for item in project.narration.utterances}
    sources = {
        path.stem: path
        for path in compilation.source_files
    }
    prior = _prior_reports(runs_dir, run_dir)
    entries: list[dict[str, Any]] = []

    for beat, clip in zip(project.beats, compilation.timeline.clips, strict=True):
        payload = {
            "beat": beat.model_dump(mode="json"),
            "utterance": (
                utterances[beat.narration_utterance_id].model_dump(mode="json")
                if beat.narration_utterance_id
                else None
            ),
            "style": style.model_dump(mode="json"),
            "render": project.render.model_dump(mode="json"),
            "compiler_version": __version__,
        }
        input_sha = sha256_json(payload)
        source = sources.get(beat.id)
        source_sha = _sha256_file(source) if source is not None else None
        entry: dict[str, Any] = {
            "beat_id": beat.id,
            "input_sha256": input_sha,
            "source_sha256": source_sha,
            "status": "miss",
            "reused_from": None,
        }
        for previous_dir, previous_report in prior:
            match = next(
                (
                    candidate
                    for candidate in previous_report.get("entries", [])
                    if candidate.get("beat_id") == beat.id
                    and candidate.get("input_sha256") == input_sha
                    and candidate.get("source_sha256") == source_sha
                ),
                None,
            )
            previous_clip = previous_dir / clip.expected_media_path
            if match is not None and previous_clip.is_file():
                entry["status"] = "hit"
                entry["reused_from"] = str(previous_dir)
                break
        entries.append(entry)

    report = {
        "schema_version": "math-animation.cache.v1",
        "project_id": project.project_id,
        "entries": entries,
    }
    write_json_atomic(run_dir / "cache.json", report)
    return report


def reuse_cached_clip(
    entry: dict[str, Any],
    destination: Path,
    expected_media_path: str,
) -> bool:
    source_root = entry.get("reused_from")
    if entry.get("status") != "hit" or not source_root:
        return False
    source = Path(source_root) / expected_media_path
    if not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True
