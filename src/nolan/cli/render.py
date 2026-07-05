"""Rendering and assembly commands (infographic, render-infographics, render-clips, render-lottie, assemble, render-flow).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


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
    # Relative -o resolves against the CWD (standard CLI expectation) — it
    # previously resolved against the PLAN's directory, silently writing to
    # <plan_dir>/<relative> while callers believed rc=0 meant success.
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
            raise SystemExit(1)

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
            raise SystemExit(1)

    if not output_path.exists() or output_path.stat().st_size < 1024:
        click.echo(f"ERROR: assembly produced no output at {output_path}")
        raise SystemExit(1)
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


