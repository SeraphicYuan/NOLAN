"""Audio transcription and alignment commands (transcribe, align).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


@main.command()
@click.argument('audio_file', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output file path (defaults to same name with .srt extension).')
@click.option('--format', '-f', 'output_format', type=click.Choice(['srt', 'json', 'txt']),
              default='srt', help='Output format.')
@click.option('--model', '-m', type=click.Choice(['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']),
              default='base', help='Whisper model size.')
@click.option('--language', '-l', type=str, default=None,
              help='Language code (e.g., "en", "es"). Auto-detect if not specified.')
@click.pass_context
def transcribe(ctx, audio_file, output, output_format, model, language):
    """Transcribe audio/video to subtitles using Whisper.

    AUDIO_FILE is the path to an audio or video file.

    This command will:
    1. Extract audio (if video file)
    2. Transcribe using Whisper
    3. Output subtitles in specified format

    Examples:

      nolan transcribe voiceover.mp3

      nolan transcribe voiceover.mp3 -o subtitles.srt

      nolan transcribe video.mp4 -f json -m medium

      nolan transcribe audio.wav -l en -m large-v2
    """
    from pathlib import Path

    audio_path = Path(audio_file)

    # Determine output path
    if output is None:
        output_path = audio_path.with_suffix(f'.{output_format}')
    else:
        output_path = Path(output)

    click.echo(f"Input: {audio_path}")
    click.echo(f"Output: {output_path}")
    click.echo(f"Model: {model}")
    click.echo(f"Format: {output_format}")

    _transcribe_audio(audio_path, output_path, output_format, model, language)


def _transcribe_audio(audio_path, output_path, output_format, model_size, language):
    """Implementation of transcribe command."""
    import json
    from nolan.whisper import (
        WhisperTranscriber, WhisperConfig, check_ffmpeg,
        save_srt, segments_to_srt
    )

    # Check ffmpeg
    if not check_ffmpeg():
        click.echo("Error: ffmpeg not found. Please install ffmpeg.")
        return

    # Initialize Whisper
    click.echo("\nLoading Whisper model...")

    def progress(p):
        pct = int(p * 100)
        click.echo(f"  Progress: {pct}%", nl=False)
        click.echo("\r", nl=False)

    segments = None

    # Try CUDA first, fall back to CPU
    try:
        config = WhisperConfig(
            model_size=model_size,
            device='cuda',
            compute_type='float16',
            language=language,
        )
        transcriber = WhisperTranscriber(config)
        click.echo(f"  Trying: CUDA (GPU)")
        click.echo("\nTranscribing...")
        segments = transcriber.transcribe(audio_path, progress_callback=progress)
    except Exception as e:
        click.echo(f"\n  CUDA failed: {str(e)[:50]}...")
        click.echo("  Falling back to CPU...")

        config = WhisperConfig(
            model_size=model_size,
            device='cpu',
            compute_type='int8',
            language=language,
        )
        transcriber = WhisperTranscriber(config)
        click.echo("\nTranscribing (CPU)...")
        segments = transcriber.transcribe(audio_path, progress_callback=progress)

    click.echo(f"\n  Segments: {len(segments)}")

    # Calculate total duration
    if segments:
        duration = segments[-1].end
        click.echo(f"  Duration: {duration:.1f}s")

    # Save output
    click.echo(f"\nSaving {output_format}...")

    if output_format == 'srt':
        save_srt(segments, output_path)

    elif output_format == 'json':
        output_data = {
            "text": " ".join(s.text for s in segments),
            "segments": [
                {"id": i, "start": s.start, "end": s.end, "text": s.text}
                for i, s in enumerate(segments)
            ],
            "language": language or "auto",
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

    elif output_format == 'txt':
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(" ".join(s.text for s in segments))

    click.echo(f"\nDone! Saved to: {output_path}")


@main.command('align')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.argument('audio_file', type=click.Path(exists=True))
@click.option('--model', '-m', type=click.Choice(['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']),
              default='base', help='Whisper model size.')
@click.option('--language', '-l', type=str, default=None,
              help='Language code (e.g., "en"). Auto-detect if not specified.')
@click.option('--save-words', is_flag=True,
              help='Save word-level timestamps to JSON.')
@click.pass_context
def align(ctx, scene_plan, audio_file, model, language, save_words):
    """Align scene plan to audio using word-level timestamps.

    SCENE_PLAN is the path to scene_plan.json.
    AUDIO_FILE is the path to the voiceover audio.

    This command will:
    1. Transcribe audio with word-level timestamps
    2. Match each scene's narration_excerpt to the word stream
    3. Update scene_plan.json with start_seconds and end_seconds

    Examples:

      nolan align scene_plan.json voiceover.mp3

      nolan align scene_plan.json voiceover.mp3 -m medium --save-words
    """
    from pathlib import Path
    from nolan.scenes import ScenePlan

    scene_plan_path = Path(scene_plan)
    audio_path = Path(audio_file)

    click.echo(f"Scene plan: {scene_plan_path}")
    click.echo(f"Audio: {audio_path}")
    click.echo(f"Model: {model}")

    # Load scene plan
    plan = ScenePlan.load(str(scene_plan_path))

    # Flatten scenes for alignment
    all_scenes = []
    scene_map = {}  # Map scene_id to (section, index) for updating
    for section_name, scenes in plan.sections.items():
        for i, scene in enumerate(scenes):
            scene_dict = {
                'id': f"{section_name}_{scene.id}",  # Unique ID
                'narration_excerpt': scene.narration_excerpt,
            }
            all_scenes.append(scene_dict)
            scene_map[scene_dict['id']] = (section_name, i)

    click.echo(f"\nScenes to align: {len(all_scenes)}")

    # Transcribe and align
    from nolan.aligner import transcribe_and_align, save_word_timestamps, save_unmatched_scenes

    def progress(phase, p):
        if phase == 'transcribing':
            click.echo(f"\rTranscribing: {int(p * 100)}%", nl=False)
        elif phase == 'aligning':
            if p == 0:
                click.echo("\nAligning scenes...")

    words, alignments, unmatched = transcribe_and_align(
        audio_path,
        all_scenes,
        model_size=model,
        language=language,
        progress_callback=progress,
    )

    click.echo(f"\nWords transcribed: {len(words)}")
    click.echo(f"Alignments: {len(alignments)}")

    # Save word timestamps if requested
    if save_words:
        words_path = scene_plan_path.parent / 'word_timestamps.json'
        save_word_timestamps(words, words_path)
        click.echo(f"Word timestamps saved: {words_path}")

    # Save unmatched scenes for review
    if unmatched:
        unmatched_path = scene_plan_path.parent / 'unmatched_align_scenes.json'
        save_unmatched_scenes(unmatched, unmatched_path)
        click.echo(f"Unmatched scenes saved: {unmatched_path}")

    # Update scene plan with alignments
    matched = 0
    low_confidence = 0
    no_match = 0
    for alignment in alignments:
        if alignment.scene_id in scene_map:
            section_name, idx = scene_map[alignment.scene_id]
            scene = plan.sections[section_name][idx]
            scene.start_seconds = alignment.start_seconds
            scene.end_seconds = alignment.end_seconds

            if alignment.confidence >= 0.8:
                matched += 1
            elif alignment.confidence > 0:
                low_confidence += 1
            else:
                no_match += 1

    # Tile the windows to the audio: extend each scene to the next scene's
    # start (last one to audio end) so pauses belong to the preceding scene
    # and total video duration equals the narration.
    try:
        import json as _json
        import subprocess as _sp
        from pathlib import Path as _P

        def _dur(f):
            _pr = _sp.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                           "-show_format", str(f)], capture_output=True, text=True)
            return float(_json.loads(_pr.stdout)["format"]["duration"])

        # Beat-anchored mode: when the VO was synthesized per-section (the
        # generate-voiceover pipeline keeps _work/sec_NNNN.wav), the section
        # boundaries in the audio are EXACT — confine each section's scenes
        # to its span so sync error can never cross a beat boundary.
        sec_files = sorted(_P(str(audio_file)).parent.glob("_work/sec_*.wav"))
        if sec_files and len(sec_files) == len(plan.sections):
            from nolan.scenes import anchor_scenes_to_sections
            n = anchor_scenes_to_sections(plan, [_dur(f) for f in sec_files])
            click.echo(f"  Beat-anchored {n} scenes to {len(sec_files)} exact section spans")
        else:
            from nolan.scenes import tile_scene_windows
            audio_dur = _dur(audio_file)
            tiled = tile_scene_windows(plan, float(audio_dur))
            click.echo(f"  Tiled {tiled} scene windows to the audio ({audio_dur:.1f}s)")
    except Exception as exc:
        click.echo(f"  (window tiling skipped: {exc})")

    # Save updated plan
    plan.save(str(scene_plan_path))

    # Summary
    click.echo(f"\nAlignment Summary:")
    click.echo(f"  High confidence (>=80%): {matched}")
    click.echo(f"  Low confidence (<80%): {low_confidence}")
    click.echo(f"  No match (estimated): {no_match}")
    click.echo(f"\nScene plan updated: {scene_plan_path}")

    # Show first few alignments as sample
    click.echo(f"\nSample alignments:")
    for a in alignments[:5]:
        conf = f"{a.confidence*100:.0f}%" if a.confidence else "N/A"
        click.echo(f"  {a.scene_id}: {a.start_seconds:.1f}s - {a.end_seconds:.1f}s ({conf})")


