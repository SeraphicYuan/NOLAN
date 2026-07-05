"""Essay processing pipeline commands (process, script, design).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


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


