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


@main.command()
@click.argument('essay', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default='./output',
              help='Output directory for generated files.')
@click.option('--skip-scenes', is_flag=True, help='Skip scene design step.')
@click.option('--skip-assets', is_flag=True, help='Skip asset matching step.')
@click.pass_context
def process(ctx, essay, output, skip_scenes, skip_assets):
    """Process an essay through the full pipeline.

    ESSAY is the path to your markdown essay file.

    This command will:
    1. Convert the essay to a video script
    2. Design visual scenes for each section
    3. Match scenes to your video library
    4. Generate images via ComfyUI (if configured)
    """
    config = ctx.obj['config']
    output_path = Path(output)
    essay_path = Path(essay)

    click.echo(f"Processing: {essay_path.name}")
    click.echo(f"Output: {output_path}")

    asyncio.run(_process_essay(config, essay_path, output_path, skip_scenes, skip_assets))


async def _process_essay(config, essay_path, output_path, skip_scenes, skip_assets):
    """Async implementation of process command."""
    from nolan.parser import parse_essay
    from nolan.script import ScriptConverter
    from nolan.scenes import SceneDesigner
    from nolan.llm import GeminiClient

    # Setup
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "assets" / "generated").mkdir(parents=True, exist_ok=True)
    (output_path / "assets" / "matched").mkdir(parents=True, exist_ok=True)

    # Initialize LLM
    llm = GeminiClient(
        api_key=config.gemini.api_key,
        model=config.gemini.model
    )

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
@click.option('--output', '-o', type=click.Path(), default='./output',
              help='Output directory for generated files.')
@click.pass_context
def script(ctx, essay, output):
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
    output_path = Path(output)
    essay_path = Path(essay)

    click.echo(f"Converting: {essay_path.name}")
    click.echo(f"Output: {output_path}")

    asyncio.run(_convert_script(config, essay_path, output_path))


async def _convert_script(config, essay_path, output_path):
    """Async implementation of script command."""
    from nolan.parser import parse_essay
    from nolan.script import ScriptConverter
    from nolan.llm import GeminiClient

    # Setup
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize LLM
    llm = GeminiClient(
        api_key=config.gemini.api_key,
        model=config.gemini.model
    )

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
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Output directory (defaults to same as script file).')
@click.pass_context
def design(ctx, script_file, output):
    """Design visual scenes from a script.

    SCRIPT_FILE is the path to script.json (from 'nolan script' command).

    This command will:
    1. Load the narration script
    2. Design visual scenes for each section using AI
    3. Output scene_plan.json with visual specifications

    Each scene includes:
    - Visual type (b-roll, infographic, generated-image, etc.)
    - Search queries for stock footage
    - AI image generation prompts
    - Animation hints and sync points
    """
    config = ctx.obj['config']
    script_path = Path(script_file)

    # Default output to script file's directory
    if output is None:
        output_path = script_path.parent
    else:
        output_path = Path(output)

    click.echo(f"Designing scenes from: {script_path.name}")
    click.echo(f"Output: {output_path}")

    asyncio.run(_design_scenes(config, script_path, output_path))


async def _design_scenes(config, script_path, output_path):
    """Async implementation of design command."""
    from nolan.script import Script
    from nolan.scenes import SceneDesigner
    from nolan.llm import GeminiClient

    # Setup
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize LLM
    llm = GeminiClient(
        api_key=config.gemini.api_key,
        model=config.gemini.model
    )

    # Step 1: Load script
    click.echo("\n[1/2] Loading script...")
    script = Script.load_json(str(script_path))
    click.echo(f"  Sections: {len(script.sections)}")
    click.echo(f"  Duration: {script.total_duration:.0f}s")

    # Step 2: Design scenes
    click.echo("\n[2/2] Designing scenes...")
    designer = SceneDesigner(llm)
    plan = await designer.design_full_plan(script.sections)

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
@click.argument('directory', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True,
              help='Scan subdirectories.')
@click.option('--frame-interval', default=5, type=int,
              help='Seconds between sampled frames.')
@click.option('--vision', default='ollama',
              type=click.Choice(['ollama', 'gemini']),
              help='Vision provider for frame analysis.')
@click.option('--whisper/--no-whisper', default=False,
              help='Auto-generate transcripts with Whisper for videos without them.')
@click.option('--whisper-model', default='base',
              type=click.Choice(['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']),
              help='Whisper model size (larger = better quality, slower).')
@click.pass_context
def index(ctx, directory, recursive, frame_interval, vision, whisper, whisper_model):
    """Index a video directory for asset matching.

    DIRECTORY is the path to your video library folder.

    This scans video files, samples frames, and uses AI to describe
    what's in each segment. The index is stored locally for fast
    searching during the process command.

    Use --whisper to auto-generate transcripts for videos without them.
    This requires ffmpeg to be installed for audio extraction.
    """
    config = ctx.obj['config']
    directory_path = Path(directory)

    click.echo(f"Indexing: {directory_path}")
    click.echo(f"Recursive: {recursive}")
    click.echo(f"Frame interval: {frame_interval}s")

    asyncio.run(_index_videos(config, directory_path, recursive, frame_interval, vision, whisper, whisper_model))


async def _index_videos(config, directory, recursive, frame_interval, vision_provider='ollama', whisper_enabled=False, whisper_model='base'):
    """Async implementation of index command."""
    from nolan.indexer import HybridVideoIndexer, VideoIndex
    from nolan.vision import create_vision_provider, VisionConfig
    from nolan.sampler import create_sampler, SamplerConfig, SamplingStrategy
    from nolan.llm import GeminiClient

    # Initialize database
    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    # Determine vision model based on provider
    if vision_provider == "gemini":
        vision_model = "gemini-3-flash-preview"
        api_key = config.gemini.api_key
    else:
        vision_model = config.vision.model
        api_key = None

    # Initialize vision provider
    vision_config = VisionConfig(
        provider=vision_provider,
        model=vision_model,
        host=config.vision.host,
        port=config.vision.port,
        timeout=config.vision.timeout,
        api_key=api_key
    )
    vision = create_vision_provider(vision_config)

    # Check vision provider connection
    click.echo(f"\nVision provider: {vision_provider} ({vision_model})")
    if not await vision.check_connection():
        click.echo(f"Error: Cannot connect to {vision_provider}. Is it running?")
        return

    # Initialize sampler
    sampler_config = SamplerConfig(
        strategy=SamplingStrategy(config.indexing.sampling_strategy),
        fixed_interval=float(frame_interval),
        min_interval=config.indexing.min_interval,
        max_interval=config.indexing.max_interval,
        scene_threshold=config.indexing.scene_threshold,
    )
    sampler = create_sampler(sampler_config)
    click.echo(f"Sampling strategy: {config.indexing.sampling_strategy}")

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
    if config.indexing.enable_inference and config.gemini.api_key:
        llm = GeminiClient(
            api_key=config.gemini.api_key,
            model=config.gemini.model
        )
        click.echo("Inference: enabled (using Gemini)")
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
        enable_inference=config.indexing.enable_inference
    )

    def progress(current, total, message):
        click.echo(f"  [{current}/{total}] {message}")

    click.echo("\nScanning for videos...")
    stats = await indexer.index_directory(directory, recursive=recursive, progress_callback=progress)

    click.echo(f"\nIndexing complete:")
    click.echo(f"  Videos found: {stats['total']}")
    click.echo(f"  Newly indexed: {stats['indexed']}")
    click.echo(f"  Skipped (unchanged): {stats['skipped']}")
    click.echo(f"  Segments added: {stats['segments']}")
    click.echo(f"\nDatabase: {db_path}")


@main.command()
@click.option('--project', '-p', type=click.Path(exists=True), default='./output',
              help='Project output directory to view.')
@click.option('--host', default='127.0.0.1', help='Server host.')
@click.option('--port', default=8000, type=int, help='Server port.')
def serve(project, host, port):
    """Launch the viewer to review pipeline outputs.

    Opens a browser to view your script, scene plan, and assets.
    """
    from nolan.viewer import run_server

    project_path = Path(project)
    click.echo(f"Serving: {project_path}")
    click.echo(f"Opening: http://{host}:{port}")

    run_server(project_path, host=host, port=port)


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

    # Determine output path
    if output_path is None:
        output_path = 'library_export.json'
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
@click.option('--refine/--no-refine', default=False,
              help='Use LLM to detect story boundaries within clusters (slower but more accurate).')
@click.option('--max-gap', default=2.0, type=float,
              help='Maximum time gap (seconds) between segments to consider clustering.')
@click.pass_context
def cluster(ctx, video, output, cluster_all, summarize, refine, max_gap):
    """Cluster video segments into story moments.

    VIDEO is the path to an indexed video file.

    Clustering groups continuous segments that share:
    - Same characters/people
    - Same location
    - Related story context

    Examples:
        nolan cluster video.mp4 -o clusters.json
        nolan cluster --all -o all_clusters.json
        nolan cluster video.mp4 --refine  # Use LLM for better boundaries
    """
    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()

    if not db_path.exists():
        click.echo(f"Error: Database not found at {db_path}")
        click.echo("Run 'nolan index' first to index videos.")
        return

    if cluster_all:
        asyncio.run(_cluster_all_videos(config, db_path, output, summarize, refine, max_gap))
    elif video:
        asyncio.run(_cluster_video(config, db_path, Path(video), output, summarize, refine, max_gap))
    else:
        click.echo("Error: Provide a VIDEO path or use --all flag.")


async def _cluster_video(config, db_path, video_path, output_path, summarize, refine, max_gap):
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
    click.echo(f"Created {len(clusters)} clusters")

    # Refine with LLM story boundary detection
    if refine and config.gemini.api_key:
        click.echo("Refining clusters with LLM story boundary detection...")
        from nolan.llm import GeminiClient
        llm = GeminiClient(api_key=config.gemini.api_key, model=config.gemini.model)
        detector = StoryBoundaryDetector(llm)
        clusters = await detector.refine_clusters(clusters)
        click.echo(f"Refined to {len(clusters)} clusters")

    # Generate summaries
    if summarize and config.gemini.api_key:
        click.echo("Generating cluster summaries...")
        from nolan.llm import GeminiClient
        llm = GeminiClient(api_key=config.gemini.api_key, model=config.gemini.model)
        analyzer = ClusterAnalyzer(llm)
        clusters = await analyzer.analyze_clusters(clusters)

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


async def _cluster_all_videos(config, db_path, output_path, summarize, refine, max_gap):
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
    if (summarize or refine) and config.gemini.api_key:
        from nolan.llm import GeminiClient
        llm = GeminiClient(api_key=config.gemini.api_key, model=config.gemini.model)

    output = {'videos': []}

    for video_path in videos:
        click.echo(f"\nProcessing: {Path(video_path).name}")
        segments = index.get_segments(video_path)

        if not segments:
            click.echo("  No segments found, skipping")
            continue

        # Cluster
        clusters = cluster_segments(segments, max_gap=max_gap)
        click.echo(f"  Created {len(clusters)} clusters from {len(segments)} segments")

        # Refine
        if refine and llm:
            detector = StoryBoundaryDetector(llm)
            clusters = await detector.refine_clusters(clusters)

        # Summarize
        if summarize and llm:
            analyzer = ClusterAnalyzer(llm)
            clusters = await analyzer.analyze_clusters(clusters)

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

    # Save
    if output_path is None:
        output_path = 'library_clusters.json'
    output_path = Path(output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_clusters = sum(len(v['clusters']) for v in output['videos'])
    click.echo(f"\nExported {len(videos)} videos ({total_clusters} clusters) to {output_path}")


@main.command()
@click.option('--host', default='127.0.0.1', help='Server host.')
@click.option('--port', default=8001, type=int, help='Server port.')
@click.pass_context
def browse(ctx, host, port):
    """Browse your indexed video library in a web UI.

    Opens a browser to explore indexed videos, segments, and clusters.
    Search across all segments and preview videos at specific timestamps.

    Requires running 'nolan index' first to populate the library.
    """
    from nolan.library_viewer import run_library_server

    config = ctx.obj['config']
    db_path = Path(config.indexing.database).expanduser()

    if not db_path.exists():
        click.echo(f"Error: Database not found at {db_path}")
        click.echo("Run 'nolan index <folder>' first to index videos.")
        return

    click.echo(f"Database: {db_path}")
    click.echo(f"Opening: http://{host}:{port}")

    run_library_server(db_path, host=host, port=port)


@main.command()
@click.option('--scene', type=str, help='Generate for a specific scene ID.')
@click.option('--project', '-p', type=click.Path(exists=True), default='./output',
              help='Project directory with scene_plan.json.')
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


async def _generate_images(config, project_path, scene_id, workflow_path=None, prompt_node=None, overrides=None):
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
            if s.visual_type == "generated-image" and not s.skip_generation:
                scenes_to_generate.append(s)

    if not scenes_to_generate:
        click.echo("No scenes to generate.")
        return

    click.echo(f"\nGenerating {len(scenes_to_generate)} images...")

    for s in scenes_to_generate:
        click.echo(f"\n  {s.id}: {s.comfyui_prompt[:50]}...")
        output_path = output_dir / f"{s.id}.png"

        try:
            await client.generate(s.comfyui_prompt, output_path)
            s.generated_asset = f"{s.id}.png"
            click.echo(f"    Saved: {output_path}")
        except Exception as e:
            click.echo(f"    Error: {e}")

    # Save updated plan
    plan.save(str(plan_path))
    click.echo(f"\nScene plan updated: {plan_path}")


@main.command('generate-test')
@click.argument('prompt')
@click.option('--output', '-o', type=click.Path(), default='./test_output.png',
              help='Output path for generated image.')
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
@click.option('--project', '-p', type=click.Path(exists=True), default='./output',
              help='Project directory with scene_plan.json.')
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
    """
    asyncio.run(_render_infographics(project, host, port, engine_mode, force))


async def _render_infographics(project, host, port, engine_mode, force):
    """Async implementation of render-infographics."""
    import shutil
    from pathlib import Path
    from nolan.scenes import ScenePlan
    from nolan.infographic_client import InfographicClient, Engine

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

        click.echo(f"Rendering {scene.id} ({template}, {theme})...")

        try:
            job = await client.submit(
                engine=Engine.INFOGRAPHIC,
                data=data,
                template=template,
                theme=theme,
                engine_mode=engine_mode,
            )

            completed = await client.wait_for_completion(job.job_id)
            output_path = Path(completed.video_path)
            if not output_path.exists():
                click.echo(f"  Failed: output not found for {scene.id}")
                continue

            dest = output_dir / f"{scene.id}.svg"
            shutil.copy(output_path, dest)
            scene.infographic_asset = f"infographics/{dest.name}"
            rendered += 1
        except Exception as e:
            click.echo(f"  Error rendering {scene.id}: {e}")

    plan.save(str(plan_path))
    click.echo(f"Rendered {rendered} infographic(s). Scene plan updated.")


@main.command('image-search')
@click.argument('query')
@click.option('--source', '-s', type=click.Choice(['ddgs', 'pexels', 'pixabay', 'wikimedia', 'smithsonian', 'loc', 'all']),
              default='ddgs', help='Image source to search.')
@click.option('--output', '-o', type=click.Path(), default='./image_search_results.json',
              help='Output JSON file for results.')
@click.option('--max-results', '-n', type=int, default=10,
              help='Maximum number of results per source.')
@click.option('--score/--no-score', default=False,
              help='Score images by relevance using vision model.')
@click.option('--vision', type=click.Choice(['gemini', 'ollama']),
              default='gemini', help='Vision provider for scoring.')
@click.option('--context', '-c', type=str, default=None,
              help='Additional context for scoring (e.g., "for a documentary about history").')
@click.pass_context
def image_search(ctx, query, source, output, max_results, score, vision, context):
    """Search for images from various sources.

    QUERY is the search term for finding images.

    Sources:
      - ddgs: DuckDuckGo image search (no API key needed)
      - pexels: Pexels stock photos (requires PEXELS_API_KEY)
      - pixabay: Pixabay stock photos (requires PIXABAY_API_KEY)
      - wikimedia: Wikimedia Commons (no API key needed, public domain)
      - smithsonian: Smithsonian Open Access (requires SMITHSONIAN_API_KEY, CC0)
      - loc: Library of Congress (no API key needed, public domain)
      - all: Search all available sources

    Scoring:
      Use --score to rank images by relevance using a vision model.
      Use --vision to choose between 'gemini' or 'ollama' for scoring.

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

        # Score images if requested
        if score:
            click.echo(f"\nScoring images with {vision}...")

            # Configure vision provider
            if vision == "gemini":
                vision_config = {"api_key": config.gemini.api_key}
            else:  # ollama
                vision_config = {
                    "host": config.vision.host,
                    "port": config.vision.port,
                    "model": config.vision.model,
                }

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


if __name__ == '__main__':
    main()
