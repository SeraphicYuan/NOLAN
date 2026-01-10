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
@click.option('--scene', type=str, help='Generate for a specific scene ID.')
@click.option('--project', '-p', type=click.Path(exists=True), default='./output',
              help='Project directory with scene_plan.json.')
@click.pass_context
def generate(ctx, scene, project):
    """Generate images via ComfyUI for scenes.

    Reads the scene plan and generates images for scenes
    marked as 'generated-image' type.
    """
    config = ctx.obj['config']
    project_path = Path(project)

    click.echo(f"Project: {project_path}")
    if scene:
        click.echo(f"Scene: {scene}")

    asyncio.run(_generate_images(config, project_path, scene))


async def _generate_images(config, project_path, scene_id):
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
        steps=config.comfyui.steps
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


if __name__ == '__main__':
    main()
