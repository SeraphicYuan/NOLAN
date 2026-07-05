"""Video generation commands (video-gen group).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


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


