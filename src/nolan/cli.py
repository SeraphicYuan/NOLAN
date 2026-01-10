"""Command-line interface for NOLAN."""

import asyncio
from pathlib import Path

import click

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
@click.option('--whisper/--no-whisper', default=False,
              help='Auto-generate transcripts with Whisper for videos without them.')
@click.option('--whisper-model', default='base',
              type=click.Choice(['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']),
              help='Whisper model size (larger = better quality, slower).')
@click.pass_context
def index(ctx, directory, recursive, frame_interval, whisper, whisper_model):
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

    asyncio.run(_index_videos(config, directory_path, recursive, frame_interval, whisper, whisper_model))


async def _index_videos(config, directory, recursive, frame_interval, whisper_enabled=False, whisper_model='base'):
    """Async implementation of index command."""
    from nolan.indexer import HybridVideoIndexer, VideoIndex
    from nolan.vision import create_vision_provider, VisionConfig
    from nolan.sampler import create_sampler, SamplerConfig, SamplingStrategy
    from nolan.llm import GeminiClient

    # Initialize database
    db_path = Path(config.indexing.database).expanduser()
    index = VideoIndex(db_path)

    # Initialize vision provider
    vision_config = VisionConfig(
        provider=config.vision.provider,
        model=config.vision.model,
        host=config.vision.host,
        port=config.vision.port,
        timeout=config.vision.timeout,
        api_key=config.gemini.api_key if config.vision.provider == "gemini" else None
    )
    vision = create_vision_provider(vision_config)

    # Check vision provider connection
    click.echo(f"\nVision provider: {config.vision.provider} ({config.vision.model})")
    if not await vision.check_connection():
        click.echo(f"Error: Cannot connect to {config.vision.provider}. Is it running?")
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
                whisper_config = WhisperConfig(model_size=whisper_model)
                whisper_transcriber = WhisperTranscriber(whisper_config)
                click.echo(f"Whisper: enabled (model: {whisper_model})")
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
