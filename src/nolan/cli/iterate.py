"""Scene iteration commands (revise-scene, rerender).

Split verbatim from the legacy monolithic CLI module.
"""

import asyncio
import sys
from pathlib import Path

import click

from ._root import main


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


