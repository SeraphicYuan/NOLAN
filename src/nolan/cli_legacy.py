"""Command-line interface for NOLAN."""

import asyncio
import sys
from pathlib import Path

import click

# Fix Windows console encoding for Unicode filenames
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from nolan import __version__
from nolan.config import load_config


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def main(ctx):
    """NOLAN - Video Essay Pipeline.

    Transform structured essays into video production packages.
    """
    ctx.ensure_object(dict)
    ctx.obj['config'] = load_config()


def _get_project_output_path(project: str = None, output: str = None, essay_path: Path = None) -> Path:
    """Determine output path from project name or output option.

    Priority: --output > --project > derived from essay name
    """
    if output:
        return Path(output)
    if project:
        return Path("projects") / project
    if essay_path:
        # Derive project name from essay filename
        project_name = essay_path.stem.lower().replace(" ", "-").replace("_", "-")
        return Path("projects") / project_name
    return Path("projects") / "default"


@main.command()
@click.argument('essay', type=click.Path(exists=True))
@click.option('--project', '-p', type=str, default=None,
              help='Project name (outputs to projects/<name>/).')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output directory (overrides --project).')
@click.option('--skip-scenes', is_flag=True, help='Skip scene design step.')
@click.option('--skip-assets', is_flag=True, help='Skip asset matching step.')
@click.pass_context
def process(ctx, essay, project, output, skip_scenes, skip_assets):
    """Process an essay through the full pipeline.

    ESSAY is the path to your markdown essay file.

    This command will:
    1. Convert the essay to a video script
    2. Design visual scenes for each section
    3. Match scenes to your video library
    4. Generate images via ComfyUI (if configured)

    Examples:

        nolan process essay.md --project venezuela

        nolan process my-essay.md  # outputs to projects/my-essay/
    """
    config = ctx.obj['config']
    essay_path = Path(essay)
    output_path = _get_project_output_path(project, output, essay_path)

    click.echo(f"Processing: {essay_path.name}")
    click.echo(f"Project: {output_path}")

    asyncio.run(_process_essay(config, essay_path, output_path, skip_scenes, skip_assets))


async def _process_essay(config, essay_path, output_path, skip_scenes, skip_assets):
    """Async implementation of process command."""
    from nolan.parser import parse_essay
    from nolan.script import ScriptConverter
    from nolan.scenes import SceneDesigner
    from nolan.llm import create_text_llm

    # Setup
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "assets" / "generated").mkdir(parents=True, exist_ok=True)
    (output_path / "assets" / "matched").mkdir(parents=True, exist_ok=True)

    # Initialize LLM
    llm = create_text_llm(config)

    # Step 1: Parse essay
    click.echo("\n[1/4] Parsing essay...")
    essay_text = essay_path.read_text(encoding='utf-8')
    sections = parse_essay(essay_text)
    click.echo(f"  Found {len(sections)} sections")

    # Step 2: Convert to script
    click.echo("\n[2/4] Converting to script...")
    converter = ScriptConverter(llm, words_per_minute=config.defaults.words_per_minute)
    script = await converter.convert_essay(sections)

    script_path = output_path / "script.md"
    script_path.write_text(script.to_markdown(), encoding='utf-8')
    click.echo(f"  Script saved: {script_path}")
    click.echo(f"  Total duration: {script.total_duration:.0f}s")

    if skip_scenes:
        click.echo("\n[3/4] Skipping scene design (--skip-scenes)")
        click.echo("\n[4/4] Skipping asset matching (--skip-assets)")
        click.echo("\nDone! Script generated.")
        return

    # Step 3: Design scenes
    click.echo("\n[3/4] Designing scenes...")
    designer = SceneDesigner(llm)
    plan = await designer.design_full_plan(script.sections)

    plan_path = output_path / "scene_plan.json"
    plan.save(str(plan_path))
    click.echo(f"  Scene plan saved: {plan_path}")
    click.echo(f"  Total scenes: {len(plan.all_scenes)}")

    if skip_assets:
        click.echo("\n[4/4] Skipping asset matching (--skip-assets)")
        click.echo("\nDone! Script and scenes generated.")
        return

    # Step 4: Match assets
    click.echo("\n[4/4] Matching assets...")
    # Asset matching requires indexed library - skip if not available
    click.echo("  (Asset matching requires indexed video library)")
    click.echo("  Run 'nolan index <video_folder>' first to index your library")

    click.echo(f"\nDone! Output saved to: {output_path}")


@main.command()
@click.argument('essay', type=click.Path(exists=True))
@click.option('--project', '-p', type=str, default=None,
              help='Project name (outputs to projects/<name>/).')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output directory (overrides --project).')
@click.pass_context
def script(ctx, essay, project, output):
    """Convert an essay to a narration script.

    ESSAY is the path to your markdown essay file.

    This command will:
    1. Parse the essay into sections
    2. Convert each section to spoken narration
    3. Output script.md (human-readable) and script.json (for scene design)

    After this step, you can:
    - Review and edit the script
    - Record voiceover from script.md
    - Run 'nolan design script.json' to generate scene plans
    """
    config = ctx.obj['config']
    essay_path = Path(essay)
    output_path = _get_project_output_path(project, output, essay_path)

    click.echo(f"Converting: {essay_path.name}")
    click.echo(f"Project: {output_path}")

    asyncio.run(_convert_script(config, essay_path, output_path))


async def _convert_script(config, essay_path, output_path):
    """Async implementation of script command."""
    from nolan.parser import parse_essay
    from nolan.script import ScriptConverter
    from nolan.llm import create_text_llm

    # Setup
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize LLM
    llm = create_text_llm(config)

    # Step 1: Parse essay
    click.echo("\n[1/2] Parsing essay...")
    essay_text = essay_path.read_text(encoding='utf-8')
    sections = parse_essay(essay_text)
    click.echo(f"  Found {len(sections)} sections")

    # Step 2: Convert to script
    click.echo("\n[2/2] Converting to narration script...")
    converter = ScriptConverter(llm, words_per_minute=config.defaults.words_per_minute)
    script = await converter.convert_essay(sections)

    # Save markdown (human-readable)
    script_md_path = output_path / "script.md"
    script_md_path.write_text(script.to_markdown(), encoding='utf-8')
    click.echo(f"  Script (markdown): {script_md_path}")

    # Save JSON (for scene design)
    script_json_path = output_path / "script.json"
    script.save_json(str(script_json_path))
    click.echo(f"  Script (JSON): {script_json_path}")

    click.echo(f"\n  Sections: {len(script.sections)}")
    click.echo(f"  Total duration: {script.total_duration:.0f}s (~{script.total_duration/60:.1f} min)")

    click.echo(f"\nDone! Next steps:")
    click.echo(f"  1. Review/edit script.md")
    click.echo(f"  2. Run: nolan design {script_json_path}")


@main.command()
@click.argument('script_file', type=click.Path(exists=True))
@click.option('--project', '-p', type=str, default=None,
              help='Project name (outputs to projects/<name>/).')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output directory (overrides --project).')
@click.option('--beats-only', is_flag=True,
              help='Run Pass 1 only: detect beats and visual categories for review.')
@click.pass_context
def design(ctx, script_file, project, output, beats_only):
    """Design visual scenes from a script (two-pass approach).

    SCRIPT_FILE is the path to script.json (from 'nolan script' command).

    TWO-PASS WORKFLOW:
    Pass 1 (--beats-only): Break narration into beats, assign visual categories.
           Outputs beats.json and av_script.txt for human review.

    Pass 2 (default): Enrich beats with category-specific details.
           Outputs full scene_plan.json.

    VISUAL CATEGORIES:
    - b-roll: Stock/archival footage
    - graphics: Infographics, charts, text overlays
    - a-roll: Primary footage of subject
    - generated: AI-generated images
    - host: Face-to-camera moments
    """
    config = ctx.obj['config']
    script_path = Path(script_file)

    # Priority: --output > --project > script file's directory
    if output:
        output_path = Path(output)
    elif project:
        output_path = Path("projects") / project
    else:
        output_path = script_path.parent

    click.echo(f"Designing scenes from: {script_path.name}")
    click.echo(f"Project: {output_path}")
    if beats_only:
        click.echo("Mode: Pass 1 only (beats detection)")

    asyncio.run(_design_scenes(config, script_path, output_path, beats_only))


async def _design_scenes(config, script_path, output_path, beats_only=False):
    """Async implementation of design command."""
    import json
    from nolan.script import Script
    from nolan.scenes import SceneDesigner
    from nolan.llm import create_text_llm

    # Setup
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize LLM
    llm = create_text_llm(config)

    # Step 1: Load script
    click.echo("\n[1/2] Loading script...")
    script = Script.load_json(str(script_path))
    click.echo(f"  Sections: {len(script.sections)}")
    click.echo(f"  Duration: {script.total_duration:.0f}s")

    designer = SceneDesigner(llm)

    if beats_only:
        # Pass 1 only: Detect beats
        click.echo("\n[2/2] Pass 1: Detecting beats...")
        beat_plans = await designer.design_full_beats(script.sections)

        # Save beats JSON
        beats_data = {"sections": [bp.to_dict() for bp in beat_plans]}
        beats_path = output_path / "beats.json"
        with open(beats_path, 'w', encoding='utf-8') as f:
            json.dump(beats_data, f, indent=2)

        # Save A/V script for human review
        av_script_path = output_path / "av_script.txt"
        with open(av_script_path, 'w', encoding='utf-8') as f:
            for bp in beat_plans:
                f.write(bp.to_av_script())
                f.write("\n\n")

        # Summary
        total_beats = sum(len(bp.beats) for bp in beat_plans)
        visual_holes = sum(1 for bp in beat_plans for b in bp.beats if b.has_visual_hole)
        categories = {}
        for bp in beat_plans:
            for beat in bp.beats:
                categories[beat.category] = categories.get(beat.category, 0) + 1

        click.echo(f"\n  Beats JSON: {beats_path}")
        click.echo(f"  A/V Script: {av_script_path}")
        click.echo(f"  Total beats: {total_beats}")
        if visual_holes:
            click.echo(f"  ⚠️  Visual holes: {visual_holes}")
        click.echo(f"  Categories:")
        for cat, count in sorted(categories.items()):
            click.echo(f"    - {cat}: {count}")

        click.echo(f"\nDone! Review the A/V script, then run:")
        click.echo(f"  nolan design {script_path}  # (without --beats-only)")

    else:
        # Full two-pass design
        click.echo("\n[2/2] Designing scenes (Pass 1 + Pass 2)...")
        plan = await designer.design_full_plan(script.sections, enrich=True)

        # Save scene plan
        plan_path = output_path / "scene_plan.json"
        plan.save(str(plan_path))

        # Count scene types
        type_counts = {}
        sync_point_count = 0
        for scene in plan.all_scenes:
            vtype = scene.visual_type
            type_counts[vtype] = type_counts.get(vtype, 0) + 1
            sync_point_count += len(scene.sync_points)

        click.echo(f"\n  Scene plan: {plan_path}")
        click.echo(f"  Total scenes: {len(plan.all_scenes)}")
        click.echo(f"  Sync points: {sync_point_count}")
        click.echo(f"  Scene types:")
        for vtype, count in sorted(type_counts.items()):
            click.echo(f"    - {vtype}: {count}")

        click.echo(f"\nDone! Next steps:")
        click.echo(f"  1. Review scene_plan.json")
        click.echo(f"  2. Run: nolan prepare-assets {plan_path}")


@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True,
              help='Scan subdirectories (only applies to directories).')
@click.option('--frame-interval', default=5, type=int,
              help='Seconds between sampled frames (for fixed sampler).')
@click.option('--sampler', '-s', default=None,
              type=click.Choice(['ffmpeg_scene', 'hybrid', 'fixed', 'scene_change']),
              help='Frame sampling strategy. ffmpeg_scene (default) is 10-50x faster.')
@click.option('--vision', default='openrouter',
              type=click.Choice(['openrouter', 'gemini', 'ollama']),
              help='Vision provider for frame analysis. Default: openrouter (qwen/qwen3.7-plus, reasoning off).')
@click.option('--whisper/--no-whisper', default=True,
              help='Auto-generate transcripts with Whisper when no subtitle file exists (default: enabled).')
@click.option('--whisper-model', default='base',
              type=click.Choice(['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']),
              help='Whisper model size (default: base). Larger = better quality, slower.')
@click.option('--project', '-p', type=str, default=None,
              help='Project slug to associate indexed videos with.')
@click.option('--concurrency', '-c', default=None, type=int,
              help='Max concurrent API calls (defaults to config.indexing.concurrency).')
@click.option('--force', is_flag=True, default=False,
              help='Force reindexing even if video is already indexed.')
@click.pass_context
def index(ctx, path, recursive, frame_interval, sampler, vision, whisper, whisper_model, project, concurrency, force):
    """Index videos for asset matching.

    PATH can be a video file or a directory containing videos.

    This scans video files, samples frames, and uses AI to describe
    what's in each segment. The index is stored locally for fast
    searching during the process command.

    Transcripts are automatically generated with Whisper when no subtitle
    file (.srt, .vtt) exists. Use --no-whisper to disable this.
    Requires ffmpeg for audio extraction.

    Use --project to associate indexed videos with a specific project.
    Create a project first with: nolan projects create "My Project"

    Use --concurrency to control parallel API calls (defaults to config.indexing.concurrency).
    Lower values for rate-limited accounts, higher for paid tiers.
    """
    config = ctx.obj['config']
    input_path = Path(path)

    if concurrency is None:
        concurrency = config.indexing.concurrency

    # Detect if input is a file or directory
    is_single_file = input_path.is_file()

    # Resolve project slug to ID
    project_id = None
    if project:
        from nolan.indexer import VideoIndex
        db_path = Path(config.indexing.database).expanduser()
        idx = VideoIndex(db_path)
        proj = idx.get_project(project)
        if not proj:
            click.echo(f"Error: Project '{project}' not found.")
            click.echo("Create it with: nolan projects create \"Project Name\"")
            click.echo("Or list existing: nolan projects list")
            return
        project_id = proj['id']
        click.echo(f"Project: {proj['name']} ({proj['slug']})")

    # Use CLI sampler or fall back to config default
    sampling_strategy = sampler or config.indexing.sampling_strategy

    if is_single_file:
        click.echo(f"Indexing file: {input_path.name}")
    else:
        click.echo(f"Indexing directory: {input_path}")
        click.echo(f"Recursive: {recursive}")
    click.echo(f"Sampler: {sampling_strategy}")
    click.echo(f"Concurrency: {concurrency}")
    if force:
        click.echo("Force reindex: enabled")

    asyncio.run(_index_videos(config, input_path, recursive, frame_interval, sampling_strategy, vision, whisper, whisper_model, project_id, concurrency, force, is_single_file))


async def _index_videos(config, input_path, recursive, frame_interval, sampling_strategy, vision_provider='ollama', whisper_enabled=False, whisper_model='base', project_id=None, concurrency=10, force=False, is_single_file=False):
    """Async implementation of index command."""
    from nolan.indexer import HybridVideoIndexer, VideoIndex
    from nolan.vision import create_vision_provider, VisionConfig
    from nolan.sampler import create_sampler, SamplerConfig, SamplingStrategy
    from nolan.llm import create_text_llm

    # Initialize database
    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    # Determine vision model based on provider
    if vision_provider == "gemini":
        vision_model = "gemini-3-flash-preview"
        api_key = config.gemini.api_key
    elif vision_provider == "openrouter":
        # OpenRouter model slugs contain '/'; fall back to the default if the
        # configured model looks like an Ollama tag (e.g. "qwen3-vl:8b").
        vision_model = config.vision.model if "/" in config.vision.model else "qwen/qwen3.7-plus"
        api_key = config.vision.openrouter_api_key
    else:  # ollama
        vision_model = config.vision.model if "/" not in config.vision.model else "qwen3-vl:8b"
        api_key = None

    # Initialize vision provider
    vision_config = VisionConfig(
        provider=vision_provider,
        model=vision_model,
        host=config.vision.host,
        port=config.vision.port,
        timeout=config.vision.timeout,
        api_key=api_key,
        base_url=config.vision.base_url,
        reasoning_enabled=config.vision.reasoning_enabled,
        reasoning_max_tokens=config.vision.reasoning_max_tokens,
    )
    vision = create_vision_provider(vision_config)

    # Check vision provider connection
    click.echo(f"\nVision provider: {vision_provider} ({vision_model})")
    if not await vision.check_connection():
        click.echo(f"Error: Cannot connect to {vision_provider}. Is it running?")
        return

    # Initialize sampler
    sampler_config = SamplerConfig(
        strategy=SamplingStrategy(sampling_strategy),
        fixed_interval=float(frame_interval),
        min_interval=config.indexing.min_interval,
        max_interval=config.indexing.max_interval,
        scene_threshold=config.indexing.scene_threshold,
        ffmpeg_scene_threshold=getattr(config.indexing, 'ffmpeg_scene_threshold', None),  # None = adaptive 5σ
        ffmpeg_adaptive_sigma=getattr(config.indexing, 'ffmpeg_adaptive_sigma', 5.0),
    )
    sampler = create_sampler(sampler_config)
    click.echo(f"Sampling strategy: {sampling_strategy}")

    # Initialize Whisper transcriber (if enabled)
    whisper_transcriber = None
    if whisper_enabled:
        try:
            from nolan.whisper import WhisperTranscriber, WhisperConfig, check_ffmpeg
            if not check_ffmpeg():
                click.echo("Warning: ffmpeg not found. Whisper transcription disabled.")
            else:
                # Try CUDA first, fall back to CPU
                whisper_config = WhisperConfig(
                    model_size=whisper_model,
                    device='cuda',
                    compute_type='float16'
                )
                try:
                    whisper_transcriber = WhisperTranscriber(whisper_config)
                    # Test if CUDA works by accessing the model
                    _ = whisper_transcriber.model
                    click.echo(f"Whisper: enabled (model: {whisper_model}, device: cuda)")
                except Exception:
                    # Fall back to CPU
                    whisper_config = WhisperConfig(
                        model_size=whisper_model,
                        device='cpu',
                        compute_type='int8'
                    )
                    whisper_transcriber = WhisperTranscriber(whisper_config)
                    click.echo(f"Whisper: enabled (model: {whisper_model}, device: cpu)")
        except ImportError as e:
            click.echo(f"Warning: Whisper unavailable ({e}). Transcription disabled.")

    if not whisper_transcriber:
        click.echo("Whisper: disabled")

    # Initialize LLM for inference (if enabled)
    llm = None
    if config.indexing.enable_inference:
        llm = create_text_llm(config)
        click.echo(f"Inference: enabled ({config.llm.provider}:{config.llm.model})")
    else:
        click.echo("Inference: disabled")

    click.echo(f"Transcript: {'enabled' if config.indexing.enable_transcript else 'disabled'}")

    # Create indexer
    indexer = HybridVideoIndexer(
        vision_provider=vision,
        index=index,
        sampler=sampler,
        llm_client=llm,
        whisper_transcriber=whisper_transcriber,
        enable_transcript=config.indexing.enable_transcript,
        enable_inference=config.indexing.enable_inference,
        project_id=project_id,
        concurrency=concurrency,
        force_reindex=force
    )

    def progress(current, total, message):
        click.echo(f"  [{current}/{total}] {message}")

    if is_single_file:
        # Index single video file
        click.echo(f"\nIndexing single video...")
        segments = await indexer.index_video(input_path, progress_callback=progress)
        stats = {
            'total': 1,
            'indexed': 1 if segments > 0 else 0,
            'skipped': 0 if segments > 0 else 1,
            'segments': segments
        }
    else:
        # Index directory
        click.echo("\nScanning for videos...")
        stats = await indexer.index_directory(input_path, recursive=recursive, progress_callback=progress)

    click.echo(f"\nIndexing complete:")
    click.echo(f"  Videos found: {stats['total']}")
    click.echo(f"  Newly indexed: {stats['indexed']}")
    click.echo(f"  Skipped (unchanged): {stats['skipped']}")
    click.echo(f"  Segments added: {stats['segments']}")
    click.echo(f"\nDatabase: {db_path}")

    # Auto-sync vectors if any videos were indexed
    if stats['indexed'] > 0:
        click.echo("\n[Auto] Syncing vectors for semantic search...")
        try:
            from nolan.vector_search import VectorSearch
            vector_db_path = db_path.parent / "vectors"
            vector_search = VectorSearch(vector_db_path, index=index)

            # Only sync the newly indexed videos (incremental sync handles this via fingerprints)
            def vec_progress(current, total, msg):
                click.echo(f"\r  [{current}/{total}] {msg[:50]:<50}", nl=False)

            result = vector_search.sync_from_index(
                project_id=project_id,
                progress_callback=vec_progress,
                incremental=True
            )
            click.echo()  # newline

            skipped = result.get('skipped', 0)
            if skipped > 0:
                click.echo(f"  Vectors: {result['segments']} segments, {result['clusters']} clusters (skipped {skipped} unchanged)")
            else:
                click.echo(f"  Vectors: {result['segments']} segments, {result['clusters']} clusters")
        except Exception as e:
            click.echo(f"  Warning: Vector sync failed: {e}")
            click.echo("  Run 'nolan sync-vectors' manually to enable semantic search.")


@main.command()
@click.argument('video', type=click.Path(exists=True), required=False)
@click.option('--output', '-o', type=click.Path(), help='Output JSON file path.')
@click.option('--all', 'export_all', is_flag=True, help='Export all indexed videos.')
@click.pass_context
def export(ctx, video, output, export_all):
    """Export indexed video segments to JSON.

    VIDEO is the path to an indexed video file.

    Examples:
        nolan export video.mp4 -o segments.json
        nolan export --all -o library.json
    """
    import json
    from nolan.indexer import VideoIndex

    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()

    if not db_path.exists():
        click.echo(f"Error: Database not found at {db_path}")
        click.echo("Run 'nolan index' first to index videos.")
        return

    index = VideoIndex(db_path)

    if export_all:
        # Export all videos
        _export_all_videos(index, output)
    elif video:
        # Export single video
        _export_single_video(index, Path(video), output)
    else:
        click.echo("Error: Provide a VIDEO path or use --all flag.")
        return


def _export_single_video(index, video_path: Path, output_path):
    """Export segments for a single video."""
    import json

    # Try both absolute and relative paths
    segments = index.get_segments(str(video_path))
    if not segments:
        segments = index.get_segments(str(video_path.resolve()))
    if not segments:
        # Try matching by filename
        import sqlite3
        with sqlite3.connect(index.db_path) as conn:
            for row in conn.execute('SELECT path FROM videos'):
                if video_path.name in row[0]:
                    segments = index.get_segments(row[0])
                    break

    if not segments:
        click.echo(f"Error: No indexed segments found for {video_path}")
        return

    output = {
        'video': {
            'path': str(video_path),
            'name': video_path.name
        },
        'segments': []
    }

    for seg in segments:
        segment_data = {
            'timestamp_start': seg.timestamp_start,
            'timestamp_end': seg.timestamp_end,
            'timestamp_formatted': seg.timestamp_formatted,
            'duration': seg.duration,
            'frame_description': seg.frame_description,
            'transcript': seg.transcript,
            'combined_summary': seg.combined_summary,
            'inferred_context': seg.inferred_context.to_dict() if seg.inferred_context else None,
            'sample_reason': seg.sample_reason
        }
        output['segments'].append(segment_data)

    # Determine output path
    if output_path is None:
        output_path = video_path.with_suffix('.segments.json')
    else:
        output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    click.echo(f"Exported {len(segments)} segments to {output_path}")


def _export_all_videos(index, output_path):
    """Export all indexed videos."""
    import json
    import sqlite3

    with sqlite3.connect(index.db_path) as conn:
        videos = [row[0] for row in conn.execute('SELECT path FROM videos')]

    if not videos:
        click.echo("No indexed videos found.")
        return

    output = {'videos': []}

    for video_path in videos:
        segments = index.get_segments(video_path)
        video_data = {
            'path': video_path,
            'name': Path(video_path).name,
            'segments': []
        }

        for seg in segments:
            segment_data = {
                'timestamp_start': seg.timestamp_start,
                'timestamp_end': seg.timestamp_end,
                'timestamp_formatted': seg.timestamp_formatted,
                'duration': seg.duration,
                'frame_description': seg.frame_description,
                'transcript': seg.transcript,
                'combined_summary': seg.combined_summary,
                'inferred_context': seg.inferred_context.to_dict() if seg.inferred_context else None,
                'sample_reason': seg.sample_reason
            }
            video_data['segments'].append(segment_data)

        output['videos'].append(video_data)

    # Determine output path - default to .scratch/ to avoid root clutter
    if output_path is None:
        scratch_dir = Path('.scratch')
        scratch_dir.mkdir(exist_ok=True)
        output_path = scratch_dir / 'library_export.json'
    output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_segments = sum(len(v['segments']) for v in output['videos'])
    click.echo(f"Exported {len(videos)} videos ({total_segments} segments) to {output_path}")


@main.command()
@click.argument('video', type=click.Path(exists=True), required=False)
@click.option('--output', '-o', type=click.Path(), help='Output JSON file path.')
@click.option('--all', 'cluster_all', is_flag=True, help='Cluster all indexed videos.')
@click.option('--summarize/--no-summarize', default=True,
              help='Generate cluster summaries using LLM.')
@click.option('--refine/--no-refine', default=True,
              help='Use LLM to detect story boundaries (default: enabled). Use --no-refine to skip.')
@click.option('--max-gap', default=2.0, type=float,
              help='Maximum time gap (seconds) between segments to consider clustering.')
@click.option('--concurrency', '-c', default=10, type=int,
              help='Max concurrent API calls for summary generation (default 10).')
@click.option('--chunk-size', default=50, type=int,
              help='Segments per batch for boundary detection (default 50).')
@click.option('--overlap', default=15, type=int,
              help='Overlap between chunks for boundary detection (default 15).')
@click.pass_context
def cluster(ctx, video, output, cluster_all, summarize, refine, max_gap, concurrency, chunk_size, overlap):
    """Cluster video segments into story moments.

    VIDEO is the path to an indexed video file.

    Clustering groups continuous segments that share:
    - Same characters/people
    - Same location
    - Related story context

    Examples:
        nolan cluster video.mp4 -o clusters.json
        nolan cluster --all -o all_clusters.json
        nolan cluster video.mp4 --no-refine  # Skip LLM boundary detection (faster)
        nolan cluster video.mp4 -c 15 --chunk-size 40  # Custom settings
    """
    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()

    if not db_path.exists():
        click.echo(f"Error: Database not found at {db_path}")
        click.echo("Run 'nolan index' first to index videos.")
        return

    if cluster_all:
        asyncio.run(_cluster_all_videos(config, db_path, output, summarize, refine, max_gap, concurrency, chunk_size, overlap))
    elif video:
        asyncio.run(_cluster_video(config, db_path, Path(video), output, summarize, refine, max_gap, concurrency, chunk_size, overlap))
    else:
        click.echo("Error: Provide a VIDEO path or use --all flag.")


async def _cluster_video(config, db_path, video_path, output_path, summarize, refine, max_gap, concurrency, chunk_size, overlap):
    """Cluster segments for a single video."""
    import json
    from nolan.indexer import VideoIndex
    from nolan.clustering import cluster_segments, ClusterAnalyzer, StoryBoundaryDetector

    index = VideoIndex(db_path)

    # Find segments
    segments = index.get_segments(str(video_path))
    if not segments:
        segments = index.get_segments(str(video_path.resolve()))
    if not segments:
        # Try matching by filename
        import sqlite3
        with sqlite3.connect(index.db_path) as conn:
            for row in conn.execute('SELECT path FROM videos'):
                if video_path.name in row[0]:
                    segments = index.get_segments(row[0])
                    break

    if not segments:
        click.echo(f"Error: No indexed segments found for {video_path}")
        return

    click.echo(f"Found {len(segments)} segments")

    # Cluster segments
    click.echo("Clustering segments...")
    clusters = cluster_segments(segments, max_gap=max_gap)
    click.echo(f"Created {len(clusters)} initial clusters")

    # Refine with LLM story boundary detection (smart chunking)
    if refine and config.gemini.api_key:
        click.echo(f"Detecting story boundaries (chunk_size={chunk_size})...")
        from nolan.llm import create_text_llm
        llm = create_text_llm(config)
        detector = StoryBoundaryDetector(llm, chunk_size=chunk_size, overlap=overlap)

        def refine_progress(current, total, msg):
            click.echo(f"  [{current}/{total}] {msg}")

        clusters = await detector.refine_clusters(clusters, progress_callback=refine_progress)
        click.echo(f"Refined to {len(clusters)} clusters")

    # Generate summaries (async batch processing)
    if summarize and config.gemini.api_key:
        click.echo(f"Generating cluster summaries (concurrency={concurrency})...")
        from nolan.llm import create_text_llm
        llm = create_text_llm(config)
        analyzer = ClusterAnalyzer(llm, concurrency=concurrency)

        def summary_progress(current, total, msg):
            click.echo(f"  [{current}/{total}] {msg}")

        clusters = await analyzer.analyze_clusters(clusters, progress_callback=summary_progress)

    # Save clusters to database
    import sqlite3
    # Find video in database by matching path
    video_id = None
    with sqlite3.connect(index.db_path) as conn:
        for row in conn.execute('SELECT id, path FROM videos'):
            if video_path.name in row[1] or str(video_path) == row[1]:
                video_id = row[0]
                break

    if video_id:
        # Clear existing clusters for this video
        with sqlite3.connect(index.db_path) as conn:
            conn.execute("DELETE FROM clusters WHERE video_id = ?", (video_id,))
            conn.commit()

        # Add new clusters
        click.echo("Saving clusters to database...")
        for i, c in enumerate(clusters):
            index.add_cluster(
                video_id=video_id,
                cluster_index=i,
                timestamp_start=c.timestamp_start,
                timestamp_end=c.timestamp_end,
                cluster_summary=c.cluster_summary,
                people=c.people,
                locations=c.locations,
                segment_ids=None
            )

    # Build output
    output = {
        'video': {
            'path': str(video_path),
            'name': video_path.name
        },
        'clustering': {
            'max_gap': max_gap,
            'refined': refine,
            'summarized': summarize
        },
        'clusters': [c.to_dict() for c in clusters]
    }

    # Determine output path
    if output_path is None:
        output_path = video_path.with_suffix('.clusters.json')
    else:
        output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    click.echo(f"\nExported {len(clusters)} clusters to {output_path}")

    # Print summary
    for c in clusters:
        click.echo(f"  Cluster {c.id}: {c.timestamp_formatted} ({len(c.segments)} segments, {c.duration:.1f}s)")


async def _cluster_all_videos(config, db_path, output_path, summarize, refine, max_gap, concurrency, chunk_size, overlap):
    """Cluster all indexed videos."""
    import json
    import sqlite3
    from nolan.indexer import VideoIndex
    from nolan.clustering import cluster_segments, ClusterAnalyzer, StoryBoundaryDetector

    index = VideoIndex(db_path)

    with sqlite3.connect(db_path) as conn:
        videos = [row[0] for row in conn.execute('SELECT path FROM videos')]

    if not videos:
        click.echo("No indexed videos found.")
        return

    # Setup LLM if needed
    llm = None
    detector = None
    analyzer = None
    if (summarize or refine) and config.gemini.api_key:
        from nolan.llm import create_text_llm
        llm = create_text_llm(config)
        if refine:
            detector = StoryBoundaryDetector(llm, chunk_size=chunk_size, overlap=overlap)
        if summarize:
            analyzer = ClusterAnalyzer(llm, concurrency=concurrency)

    output = {'videos': []}

    for video_path in videos:
        click.echo(f"\nProcessing: {Path(video_path).name}")
        segments = index.get_segments(video_path)

        if not segments:
            click.echo("  No segments found, skipping")
            continue

        # Cluster
        clusters = cluster_segments(segments, max_gap=max_gap)
        click.echo(f"  Created {len(clusters)} initial clusters from {len(segments)} segments")

        # Refine with smart chunking
        if refine and detector:
            clusters = await detector.refine_clusters(clusters)
            click.echo(f"  Refined to {len(clusters)} clusters")

        # Summarize with async batch processing
        if summarize and analyzer:
            clusters = await analyzer.analyze_clusters(clusters)
            click.echo(f"  Generated {len(clusters)} summaries")

        # Save clusters to database
        video_id = index.get_video_id_by_path(video_path)
        if video_id:
            # Clear existing clusters for this video
            with sqlite3.connect(db_path) as conn:
                conn.execute("DELETE FROM clusters WHERE video_id = ?", (video_id,))
                conn.commit()

            # Add new clusters
            for i, c in enumerate(clusters):
                index.add_cluster(
                    video_id=video_id,
                    cluster_index=i,
                    timestamp_start=c.timestamp_start,
                    timestamp_end=c.timestamp_end,
                    cluster_summary=c.cluster_summary,
                    people=c.people,
                    locations=c.locations,
                    segment_ids=None  # Could track segment IDs if needed
                )

        video_data = {
            'path': video_path,
            'name': Path(video_path).name,
            'clusters': [c.to_dict() for c in clusters]
        }
        output['videos'].append(video_data)

    # Save - default to .scratch/ to avoid root clutter
    if output_path is None:
        scratch_dir = Path('.scratch')
        scratch_dir.mkdir(exist_ok=True)
        output_path = scratch_dir / 'library_clusters.json'
    output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_clusters = sum(len(v['clusters']) for v in output['videos'])
    click.echo(f"\nExported {len(videos)} videos ({total_clusters} clusters) to {output_path}")


@main.command()
@click.option('--scene', type=str, help='Generate for a specific scene ID.')
@click.option('--project', '-p', type=click.Path(exists=True), required=True,
              help='Project directory with scene_plan.json (e.g., projects/venezuela).')
@click.option('--workflow', '-w', type=click.Path(exists=True),
              help='Custom ComfyUI workflow JSON file.')
@click.option('--prompt-node', '-n', type=str, default=None,
              help='Node ID for prompt injection (overrides auto-detection).')
@click.option('--set', '-s', 'overrides', multiple=True,
              help='Override workflow param: "node_id:param=value". Can be used multiple times.')
@click.pass_context
def generate(ctx, scene, project, workflow, prompt_node, overrides):
    """Generate images via ComfyUI for scenes.

    Reads the scene plan and generates images for scenes
    marked as 'generated-image' type.

    Use --workflow to specify a custom ComfyUI workflow file.
    Use --prompt-node to specify which node receives the prompt.
    Use --set to override any workflow parameter.

    Examples:

        nolan generate --project projects/venezuela

        nolan generate --project projects/venezuela --scene scene-01
    """
    config = ctx.obj['config']
    project_path = Path(project)
    workflow_path = Path(workflow) if workflow else None

    click.echo(f"Project: {project_path}")
    if scene:
        click.echo(f"Scene: {scene}")
    if workflow_path:
        click.echo(f"Workflow: {workflow_path}")
    if prompt_node:
        click.echo(f"Prompt node: {prompt_node}")
    if overrides:
        click.echo(f"Overrides: {', '.join(overrides)}")

    asyncio.run(_generate_images(config, project_path, scene, workflow_path, prompt_node, list(overrides)))


async def _generate_images(config, project_path, scene_id, workflow_path=None, prompt_node=None, overrides=None, prompt_suffix=""):
    """Async implementation of generate command."""
    from nolan.scenes import ScenePlan
    from nolan.comfyui import ComfyUIClient

    # Load scene plan
    plan_path = project_path / "scene_plan.json"
    if not plan_path.exists():
        click.echo("Error: scene_plan.json not found. Run 'nolan process' first.")
        return

    plan = ScenePlan.load(str(plan_path))

    # Initialize ComfyUI client
    client = ComfyUIClient(
        host=config.comfyui.host,
        port=config.comfyui.port,
        width=config.comfyui.width,
        height=config.comfyui.height,
        steps=config.comfyui.steps,
        workflow_file=workflow_path,
        prompt_node=prompt_node,
        node_overrides=overrides
    )

    # Check connection
    if not await client.check_connection():
        click.echo("Error: Cannot connect to ComfyUI. Is it running?")
        return

    # Find scenes to generate
    output_dir = project_path / "assets" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    scenes_to_generate = []
    for section_scenes in plan.sections.values():
        for s in section_scenes:
            if scene_id and s.id != scene_id:
                continue
            if s.visual_type in ("generated", "generated-image") and not s.skip_generation:
                scenes_to_generate.append(s)

    if not scenes_to_generate:
        click.echo("No scenes to generate.")
        return

    click.echo(f"\nGenerating {len(scenes_to_generate)} images...")

    for s in scenes_to_generate:
        click.echo(f"\n  {s.id}: {s.comfyui_prompt[:50]}...")
        output_path = output_dir / f"{s.id}.png"
        gen_prompt = s.comfyui_prompt
        if prompt_suffix:
            gen_prompt = f"{gen_prompt.rstrip(', ')}, {prompt_suffix}"

        try:
            await client.generate(gen_prompt, output_path)
            s.generated_asset = f"{s.id}.png"
            click.echo(f"    Saved: {output_path}")
        except Exception as e:
            click.echo(f"    Error: {e}")

    # Save updated plan
    plan.save(str(plan_path))
    click.echo(f"\nScene plan updated: {plan_path}")


@main.command('generate-test')
@click.argument('prompt')
@click.option('--output', '-o', type=click.Path(), default='.scratch/test_output.png',
              help='Output path for generated image (default: .scratch/test_output.png).')
@click.option('--workflow', '-w', type=click.Path(exists=True),
              help='Custom ComfyUI workflow JSON file.')
@click.option('--prompt-node', '-n', type=str, default=None,
              help='Node ID for prompt injection (overrides auto-detection).')
@click.option('--set', '-s', 'overrides', multiple=True,
              help='Override workflow param: "node_id:param=value". Can be used multiple times.')
@click.pass_context
def generate_test(ctx, prompt, output, workflow, prompt_node, overrides):
    """Generate a single test image via ComfyUI.

    PROMPT is the text description for image generation.

    Use this to quickly test ComfyUI connection and workflow
    without needing a full scene plan.

    Examples:

      nolan generate-test "a cat" -w workflow.json

      nolan generate-test "a cat" -w workflow.json -n "26:24"

      nolan generate-test "a cat" -w workflow.json -s "3:steps=40" -s "13:width=1536"
    """
    config = ctx.obj['config']
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    workflow_path = Path(workflow) if workflow else None

    if workflow_path:
        click.echo(f"Workflow: {workflow_path}")
    if prompt_node:
        click.echo(f"Prompt node: {prompt_node}")
    if overrides:
        click.echo(f"Overrides: {', '.join(overrides)}")
    click.echo(f"Prompt: {prompt[:80]}...")
    click.echo(f"Output: {output_path}")

    asyncio.run(_generate_test_image(config, prompt, output_path, workflow_path, prompt_node, list(overrides)))


async def _generate_test_image(config, prompt, output_path, workflow_path=None, prompt_node=None, overrides=None):
    """Async implementation of generate-test command."""
    from nolan.comfyui import ComfyUIClient

    # Initialize ComfyUI client
    client = ComfyUIClient(
        host=config.comfyui.host,
        port=config.comfyui.port,
        width=config.comfyui.width,
        height=config.comfyui.height,
        steps=config.comfyui.steps,
        workflow_file=workflow_path,
        prompt_node=prompt_node,
        node_overrides=overrides
    )

    # Check connection
    if not await client.check_connection():
        click.echo("Error: Cannot connect to ComfyUI. Is it running?")
        return

    click.echo("\nGenerating image...")
    try:
        await client.generate(prompt, output_path)
        click.echo(f"Success! Image saved to: {output_path}")
    except Exception as e:
        click.echo(f"Error: {e}")


@main.command()
@click.argument('spec_file', type=click.Path(exists=True), required=False)
@click.option('--template', '-t', type=click.Choice(['steps', 'list', 'comparison']),
              default='steps', help='Infographic template type.')
@click.option('--theme', type=click.Choice(['default', 'dark', 'warm', 'cool']),
              default='default', help='Color theme.')
@click.option('--title', type=str, help='Infographic title.')
@click.option('--items', '-i', multiple=True, help='Items as "label:description". Can be used multiple times.')
@click.option('--output', '-o', type=click.Path(), help='Output path for generated SVG.')
@click.option('--width', type=int, default=1920, help='Output width in pixels.')
@click.option('--height', type=int, default=1080, help='Output height in pixels.')
@click.option('--host', default='127.0.0.1', help='Render service host.')
@click.option('--port', default=3010, type=int, help='Render service port.')
@click.pass_context
def infographic(ctx, spec_file, template, theme, title, items, output, width, height, host, port):
    """Generate an infographic using the render service.

    You can provide data in three ways:

    1. From a JSON spec file:
       nolan infographic spec.json

    2. From command line options:
       nolan infographic --title "My Process" --items "Step 1:First" --items "Step 2:Second"

    3. From stdin (pipe JSON):
       echo '{"title": "Test", "items": [...]}' | nolan infographic -

    Templates:
      - steps: Sequential process with numbered circles (default)
      - list: Vertical list with bullets
      - comparison: Side-by-side comparison

    Themes:
      - default: Blue/green professional look
      - dark: Dark background with light text
      - warm: Orange/red warm tones
      - cool: Purple/cyan cool tones

    Examples:

      nolan infographic --title "How to Code" -i "Learn:Start basics" -i "Practice:Build projects"

      nolan infographic spec.json -o my_infographic.svg

      nolan infographic --template list --theme dark --title "Features" -i "Fast:Blazing speed" -i "Easy:Simple API"
    """
    asyncio.run(_infographic(spec_file, template, theme, title, items, output, width, height, host, port))


async def _infographic(spec_file, template, theme, title, items, output, width, height, host, port):
    """Async implementation of infographic command."""
    import json
    from nolan.infographic_client import InfographicClient, Engine

    # Build data from sources
    data = {}

    if spec_file:
        # Load from JSON file
        if spec_file == '-':
            # Read from stdin
            import sys
            spec_text = sys.stdin.read()
        else:
            with open(spec_file, 'r', encoding='utf-8') as f:
                spec_text = f.read()

        spec = json.loads(spec_text)
        data = spec.get('data', spec)  # Support both {data: {...}} and flat format
        template = spec.get('template', template)
        theme = spec.get('theme', theme)
        width = spec.get('width', width)
        height = spec.get('height', height)
        if not output:
            output = spec.get('output')
    else:
        # Build from command line options
        if title:
            data['title'] = title

        if items:
            data['items'] = []
            for item in items:
                if ':' in item:
                    label, desc = item.split(':', 1)
                    data['items'].append({'label': label.strip(), 'description': desc.strip()})
                else:
                    data['items'].append({'label': item.strip(), 'description': ''})

    if not data:
        click.echo("Error: No data provided. Use --title/--items or provide a spec file.")
        return

    # Initialize client
    client = InfographicClient(host=host, port=port)

    # Check connection
    click.echo(f"Connecting to render service at {host}:{port}...")
    if not await client.health_check():
        click.echo("Error: Cannot connect to render service. Is it running?")
        click.echo("Start it with: cd render-service && npm run dev")
        return

    click.echo(f"Template: {template}")
    click.echo(f"Theme: {theme}")
    click.echo(f"Size: {width}x{height}")

    # Build full spec
    full_data = {
        'title': data.get('title', 'Infographic'),
        'items': data.get('items', [])
    }

    # Submit job
    click.echo("\nSubmitting render job...")

    def progress_callback(progress: float):
        pct = int(progress * 100)
        click.echo(f"  Progress: {pct}%")

    try:
        # The render expects: engine, data, template, etc at top level
        # We need to send: {engine, template, theme, width, height, data: {title, items}}
        job = await client.submit(
            engine=Engine.INFOGRAPHIC,
            data=full_data,
            template=template,
            theme=theme,
            width=width,
            height=height,
        )
        click.echo(f"Job ID: {job.job_id}")

        # Wait for completion
        completed = await client.wait_for_completion(
            job.job_id,
            progress_callback=progress_callback
        )

        output_path = completed.video_path
        click.echo(f"\nSuccess! Infographic saved to: {output_path}")

        # Copy to user-specified output if provided
        if output:
            import shutil
            from pathlib import Path
            dest = Path(output)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(output_path, dest)
            click.echo(f"Copied to: {dest}")

    except RuntimeError as e:
        click.echo(f"Error: {e}")
    except TimeoutError as e:
        click.echo(f"Timeout: {e}")


@main.command('render-infographics')
@click.option('--project', '-p', type=click.Path(exists=True), required=True,
              help='Project directory with scene_plan.json (e.g., projects/venezuela).')
@click.option('--host', default='127.0.0.1', help='Render service host.')
@click.option('--port', default=3010, type=int, help='Render service port.')
@click.option('--engine-mode', type=click.Choice(['auto', 'antv', 'svg']),
              default='auto', help='Force render engine mode.')
@click.option('--force', is_flag=True, help='Re-render even if infographic already exists.')
@click.pass_context
def render_infographics(ctx, project, host, port, engine_mode, force):
    """Render infographic scenes from a scene plan.

    Reads scene_plan.json and renders scenes with visual_type=infographic.
    Saves outputs into assets/infographics and updates scene_plan.json.

    Examples:

        nolan render-infographics --project projects/venezuela
    """
    asyncio.run(_render_infographics(project, host, port, engine_mode, force))


async def _render_infographics(project, host, port, engine_mode, force):
    """Async implementation of render-infographics."""
    import shutil
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.infographic_client import InfographicClient, Engine
    from nolan.infographic_icons import IconResolver

    project_path = Path(project)
    plan_path = project_path / "scene_plan.json"
    if not plan_path.exists():
        click.echo("Error: scene_plan.json not found. Run 'nolan process' first.")
        return

    output_dir = project_path / "assets" / "infographics"
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = ScenePlan.load(str(plan_path))
    scenes = [s for s in plan.all_scenes if s.visual_type == "infographic" or s.infographic]

    if not scenes:
        click.echo("No infographic scenes found.")
        return

    client = InfographicClient(host=host, port=port)
    click.echo(f"Connecting to render service at {host}:{port}...")
    if not await client.health_check():
        click.echo("Error: Cannot connect to render service. Is it running?")
        click.echo("Start it with: cd render-service && npm run dev")
        return

    rendered = 0
    icon_resolver = IconResolver()
    for scene in scenes:
        if scene.infographic_asset and not force:
            continue

        spec = scene.infographic or {}
        template = spec.get("template", "list")
        theme = spec.get("theme", "default")
        data = spec.get("data", {})

        if not data:
            data = {
                "title": scene.visual_description or scene.id,
                "items": [],
            }

        if isinstance(data.get("items"), list):
            try:
                changed = await icon_resolver.apply_to_items(data["items"])
                if changed and scene.infographic:
                    scene.infographic["data"] = data
            except Exception:
                pass

        click.echo(f"Rendering {scene.id} ({template}, {theme})...")

        try:
            job = await client.submit(
                engine=Engine.INFOGRAPHIC,
                data={
                    **data,
                    "output_formats": ["svg", "png"],
                },
                template=template,
                theme=theme,
                engine_mode=engine_mode,
            )

            completed = await client.wait_for_completion(job.job_id)
            output_path = Path(completed.video_path)
            if not output_path.exists():
                click.echo(f"  Failed: output not found for {scene.id}")
                continue

            dest_svg = output_dir / f"{scene.id}.svg"
            shutil.copy(output_path, dest_svg)
            scene.infographic_asset = f"infographics/{dest_svg.name}"

            png_path = output_path.with_suffix(".png")
            if png_path.exists():
                dest_png = output_dir / f"{scene.id}.png"
                shutil.copy(png_path, dest_png)
                scene.infographic_asset_png = f"infographics/{dest_png.name}"
            rendered += 1
        except Exception as e:
            click.echo(f"  Error rendering {scene.id}: {e}")

    plan.save(str(plan_path))
    click.echo(f"Rendered {rendered} infographic(s). Scene plan updated.")


def _scoring_vision_config(config, vision: str) -> dict:
    """Build the ImageScorer vision_config dict for the chosen provider."""
    if vision == "gemini":
        return {"api_key": config.gemini.api_key, "model": "gemini-3-flash-preview"}
    if vision == "openrouter":
        model = config.vision.model if "/" in config.vision.model else "qwen/qwen3.7-plus"
        return {
            "api_key": config.vision.openrouter_api_key,
            "model": model,
            "base_url": config.vision.base_url,
            "reasoning_enabled": config.vision.reasoning_enabled,
            "reasoning_max_tokens": config.vision.reasoning_max_tokens,
        }
    # ollama
    return {
        "host": config.vision.host,
        "port": config.vision.port,
        "model": config.vision.model if "/" not in config.vision.model else "qwen3-vl:8b",
    }


@main.command('image-search')
@click.argument('query')
@click.option('--source', '-s', type=click.Choice(['ddgs', 'pexels', 'pixabay', 'wikimedia', 'smithsonian', 'loc', 'wellcome', 'europeana', 'dpla', 'all']),
              default='ddgs', help='Image source to search.')
@click.option('--output', '-o', type=click.Path(), default='.scratch/image_search_results.json',
              help='Output JSON file for results (default: .scratch/image_search_results.json).')
@click.option('--max-results', '-n', type=int, default=10,
              help='Maximum number of results per source.')
@click.option('--score/--no-score', default=False,
              help='Score images by relevance using vision model.')
@click.option('--vision', type=click.Choice(['openrouter', 'gemini', 'ollama']),
              default='openrouter', help='Vision provider for scoring. Default: openrouter (qwen/qwen3.7-plus).')
@click.option('--context', '-c', type=str, default=None,
              help='Additional context for scoring (e.g., "for a documentary about history").')
@click.option('--resolve/--no-resolve', default=False,
              help='Upgrade thumbnails to full-res by extracting from each result\'s source page '
                   '(useful for aggregators like DPLA that return previews).')
@click.option('--save/--no-save', default=False,
              help='Save results into the picture library (tagged with the query).')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global',
              help='Picture-library scope when --save is used.')
@click.option('--project', '-p', default=None, help='Project name (for --scope project).')
@click.pass_context
def image_search(ctx, query, source, output, max_results, score, vision, context, resolve, save, scope, project):
    """Search for images from various sources.

    QUERY is the search term for finding images.

    Sources:
      - ddgs: DuckDuckGo image search (no API key needed)
      - pexels: Pexels stock photos (requires PEXELS_API_KEY)
      - pixabay: Pixabay stock photos (requires PIXABAY_API_KEY)
      - wikimedia: Wikimedia Commons (no API key needed, public domain)
      - smithsonian: Smithsonian Open Access (requires SMITHSONIAN_API_KEY, CC0)
      - loc: Library of Congress (no API key needed, public domain)
      - wellcome: Wellcome Collection (no API key needed, CC/PD history & medicine)
      - europeana: Europeana EU cultural heritage (needs EUROPEANA_API_KEY)
      - dpla: Digital Public Library of America (needs DPLA_API_KEY)
      - all: Search all available sources

    Scoring:
      Use --score to rank images by relevance using a vision model.
      Use --vision to choose 'openrouter' (default), 'gemini', or 'ollama'.

    Examples:

      nolan image-search "sunset mountains"

      nolan image-search "sunset mountains" -s wikimedia -n 20

      nolan image-search "historical photographs" -s loc

      nolan image-search "sunset mountains" -s all -o results.json

      nolan image-search "sunset mountains" --score --vision gemini
    """
    config = ctx.obj['config']
    output_path = Path(output)

    from nolan.image_search import ImageSearchClient, ImageScorer

    # Initialize client with API keys from config
    client = ImageSearchClient(
        pexels_api_key=config.image_sources.pexels_api_key,
        pixabay_api_key=config.image_sources.pixabay_api_key,
        smithsonian_api_key=config.image_sources.smithsonian_api_key,
        keys=config.image_sources.provider_keys(),
    )

    # Show available providers
    available = client.get_available_providers()
    click.echo(f"Available sources: {', '.join(available)}")

    if source != "all" and source not in available:
        click.echo(f"Error: Source '{source}' is not available. Check API keys.")
        return

    click.echo(f"Searching '{query}' on {source}...")

    try:
        results = client.search(query, source, max_results)
        click.echo(f"Found {len(results)} results")

        # Upgrade thumbnails -> full-res via the extractor registry
        if resolve and results:
            click.echo("\nResolving full-res from source pages...")
            from nolan.extractors import resolve_results
            before = [r.url for r in results]
            results = resolve_results(results)
            upgraded = sum(1 for old, r in zip(before, results) if r.url != old)
            click.echo(f"Upgraded {upgraded}/{len(results)} to full-res.")

        # Score images if requested
        if score:
            click.echo(f"\nScoring images with {vision}...")

            # Configure vision provider
            vision_config = _scoring_vision_config(config, vision)

            scorer = ImageScorer(vision_provider=vision, vision_config=vision_config)

            def progress(current, total, result):
                score_str = f"{result.score:.1f}" if result.score else "?"
                quality_str = f" Q:{result.quality_score:.0f}" if result.quality_score is not None else ""
                click.echo(f"  [{current}/{total}] Score: {score_str}{quality_str} - {result.title[:40] if result.title else 'No title'}...")

            results = scorer.score_results(results, query, context=context, progress_callback=progress)
            click.echo(f"\nScoring complete. Results sorted by relevance.")

        # Save results to JSON
        import json
        output_data = {
            "query": query,
            "source": source,
            "count": len(results),
            "scored": score,
            "scored_by": vision if score else None,
            "context": context,
            "results": [r.to_dict() for r in results],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        click.echo(f"\nResults saved to: {output_path}")

        # Save into the picture library (tagged with the query)
        if save and results:
            from nolan.imagelib import ImageLibrary
            lib = ImageLibrary(scope=scope, project=project)
            click.echo(f"\nSaving to {scope} picture library...")
            added = dup = failed = 0
            for r in results:
                if not r.url:
                    continue
                try:
                    _, created = lib.add_result(r, query=query)
                    added += int(created); dup += int(not created)
                except Exception:
                    failed += 1
            click.echo(f"Library: +{added} new, {dup} duplicate, {failed} failed.")

        # Show results
        for i, r in enumerate(results[:5]):
            score_str = f" (Score: {r.score:.1f}" if r.score is not None else ""
            if score_str and r.quality_score is not None:
                score_str += f", Quality: {r.quality_score:.0f}/10)"
            elif score_str:
                score_str += ")"
            click.echo(f"  {i+1}. [{r.source}]{score_str} {r.title[:50] if r.title else 'No title'}...")
            if r.score_reason:
                click.echo(f"     Relevance: {r.score_reason}")
            if r.quality_reason:
                click.echo(f"     Quality: {r.quality_reason}")
            click.echo(f"     {r.url[:80]}...")

        if len(results) > 5:
            click.echo(f"  ... and {len(results) - 5} more")

    except Exception as e:
        click.echo(f"Error: {e}")


@main.command('extract-assets')
@click.argument('url')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Directory to download assets into (default: .scratch/extracted/<host>).')
@click.option('--limit', '-n', type=int, default=None,
              help='Maximum number of assets to extract.')
@click.option('--manifest', '-m', type=click.Path(), default=None,
              help='JSON manifest path (default: <output>/manifest.json).')
@click.option('--download/--no-download', default=True,
              help='Download the full-resolution assets (default: on).')
@click.option('--save-to-library/--no-save-to-library', 'save_to_library', default=False,
              help='Also ingest the assets into the picture library.')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global',
              help='Picture-library scope for --save-to-library.')
@click.option('--project', '-p', default=None, help='Project name (for --scope project).')
@click.pass_context
def extract_assets(ctx, url, output, limit, manifest, download, save_to_library, scope, project):
    """Extract high-definition image assets from a web page URL.

    Uses a registry of parsers (Project Gutenberg, Wikimedia Commons, The Met,
    Internet Archive, Library of Congress, and any IIIF manifest/info.json) plus
    a universal HTML fallback that prefers linked full-res over thumbnails,
    srcset, and og:image.

    Examples:

      nolan extract-assets https://www.gutenberg.org/files/21790/21790-h/21790-h.htm

      nolan extract-assets https://commons.wikimedia.org/wiki/File:The_Blue_Marble.jpg -n 1

      nolan extract-assets https://www.loc.gov/item/2021669449/

      nolan extract-assets https://iiif.io/api/cookbook/recipe/0009-book-1/manifest.json
    """
    import asyncio
    import json
    from urllib.parse import urlparse

    from nolan.extractors import download_assets, extract_from_url, get_extractor

    ex = get_extractor(url)
    click.echo(f"Extractor: {ex.name}")
    try:
        results = extract_from_url(url, limit=limit)
    except Exception as e:
        click.echo(f"Error fetching/parsing: {e}")
        return

    click.echo(f"Found {len(results)} asset(s)")
    for i, r in enumerate(results[:10]):
        click.echo(f"  {i + 1}. {r.url}")
    if len(results) > 10:
        click.echo(f"  ... and {len(results) - 10} more")
    if not results:
        return

    host = urlparse(url).netloc.replace(":", "_") or "page"
    out_dir = Path(output) if output else Path(".scratch/extracted") / host
    records = [r.to_dict() for r in results]

    if download:
        click.echo(f"\nDownloading to {out_dir} ...")
        records = asyncio.run(download_assets(results, out_dir))
        ok = sum(1 for r in records if r.get("local_path"))
        click.echo(f"Downloaded {ok}/{len(records)}")
        for r in records:
            if r.get("error"):
                click.echo(f"  ! {r['url']}: {r['error']}")

    manifest_path = Path(manifest) if manifest else out_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"url": url, "extractor": ex.name, "count": len(records), "results": records},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    click.echo(f"Manifest: {manifest_path}")

    if save_to_library and results:
        from nolan.imagelib import ImageLibrary
        click.echo(f"\nSaving to {scope} picture library...")
        lib = ImageLibrary(scope=scope, project=project)
        local_by_url = {r.get("url"): r.get("local_path") for r in records}
        added = dup = 0
        with click.progressbar(results, label='Ingesting') as bar:
            for r in bar:
                try:
                    local = local_by_url.get(r.url)
                    if local and Path(local).exists():
                        _, created = lib.add_file(
                            local, url=r.url, source=r.source, source_url=r.source_url,
                            license=r.license, title=r.title, width=r.width,
                            height=r.height, query=url)
                    else:
                        _, created = lib.add_result(r, query=url)
                    added += int(created); dup += int(not created)
                except Exception:
                    pass
        click.echo(f"Library: +{added} new, {dup} duplicate.")


@main.group('images')
def images():
    """Picture library — persistent, searchable, license-aware image store.

    Global library lives in _library/images/; per-project in
    projects/<name>/imagelib/. Semantic search uses CLIP (text -> image).
    """
    pass


def _open_library(scope, project):
    from nolan.imagelib import ImageLibrary
    return ImageLibrary(scope=scope, project=project)


@images.command('search')
@click.argument('query')
@click.option('--scope', type=click.Choice(['global', 'project', 'both']), default='global')
@click.option('--project', '-p', default=None, help='Project name (for project/both scope).')
@click.option('--top', '-k', type=int, default=12, help='Number of results.')
@click.option('--license', 'license_contains', default=None, help='Only results whose license contains this text.')
def images_search(query, scope, project, top, license_contains):
    """Semantic search the picture library."""
    from nolan.imagelib import ImageLibrary, search_all
    if scope == 'both':
        hits = search_all(query, project=project, k=top, license_contains=license_contains)
    else:
        hits = ImageLibrary(scope=scope, project=project).search(
            query, k=top, license_contains=license_contains)
    click.echo(f"{len(hits)} result(s) for '{query}':")
    for h in hits:
        a = h.asset
        click.echo(f"  [{h.score:.3f}] #{a.id} {a.title or '(untitled)'} "
                   f"({a.width}x{a.height}) {a.license or '?'}")
        click.echo(f"          {a.path}  <- {a.source or '?'}")


@images.command('add')
@click.argument('url_or_manifest')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
@click.option('--source', default=None)
@click.option('--license', 'license_', default=None)
@click.option('--query', default=None, help='Tag with the query/topic this asset is for.')
def images_add(url_or_manifest, scope, project, source, license_, query):
    """Add an image URL, or ingest a manifest.json from `extract-assets`."""
    import json
    lib = _open_library(scope, project)
    added = skipped = 0
    if url_or_manifest.startswith('http'):
        try:
            a, created = lib.add_url(url_or_manifest, source=source, license=license_, query=query)
            added += int(created); skipped += int(not created)
            click.echo(f"{'Added' if created else 'Exists'} #{a.id}: {a.path}")
        except Exception as e:
            click.echo(f"Failed: {e}")
    else:
        data = json.loads(Path(url_or_manifest).read_text(encoding='utf-8'))
        items = data.get('results', data) if isinstance(data, dict) else data
        with click.progressbar(items, label='Ingesting') as bar:
            for it in bar:
                url = it.get('url')
                if not url:
                    continue
                local = it.get('local_path')  # prefer already-downloaded file (no re-fetch)
                try:
                    if local and Path(local).exists():
                        a, created = lib.add_file(
                            local, url=url, source=it.get('source') or source,
                            source_url=it.get('source_url'),
                            license=it.get('license') or license_,
                            title=it.get('title'), query=query)
                    else:
                        a, created = lib.add_url(
                            url, source=it.get('source') or source,
                            source_url=it.get('source_url'),
                            license=it.get('license') or license_,
                            title=it.get('title'), query=query)
                    added += int(created); skipped += int(not created)
                except Exception as e:
                    click.echo(f"\n  ! {url[:60]}: {e}")
        click.echo(f"Added {added}, skipped {skipped} (duplicates).")


@images.command('list')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
@click.option('--source', default=None)
@click.option('--license', 'license_contains', default=None)
@click.option('--status', default='active')
@click.option('--limit', '-n', type=int, default=30)
def images_list(scope, project, source, license_contains, status, limit):
    """List library assets."""
    lib = _open_library(scope, project)
    for a in lib.list(status=status, source=source, license_contains=license_contains, limit=limit):
        click.echo(f"  #{a.id} [{a.source or '?'}] {a.title or '(untitled)'} "
                   f"({a.width}x{a.height}) {a.license or '?'}")


@images.command('reject')
@click.argument('asset_id', type=int)
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_reject(asset_id, scope, project):
    """Reject an asset (hidden from search; removed from the vector index)."""
    _open_library(scope, project).set_status(asset_id, 'rejected')
    click.echo(f"Rejected #{asset_id}.")


@images.command('promote')
@click.argument('asset_id', type=int)
@click.option('--project', '-p', required=True, help='Project the asset lives in.')
def images_promote(asset_id, project):
    """Copy a project-library asset into the global library."""
    from nolan.imagelib import promote_to_global
    try:
        asset, created = promote_to_global(project, asset_id)
    except Exception as e:
        click.echo(f"Failed: {e}")
        return
    click.echo(f"{'Promoted to' if created else 'Already in'} global #{asset.id}: {asset.title or asset.path}")


@images.command('stats')
@click.option('--scope', type=click.Choice(['global', 'project']), default='global')
@click.option('--project', '-p', default=None)
def images_stats(scope, project):
    """Show library counts."""
    click.echo(_open_library(scope, project).stats())


@main.command('match-broll')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output directory for downloaded images (defaults to assets/broll next to scene_plan).')
@click.option('--source', '-s', type=click.Choice(['ddgs', 'pexels', 'pixabay', 'wikimedia', 'loc', 'all']),
              default='wikimedia', help='Image source to search.')
@click.option('--max-results', '-n', type=int, default=5,
              help='Maximum results to consider per scene.')
@click.option('--score/--no-score', default=True,
              help='Score images by relevance using vision model.')
@click.option('--vision', type=click.Choice(['openrouter', 'gemini', 'ollama']),
              default='openrouter', help='Vision provider for scoring. Default: openrouter (qwen/qwen3.7-plus).')
@click.option('--skip-existing/--no-skip-existing', default=True,
              help='Skip scenes that already have matched assets.')
@click.option('--dry-run', is_flag=True,
              help='Show what would be downloaded without actually downloading.')
@click.pass_context
def match_broll(ctx, scene_plan, output, source, max_results, score, vision, skip_existing, dry_run):
    """Search and download images for b-roll scenes.

    SCENE_PLAN is the path to scene_plan.json.

    This command will:
    1. Find all b-roll scenes with search_query
    2. Search for images using the specified source
    3. Score images by relevance (optional)
    4. Download the best match for each scene
    5. Update scene_plan.json with matched_asset paths

    Examples:

      nolan match-broll test_output/scene_plan.json

      nolan match-broll scene_plan.json -s pexels --score --vision gemini

      nolan match-broll scene_plan.json --dry-run
    """
    config = ctx.obj['config']
    asyncio.run(_match_broll(config, scene_plan, output, source, max_results, score, vision, skip_existing, dry_run))


async def _match_broll(config, scene_plan_path, output_dir, source, max_results, score, vision, skip_existing, dry_run):
    """Async implementation of match-broll command."""
    import json
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.image_search import ImageSearchClient, ImageScorer

    scene_plan_path = Path(scene_plan_path)
    plan = ScenePlan.load(str(scene_plan_path))

    # Default output directory
    if output_dir is None:
        output_dir = scene_plan_path.parent / "assets" / "broll"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find b-roll scenes with search queries
    broll_scenes = []
    for section_name, scenes in plan.sections.items():
        for scene in scenes:
            if scene.visual_type == "b-roll" and scene.search_query:
                if skip_existing and scene.matched_asset:
                    continue
                broll_scenes.append((section_name, scene))

    if not broll_scenes:
        click.echo("No b-roll scenes to match (all may already have matched_asset).")
        return

    click.echo(f"Found {len(broll_scenes)} b-roll scenes to match")
    click.echo(f"Source: {source}")
    click.echo(f"Output: {output_dir}")
    if dry_run:
        click.echo("Mode: DRY RUN (no downloads)")

    # Initialize search client
    client = ImageSearchClient(
        pexels_api_key=config.image_sources.pexels_api_key,
        pixabay_api_key=config.image_sources.pixabay_api_key,
        smithsonian_api_key=config.image_sources.smithsonian_api_key,
        keys=config.image_sources.provider_keys(),
    )

    # Check if source is available
    available = client.get_available_providers()
    if source != "all" and source not in available:
        click.echo(f"Error: Source '{source}' is not available. Check API keys.")
        click.echo(f"Available: {', '.join(available)}")
        return

    # Initialize scorer if needed
    scorer = None
    if score:
        vision_config = _scoring_vision_config(config, vision)
        scorer = ImageScorer(vision_provider=vision, vision_config=vision_config)

    matched_count = 0
    failed_count = 0

    for i, (section_name, scene) in enumerate(broll_scenes):
        click.echo(f"\n[{i+1}/{len(broll_scenes)}] {scene.id}")
        click.echo(f"  Query: {scene.search_query}")

        try:
            # Search for images
            results = client.search(scene.search_query, source, max_results)

            if not results:
                click.echo(f"  No results found")
                failed_count += 1
                continue

            click.echo(f"  Found {len(results)} results")

            # Score if enabled
            if scorer and results:
                click.echo(f"  Scoring with {vision}...")
                results = scorer.score_results(
                    results,
                    scene.search_query,
                    context=f"for a video essay scene: {scene.visual_description}",
                    include_quality=True
                )

            # Pick best result
            best = results[0]
            score_info = f" (score: {best.score:.1f})" if best.score else ""
            click.echo(f"  Best: {best.title or 'No title'}{score_info}")
            click.echo(f"  URL: {best.url[:80]}...")

            if dry_run:
                click.echo(f"  [DRY RUN] Would download to: {output_dir / f'{scene.id}.jpg'}")
                continue

            # Download image
            output_path = output_dir / scene.id
            downloaded_path = client.download_image(best, output_path, prefer_large=True)

            if downloaded_path:
                # Update scene with relative path
                rel_path = downloaded_path.relative_to(scene_plan_path.parent)
                scene.matched_asset = str(rel_path)
                click.echo(f"  Downloaded: {downloaded_path.name}")
                matched_count += 1
            else:
                click.echo(f"  Failed to download")
                failed_count += 1

        except Exception as e:
            click.echo(f"  Error: {e}")
            failed_count += 1

    # Save updated plan
    if not dry_run and matched_count > 0:
        plan.save(str(scene_plan_path))
        click.echo(f"\nScene plan updated: {scene_plan_path}")

    click.echo(f"\nSummary:")
    click.echo(f"  Matched: {matched_count}")
    click.echo(f"  Failed: {failed_count}")
    click.echo(f"  Skipped: {len([s for s in plan.all_scenes if s.visual_type == 'b-roll' and s.matched_asset]) - matched_count}")


@main.command('match-clips')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.option('--candidates', '-c', type=int, default=None,
              help='Candidates per scene (overrides config, default: 3).')
@click.option('--min-similarity', type=float, default=None,
              help='Minimum similarity threshold 0-1 (overrides config, default: 0.5).')
@click.option('--project', '-p', type=str, default=None,
              help='Filter to clips from this project.')
@click.option('--skip-existing/--no-skip-existing', default=True,
              help='Skip scenes that already have matched_clip.')
@click.option('--dry-run', is_flag=True,
              help='Show matches without saving to scene plan.')
@click.option('--search-level', type=click.Choice(['segments', 'clusters', 'both']),
              default=None, help='Search level (overrides config).')
@click.option('--concurrency', '-C', type=int, default=None,
              help='Parallel scene matches (defaults to config.clip_matching.concurrency).')
@click.pass_context
def match_clips(ctx, scene_plan, candidates, min_similarity, project, skip_existing, dry_run, search_level, concurrency):
    """Match scenes to video library clips using semantic search.

    SCENE_PLAN is the path to scene_plan.json.

    This command will:
    1. Search indexed video library for relevant clips
    2. Use LLM to select best candidate for each scene
    3. Apply smart clip tailoring for optimal start/end points
    4. Update scene_plan.json with matched_clip field

    The matched_clip includes video_path, clip_start, clip_end, and reasoning.

    Examples:

      nolan match-clips scene_plan.json

      nolan match-clips scene_plan.json -p venezuela --candidates 5

      nolan match-clips scene_plan.json --min-similarity 0.6 --dry-run
    """
    config = ctx.obj['config']
    asyncio.run(_match_clips(config, scene_plan, candidates, min_similarity, project, skip_existing, dry_run, search_level, concurrency))


async def _match_clips(config, scene_plan_path, candidates, min_similarity, project, skip_existing, dry_run, search_level, concurrency):
    """Async implementation of match-clips command."""
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.clip_matcher import ClipMatcher
    from nolan.vector_search import VectorSearch
    from nolan.indexer import VideoIndex
    from nolan.llm import create_text_llm
    from nolan.config import ClipMatchingConfig

    scene_plan_path = Path(scene_plan_path)
    plan = ScenePlan.load(str(scene_plan_path))

    # Build config with CLI overrides
    match_config = ClipMatchingConfig(
        candidates_per_scene=candidates if candidates is not None else config.clip_matching.candidates_per_scene,
        min_similarity=min_similarity if min_similarity is not None else config.clip_matching.min_similarity,
        search_level=search_level if search_level is not None else config.clip_matching.search_level,
        skip_edge_percent=config.clip_matching.skip_edge_percent,
        concurrency=concurrency if concurrency is not None else config.clip_matching.concurrency
    )

    # Count scenes
    total_scenes = len(plan.all_scenes)
    scenes_with_query = sum(1 for s in plan.all_scenes if s.search_query or s.visual_description or s.narration_excerpt)

    click.echo(f"Scene plan: {scene_plan_path.name}")
    click.echo(f"Total scenes: {total_scenes}")
    click.echo(f"Matchable scenes: {scenes_with_query}")
    click.echo(f"Candidates per scene: {match_config.candidates_per_scene}")
    click.echo(f"Min similarity: {match_config.min_similarity}")
    click.echo(f"Search level: {match_config.search_level}")
    click.echo(f"Concurrency: {match_config.concurrency}")
    if project:
        click.echo(f"Project filter: {project}")
    if dry_run:
        click.echo("Mode: DRY RUN (no changes saved)")

    # Initialize components
    db_path = Path(config.indexing.database).expanduser()

    # Check if database exists
    if not db_path.exists():
        click.echo(f"\nError: Video library not found at {db_path}")
        click.echo("Run 'nolan index <video_folder>' first to index your library")
        return

    index = VideoIndex(db_path)

    # Initialize vector search
    vector_db_path = db_path.parent / "vectors"
    vector_search = VectorSearch(db_path=vector_db_path, index=index)

    # Check vector DB has content
    stats = vector_search.get_stats()
    if stats["segments"] == 0 and stats["clusters"] == 0:
        click.echo(f"\nError: Vector search database is empty")
        click.echo("Run 'nolan sync-vectors' first to build the search index")
        return

    click.echo(f"\nVector DB: {stats['segments']} segments, {stats['clusters']} clusters")

    # Resolve project slug to ID if provided
    project_id = None
    if project:
        proj = index.get_project(project)
        if not proj:
            click.echo(f"\nWarning: Project '{project}' not found. Searching all projects.")
        else:
            project_id = proj['id']

    # Initialize LLM
    llm = create_text_llm(config)

    # Initialize matcher
    matcher = ClipMatcher(vector_search, llm, match_config)

    # Whole-script context: load the ScriptContext from the plan's project dir so retrieval +
    # LLM selection are subject/era aware (bare "the horse" → the Trojan horse in this script).
    try:
        from nolan.script_context import ScriptContext
        _sctx = ScriptContext.load(Path(scene_plan_path).parent)
        if _sctx.beats:
            matcher.set_script_context(_sctx)
            click.echo(f"  (context: {_sctx.subject or _sctx.slug})")
    except Exception:
        pass

    # Progress callback
    def progress(current, total, message):
        click.echo(f"[{current}/{total}] {message}")

    # Match scenes
    click.echo("\nMatching scenes to library clips...")
    result = await matcher.match_plan(
        plan,
        project_id=project_id,
        skip_existing=skip_existing,
        progress_callback=progress
    )

    # Show results
    click.echo(f"\nResults:")
    click.echo(f"  Matched: {result['matched']}")
    click.echo(f"  No match found: {result['no_match']}")
    click.echo(f"  Skipped (existing): {result['skipped']}")

    # Show matches in dry-run mode
    if dry_run and result['matched'] > 0:
        click.echo("\nMatched clips (DRY RUN - not saved):")
        for scene in plan.all_scenes:
            if scene.matched_clip:
                mc = scene.matched_clip
                video_name = Path(mc['video_path']).name if mc.get('video_path') else 'Unknown'
                click.echo(f"\n  {scene.id}:")
                click.echo(f"    Video: {video_name}")
                click.echo(f"    Clip: {mc['clip_start']:.1f}s - {mc['clip_end']:.1f}s")
                click.echo(f"    Confidence: {mc['confidence']:.2f}")
                reason = mc.get('match_reasoning', '')[:80]
                if len(mc.get('match_reasoning', '')) > 80:
                    reason += "..."
                click.echo(f"    Reason: {reason}")

    # Save updated plan (unless dry-run)
    if not dry_run and result['matched'] > 0:
        plan.save(str(scene_plan_path))
        click.echo(f"\nScene plan updated: {scene_plan_path}")
    elif not dry_run:
        click.echo("\nNo changes to save.")


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


def _unified_render_clip(scene, clips_dir, duration, project_root, llm=None):
    """Render a graphic/text/data/generated scene through the unified core (lazy
    motion authoring + render_dispatch.render_one). Returns the rendered_clip rel
    path, or None if the core can't handle this scene (caller falls back to legacy).
    """
    from nolan.render_dispatch import render_one

    # Lazily author a motion_spec for a graphic/text/data scene that lacks one.
    # Generated (ComfyUI image) scenes are excluded — they belong to the
    # comfyui/card branch of render_one, not motion authoring (which would
    # produce a remotion spec that can't render locally → black).
    _vt = (getattr(scene, "visual_type", "") or "").lower()
    if (not getattr(scene, "motion_spec", None) and llm is not None
            and not _vt.startswith("generated")):
        try:
            from nolan.motion import compile_spec
            from nolan.segment.render import _run_async
            brief = (getattr(scene, "visual_description", "")
                     or getattr(scene, "narration_excerpt", "") or "").strip()
            if brief:
                spec, _errs = _run_async(compile_spec(brief, llm))
                if spec.get("backend"):
                    scene.motion_spec = spec
        except Exception:
            pass

    out = Path(clips_dir) / f"{scene.id}.mp4"
    try:
        kind = render_one(scene, out, duration=max(float(duration), 1.0))
    except Exception:
        return None
    if not kind:
        return None
    return str(out.relative_to(project_root)).replace("\\", "/")


@main.command('render-clips')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.option('--force', is_flag=True, help='Re-render even if clip exists.')
@click.option('--resolution', '-r', default='1920x1080', help='Output resolution.')
@click.option('--fps', default=30, type=int, help='Frame rate.')
@click.option('--unified/--no-unified', default=True,
              help='Render graphic/text/data scenes through the unified core first '
                   '(lazy motion + render_one); render-service is the fallback.')
@click.pass_context
def render_clips(ctx, scene_plan, force, resolution, fps, unified):
    """Pre-render animated scenes to MP4 clips.

    SCENE_PLAN is the path to scene_plan.json.

    This command renders:
    - Infographic scenes (with animation)
    - Scenes with sync_points
    - Scenes with animation_type specified

    Examples:

      nolan render-clips scene_plan.json

      nolan render-clips scene_plan.json --force -r 1280x720
    """
    from pathlib import Path
    import httpx

    config = ctx.obj['config']
    scene_plan_path = Path(scene_plan)

    # Parse resolution
    width, height = map(int, resolution.split('x'))

    # Load scene plan
    from nolan.scenes import ScenePlan
    plan = ScenePlan.load(str(scene_plan_path))

    clips_dir = scene_plan_path.parent / 'assets' / 'clips'
    clips_dir.mkdir(parents=True, exist_ok=True)
    rendered = 0
    failed = 0

    # P3: render eligible scenes through the unified core first (lazy motion + render_one).
    # The render-service loop below is the fallback for anything the core can't handle.
    if unified:
        _llm = None
        try:
            from nolan.llm import create_text_llm
            _llm = create_text_llm(config)
        except Exception:
            _llm = None
        _MOTION_VT = {"graphics", "graphic", "text-overlay", "text", "data", "infographic",
                      "generated", "generated-image", "lower-third", "lower-thirds", "quote",
                      "title", "chart", "counter", "stat", "callout"}
        for section_name, scenes in plan.sections.items():
            for scene in scenes:
                if scene.rendered_clip and not force:
                    continue
                vt = (scene.visual_type or "").lower().strip()
                if vt not in _MOTION_VT and not scene.motion_spec:
                    continue
                dur = max((scene.end_seconds or 5.0) - (scene.start_seconds or 0.0), 1.0)
                rel = _unified_render_clip(scene, clips_dir, dur, scene_plan_path.parent, _llm)
                if rel:
                    scene.rendered_clip = rel
                    rendered += 1
                    click.echo(f"  [core] {scene.id}: {Path(rel).name}")
        if rendered:
            click.echo(f"Rendered {rendered} scene(s) via the unified core.")

    # Find scenes that still need rendering (render-service fallback)
    to_render = []
    for section_name, scenes in plan.sections.items():
        for scene in scenes:
            needs_render = False

            # Skip if already has rendered_clip and not forcing
            if scene.rendered_clip and not force:
                continue

            # Check if scene needs pre-rendering
            if scene.visual_type == 'graphics' and scene.infographic:
                needs_render = True
            elif scene.sync_points and len(scene.sync_points) > 0:
                needs_render = True
            elif scene.animation_type and scene.animation_type != 'static':
                needs_render = True

            if needs_render:
                duration = (scene.end_seconds or 5.0) - (scene.start_seconds or 0.0)
                to_render.append((section_name, scene, duration))

    if not to_render:
        if rendered > 0:
            plan.save(str(scene_plan_path))
            click.echo(f"\nScene plan updated: {scene_plan_path}")
        click.echo("No scenes need the render-service fallback.")
        return

    click.echo(f"Scenes to render: {len(to_render)}")
    click.echo(f"Resolution: {width}x{height} @ {fps}fps")

    # Output directory
    clips_dir = scene_plan_path.parent / 'assets' / 'clips'
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Connect to render service
    render_host = config.render_service.host if hasattr(config, 'render_service') else '127.0.0.1'
    render_port = config.render_service.port if hasattr(config, 'render_service') else 3010
    base_url = f"http://{render_host}:{render_port}"

    click.echo(f"Render service: {base_url}")

    for i, (section_name, scene, duration) in enumerate(to_render):
        scene_id = f"{section_name}_{scene.id}"
        click.echo(f"\n[{i+1}/{len(to_render)}] {scene_id} ({duration:.1f}s)")

        try:
            # Build render spec
            spec = {
                'width': width,
                'height': height,
                'fps': fps,
                'duration': duration,
            }

            if scene.infographic:
                spec['template'] = scene.infographic.get('template', 'list')
                spec['theme'] = scene.infographic.get('theme', 'default')
                spec['data'] = scene.infographic.get('data', {})

            # Submit render job
            with httpx.Client(timeout=300.0) as client:
                # Create job
                response = client.post(
                    f"{base_url}/render",
                    json={
                        'engine': 'remotion',
                        'output_format': 'mp4',
                        'spec': spec,
                    }
                )

                if response.status_code != 200:
                    click.echo(f"  Error: {response.text}")
                    failed += 1
                    continue

                result = response.json()
                job_id = result.get('job_id')

                if not job_id:
                    click.echo(f"  Error: No job_id returned")
                    failed += 1
                    continue

                click.echo(f"  Job: {job_id}")

                # Poll for completion
                import time
                while True:
                    status_response = client.get(f"{base_url}/jobs/{job_id}")
                    status = status_response.json()

                    if status.get('status') == 'completed':
                        output_file = status.get('output')
                        if output_file:
                            # Copy/move to clips directory
                            output_path = clips_dir / f"{scene.id}.mp4"
                            # For now, just record the path
                            scene.rendered_clip = f"assets/clips/{scene.id}.mp4"
                            click.echo(f"  Done: {scene.rendered_clip}")
                            rendered += 1
                        break
                    elif status.get('status') == 'failed':
                        click.echo(f"  Failed: {status.get('error', 'Unknown error')}")
                        failed += 1
                        break
                    else:
                        time.sleep(1)

        except Exception as e:
            click.echo(f"  Error: {e}")
            failed += 1

    # Save updated plan
    if rendered > 0:
        plan.save(str(scene_plan_path))
        click.echo(f"\nScene plan updated: {scene_plan_path}")

    click.echo(f"\nSummary:")
    click.echo(f"  Rendered: {rendered}")
    click.echo(f"  Failed: {failed}")
    click.echo(f"  Skipped: {len([s for sec in plan.sections.values() for s in sec if s.rendered_clip]) - rendered}")


@main.command('render-lottie')
@click.argument('lottie', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default='lottie.mp4', help='Output MP4 path.')
@click.option('--text', multiple=True, help='Text replacement OLD=NEW (repeatable).')
@click.option('--color', multiple=True, help='Color map #OLD=#NEW (repeatable).')
@click.option('--duration', type=float, default=5.0, help='Duration in seconds.')
@click.option('--fps', type=int, default=30)
@click.option('--resolution', '-r', default='1920x1080')
@click.option('--service', default='http://127.0.0.1:3010', help='Render-service URL.')
def render_lottie(lottie, output, text, color, duration, fps, resolution, service):
    """Render a Lottie template/animation to MP4 via the render-service.

    Optionally customize text/colors first. Requires the node render-service
    (cd render-service && npm run dev).

    Examples:

      nolan render-lottie lower-third.json -o speaker.mp4 --duration 6

      nolan render-lottie lower-third.json --text "Name=Jane Doe" --color "#ff0000=#00ff00"
    """
    from nolan.lottie_render import prepare_lottie, render_lottie_to_mp4
    width, height = map(int, resolution.split('x'))
    src = Path(lottie)
    cfg = {"duration": duration, "fps": fps, "width": width, "height": height}
    if text:
        cfg["text"] = dict(kv.split("=", 1) for kv in text)
    if color:
        cfg["colors"] = dict(kv.split("=", 1) for kv in color)
    if cfg.get("text") or cfg.get("colors"):
        import tempfile
        prepared = Path(tempfile.gettempdir()) / (src.stem + ".prepared.json")
        prepare_lottie(src, prepared, cfg)
        src = prepared
        click.echo(f"Customized → {src}")
    try:
        out = render_lottie_to_mp4(src, output, service_url=service, width=width,
                                   height=height, fps=fps, duration=duration)
        click.echo(f"Rendered: {out}")
    except Exception as e:
        click.echo(f"Failed: {e}")
        click.echo("Is the render-service running?  cd render-service && npm run dev")


@main.command('assemble')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.argument('audio_file', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default='final_video.mp4',
              help='Output video path.')
@click.option('--resolution', '-r', default='1920x1080', help='Output resolution.')
@click.option('--fps', default=30, type=int, help='Frame rate.')
@click.option('--transition', '-t', type=click.Choice(['cut', 'fade', 'crossfade']),
              default='cut', help='Transition between scenes.')
@click.option('--transition-duration', default=0.5, type=float,
              help='Transition duration in seconds.')
@click.pass_context
def assemble(ctx, scene_plan, audio_file, output, resolution, fps, transition, transition_duration):
    """Assemble final video from scene plan and audio.

    SCENE_PLAN is the path to scene_plan.json.
    AUDIO_FILE is the path to the voiceover audio.

    This command:
    1. Resolves assets for each scene (rendered_clip > generated > matched > infographic)
    2. Scales/pads images to target resolution
    3. Concatenates with transitions
    4. Adds voiceover audio
    5. Exports final MP4

    Examples:

      nolan assemble scene_plan.json voiceover.mp3

      nolan assemble scene_plan.json voiceover.mp3 -o my_video.mp4 -t crossfade
    """
    from pathlib import Path
    import subprocess
    import tempfile

    scene_plan_path = Path(scene_plan)
    audio_path = Path(audio_file)
    output_path = scene_plan_path.parent / output if not Path(output).is_absolute() else Path(output)

    # Parse resolution
    width, height = map(int, resolution.split('x'))

    # Load scene plan
    from nolan.scenes import ScenePlan
    plan = ScenePlan.load(str(scene_plan_path))

    # Flatten scenes in order
    all_scenes = []
    for section_name, scenes in plan.sections.items():
        for scene in scenes:
            all_scenes.append(scene)

    click.echo(f"Scenes: {len(all_scenes)}")
    click.echo(f"Audio: {audio_path}")
    click.echo(f"Output: {output_path}")
    click.echo(f"Resolution: {width}x{height} @ {fps}fps")
    click.echo(f"Transition: {transition}")

    # Resolve assets for each scene
    scene_assets = []
    missing = 0
    black_ids = []

    for scene in all_scenes:
        asset = None
        asset_type = None

        # Priority: rendered_clip > generated > matched > infographic
        if scene.rendered_clip:
            asset = scene_plan_path.parent / scene.rendered_clip
            asset_type = 'clip'
        elif scene.generated_asset:
            asset = scene_plan_path.parent / 'assets' / 'generated' / scene.generated_asset
            asset_type = 'image'
        elif scene.matched_asset:
            asset = scene_plan_path.parent / scene.matched_asset
            asset_type = 'image'
        elif scene.infographic_asset:
            # infographic_asset stored as "infographics/X.svg", actual path is "assets/infographics/X.svg"
            asset = scene_plan_path.parent / 'assets' / scene.infographic_asset
            asset_type = 'image'

        duration = (scene.end_seconds or 5.0) - (scene.start_seconds or 0.0)

        if asset and asset.exists():
            scene_assets.append({
                'scene_id': scene.id,
                'asset': asset,
                'type': asset_type,
                'start': scene.start_seconds or 0.0,
                'duration': max(0.1, duration),  # Minimum 0.1s
            })
        else:
            # No asset - create blank (black) frame for this scene
            click.echo(f"  Note: {scene.id} has no asset (will use black frame)")
            scene_assets.append({
                'scene_id': scene.id,
                'asset': None,  # Signals to create black frame
                'type': 'blank',
                'start': scene.start_seconds or 0.0,
                'duration': max(0.1, duration),
            })
            missing += 1
            black_ids.append(scene.id)

    if missing > 0:
        click.echo(f"\nWarning: {missing} scenes have no assets")

    if not scene_assets:
        click.echo("Error: No assets found. Run asset preparation commands first.")
        return

    click.echo(f"\nAssets resolved: {len(scene_assets)}")

    # Sort scenes by start time for timeline-accurate assembly
    scene_assets.sort(key=lambda x: x['start'])

    # Insert gaps between scenes to match audio timeline
    timeline_assets = []
    current_time = 0.0

    for item in scene_assets:
        scene_start = item['start']
        # If there's a gap before this scene, fill with black
        if scene_start > current_time + 0.1:  # Gap > 0.1s
            gap_duration = scene_start - current_time
            timeline_assets.append({
                'scene_id': f'gap_{len(timeline_assets):03d}',
                'asset': None,
                'type': 'blank',
                'start': current_time,
                'duration': gap_duration,
            })
        timeline_assets.append(item)
        current_time = item['start'] + item['duration']

    # Get audio duration and add final gap if needed
    import subprocess
    probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    audio_duration = float(result.stdout.strip()) if result.returncode == 0 else current_time

    if audio_duration > current_time + 0.1:
        final_gap = audio_duration - current_time
        timeline_assets.append({
            'scene_id': 'final_gap',
            'asset': None,
            'type': 'blank',
            'start': current_time,
            'duration': final_gap,
        })

    total_duration = sum(a['duration'] for a in timeline_assets)
    gap_count = len([a for a in timeline_assets if a['scene_id'].startswith('gap_') or a['scene_id'] == 'final_gap'])
    click.echo(f"Timeline: {len(timeline_assets)} segments ({gap_count} gaps filled)")
    click.echo(f"Total duration: {total_duration:.1f}s (audio: {audio_duration:.1f}s)")

    scene_assets = timeline_assets

    # Create temporary directory for intermediate files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Step 1: Convert each asset to a clip
        click.echo("\nConverting assets to clips...")
        clip_files = []

        for i, item in enumerate(scene_assets):
            clip_path = tmpdir / f"clip_{i:04d}.mp4"
            asset = item['asset']
            duration = item['duration']

            click.echo(f"  [{i+1}/{len(scene_assets)}] {item['scene_id']} ({duration:.1f}s)")

            if item['type'] == 'clip':
                # Already a video, just copy/trim
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(asset),
                    '-t', str(duration),
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    '-an',  # No audio
                    str(clip_path)
                ]
            elif item['type'] == 'blank':
                # No asset - generate black frame
                cmd = [
                    'ffmpeg', '-y',
                    '-f', 'lavfi',
                    '-i', f'color=c=black:s={width}x{height}:r={fps}:d={duration}',
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    str(clip_path)
                ]
            else:
                # Image - scale and create video
                input_asset = asset

                # SVG files need conversion to PNG first
                if str(asset).lower().endswith('.svg'):
                    png_path = tmpdir / f"{item['scene_id']}.png"
                    try:
                        import cairosvg
                        cairosvg.svg2png(url=str(asset), write_to=str(png_path),
                                        output_width=width, output_height=height)
                        input_asset = png_path
                    except ImportError:
                        # Fallback: try Inkscape
                        inkscape_cmd = [
                            'inkscape', str(asset),
                            '--export-type=png',
                            f'--export-filename={png_path}',
                            f'-w', str(width), '-h', str(height)
                        ]
                        ink_result = subprocess.run(inkscape_cmd, capture_output=True, text=True)
                        if ink_result.returncode == 0:
                            input_asset = png_path
                        else:
                            click.echo(f"    Warning: Could not convert SVG, skipping")
                            continue
                else:
                    # Check for AVIF/HEIC images (may have wrong extension)
                    # FFmpeg 4.x doesn't support AVIF, so convert via PIL
                    try:
                        from PIL import Image
                        with Image.open(asset) as img:
                            if img.format in ('AVIF', 'HEIF', 'HEIC'):
                                png_path = tmpdir / f"{item['scene_id']}.png"
                                img.convert('RGB').save(png_path, 'PNG')
                                input_asset = png_path
                                click.echo(f"    (converted {img.format} to PNG)")
                    except Exception:
                        pass  # If PIL fails, let FFmpeg try anyway

                cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-i', str(input_asset),
                    '-t', str(duration),
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black',
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    '-r', str(fps),
                    str(clip_path)
                ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                click.echo(f"    Error: {result.stderr[:100]}")
                continue

            clip_files.append(clip_path)

        if not clip_files:
            click.echo("Error: No clips created.")
            return

        click.echo(f"\nClips created: {len(clip_files)}")

        # Step 2: Concatenate clips
        click.echo("\nConcatenating clips...")
        concat_list = tmpdir / 'concat.txt'
        with open(concat_list, 'w') as f:
            for clip in clip_files:
                f.write(f"file '{clip}'\n")

        video_only = tmpdir / 'video_only.mp4'

        if transition == 'cut':
            # Simple concatenation
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_list),
                '-c', 'copy',
                str(video_only)
            ]
        else:
            # For crossfade, need filter_complex (simplified version)
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_list),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                str(video_only)
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            click.echo(f"Error concatenating: {result.stderr}")
            return

        # Step 3: Add audio
        click.echo("\nAdding audio...")
        cmd = [
            'ffmpeg', '-y',
            '-i', str(video_only),
            '-i', str(audio_path),
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest',
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            click.echo(f"Error adding audio: {result.stderr}")
            return

    click.echo(f"\nDone! Output: {output_path}")

    # Get file size
    size_mb = output_path.stat().st_size / (1024 * 1024)
    click.echo(f"Size: {size_mb:.1f} MB")

    # QA: loudly flag black scenes so a "successful" render that is mostly black
    # can't pass silently (assemble exits 0 either way for caller compatibility).
    if black_ids:
        total = len(all_scenes)
        pct = 100.0 * len(black_ids) / max(1, total)
        click.echo("")
        click.echo(f"  !!  {len(black_ids)}/{total} scenes ({pct:.0f}%) rendered as BLACK "
                   f"(no asset): {', '.join(black_ids[:12])}"
                   + (" …" if len(black_ids) > 12 else ""))
        click.echo("      Run match / render-clips for these before publishing.")


@main.command('yt-download')
@click.argument('url_or_file')
@click.option('--output', '-o', type=click.Path(), default='.scratch/downloads',
              help='Output directory for downloaded videos (default: .scratch/downloads).')
@click.option('--format', '-f', 'video_format', default='bestvideo[height<=720]+bestaudio/best[height<=720]',
              help='yt-dlp format string.')
@click.option('--subtitles/--no-subtitles', default=True,
              help='Download subtitles.')
@click.option('--langs', '-l', default='en',
              help='Subtitle languages (comma-separated).')
@click.option('--playlist', is_flag=True,
              help='Download entire playlist.')
@click.option('--limit', type=int, default=None,
              help='Limit playlist downloads to N videos.')
@click.pass_context
def yt_download(ctx, url_or_file, output, video_format, subtitles, langs, playlist, limit):
    """Download YouTube videos using yt-dlp.

    URL_OR_FILE can be:
      - A YouTube video URL
      - A YouTube playlist URL (use --playlist)
      - A text file with URLs (one per line)

    Examples:

      nolan yt-download "https://youtube.com/watch?v=xxxxx"

      nolan yt-download urls.txt -o ./videos

      nolan yt-download "https://youtube.com/playlist?list=xxxxx" --playlist --limit 10

      nolan yt-download "https://youtube.com/watch?v=xxxxx" -f "bestvideo[height<=1080]+bestaudio"
    """
    from nolan.youtube import YouTubeClient, is_youtube_url, is_playlist_url

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    subtitle_langs = [l.strip() for l in langs.split(',')]

    client = YouTubeClient(
        output_dir=output_path,
        format=video_format,
        download_subtitles=subtitles,
        subtitle_langs=subtitle_langs,
    )

    url_or_file_path = Path(url_or_file)

    def progress_callback(current, total, result):
        status = "OK" if result.success else f"FAILED: {result.error}"
        click.echo(f"  [{current}/{total}] {result.title[:50]}... {status}")

    if url_or_file_path.exists() and url_or_file_path.is_file():
        # Download from file
        click.echo(f"Downloading from file: {url_or_file_path}")
        click.echo(f"Output: {output_path}")
        results = client.download_from_file(url_or_file_path, progress_callback=progress_callback)
    elif playlist or is_playlist_url(url_or_file):
        # Download playlist
        click.echo(f"Downloading playlist: {url_or_file}")
        click.echo(f"Output: {output_path}")
        if limit:
            click.echo(f"Limit: {limit} videos")
        results = client.download_playlist(url_or_file, limit=limit, progress_callback=progress_callback)
    elif is_youtube_url(url_or_file):
        # Download single video
        click.echo(f"Downloading: {url_or_file}")
        click.echo(f"Output: {output_path}")

        def single_progress(d):
            if d['status'] == 'downloading':
                pct = d.get('_percent_str', '?%')
                speed = d.get('_speed_str', '?')
                click.echo(f"\r  {pct} at {speed}", nl=False)
            elif d['status'] == 'finished':
                click.echo(f"\r  Download complete, processing...")

        result = client.download(url_or_file, progress_callback=single_progress)
        results = [result]
    else:
        click.echo(f"Error: '{url_or_file}' is not a valid YouTube URL or file.")
        return

    # Summary
    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    click.echo(f"\nDownloaded {success}/{len(results)} videos")
    if failed > 0:
        click.echo(f"Failed: {failed}")
        for r in results:
            if not r.success:
                click.echo(f"  - {r.error}")

    for r in results:
        if r.success and r.output_path:
            click.echo(f"  {r.output_path}")


@main.command('yt-search')
@click.argument('query')
@click.option('--limit', '-n', type=int, default=10,
              help='Maximum number of results.')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output JSON file for results.')
@click.option('--download', '-d', is_flag=True,
              help='Download the first result.')
@click.option('--download-dir', type=click.Path(), default='./downloads',
              help='Directory for downloaded videos (with --download).')
@click.pass_context
def yt_search(ctx, query, limit, output, download, download_dir):
    """Search YouTube for videos.

    QUERY is the search term.

    Examples:

      nolan yt-search "python tutorial"

      nolan yt-search "machine learning" -n 20 -o results.json

      nolan yt-search "documentary" --download
    """
    import json
    from nolan.youtube import YouTubeClient

    client = YouTubeClient()

    click.echo(f"Searching: {query}")
    click.echo(f"Limit: {limit}")

    def progress(current, total):
        click.echo(f"\r  Found {current}/{total}...", nl=False)

    try:
        results = client.search(query, limit=limit, progress_callback=progress)
        click.echo()  # newline after progress

        if not results:
            click.echo("No results found.")
            return

        click.echo(f"\nFound {len(results)} videos:\n")

        for i, video in enumerate(results, 1):
            duration = video.duration_formatted
            views = f"{int(video.view_count):,}" if video.view_count else "?"
            click.echo(f"  {i}. [{duration}] {video.title[:60]}")
            click.echo(f"     Channel: {video.channel or 'Unknown'} | Views: {views}")
            click.echo(f"     {video.url}")
            click.echo()

        # Save to JSON if requested
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_data = {
                "query": query,
                "count": len(results),
                "results": [v.to_dict() for v in results],
            }
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            click.echo(f"Results saved to: {output_path}")

        # Download first result if requested
        if download and results:
            click.echo("\nDownloading first result...")
            download_path = Path(download_dir)
            download_path.mkdir(parents=True, exist_ok=True)

            download_client = YouTubeClient(output_dir=download_path)
            result = download_client.download(results[0].url)

            if result.success:
                click.echo(f"Downloaded: {result.output_path}")
            else:
                click.echo(f"Download failed: {result.error}")

    except Exception as e:
        click.echo(f"Error: {e}")


@main.command('yt-info')
@click.argument('url')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output JSON file for video info.')
@click.pass_context
def yt_info(ctx, url, output):
    """Get information about a YouTube video.

    URL is the YouTube video URL.

    Examples:

      nolan yt-info "https://youtube.com/watch?v=xxxxx"

      nolan yt-info "https://youtube.com/watch?v=xxxxx" -o video_info.json
    """
    import json
    from nolan.youtube import YouTubeClient

    client = YouTubeClient()

    click.echo(f"Fetching info: {url}")

    try:
        info = client.get_info(url)

        click.echo(f"\nTitle: {info.title}")
        click.echo(f"Channel: {info.channel or 'Unknown'}")
        click.echo(f"Duration: {info.duration_formatted}")
        click.echo(f"Views: {int(info.view_count):,}" if info.view_count else "Views: Unknown")
        click.echo(f"Upload date: {info.upload_date or 'Unknown'}")
        click.echo(f"URL: {info.url}")

        if info.description:
            desc = info.description[:200] + "..." if len(info.description) > 200 else info.description
            click.echo(f"\nDescription:\n{desc}")

        if info.tags:
            click.echo(f"\nTags: {', '.join(info.tags[:10])}")

        if info.categories:
            click.echo(f"Categories: {', '.join(info.categories)}")

        # Save to JSON if requested
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(info.to_dict(), f, indent=2, ensure_ascii=False)
            click.echo(f"\nInfo saved to: {output_path}")

    except Exception as e:
        click.echo(f"Error: {e}")


# ==================== Project Management Commands ====================

@main.group()
def projects():
    """Manage projects for organizing video assets.

    Projects help organize your video library into separate collections.
    Each project has a slug (e.g., 'venezuela') for easy reference.
    """
    pass


@projects.command('init')
@click.argument('slug')
@click.option('--name', '-n', type=str, default=None,
              help='Display name for the project (defaults to slug).')
@click.option('--description', '-d', type=str, default=None,
              help='Project description.')
@click.option('--script', '-s', type=click.Path(exists=True, dir_okay=False), default=None,
              help='Path to an existing script.md to copy in.')
@click.option('--projects-root', type=click.Path(file_okay=False), default='projects',
              help='Parent directory for the new project (default: projects/).')
@click.pass_context
def projects_init(ctx, slug, name, description, script, projects_root):
    """Scaffold a new orchestrator-ready project folder.

    Creates `projects/<slug>/` with `project.yaml`, `script.md`, and the
    standard `source/`, `assets/`, `output/`, `.orchestrator/` subdirectories.

    Use this for greenfield orchestration. Subsequent `nolan index` calls scoped
    `--project <slug>` will populate the indexed library; `nolan orchestrate
    projects/<slug>` then drives the pipeline.

    Examples:

      nolan projects init venezuela --name "Venezuela Documentary"

      nolan projects init tutorials -d "Python tutorial series"

      nolan projects init tech-essay --script ./drafts/tech-essay.md
    """
    import shutil
    import yaml as yaml_lib

    project_dir = Path(projects_root) / slug
    if project_dir.exists():
        click.echo(f"Error: {project_dir} already exists. Pick a different slug or remove the folder.", err=True)
        ctx.exit(1)

    display_name = name or slug.replace('-', ' ').replace('_', ' ').title()

    # Create the directory tree
    project_dir.mkdir(parents=True)
    for sub in ("source", "assets", "output",
                ".orchestrator/instructions",
                ".orchestrator/feedback",
                ".orchestrator/history",
                ".orchestrator/modules"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    # project.yaml
    project_yaml_data = {
        "name": display_name,
        "slug": slug,
        "description": description or "",
        "source_videos": ["source/"],
        "output_dir": "output/",
        "assets_dir": "assets/",
    }
    (project_dir / "project.yaml").write_text(
        yaml_lib.safe_dump(project_yaml_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # script.md — copied from --script flag, or a starter template
    if script:
        shutil.copy(script, project_dir / "script.md")
        script_msg = f"copied from {script}"
    else:
        starter = (
            f"# Video Script\n\n"
            f"**Total Duration:** _set after writing_\n\n"
            f"---\n\n"
            f"## Hook [0:00 - 0:??]\n\n"
            f"<paradox or contrast that frames the central question>\n\n"
            f"## Context [0:?? - ?:??]\n\n"
            f"<historical or definitional setup>\n\n"
            f"## Thesis [?:?? - ?:??]\n\n"
            f"<single sentence stating the argument; enumerate evidence sections>\n\n"
            f"## Evidence 1 [?:?? - ?:??]\n\n"
            f"<first lens / cause / pillar>\n\n"
            f"## Evidence 2 [?:?? - ?:??]\n\n"
            f"<second lens>\n\n"
            f"## Evidence 3 [?:?? - ?:??]\n\n"
            f"<third lens>\n\n"
            f"## Conclusion [?:?? - ?:??]\n\n"
            f"<synthesis + reflective close>\n"
        )
        (project_dir / "script.md").write_text(starter, encoding="utf-8")
        script_msg = "starter template"

    click.echo(f"Created project at {project_dir}")
    click.echo(f"  slug:        {slug}")
    click.echo(f"  name:        {display_name}")
    if description:
        click.echo(f"  description: {description}")
    click.echo(f"  script.md:   {script_msg}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Edit `{project_dir}/script.md`.")
    click.echo(f"  2. Drop source videos in `{project_dir}/source/` and run "
               f"`nolan index {project_dir}/source --project {slug}`.")
    click.echo(f"  3. Run `nolan orchestrate {project_dir}` to advance the pipeline "
               f"(or add `--auto` to run all steps).")


@projects.command('create')
@click.argument('name')
@click.option('--slug', '-s', type=str, default=None,
              help='Custom slug (auto-generated from name if not provided).')
@click.option('--description', '-d', type=str, default=None,
              help='Project description.')
@click.option('--path', '-p', type=click.Path(), default=None,
              help='Project directory path.')
@click.pass_context
def projects_create(ctx, name, slug, description, path):
    """Create a new project.

    NAME is the human-readable project name.

    Examples:

      nolan projects create "Venezuela Documentary"

      nolan projects create "Tutorial Series" -s tutorials -d "Python tutorials"

      nolan projects create "My Project" -p ./projects/my-project
    """
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex

    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    try:
        project = index.create_project(name, slug=slug, description=description, path=path)
        click.echo(f"Created project:")
        click.echo(f"  Name: {project['name']}")
        click.echo(f"  Slug: {project['slug']}")
        click.echo(f"  ID:   {project['id']}")
        if project['path']:
            click.echo(f"  Path: {project['path']}")
        click.echo(f"\nUse this slug when indexing videos:")
        click.echo(f"  nolan index <videos> --project {project['slug']}")
    except ValueError as e:
        click.echo(f"Error: {e}")


@projects.command('list')
@click.pass_context
def projects_list(ctx):
    """List all projects.

    Shows project slug, name, and video count.
    """
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex

    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    projects = index.list_projects()

    if not projects:
        click.echo("No projects found.")
        click.echo("Create one with: nolan projects create \"My Project\"")
        return

    click.echo(f"{'SLUG':<20} {'NAME':<30} {'VIDEOS':<8}")
    click.echo("-" * 60)
    for p in projects:
        click.echo(f"{p['slug']:<20} {p['name'][:28]:<30} {p['video_count']:<8}")


@projects.command('status')
@click.option('--root', type=click.Path(), default='projects', help='Projects directory.')
@click.pass_context
def projects_status(ctx, root):
    """Unified project view: capabilities + library-DB link (C1).

    One list across script/scenes/orchestrator/segment workflows, replacing the
    per-page fragmented views.
    """
    from nolan import projects as P
    from nolan.indexer import VideoIndex
    config = ctx.obj['config']
    idx = None
    db_path = Path(config.indexing.database).expanduser()
    if db_path.exists():
        try:
            idx = VideoIndex(db_path)
        except Exception:
            idx = None
    found = P.discover_projects(Path(root), index=idx)
    if not found:
        click.echo("No projects found under " + str(root))
        return
    click.echo(f"{'SLUG':<30} {'KINDS':<26} {'DB':<4} SCENES")
    click.echo("-" * 72)
    for p in found:
        kinds = ",".join(p.kinds) or "-"
        db = "yes" if p.library_project_id else "-"
        click.echo(f"{p.slug[:29]:<30} {kinds[:25]:<26} {db:<4} {p.scene_count}")


@projects.command('backfill')
@click.option('--root', type=click.Path(), default='projects', help='Projects directory.')
@click.option('--dry-run', is_flag=True, help='Show what would be linked without writing.')
@click.pass_context
def projects_backfill(ctx, root, dry_run):
    """Register a library-DB project row for each filesystem project missing one (C1).

    Closes the FS↔DB gap: script/orchestrator projects created on disk never had a
    DB row, so videos/clips couldn't attach. Idempotent.
    """
    from nolan import projects as P
    from nolan.indexer import VideoIndex
    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)
    linked = skipped = 0
    for proj in P.discover_projects(Path(root), index=index):
        if proj.library_project_id:
            skipped += 1
            continue
        if dry_run:
            click.echo(f"  would link: {proj.slug}")
            linked += 1
            continue
        pid = P.link_db_project(index, proj)
        if pid:
            click.echo(f"  linked {proj.slug} -> {pid}")
            linked += 1
    verb = "would link" if dry_run else "linked"
    click.echo(f"{verb} {linked}, already-linked {skipped}.")


@projects.command('info')
@click.argument('slug')
@click.pass_context
def projects_info(ctx, slug):
    """Show project details.

    SLUG is the project slug or ID.

    Examples:

      nolan projects info venezuela

      nolan projects info fcaa7aa9
    """
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex

    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    project = index.get_project(slug)

    if not project:
        click.echo(f"Project not found: {slug}")
        return

    click.echo(f"Name:        {project['name']}")
    click.echo(f"Slug:        {project['slug']}")
    click.echo(f"ID:          {project['id']}")
    click.echo(f"Description: {project['description'] or '(none)'}")
    click.echo(f"Path:        {project['path'] or '(none)'}")
    click.echo(f"Created:     {project['created_at']}")

    # Get video count
    videos = index.get_videos_by_project(project['id'])
    click.echo(f"\nVideos: {len(videos)}")
    for v in videos[:5]:
        path = Path(v['path']).name if v['path'] else 'Unknown'
        click.echo(f"  - {path}")
    if len(videos) > 5:
        click.echo(f"  ... and {len(videos) - 5} more")


@projects.command('delete')
@click.argument('slug')
@click.option('--delete-videos', is_flag=True,
              help='Also delete indexed videos from database.')
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt.')
@click.pass_context
def projects_delete(ctx, slug, delete_videos, force):
    """Delete a project.

    SLUG is the project slug or ID.

    By default, only removes the project entry. Videos remain in the index
    but become unassociated. Use --delete-videos to also remove videos.

    Examples:

      nolan projects delete my-project

      nolan projects delete my-project --delete-videos -f
    """
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex

    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    project = index.get_project(slug)
    if not project:
        click.echo(f"Project not found: {slug}")
        return

    if not force:
        videos = index.get_videos_by_project(project['id'])
        msg = f"Delete project '{project['name']}'?"
        if delete_videos and videos:
            msg += f" This will also delete {len(videos)} indexed video(s)."
        if not click.confirm(msg):
            click.echo("Cancelled.")
            return

    if index.delete_project(slug, delete_videos=delete_videos):
        click.echo(f"Deleted project: {project['name']}")
        if delete_videos:
            click.echo("Associated videos were also deleted from index.")
    else:
        click.echo("Failed to delete project.")


# ==================== Semantic Search Commands ====================

@main.command('sync-vectors')
@click.option('--project', '-p', type=str, default=None,
              help='Only sync videos from this project slug.')
@click.option('--clear', is_flag=True,
              help='Clear existing vectors before syncing.')
@click.option('--force', '-f', is_flag=True,
              help='Force full sync, ignoring fingerprints (re-embed everything).')
@click.pass_context
def sync_vectors(ctx, project, clear, force):
    """Sync video index to vector database for semantic search.

    This command populates ChromaDB with embeddings from your indexed
    video segments and clusters, enabling semantic search.

    By default, uses incremental sync - only re-embeds videos whose
    fingerprints have changed since last sync. Use --force to re-embed all.

    This is automatically called after 'nolan index' completes.

    Examples:

      nolan sync-vectors

      nolan sync-vectors --project venezuela

      nolan sync-vectors --clear

      nolan sync-vectors --force  # Re-embed everything
    """
    config = ctx.obj['config']
    _sync_vectors_impl(config, project, clear, force)


def _sync_vectors_impl(config, project=None, clear=False, force=False, quiet=False):
    """Implementation of vector sync (shared by CLI and auto-sync)."""
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch

    db_path = Path(config.indexing.database).expanduser()
    if not db_path.exists():
        if not quiet:
            click.echo(f"Error: Database not found at {db_path}")
        return False

    index = VideoIndex(db_path)

    # Vector DB path alongside SQLite
    vector_db_path = db_path.parent / "vectors"
    if not quiet:
        click.echo(f"SQLite: {db_path}")
        click.echo(f"Vector DB: {vector_db_path}")

    # Resolve project
    project_id = None
    if project:
        proj = index.get_project(project)
        if not proj:
            if not quiet:
                click.echo(f"Error: Project '{project}' not found.")
            return False
        project_id = proj['id']
        if not quiet:
            click.echo(f"Project: {proj['name']} ({proj['slug']})")

    # Initialize vector search
    vector_search = VectorSearch(vector_db_path, index=index)

    # Clear if requested
    if clear:
        if not quiet:
            click.echo("Clearing existing vectors...")
        vector_search.clear()

    # Show current stats
    stats = vector_search.get_stats()
    if not quiet:
        click.echo(f"Current vectors: {stats['segments']} segments, {stats['clusters']} clusters")

    # Sync
    if not quiet:
        click.echo("\nSyncing to vector database...")
        if stats['segments'] == 0:
            click.echo("(First run will download embedding model ~440MB)")

    def progress(current, total, msg):
        if not quiet:
            click.echo(f"\r  [{current}/{total}] {msg[:50]:<50}", nl=False)

    result = vector_search.sync_from_index(
        project_id=project_id,
        progress_callback=progress,
        incremental=not force
    )
    if not quiet:
        click.echo()  # newline after progress

    skipped = result.get('skipped', 0)
    if not quiet:
        if skipped > 0:
            click.echo(f"\nSynced: {result['segments']} segments, {result['clusters']} clusters (skipped {skipped} unchanged)")
        else:
            click.echo(f"\nSynced: {result['segments']} segments, {result['clusters']} clusters")

    # Final stats
    stats = vector_search.get_stats()
    if not quiet:
        click.echo(f"Total vectors: {stats['segments']} segments, {stats['clusters']} clusters")

    return True


@main.command('semantic-search')
@click.argument('query')
@click.option('--limit', '-n', type=int, default=10,
              help='Maximum number of results.')
@click.option('--level', '-l', type=click.Choice(['segments', 'clusters', 'both']),
              default='both', help='Search level: segments, clusters, or both.')
@click.option('--project', '-p', type=str, default=None,
              help='Filter by project slug.')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output JSON file for results.')
@click.pass_context
def semantic_search(ctx, query, limit, level, project, output):
    """Semantic search across your video library.

    QUERY is a natural language description of what you're looking for.

    Unlike keyword search, semantic search understands meaning:
    - "person looking worried" finds "anxious expression", "concerned face"
    - "establishing shot of city" finds "urban skyline", "downtown aerial"

    Run 'nolan sync-vectors' first to populate the vector database.

    Examples:

      nolan semantic-search "person speaking to camera"

      nolan semantic-search "dramatic landscape" --level clusters

      nolan semantic-search "historical footage" --project venezuela -n 20

      nolan semantic-search "emotional moment" -o results.json
    """
    import json
    config = ctx.obj['config']
    from nolan.indexer import VideoIndex
    from nolan.vector_search import VectorSearch

    db_path = Path(config.indexing.database).expanduser()
    if not db_path.exists():
        click.echo(f"Error: Database not found at {db_path}")
        return

    vector_db_path = db_path.parent / "vectors"
    if not vector_db_path.exists():
        click.echo(f"Error: Vector database not found at {vector_db_path}")
        click.echo("Run 'nolan sync-vectors' first to create embeddings.")
        return

    index = VideoIndex(db_path)
    vector_search = VectorSearch(vector_db_path, index=index)

    # Check if vectors exist
    stats = vector_search.get_stats()
    if stats['segments'] == 0 and stats['clusters'] == 0:
        click.echo("Error: Vector database is empty.")
        click.echo("Run 'nolan sync-vectors' first to create embeddings.")
        return

    # Resolve project
    project_id = None
    if project:
        proj = index.get_project(project)
        if not proj:
            click.echo(f"Error: Project '{project}' not found.")
            return
        project_id = proj['id']
        click.echo(f"Project: {proj['name']}")

    click.echo(f"Query: \"{query}\"")
    click.echo(f"Level: {level}")
    click.echo(f"Searching...")

    # Perform search
    results = vector_search.search(
        query=query,
        limit=limit,
        search_level=level,
        project_id=project_id
    )

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"\nFound {len(results)} results:\n")

    # Display results
    for i, r in enumerate(results, 1):
        score_pct = f"{r.score * 100:.1f}%"
        time_str = f"{int(r.timestamp_start // 60):02d}:{int(r.timestamp_start % 60):02d}"
        video_name = Path(r.video_path).name if r.video_path else "Unknown"

        type_badge = f"[{r.content_type.upper()}]"
        click.echo(f"  {i}. {type_badge} {score_pct} @ {time_str}")
        click.echo(f"     Video: {video_name[:50]}")

        desc = r.description[:100] + "..." if len(r.description or "") > 100 else (r.description or "")
        click.echo(f"     {desc}")

        if r.people:
            click.echo(f"     People: {', '.join(r.people[:3])}")
        if r.location:
            click.echo(f"     Location: {r.location}")
        click.echo()

    # Save to JSON if requested
    if output:
        output_path = Path(output)
        output_data = {
            "query": query,
            "level": level,
            "project": project,
            "results": [
                {
                    "score": r.score,
                    "content_type": r.content_type,
                    "video_path": r.video_path,
                    "timestamp_start": r.timestamp_start,
                    "timestamp_end": r.timestamp_end,
                    "description": r.description,
                    "transcript": r.transcript,
                    "people": r.people,
                    "location": r.location,
                    "objects": r.objects,
                }
                for r in results
            ]
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        click.echo(f"Results saved to: {output_path}")


@main.command()
@click.option('--projects', '-p', type=click.Path(), default='projects',
              help='Directory containing projects (default: projects/).')
@click.option('--host', default='127.0.0.1', help='Host to bind to.')
@click.option('--port', default=8011, type=int, help='Port to bind to (8001 is SPARTA).')
@click.pass_context
def hub(ctx, projects, host, port):
    """Launch the unified NOLAN Hub UI.

    A unified interface combining:
    - Video Library: Browse indexed videos, segments, and clusters
    - Motion Effects Showcase: Generate motion effects for video essays
    - Scene Viewer: Review scene plans with A/V script layout

    Projects are auto-discovered from the projects directory (default: ./projects).
    Each subdirectory containing a scene_plan.json is shown as a project.

    Examples:

      nolan hub

      nolan hub --projects /path/to/projects

      nolan hub --port 8080
    """
    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()
    projects_dir = Path(projects) if projects else None

    from nolan.hub import create_hub_app, scan_projects
    import uvicorn

    click.echo(f"Starting NOLAN Hub at http://{host}:{port}")
    if db_path.exists():
        click.echo(f"Database: {db_path}")
    else:
        click.echo(f"Database not found - Library features will be limited")
    if projects_dir and projects_dir.exists():
        found_projects = scan_projects(projects_dir)
        click.echo(f"Projects directory: {projects_dir} ({len(found_projects)} projects found)")
    else:
        click.echo("Projects directory not found - Scene viewer will show no projects")
    click.echo("Render service should be running at http://127.0.0.1:3010")
    click.echo("Press Ctrl+C to stop.\n")

    app = create_hub_app(
        db_path=db_path if db_path.exists() else None,
        projects_dir=projects_dir,
    )
    uvicorn.run(app, host=host, port=port)


# ==================== Template Catalog Commands ====================

@main.group()
def templates():
    """Manage Lottie animation templates.

    Browse, search, and render templates from the unified catalog.
    """
    pass


@templates.command('list')
@click.option('--category', '-c', type=str, default=None,
              help='Filter by category.')
@click.option('--source', '-s', type=str, default=None,
              help='Filter by source (lottiefiles, jitter, lottieflow).')
@click.option('--with-schema', is_flag=True,
              help='Only show templates with schemas.')
def templates_list(category, source, with_schema):
    """List all available templates.

    Examples:

      nolan templates list

      nolan templates list --category lower-thirds

      nolan templates list --source jitter --with-schema
    """
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()

    if with_schema:
        items = catalog.list_with_schema()
    elif category:
        items = catalog.list_by_category(category)
    elif source:
        items = catalog.list_by_source(source)
    else:
        items = catalog.list_all()

    if not items:
        click.echo("No templates found.")
        return

    click.echo(f"{'ID':<40} {'CATEGORY':<20} {'SCHEMA':<6} {'TAGS'}")
    click.echo("-" * 90)
    for t in sorted(items, key=lambda x: (x.category, x.name)):
        schema = "Yes" if t.has_schema else "-"
        tags = ", ".join(t.tags[:3]) + ("..." if len(t.tags) > 3 else "")
        click.echo(f"{t.id[:38]:<40} {t.category[:18]:<20} {schema:<6} {tags}")

    click.echo(f"\nTotal: {len(items)} templates")


@templates.command('info')
@click.argument('template_id')
def templates_info(template_id):
    """Show detailed template information.

    TEMPLATE_ID is the template ID or local path.

    Examples:

      nolan templates info number-counter-ssLbxKeW8Z

      nolan templates info lower-thirds/simple.json
    """
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()

    template = catalog.get(template_id) or catalog.get_by_path(template_id)

    if not template:
        click.echo(f"Template not found: {template_id}")
        return

    click.echo(f"Name:     {template.name}")
    click.echo(f"ID:       {template.id}")
    click.echo(f"Category: {template.category}")
    click.echo(f"Source:   {template.source}")
    click.echo(f"Path:     {template.local_path}")
    click.echo(f"Size:     {template.width}x{template.height}")
    click.echo(f"Duration: {template.duration_seconds}s @ {template.fps} fps")
    click.echo(f"Tags:     {', '.join(template.tags) if template.tags else '(none)'}")

    if template.has_schema:
        click.echo(f"\nSchema fields: {', '.join(template.schema_fields)}")
    else:
        click.echo("\nNo schema (use 'nolan templates generate-schema' to create one)")

    if template.color_palette:
        click.echo(f"Colors:   {', '.join(template.color_palette)}")


@templates.command('search')
@click.argument('query')
@click.option('--all', 'match_all', is_flag=True,
              help='Match all tags (default: match any).')
def templates_search(query, match_all):
    """Search templates by tags.

    QUERY is a comma-separated list of tags to search for.

    Examples:

      nolan templates search counter

      nolan templates search "loading,spinner"

      nolan templates search "icon,success" --all
    """
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()

    tags = [t.strip() for t in query.split(",")]
    results = catalog.search_by_tags(tags, match_all=match_all)

    if not results:
        click.echo(f"No templates found matching: {', '.join(tags)}")
        return

    click.echo(f"{'ID':<40} {'CATEGORY':<20} {'TAGS'}")
    click.echo("-" * 80)
    for t in results:
        tags_str = ", ".join(t.tags[:4])
        click.echo(f"{t.id[:38]:<40} {t.category[:18]:<20} {tags_str}")

    click.echo(f"\nFound: {len(results)} templates")


@templates.command('categories')
def templates_categories():
    """List all template categories."""
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()

    summary = catalog.summary()

    click.echo("Template Categories:\n")
    for cat, count in sorted(summary['by_category'].items()):
        click.echo(f"  {cat:<25} {count} templates")

    click.echo(f"\nTotal: {summary['total']} templates across {len(summary['by_category'])} categories")


@templates.command('auto-tag')
def templates_auto_tag():
    """Auto-generate tags for all templates.

    Tags are generated based on category and name patterns.
    """
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()  # Load existing first

    tags_added = catalog.auto_tag_all()
    path = catalog.save_tags()

    click.echo(f"Added {tags_added} new tags")
    click.echo(f"Saved to: {path}")


@templates.command('summary')
def templates_summary():
    """Show template catalog summary."""
    from nolan.template_catalog import TemplateCatalog

    catalog = TemplateCatalog()
    catalog.load_tags()

    summary = catalog.summary()

    click.echo("=== Template Catalog Summary ===\n")
    click.echo(f"Total templates: {summary['total']}")
    click.echo(f"With schemas:    {summary['with_schema']}")
    click.echo()
    click.echo("By source:")
    for src, count in sorted(summary['by_source'].items()):
        click.echo(f"  {src:<15} {count}")
    click.echo()
    click.echo(f"Categories: {len(summary['by_category'])}")


@templates.command('index')
@click.option('--force', is_flag=True, help='Reindex all templates.')
def templates_index(force):
    """Index templates for semantic search.

    Creates vector embeddings for natural language search.
    """
    from nolan.template_catalog import TemplateCatalog, TemplateSearch

    catalog = TemplateCatalog()
    catalog.load_tags()
    catalog.auto_tag_all()  # Ensure tags are present

    search = TemplateSearch(catalog)

    click.echo("Indexing templates for semantic search...")
    indexed = search.index_templates(force=force)
    click.echo(f"Indexed {indexed} templates")


@templates.command('semantic-search')
@click.argument('query')
@click.option('-n', '--top', type=int, default=5, help='Number of results.')
@click.option('--category', '-c', type=str, default=None, help='Filter by category.')
@click.option('--with-schema', is_flag=True, help='Only templates with schemas.')
def templates_semantic_search(query, top, category, with_schema):
    """Search templates using natural language.

    QUERY is a natural language description of what you're looking for.

    Examples:

      nolan templates semantic-search "loading spinner animation"

      nolan templates semantic-search "show name at bottom" --with-schema

      nolan templates semantic-search "counting numbers" -n 10
    """
    from nolan.template_catalog import TemplateCatalog, TemplateSearch

    catalog = TemplateCatalog()
    catalog.load_tags()

    search = TemplateSearch(catalog)

    # Check if indexed
    try:
        results = search.search(query, top_k=top, category=category, with_schema_only=with_schema)
    except Exception as e:
        click.echo(f"Search failed: {e}")
        click.echo("Try running: nolan templates index")
        return

    if not results:
        click.echo("No results found. Try running: nolan templates index")
        return

    click.echo(f"{'SCORE':<8} {'ID':<35} {'CATEGORY':<20}")
    click.echo("-" * 70)
    for r in results:
        score_pct = f"{r.score * 100:.1f}%"
        click.echo(f"{score_pct:<8} {r.template.id[:33]:<35} {r.template.category[:18]:<20}")

    click.echo(f"\nFound: {len(results)} results")


@templates.command('match-scene')
@click.argument('visual_type')
@click.argument('description')
@click.option('-n', '--top', type=int, default=5, help='Number of results.')
@click.option('--with-schema', is_flag=True, help='Only templates with schemas.')
def templates_match_scene(visual_type, description, top, with_schema):
    """Find templates matching a scene specification.

    VISUAL_TYPE is the scene's visual type (lower-third, counter, title, etc.)
    DESCRIPTION is the visual description of what's needed.

    Examples:

      nolan templates match-scene lower-third "show speaker name"

      nolan templates match-scene counter "animated number statistic" --with-schema

      nolan templates match-scene title "chapter heading reveal"
    """
    from dataclasses import dataclass
    from nolan.template_catalog import (
        TemplateCatalog, TemplateSearch, find_templates_for_scene
    )

    @dataclass
    class MockScene:
        visual_type: str
        visual_description: str
        narration_excerpt: str = ''

    catalog = TemplateCatalog()
    catalog.load_tags()

    search = TemplateSearch(catalog)

    scene = MockScene(visual_type=visual_type, visual_description=description)
    results = find_templates_for_scene(
        scene, catalog, search, top_k=top, require_schema=with_schema
    )

    if not results:
        click.echo("No matching templates found.")
        return

    click.echo(f"{'SCORE':<8} {'NAME':<30} {'CATEGORY':<20} {'SCHEMA'}")
    click.echo("-" * 75)
    for r in results:
        score_pct = f"{r.score * 100:.1f}%"
        schema = "Yes" if r.template.has_schema else "-"
        click.echo(f"{score_pct:<8} {r.template.name[:28]:<30} {r.template.category[:18]:<20} {schema}")

    click.echo(f"\nTop match: {results[0].template.local_path}")


# ==================== Visual Router Commands ====================

@main.command('route-scenes')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.option('--threshold', '-t', type=float, default=0.5,
              help='Template match threshold (0-1).')
def route_scenes(scene_plan, threshold):
    """Show routing decisions for each scene.

    SCENE_PLAN is the path to scene_plan.json.

    Displays which pipeline (template, library, generation, infographic)
    each scene will use based on its visual_type.

    Examples:

      nolan route-scenes scene_plan.json

      nolan route-scenes scene_plan.json --threshold 0.6
    """
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.visual_router import VisualRouter

    plan = ScenePlan.load(scene_plan)
    router = VisualRouter(template_score_threshold=threshold)

    click.echo(f"{'SCENE':<25} {'TYPE':<15} {'ROUTE':<12} {'TEMPLATE/REASON'}")
    click.echo("-" * 80)

    all_scenes = []
    for section_name, scenes in plan.sections.items():
        for scene in scenes:
            all_scenes.append(scene)
            decision = router.route(scene)

            template_info = decision.reason[:25]
            if decision.template:
                template_info = f"{decision.template.name} ({decision.template_score:.0%})"

            scene_id = f"{section_name[:8]}:{scene.id[:14]}"
            click.echo(f"{scene_id:<25} {scene.visual_type:<15} {decision.route:<12} {template_info}")

    # Summary
    decisions = router.route_all(all_scenes)
    summary = router.summary(decisions)

    click.echo(f"\nTotal: {summary['total']} scenes")
    click.echo("By route:")
    for route, count in sorted(summary['by_route'].items()):
        click.echo(f"  {route:<12} {count}")


@main.group()
def video_gen():
    """Video generation with ComfyUI or Runway.

    Generate video clips from text prompts using local models (ComfyUI)
    or commercial APIs (Runway).
    """
    pass


@video_gen.command('check')
@click.option('--backend', '-b', type=click.Choice(['comfyui', 'runway', 'all']),
              default='all', help='Backend to check.')
@click.option('--host', type=str, default='127.0.0.1',
              help='ComfyUI host.')
@click.option('--port', type=int, default=8188,
              help='ComfyUI port.')
def video_gen_check(backend, host, port):
    """Check video generation backend availability.

    Examples:

      nolan video-gen check

      nolan video-gen check --backend comfyui

      nolan video-gen check --backend runway
    """
    import os

    if backend in ('comfyui', 'all'):
        click.echo("ComfyUI:")
        from nolan.video_gen import ComfyUIVideoGenerator, VideoGenerationConfig
        try:
            # Check if we can connect (need a workflow to instantiate)
            import httpx
            try:
                response = httpx.get(f"http://{host}:{port}/system_stats", timeout=5.0)
                if response.status_code == 200:
                    stats = response.json()
                    click.echo(f"  Status: Connected")
                    click.echo(f"  URL: http://{host}:{port}")
                    if 'system' in stats:
                        click.echo(f"  GPU: {stats['system'].get('gpu', 'Unknown')}")
                else:
                    click.echo(f"  Status: Error (HTTP {response.status_code})")
            except httpx.ConnectError:
                click.echo(f"  Status: Not running")
                click.echo(f"  URL: http://{host}:{port}")
        except Exception as e:
            click.echo(f"  Status: Error - {e}")

    if backend in ('runway', 'all'):
        click.echo("\nRunway:")
        api_key = os.environ.get('RUNWAY_API_KEY')
        if api_key:
            click.echo(f"  API Key: {'*' * 8}...{api_key[-4:]}")
            from nolan.video_gen import RunwayGenerator
            try:
                gen = RunwayGenerator(api_key=api_key)
                connected = asyncio.run(gen.check_connection())
                click.echo(f"  Status: {'Connected' if connected else 'Connection failed'}")
            except Exception as e:
                click.echo(f"  Status: Error - {e}")
        else:
            click.echo("  API Key: Not set (RUNWAY_API_KEY)")
            click.echo("  Status: Not configured")


@video_gen.command('generate')
@click.argument('prompt')
@click.option('--output', '-o', type=click.Path(), required=True,
              help='Output video path.')
@click.option('--backend', '-b', type=click.Choice(['comfyui', 'runway']),
              default='comfyui', help='Backend to use.')
@click.option('--workflow', '-w', type=click.Path(exists=True),
              help='ComfyUI workflow file (required for ComfyUI).')
@click.option('--duration', '-d', type=float, default=4.0,
              help='Video duration in seconds.')
@click.option('--width', type=int, default=1280,
              help='Video width.')
@click.option('--height', type=int, default=720,
              help='Video height.')
@click.option('--negative', type=str, default=None,
              help='Negative prompt.')
@click.option('--seed', type=int, default=None,
              help='Random seed (None = random).')
@click.option('--host', type=str, default='127.0.0.1',
              help='ComfyUI host.')
@click.option('--port', type=int, default=8188,
              help='ComfyUI port.')
@click.option('--timeout', type=float, default=600.0,
              help='Generation timeout in seconds.')
def video_gen_generate(prompt, output, backend, workflow, duration, width, height,
                       negative, seed, host, port, timeout):
    """Generate a video from a text prompt.

    PROMPT is the text description of the video to generate.

    Examples:

      nolan video-gen generate "sunset over mountains" -o sunset.mp4 -w ltx-video.json

      nolan video-gen generate "city streets at night" -o city.mp4 --backend runway

      nolan video-gen generate "ocean waves" -o waves.mp4 -w wan-video.json -d 8
    """
    from pathlib import Path
    from nolan.video_gen import (
        ComfyUIVideoGenerator, RunwayGenerator,
        VideoGenerationConfig, VideoGeneratorFactory
    )

    config = VideoGenerationConfig(
        duration=duration,
        width=width,
        height=height,
        negative_prompt=negative,
        seed=seed,
    )

    output_path = Path(output)

    click.echo(f"Backend: {backend}")
    click.echo(f"Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
    click.echo(f"Output: {output_path}")
    click.echo(f"Duration: {duration}s @ {width}x{height}")

    async def run_generation():
        if backend == 'comfyui':
            if not workflow:
                raise click.UsageError("--workflow is required for ComfyUI backend")
            generator = ComfyUIVideoGenerator(
                host=host,
                port=port,
                workflow_file=Path(workflow)
            )
        else:
            import os
            api_key = os.environ.get('RUNWAY_API_KEY')
            if not api_key:
                raise click.UsageError("RUNWAY_API_KEY environment variable required for Runway")
            generator = RunwayGenerator(api_key=api_key)

        click.echo(f"\nGenerating...")
        result = await generator.generate(prompt, output_path, config, timeout)
        return result

    result = asyncio.run(run_generation())

    if result.success:
        click.echo(f"\nSuccess!")
        click.echo(f"  Video: {result.video_path}")
        click.echo(f"  Duration: {result.duration_seconds}s")
        click.echo(f"  Generation time: {result.generation_time_seconds:.1f}s")
        if result.cost_usd:
            click.echo(f"  Cost: ${result.cost_usd:.2f}")
    else:
        click.echo(f"\nFailed: {result.error}")
        raise SystemExit(1)


@video_gen.command('scene')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.argument('scene_id')
@click.option('--backend', '-b', type=click.Choice(['comfyui', 'runway']),
              default='comfyui', help='Backend to use.')
@click.option('--workflow', '-w', type=click.Path(exists=True),
              help='ComfyUI workflow file.')
@click.option('--style', type=str, default=None,
              help='Style hint (e.g., "cinematic", "documentary").')
@click.option('--host', type=str, default='127.0.0.1',
              help='ComfyUI host.')
@click.option('--port', type=int, default=8188,
              help='ComfyUI port.')
def video_gen_scene(scene_plan, scene_id, backend, workflow, style, host, port):
    """Generate video for a specific scene.

    Uses the scene's visual_description and narration to create a video.

    SCENE_PLAN is the path to scene_plan.json.
    SCENE_ID is the scene ID to generate video for.

    Examples:

      nolan video-gen scene scene_plan.json scene_001 -w ltx-video.json

      nolan video-gen scene scene_plan.json scene_042 --backend runway --style cinematic
    """
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.video_gen import (
        ComfyUIVideoGenerator, RunwayGenerator,
        VideoGenerationConfig, generate_video_for_scene
    )

    scene_plan_path = Path(scene_plan)
    plan = ScenePlan.load(str(scene_plan_path))

    # Find scene
    scene = None
    for section_name, scenes in plan.sections.items():
        for s in scenes:
            if s.id == scene_id:
                scene = s
                break
        if scene:
            break

    if not scene:
        click.echo(f"Scene not found: {scene_id}")
        raise SystemExit(1)

    click.echo(f"Scene: {scene.id}")
    click.echo(f"Visual: {scene.visual_description[:60]}{'...' if len(scene.visual_description or '') > 60 else ''}")
    click.echo(f"Narration: {scene.narration_excerpt[:60]}{'...' if len(scene.narration_excerpt or '') > 60 else ''}")

    # Calculate duration
    duration = (scene.end_seconds or 5.0) - (scene.start_seconds or 0.0)
    click.echo(f"Duration: {duration:.1f}s")

    # Output path
    clips_dir = scene_plan_path.parent / 'assets' / 'generated'
    clips_dir.mkdir(parents=True, exist_ok=True)
    output_path = clips_dir / f"{scene_id}.mp4"

    config = VideoGenerationConfig(
        duration=duration,
        width=1920,
        height=1080,
        style=style,
    )

    async def run_generation():
        if backend == 'comfyui':
            if not workflow:
                raise click.UsageError("--workflow is required for ComfyUI backend")
            generator = ComfyUIVideoGenerator(
                host=host,
                port=port,
                workflow_file=Path(workflow)
            )
        else:
            import os
            api_key = os.environ.get('RUNWAY_API_KEY')
            if not api_key:
                raise click.UsageError("RUNWAY_API_KEY environment variable required")
            generator = RunwayGenerator(api_key=api_key)

        click.echo(f"\nGenerating with {backend}...")
        return await generate_video_for_scene(
            generator=generator,
            visual_description=scene.visual_description or "",
            narration_excerpt=scene.narration_excerpt or "",
            output_path=output_path,
            config=config,
            style_hint=style
        )

    result = asyncio.run(run_generation())

    if result.success:
        click.echo(f"\nSuccess!")
        click.echo(f"  Video: {result.video_path}")
        click.echo(f"  Generation time: {result.generation_time_seconds:.1f}s")

        # Update scene plan
        scene.rendered_clip = str(output_path.relative_to(scene_plan_path.parent))
        plan.save(str(scene_plan_path))
        click.echo(f"  Updated: {scene_plan_path}")
    else:
        click.echo(f"\nFailed: {result.error}")
        raise SystemExit(1)


@video_gen.command('batch')
@click.argument('scene_plan', type=click.Path(exists=True))
@click.option('--backend', '-b', type=click.Choice(['comfyui', 'runway']),
              default='comfyui', help='Backend to use.')
@click.option('--workflow', '-w', type=click.Path(exists=True),
              help='ComfyUI workflow file.')
@click.option('--visual-types', type=str, default='generated,generated-image',
              help='Comma-separated visual types to generate.')
@click.option('--force', is_flag=True,
              help='Regenerate even if rendered_clip exists.')
@click.option('--limit', type=int, default=None,
              help='Maximum scenes to generate.')
@click.option('--dry-run', is_flag=True,
              help='Show what would be generated without doing it.')
@click.option('--host', type=str, default='127.0.0.1',
              help='ComfyUI host.')
@click.option('--port', type=int, default=8188,
              help='ComfyUI port.')
def video_gen_batch(scene_plan, backend, workflow, visual_types, force, limit, dry_run, host, port):
    """Generate videos for multiple scenes.

    Processes all scenes matching the specified visual types.

    SCENE_PLAN is the path to scene_plan.json.

    Examples:

      nolan video-gen batch scene_plan.json -w ltx-video.json

      nolan video-gen batch scene_plan.json --visual-types b-roll,cinematic --backend runway

      nolan video-gen batch scene_plan.json -w ltx.json --dry-run
    """
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.video_gen import (
        ComfyUIVideoGenerator, RunwayGenerator,
        VideoGenerationConfig, generate_video_for_scene
    )

    scene_plan_path = Path(scene_plan)
    plan = ScenePlan.load(str(scene_plan_path))
    target_types = set(t.strip() for t in visual_types.split(','))

    # Find scenes to generate
    to_generate = []
    for section_name, scenes in plan.sections.items():
        for scene in scenes:
            if scene.visual_type not in target_types:
                continue
            if not force and scene.rendered_clip:
                continue
            to_generate.append((section_name, scene))

    if limit:
        to_generate = to_generate[:limit]

    if not to_generate:
        click.echo("No scenes to generate.")
        return

    click.echo(f"Scenes to generate: {len(to_generate)}")
    click.echo(f"Backend: {backend}")
    click.echo(f"Visual types: {', '.join(target_types)}")

    if dry_run:
        click.echo("\nDry run - would generate:")
        for section, scene in to_generate:
            duration = (scene.end_seconds or 5.0) - (scene.start_seconds or 0.0)
            desc = (scene.visual_description or "")[:40]
            click.echo(f"  {scene.id}: {scene.visual_type} - {desc}... ({duration:.1f}s)")
        return

    # Setup generator
    async def run_batch():
        if backend == 'comfyui':
            if not workflow:
                raise click.UsageError("--workflow is required for ComfyUI backend")
            generator = ComfyUIVideoGenerator(
                host=host,
                port=port,
                workflow_file=Path(workflow)
            )
        else:
            import os
            api_key = os.environ.get('RUNWAY_API_KEY')
            if not api_key:
                raise click.UsageError("RUNWAY_API_KEY environment variable required")
            generator = RunwayGenerator(api_key=api_key)

        # Check connection
        connected = await generator.check_connection()
        if not connected:
            click.echo(f"Cannot connect to {backend} backend")
            return 0, len(to_generate)

        clips_dir = scene_plan_path.parent / 'assets' / 'generated'
        clips_dir.mkdir(parents=True, exist_ok=True)

        generated = 0
        failed = 0
        total_cost = 0.0

        for i, (section_name, scene) in enumerate(to_generate):
            click.echo(f"\n[{i+1}/{len(to_generate)}] {scene.id}")

            duration = (scene.end_seconds or 5.0) - (scene.start_seconds or 0.0)
            output_path = clips_dir / f"{scene.id}.mp4"

            config = VideoGenerationConfig(
                duration=duration,
                width=1920,
                height=1080,
            )

            result = await generate_video_for_scene(
                generator=generator,
                visual_description=scene.visual_description or "",
                narration_excerpt=scene.narration_excerpt or "",
                output_path=output_path,
                config=config,
            )

            if result.success:
                scene.rendered_clip = str(output_path.relative_to(scene_plan_path.parent))
                generated += 1
                click.echo(f"  Success: {result.video_path.name} ({result.generation_time_seconds:.1f}s)")
                if result.cost_usd:
                    total_cost += result.cost_usd
            else:
                failed += 1
                click.echo(f"  Failed: {result.error}")

        # Save updated plan
        plan.save(str(scene_plan_path))
        click.echo(f"\nUpdated: {scene_plan_path}")

        return generated, failed, total_cost

    generated, failed, total_cost = asyncio.run(run_batch())
    click.echo(f"\nGenerated: {generated}, Failed: {failed}")
    if total_cost > 0:
        click.echo(f"Total cost: ${total_cost:.2f}")


@main.command()
@click.argument('project', type=click.Path(exists=True, file_okay=False))
@click.option('--auto', is_flag=True, default=False,
              help='Run all pending pipeline steps in sequence (one Director '
                   'invocation; each step still writes its own checkpoint).')
@click.option('--refine', is_flag=True, default=False,
              help='Run a refine pass on a previously-completed step using '
                   'the latest unconsumed feedback file.')
@click.option('--target', type=str, default=None,
              help='Step name to refine. Required with --refine.')
@click.pass_context
def orchestrate(ctx, project, auto, refine, target):
    """Run the two-layer Director on a project folder.

    Default mode: advance the pipeline by one step (run_next_step).
    --auto mode: run all pending steps in sequence until done or error.
    --refine mode: re-run a completed step against the latest feedback file.
    """
    from nolan.orchestrator.director import (
        DirectorError, run_auto_sync, run_refine_sync, run_sync,
    )

    if auto and refine:
        click.echo("Error: --auto and --refine are mutually exclusive.", err=True)
        ctx.exit(2)

    project_path = Path(project)

    try:
        if refine:
            if not target:
                click.echo(
                    "Error: --target STEP is required with --refine.",
                    err=True,
                )
                ctx.exit(2)
            checkpoint_path = run_refine_sync(project_path, target)
            click.echo(f"Checkpoint written: {checkpoint_path}")
            click.echo("Refine pass complete. Review the new snapshot and iterate.")
        elif auto:
            checkpoints = run_auto_sync(project_path)
            for cp in checkpoints:
                click.echo(f"Checkpoint written: {cp}")
            click.echo(
                f"Auto run finished — {len(checkpoints)} step(s) executed."
            )
        else:
            checkpoint_path = run_sync(project_path)
            click.echo(f"Checkpoint written: {checkpoint_path}")
            click.echo("Review and re-run to advance the next step.")
    except DirectorError as exc:
        click.echo(f"Director error: {exc}", err=True)
        ctx.exit(1)


@main.command('build-from-segment')
@click.option('--source', type=click.Path(exists=True), help='Indexed source video (with sibling .srt).')
@click.option('--start', type=float, help='Span start seconds (with --source).')
@click.option('--end', type=float, help='Span end seconds (with --source).')
@click.option('--srt', type=click.Path(exists=True), help='Override SRT path.')
@click.option('--index-db', type=click.Path(), help='Project index.db for b-roll search.')
@click.option('--script', 'script_file', type=click.Path(exists=True), help='Script text file.')
@click.option('--vo', type=click.Path(exists=True), help='Voiceover audio file.')
@click.option('--from-plan', type=click.Path(exists=True), help='Resume from an edited scene_plan.json.')
@click.option('--mode', type=click.Choice(['auto', 'review']), default='auto')
@click.option('--out-dir', '-o', type=click.Path(), default='segment_out')
@click.option('--music', type=click.Path(exists=True), help='Background music bed (P3).')
@click.option('--no-generation', is_flag=True, help='Disable ComfyUI fallback for unmatched b-roll.')
@click.option('--comfyui-model', type=click.Choice(['flux-dev', 'z-image']), default='flux-dev',
              help='ComfyUI model for generated scenes.')
@click.option('--comfyui-timeout', type=float, default=240.0,
              help='Per-image gen timeout (s); on timeout a scene falls back to a card.')
@click.option('--voice', help='Voice id (from the voice library) for generated VO; '
              'overrides the project/default voice. Needs tts.enabled in nolan.yaml.')
@click.option('--vo-pace', type=float, default=1.0,
              help='Voiceover pace (ffmpeg atempo, >1 faster). Default 1.0.')
@click.pass_context
def build_from_segment(ctx, source, start, end, srt, index_db, script_file, vo, from_plan,
                       mode, out_dir, music, no_generation, comfyui_model, comfyui_timeout,
                       voice, vo_pace):
    """Build a ~1-minute video essay from a segment (span / script / voiceover)."""
    config = ctx.obj['config']
    from nolan.llm import create_text_llm
    from nolan.segment import (SegmentBuilder, BuildConfig, ResolverConfig,
                               from_indexed_span, from_script, from_vo)
    llm = create_text_llm(config)
    out_dir = Path(out_dir)
    _cw = {'flux-dev': ('workflows/image/flux-dev-fp8.json', '6'),
           'z-image': ('workflows/image/basic-z-image.json', '27')}[comfyui_model]
    bcfg = BuildConfig(out_dir=out_dir, mode=mode, music=Path(music) if music else None,
                       resolver=ResolverConfig(enable_generation=not no_generation),
                       comfyui_workflow=_cw[0], comfyui_prompt_node=_cw[1], comfyui_timeout=comfyui_timeout,
                       voice=voice, vo_tempo=vo_pace)
    builder = SegmentBuilder(llm, bcfg, nolan_config=config)

    if from_plan:
        res = builder.build_from_plan(Path(from_plan))
        click.echo(f"Rendered from plan → {res.final_path}")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    if source and start is not None and end is not None:
        srt_path = srt or str(Path(source).with_suffix('.srt'))
        if not Path(srt_path).exists():
            # try the yt-dlp style sibling
            cands = list(Path(source).parent.glob(Path(source).stem + '*.srt'))
            srt_path = str(cands[0]) if cands else srt_path
        seg = from_indexed_span(Path(source), Path(srt_path), start, end, out_dir,
                                index_db=Path(index_db) if index_db else None)
    elif script_file:
        seg = from_script(Path(script_file).read_text(encoding='utf-8'), out_dir,
                          vo_path=Path(vo) if vo else None,
                          index_db=Path(index_db) if index_db else None)
    elif vo:
        seg = from_vo(Path(vo), out_dir)
    else:
        click.echo("Provide --source+--start+--end, or --script, or --vo, or --from-plan.", err=True)
        ctx.exit(1)

    res = asyncio.run(builder.build(seg))
    click.echo(f"Scenes: {len(res.manifest['scenes'])}  | plan: {res.plan_path}")
    for s in res.manifest['scenes']:
        click.echo(f"  {s['t'][0]}-{s['t'][1]}s  [{s['source']}]  {s['narration']}")
    if res.stopped_for_review:
        click.echo(f"\nReview mode: edit {res.plan_path}, then "
                   f"`nolan build-from-segment --from-plan {res.plan_path}`")
    else:
        click.echo(f"\nDone → {res.final_path}")


_COMFY_WF = {'flux-dev': ('workflows/image/flux-dev-fp8.json', '6'),
             'z-image': ('workflows/image/basic-z-image.json', '27')}


@main.command('revise-scene')
@click.argument('plan', type=click.Path(exists=True))
@click.argument('scene_id')
@click.option('--note', help='Free-text instruction; an agent rewrites the scene to match.')
@click.option('--set', 'sets', multiple=True, metavar='FIELD=VALUE',
              help='Direct field edit (repeatable). VALUE parsed as JSON, else kept as string.')
@click.pass_context
def revise_scene_cmd(ctx, plan, scene_id, note, sets):
    """Apply a comment OR a direct edit to one scene of a scene_plan.json (the gate)."""
    import json
    from nolan import iterate
    config = ctx.obj['config']
    if note and sets:
        click.echo("Use either --note (agent) or --set (direct), not both.", err=True)
        ctx.exit(1)
    if not note and not sets:
        click.echo("Provide --note or one or more --set FIELD=VALUE.", err=True)
        ctx.exit(1)

    pipeline = iterate.detect_pipeline(plan)
    if note:
        from nolan.llm import create_text_llm
        llm = create_text_llm(config)
        words = iterate.scene_words(plan)  # VO word-timing for {cue:"..."} (cached)
        patch = asyncio.run(iterate.apply_edit(plan, scene_id, note=note, client=llm,
                                               pipeline=pipeline, transcript_words=words))
    else:
        edits = {}
        for item in sets:
            if '=' not in item:
                click.echo(f"Bad --set '{item}' (need FIELD=VALUE).", err=True)
                ctx.exit(1)
            k, v = item.split('=', 1)
            try:
                edits[k] = json.loads(v)
            except (ValueError, json.JSONDecodeError):
                edits[k] = v
        patch = asyncio.run(iterate.apply_edit(plan, scene_id, patch=edits, pipeline=pipeline))

    if not patch:
        click.echo(f"No change applied to {scene_id} (note produced an empty patch?).")
        return
    click.echo(f"[{pipeline}] revised {scene_id}: {', '.join(patch.keys())}")
    click.echo(f"Re-render with: nolan rerender {plan} --scenes {scene_id}")


@main.command('publish')
@click.argument('source')
@click.option('--theme', default='press', help='reacticle theme (press/bodoni/tufte/freddie/vignelli/...)')
@click.option('--type', 'atype', default='explainer', help='article type (essay/explainer/longform/briefing/...)')
@click.option('--width', default='regular', help='narrow/regular/wide/full')
@click.option('--images', default='none', help='none/placeholders/ai-generated')
@click.option('--brand', default=None, help='brand seed hex color (recolors the theme via oklch), e.g. #3257d6')
@click.option('--slug', default=None, help='output workspace name (default: from the title)')
@click.option('--out', type=click.Path(), default=None, help='output dir (default: projects/_published)')
@click.option('--review', is_flag=True, help='scaffold + source only, then stop for authoring/review')
@click.option('--no-cover', is_flag=True, help='disable the book-style cover')
@click.pass_context
def publish_cmd(ctx, source, theme, atype, width, images, brand, slug, out, review, no_cover):
    """Turn a URL / doc / text into a self-contained, offline single-file HTML article."""
    from nolan.publish import Publisher, PublishConfig
    cfg = PublishConfig(theme=theme, type=atype, width=width, images=images,
                        brand_color=brand, cover=not no_cover,
                        mode='review' if review else 'auto', out_dir=out)
    pub = Publisher(cfg, nolan_config=ctx.obj['config'])
    res = asyncio.run(pub.run(source, slug=slug))
    if res.stopped_for_review:
        click.echo(f"Scaffolded {res.workspace}")
        click.echo("  Author the article (agent) then: build in that workspace.")
    elif res.ok:
        click.echo(f"Published -> {res.article_html}")
        click.echo(f"  {res.summary}")
    else:
        click.echo(f"Incomplete: {res.summary or res.notes}", err=True)
        ctx.exit(1)


@main.command('rerender')
@click.argument('plan', type=click.Path(exists=True))
@click.option('--scenes', required=True, help='Comma-separated scene ids to re-render.')
@click.option('--comfyui-model', type=click.Choice(['flux-dev', 'z-image']), default='flux-dev')
@click.option('--comfyui-timeout', type=float, default=240.0)
@click.pass_context
def rerender_cmd(ctx, plan, scenes, comfyui_model, comfyui_timeout):
    """Re-render only the named scenes and reassemble (works for either pipeline)."""
    from nolan import iterate
    config = ctx.obj['config']
    ids = [s.strip() for s in scenes.split(',') if s.strip()]
    pipeline = iterate.detect_pipeline(plan)
    wf, node = _COMFY_WF[comfyui_model]
    # Both pipelines may need the LLM: segment to render/escalate, either to re-resolve
    # an edited scene's library match (search_query change).
    from nolan.llm import create_text_llm
    llm = create_text_llm(config)
    click.echo(f"[{pipeline}] re-rendering {len(ids)} scene(s): {', '.join(ids)} …")
    final = iterate.rerender_scenes(
        plan, ids, pipeline=pipeline, llm_client=llm, nolan_config=config,
        comfyui_workflow=wf, comfyui_prompt_node=node, comfyui_timeout=comfyui_timeout)

    # Surface how each re-rendered scene resolved so a silent degrade (search-miss ->
    # generation/card fallback) is visible rather than hidden.
    data = iterate.load_plan_raw(plan)
    for s in (sc for _, sc in iterate.iter_scenes(data) if sc.get("id") in set(ids)):
        src = str(s.get("resolved_source") or "?")
        flag = "  ⚠ fell back" if ("miss" in src or "fallback" in src) else ""
        click.echo(f"  {s.get('id')}: {src}{flag}")
    click.echo(f"Done → {final}")


@main.command('render-flow')
@click.argument('project', type=click.Path(exists=True))
@click.option('--mode', type=click.Choice(['auto', 'semi-auto']), default='auto',
              help='auto: draft + render straight through; semi-auto: pause at authoring (Gate A).')
@click.option('--no-gate', is_flag=True, help='skip the pre-render QA gate (auto mode).')
def render_flow_cmd(project, mode, no_gate):
    """Render a flow video (art, …) for a PROJECT via the flow runner.

    The project owns its plan in flow.spec.json (flow id self-declared). auto renders +
    delivers; semi-auto stops at authoring mode so you can tweak the plan + link assets,
    then resume with `nolan render-flow <project> --mode auto`.
    """
    from nolan.flows.authoring import run
    res = run(project, mode=mode, gate=not no_gate)
    if mode == 'semi-auto':
        click.echo(f"[paused] authoring -> {res['plan']}")
        click.echo(f"   {res['beats']} beats; need assets: {res['needs_assets'] or 'none'}")
        click.echo("   Tweak the plan / link assets, then: nolan render-flow <project> --mode auto")
    else:
        click.echo(f"[ok] delivered -> {res}")


@main.command()
@click.argument('image', type=click.Path(exists=True))
@click.option('--model', '-m',
              type=click.Choice(['isnet', 'birefnet', 'u2net', 'u2netp',
                                 'isnet-anime', 'birefnet-portrait', 'silueta']),
              default='birefnet', show_default=True,
              help='Background-removal model (birefnet=best edges [default], isnet=~14x faster).')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output PNG path (default: <image>.cutout.png).')
@click.option('--alpha-matting', is_flag=True,
              help='Refine soft / hairy edges (slower; good for birefnet + portraits).')
@click.option('--to-library', is_flag=True,
              help='Also add the cutout to the global picture library (tagged "cutout").')
def cutout(image, model, output, alpha_matting, to_library):
    """Remove an image background -> transparent RGBA PNG cutout.

    IMAGE is the source photo/frame. First use of a model downloads its weights once.

    Examples:

        nolan cutout photo.jpg

        nolan cutout portrait.jpg -m birefnet --alpha-matting

        nolan cutout frame.png -o subject.png --to-library
    """
    from nolan.cutout import cutout_file

    src = Path(image)
    extra = ' + alpha-matting' if alpha_matting else ''
    click.echo(f"Cutout: {src.name}  (model={model}{extra})")
    out = cutout_file(src, output, model=model, alpha_matting=alpha_matting)
    click.echo(f"  -> {out}")

    if to_library:
        try:
            from nolan.imagelib import ImageLibrary
            lib = ImageLibrary("global")
            lib.add_file(str(out), source="cutout", tags=["cutout", model],
                         describe=False)
            click.echo("  added to picture library (global)")
        except Exception as e:
            click.echo(f"  [warn] library add failed: {e}")


@main.command('broll')
@click.argument('line')
@click.option('--operator', '-op', type=click.Choice(['tonal', 'literal', 'conceptual', 'ironic', 'trait', 'relational', 'scale', 'knowledge', 'auto']),
              default='tonal', help='Pairing operator (auto = agent picks).')
@click.option('--theme', default='dark-editorial', help='Count-up theme for the scale operator (styles number/caption).')
@click.option('--mode', '-m', type=click.Choice(['stock', 'library', 'generate']), default='stock',
              help='Asset source: stock / your indexed library / Krea-2 generation.')
@click.option('--period', default='', help='Story period (enables the anachronism gate).')
@click.option('--locale', default='', help='Story locale (enables the wrong-culture gate).')
@click.option('--literalness', '-l', type=float, default=0.25, help='0=abstract … 1=literal.')
@click.option('--mood', default=None, help='Mood steer (tonal).')
@click.option('--media', multiple=True, type=click.Choice(['video', 'image']), help='Asset types (default both).')
@click.option('--gen-style', default='Fooocus Cinematic', help='Fooocus style for generate mode.')
@click.option('--project', '-p', default=None, help='Project scope + ScriptContext (whole-script context).')
@click.option('--beat', type=int, default=None, help='Beat index in the project script (context-aware search).')
@click.option('--output', '-o', type=click.Path(), default=None, help='Write the full result as JSON.')
@click.option('--render', is_flag=True, help='Render the top pick(s) with their recommended motion to mp4.')
@click.option('--out-dir', type=click.Path(), default='broll_out', help='Output dir for --render.')
@click.pass_context
def broll(ctx, line, operator, mode, theme, period, locale, literalness, mood, media, gen_style, project, beat, output, render, out_dir):
    """Narrative→asset b-roll pairing for a narration LINE.

    Finds b-roll that carries the line's meaning via a pairing OPERATOR, from stock / your
    library / Krea-2 generation, gates on period/locale, abstains when nothing fits, and
    recommends a motion for each pick. `--render` turns the recommended motion into mp4.

    Examples:

      nolan broll "a lone figure watches the sea at dusk, full of grief"

      nolan broll "he maneuvered and waited for them to overextend" -op conceptual

      nolan broll "they toasted profits while the people queued for food" -op relational --render
    """
    import asyncio
    import json
    config = ctx.obj['config']
    from nolan.evoke_broll import EvokeBrollSearch

    searcher = EvokeBrollSearch(config=config, progress=lambda f, m: click.echo(f"  [{f:.2f}] {m}", err=True))
    r = asyncio.run(searcher.search(
        line, operator=operator, mode=mode, period=period, locale=locale, literalness=literalness,
        mood=mood, media=(list(media) or None), gen_style=gen_style, project=project, beat=beat))

    click.echo(f"\n{r['status']}  ·  {operator}/{mode}  ·  {r.get('goal_label', 'goal')}: {r.get('goal', '')}")
    if r.get('quantity'):
        q = r['quantity']
        click.echo(f"  count-up: {q.get('prefix', '')}{q.get('display') or q.get('value')}{q.get('suffix', '')} — {q.get('caption', '')}")
    if r['status'] == 'UNMATCHED' and r.get('reason'):
        click.echo(f"  reason: {r['reason']}")

    def _show(c):
        mo = c.get('motion') or {}
        loc = c.get('video_name') or c.get('source') or ''
        click.echo(f"  - [{c.get('kind')}] fit={c.get('mood')} 2nd={c.get('nonliteral')}  "
                   f"motion={mo.get('id')}  {loc}")
        if c.get('why'):
            click.echo(f"      {c['why']}")
        click.echo(f"      {c.get('url', '')}")

    if r.get('sides'):
        click.echo(f"  synthesis: {r.get('synthesis', '')}")
        for s in r['sides']:
            click.echo(f"\n  SIDE '{s['label']}': {len(s['picks'])} pick(s)")
            for c in s['picks']:
                _show(c)
    else:
        for c in r['picks']:
            _show(c)

    if output:
        Path(output).write_text(json.dumps(r, indent=2, default=str), encoding='utf-8')
        click.echo(f"\n-> {output}")

    if render:
        _broll_render(r, Path(out_dir), theme=theme)


def _broll_localize_img(src, outdir):
    """Resolve a pick's still (served /broll-gen path or remote URL) to a local jpg for rendering."""
    import hashlib
    import io
    from PIL import Image
    from nolan.evoke_broll import GEN_DIR
    from nolan.image_search import ImageScorer
    if src.startswith('/broll-gen/'):
        return GEN_DIR / src.split('/broll-gen/', 1)[1]
    data = ImageScorer()._download_image(src)
    if not data:
        return None
    out = Path(outdir) / f"src_{hashlib.md5(src.encode()).hexdigest()[:10]}.jpg"
    Image.open(io.BytesIO(data)).convert('RGB').save(out, 'JPEG', quality=90)
    return out


def _broll_render(r, out_dir, theme='dark-editorial'):
    """Render the recommended motion for image picks (or split-screen / scale count-up) to mp4."""
    from nolan.still_motion import render_still, render_split, render_stat_over
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if r.get('quantity') and r.get('picks'):
        q = r['quantity']
        for i, c in enumerate(r['picks']):
            src = c.get('poster') or c.get('url')
            li = _broll_localize_img(src, out_dir) if src else None
            if li:
                o = render_stat_over(str(li), q['value'], out_dir / f'stat{i}.mp4',
                                     prefix=q.get('prefix', ''), suffix=q.get('suffix', ''),
                                     caption=q.get('caption', ''), decimals=int(q.get('decimals', 0)),
                                     theme=theme, duration=5.0)
                click.echo(f"  rendered count-up ({theme}) -> {o}")
        return
    if r.get('sides'):
        pa = r['sides'][0]['picks'][0] if r['sides'][0]['picks'] else None
        pb = r['sides'][1]['picks'][0] if len(r['sides']) > 1 and r['sides'][1]['picks'] else None
        if pa and pb:
            la, lb = _broll_localize_img(pa['url'], out_dir), _broll_localize_img(pb['url'], out_dir)
            if la and lb:
                o = render_split(str(la), str(lb), out_dir / 'split.mp4', 4.0,
                                 r['sides'][0]['label'], r['sides'][1]['label'])
                click.echo(f"  rendered split-screen -> {o}")
        return
    for i, c in enumerate(r['picks']):
        if c.get('kind') == 'image' and c.get('url'):
            li = _broll_localize_img(c['url'], out_dir)
            if li:
                mid = (c.get('motion') or {}).get('id', 'ken-burns-in')
                o = render_still(str(li), mid, out_dir / f'pick{i}_{mid}.mp4', 4.0)
                click.echo(f"  rendered {mid} -> {o}")


@main.command('acquire-review')
@click.argument('project')
@click.option('--brains', default='engine', help='Comma list: engine,plan,agent (large-context brains).')
@click.option('--beats', default=None, help='Comma list of beat indices (default: all beats).')
@click.option('--media', multiple=True, type=click.Choice(['image', 'video']), help='Asset types (default image).')
@click.option('--agent', default='nolan4', help='NOLAN tmux agent for the agent brain.')
def acquire_review(project, brains, beats, media, agent):
    """Beat-by-beat asset acquisition with full project context — saves the TOP-5 + tags per beat
    (regardless of match) and renders a review gallery. Compare brains: engine / plan / agent.

      nolan acquire-review homer --brains engine,plan,agent
    """
    import asyncio
    from nolan.asset_review import run_review
    br = tuple(b.strip() for b in brains.split(',') if b.strip())
    bt = [int(x) for x in beats.split(',')] if beats else None
    r = asyncio.run(run_review(project, brains=br, beats=bt, media=(list(media) or None),
                               agent=agent, progress=lambda f, m: click.echo(f'[{f:.2f}] {m}')))
    click.echo(f"\ndone — {len(r['beats'])} beats · brains {r['brains']}")
    click.echo(f"gallery: /broll-gen/asset_review_{project}.html  (also projects/{project}/asset_review.json)")


if __name__ == '__main__':
    main()
