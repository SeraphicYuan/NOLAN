"""Optional standalone FFmpeg composition; Nolan can replace this whole adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path

from math_animation.contracts import ProjectSpec, TimelineArtifact
from math_animation.style import StyleTokens
from math_animation.toolchain import executable_path, subprocess_environment


class CompositionError(RuntimeError):
    pass


def compose_standalone(
    project: ProjectSpec,
    style: StyleTokens,
    timeline: TimelineArtifact,
    run_dir: Path,
    *,
    timeout_seconds: float = 1200,
) -> Path:
    ffmpeg = executable_path("ffmpeg")
    if not ffmpeg:
        raise CompositionError("ffmpeg is required for standalone composition")
    inputs: list[str] = []
    stream_labels: list[str] = []
    input_index = 0
    cursor = 0.0
    color = style.background.removeprefix("#")

    for clip in timeline.clips:
        gap = clip.start_seconds - cursor
        if gap > 1e-4:
            inputs.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    f"{gap:.6f}",
                    "-i",
                    f"color=c=0x{color}:s={timeline.pixel_width}x"
                    f"{timeline.pixel_height}:r={timeline.frame_rate}",
                ]
            )
            stream_labels.append(f"[{input_index}:v]")
            input_index += 1
        path = run_dir / clip.expected_media_path
        if not path.is_file():
            raise CompositionError(f"missing rendered clip: {path}")
        inputs.extend(["-i", str(path)])
        stream_labels.append(f"[{input_index}:v]")
        input_index += 1
        cursor = clip.end_seconds

    filter_graph = (
        "".join(stream_labels)
        + f"concat=n={len(stream_labels)}:v=1:a=0,"
        + f"fps={timeline.frame_rate},format=yuv420p[v]"
    )
    command = [ffmpeg, "-y", *inputs]
    audio_index: int | None = None
    if project.narration.audio_path:
        audio = Path(project.narration.audio_path)
        if not audio.is_file():
            raise CompositionError(f"narration audio does not exist: {audio}")
        command.extend(["-i", str(audio)])
        audio_index = input_index
    output = run_dir / "final.mp4"
    command.extend(["-filter_complex", filter_graph, "-map", "[v]"])
    if audio_index is not None:
        command.extend(["-map", f"{audio_index}:a", "-c:a", "aac", "-shortest"])
    command.extend(["-c:v", "libx264", "-crf", "18", str(output)])
    completed = subprocess.run(
        command,
        cwd=run_dir,
        env=subprocess_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "compose.stdout.log").write_text(
        completed.stdout, encoding="utf-8"
    )
    (run_dir / "logs" / "compose.stderr.log").write_text(
        completed.stderr, encoding="utf-8"
    )
    if completed.returncode or not output.is_file():
        raise CompositionError(
            "standalone FFmpeg composition failed:\n"
            + (completed.stderr or completed.stdout)[-6000:]
        )
    return output
