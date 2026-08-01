"""Create and render a brand-new vertex-form explainer end to end."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from math_animation.bundle import write_json_atomic
from math_animation.contracts import (
    NarrationInput,
    RenderSettings,
    StyleTemplateRef,
    UtteranceTiming,
    WordTiming,
)
from math_animation.expanded_planning import ExpandedPlanner
from math_animation.pedagogy import evaluate_pedagogy
from math_animation.pipeline import AuthoringPipeline
from math_animation.planning import PlanningRequest
from math_animation.synthetic import generate_synthetic_narration
from math_animation.toolchain import executable_path


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            + (completed.stderr or completed.stdout)[-3000:]
        )


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def _system_speech_narration(
    utterances: list[tuple[str, str]],
    output_path: Path,
    *,
    rate: int = 190,
    gap_seconds: float = 0.45,
) -> tuple[NarrationInput, str]:
    """Use local macOS speech with a proportional alignment stand-in."""

    say = shutil.which("say")
    ffmpeg = executable_path("ffmpeg")
    if say is None or ffmpeg is None:
        return (
            generate_synthetic_narration(
                utterances,
                output_path,
                word_seconds=0.22,
                word_gap_seconds=0.04,
                utterance_gap_seconds=gap_seconds,
                trailing_silence_seconds=0.4,
            ),
            "deterministic_tones",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vertex-form-tts-") as directory:
        temporary = Path(directory)
        speech_wavs: list[Path] = []
        durations: list[float] = []
        for index, (_, text) in enumerate(utterances):
            aiff = temporary / f"speech-{index:02d}.aiff"
            wav = temporary / f"speech-{index:02d}.wav"
            _run([say, "-r", str(rate), "-o", str(aiff), text])
            _run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(aiff),
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(wav),
                ]
            )
            speech_wavs.append(wav)
            durations.append(_wav_duration(wav))

        silence = temporary / "gap.wav"
        with wave.open(str(silence), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(24_000)
            audio.writeframes(b"\x00\x00" * round(gap_seconds * 24_000))

        concat_paths: list[Path] = []
        for index, speech in enumerate(speech_wavs):
            concat_paths.append(speech)
            if index < len(speech_wavs) - 1:
                concat_paths.append(silence)
        concat_file = temporary / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{path}'\n" for path in concat_paths),
            encoding="utf-8",
        )
        _run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-ar",
                "24000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ]
        )

    cursor = 0.0
    aligned: list[UtteranceTiming] = []
    for (utterance_id, text), duration in zip(
        utterances,
        durations,
        strict=True,
    ):
        words = text.split()
        weights = [max(1, len(word.strip(".,;:!?"))) for word in words]
        total_weight = sum(weights)
        word_timings: list[WordTiming] = []
        for word, weight in zip(words, weights, strict=True):
            word_duration = duration * weight / total_weight
            word_start = (
                word_timings[-1].end_seconds
                if word_timings
                else cursor
            )
            word_timings.append(
                WordTiming(
                    word=word,
                    start_seconds=word_start,
                    end_seconds=word_start + word_duration,
                )
            )
        aligned.append(
            UtteranceTiming(
                id=utterance_id,
                text=text,
                words=word_timings,
            )
        )
        cursor += duration + gap_seconds
    return (
        NarrationInput(
            provider="external",
            audio_path=str(output_path),
            utterances=aligned,
        ),
        "macos_system_tts_proportional_alignment",
    )


def _contact_sheet(run_dir: Path, destination: Path) -> None:
    from PIL import Image, ImageDraw

    review = json.loads(
        (run_dir / "review" / "report.json").read_text(encoding="utf-8")
    )
    frames: list[tuple[str, str, Path]] = []
    for clip in review["clips"]:
        stable = [
            item
            for item in clip["frames"]
            if item.get("kind") == "stable"
        ]
        for frame in stable or [clip["frames"][0]]:
            frames.append(
                (
                    clip["beat_id"],
                    frame["id"],
                    run_dir / frame["path"],
                )
            )
    cell_width, cell_height = 480, 300
    columns = 2
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (cell_width * columns, cell_height * rows),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (beat_id, frame_id, path) in enumerate(frames):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width, cell_height - 30))
        x = index % columns * cell_width
        y = index // columns * cell_height
        sheet.paste(image, (x, y + 30))
        draw.text(
            (x + 6, y + 6),
            f"{beat_id}: {frame_id}",
            fill="black",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("/tmp/math-animation-vertex-form-featured"),
    )
    args = parser.parse_args()

    utterances = [
        (
            "derive.words",
            "Start with standard form. Add and subtract nine, then factor the "
            "perfect square. The final expression exposes a vertex at three, "
            "negative four.",
        ),
        (
            "compare.words",
            "Standard form hides the turning point. Vertex form shows the same "
            "parabola and reveals its vertex immediately.",
        ),
    ]
    audio_path = (
        ROOT / "examples" / "assets" / "vertex_form_featured_narration.wav"
    )
    narration, narration_mode = _system_speech_narration(
        utterances,
        audio_path,
    )
    script = (
        "Derive the vertex form step by step: $y=x^2-6x+5$, then "
        "$y=(x^2-6x+9)-9+5$, and finally $y=(x-3)^2-4$.\n\n"
        "Compare standard form $y=x^2-6x+5$ with vertex form "
        "$y=(x-3)^2-4$; they describe the same parabola, but vertex form "
        "reveals the turning point."
    )
    planning = ExpandedPlanner().plan(
        PlanningRequest(
            project_id="vertex-form-featured",
            title="Completing the square reveals the vertex",
            script=script,
            audience="algebra learners",
            narration=narration,
            style=StyleTemplateRef(
                template_id="midnight-chalk",
                raw={
                    "colors": {
                        "background": "#08111f",
                        "foreground": "#f5f0e6",
                        "muted": "#99a9b8",
                    },
                    "semantic_colors": {
                        "primary": "#54d1bd",
                        "changing": "#ff8b6a",
                        "fixed": "#86a8ff",
                        "positive": "#8ed081",
                    },
                    "typography": {
                        "font": "Avenir Next",
                        "title_size": 46,
                        "body_size": 28,
                        "math_size": 68,
                    },
                    "motion": {
                        "create_seconds": 0.7,
                        "transform_seconds": 0.8,
                        "beat_hold_seconds": 0.5,
                    },
                },
            ),
            render=RenderSettings(
                renderer="cairo",
                quality="l",
                pixel_width=960,
                pixel_height=540,
                frame_rate=24,
                seed=131,
            ),
        )
    )
    pedagogy = evaluate_pedagogy(planning.project)
    examples_dir = ROOT / "examples" / "vertex_form_featured"
    examples_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(examples_dir / "project.json", planning.project)
    write_json_atomic(
        examples_dir / "expanded-planning.json",
        planning.artifact,
    )
    write_json_atomic(examples_dir / "pedagogy.json", pedagogy)

    result = AuthoringPipeline(
        runs_dir=args.runs_dir,
        render_timeout_seconds=600,
    ).run(
        planning.project,
        render=True,
        compose=True,
        minimum_pedagogy_score=0.85,
        use_cache=False,
    )
    review = json.loads(
        (result.run_dir / "review" / "report.json").read_text(encoding="utf-8")
    )
    performance = json.loads(
        (result.run_dir / "performance.json").read_text(encoding="utf-8")
    )
    video = ROOT / "artifacts" / "vertex_form_featured.mp4"
    keyframes = ROOT / "artifacts" / "vertex_form_featured_keyframes.png"
    review_artifact = (
        ROOT / "artifacts" / "vertex_form_featured_review.json"
    )
    assert result.final_video is not None
    shutil.copy2(result.final_video, video)
    _contact_sheet(result.run_dir, keyframes)
    write_json_atomic(review_artifact, review)

    templates = [
        item.selected_template for item in planning.artifact.beats
    ]
    passed = (
        templates == ["equation_sequence", "concept_comparison"]
        and pedagogy.total_score >= 0.85
        and review["status"] == "passed"
        and not review["warnings"]
        and not review["errors"]
    )
    report = {
        "schema_version": "math-animation.vertex-form-featured-report.v1",
        "status": "passed" if passed else "failed",
        "topic": "Completing the square reveals the vertex",
        "narration_mode": narration_mode,
        "alignment_note": (
            "The standalone macOS voice is timed proportionally per word. "
            "Nolan's production aligner remains authoritative."
        ),
        "selected_templates": templates,
        "pedagogy_status": pedagogy.status,
        "pedagogy_score": pedagogy.total_score,
        "dimension_scores": {
            item.dimension: item.score for item in pedagogy.dimensions
        },
        "review_status": review["status"],
        "review_warning_count": len(review["warnings"]),
        "review_error_count": len(review["errors"]),
        "performance": performance,
        "final_video_media": review["final_video_media"],
        "custom_python_rate": 0.0,
        "run_dir": str(result.run_dir),
        "video_artifact": str(video),
        "keyframes_artifact": str(keyframes),
        "review_artifact": str(review_artifact),
    }
    destination = ROOT / "artifacts" / "vertex_form_featured_report.json"
    write_json_atomic(destination, report)
    print(destination)
    print(video)
    print(keyframes)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
