"""Pipeline orchestration commands (orchestrate, build-from-segment).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


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
@click.option('--redo', type=str, default=None,
              help='Reset ONE step (history + gating artifact) and run it '
                   'now. Destructive for authoring steps — redoing '
                   'script_to_scenes regenerates the plan from scratch.')
@click.pass_context
def orchestrate(ctx, project, auto, refine, target, redo):
    """Run the two-layer Director on a project folder.

    Default mode: advance the pipeline by one step (run_next_step).
    --auto mode: run all pending steps in sequence until done or error.
    --refine mode: re-run a completed step against the latest feedback file.
    """
    from nolan.orchestrator.director import (
        DirectorError, run_auto_sync, run_refine_sync, run_sync,
    )

    if sum(map(bool, (auto, refine, redo))) > 1:
        click.echo("Error: --auto, --refine and --redo are mutually exclusive.", err=True)
        ctx.exit(2)

    project_path = Path(project)

    try:
        if redo:
            from nolan.orchestrator.director import Director
            for note in Director(project_path).redo_step(redo):
                click.echo(note)
            checkpoint_path = run_sync(project_path)
            click.echo(f"Checkpoint written: {checkpoint_path}")
            click.echo(f"'{redo}' re-ran. Review and re-run to advance.")
        elif refine:
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


