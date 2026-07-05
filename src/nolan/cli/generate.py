"""ComfyUI image generation commands (generate, generate-test).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


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

    # Initialize ComfyUI client. With no explicit --workflow file, resolve the
    # configured REGISTRY workflow (default: krea2-style-select) + config style
    # via the workflow registry; explicit --workflow keeps full manual control.
    client = None
    if workflow_path is None and prompt_node is None and not overrides:
        try:
            from nolan.workflow_registry import get_registry
            style = (getattr(config.comfyui, "style", "") or "").strip()
            kw = {}
            if style:
                kw["style"] = style if style.startswith(",") else "," + style
            client, _entry = get_registry().build_client(
                getattr(config.comfyui, "workflow", None), config, **kw)
        except Exception as exc:
            click.echo(f"  (registry workflow unavailable: {exc} — using built-in default)")
            client = None
    if client is None:
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


