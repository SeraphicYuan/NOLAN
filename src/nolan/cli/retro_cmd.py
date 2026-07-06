"""`nolan retro` — end-of-project distillation into taste-rule proposals."""

import asyncio
import json
from pathlib import Path

import click

from ._root import main


def _brief_vs_yaml_events(project: Path):
    """Deterministic override capture at retro time: the brief proposed,
    project.yaml (the human) chose differently."""
    from nolan.taste import record_taste_event
    try:
        import yaml
        from nolan.project_brief import load_brief
        brief = load_brief(project) or {}
        meta = yaml.safe_load((project / "project.yaml")
                              .read_text(encoding="utf-8")) or {}
    except Exception:
        return 0
    n = 0
    pairs = [("theme", "theme", "style"), ("music_mood", "music_mood", "soundtrack"),
             ("voice_id", "voice_id", "style")]
    for bkey, ykey, stage in pairs:
        b, y = brief.get(bkey), meta.get(ykey)
        if b and y and str(b) != str(y):
            if record_taste_event(project=project.name, stage=stage,
                                  context=f"project.yaml overrides brief {bkey}",
                                  proposed=b, chose=y, project_path=project):
                n += 1
    return n


@main.command('retro')
@click.argument('project', type=click.Path(exists=True, file_okay=False))
def retro(project):
    """Distill the override ledger into taste-rule PROPOSALS (review on /taste)."""
    from nolan.taste import distill
    project = Path(project)
    n = _brief_vs_yaml_events(project)
    if n:
        click.echo(f"captured {n} brief-vs-yaml override(s)")
    try:
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        llm = create_text_llm(load_config())
    except Exception as exc:
        click.echo(f"no LLM available ({exc}) — ledger updated, no distillation")
        return
    result = asyncio.run(distill(llm))
    if result.get("note"):
        click.echo(result["note"])
    click.echo(f"proposed: {len(result['proposed'])} rule(s) "
               f"(awaiting acceptance on /taste)")
    for r in result["proposed"]:
        click.echo(f"  [{r['id']}] ({r['scope']}/{r['stage']}) {r['rule']}")
    for rej in result["rejected"]:
        click.echo(f"  rejected: {str(rej.get('rule'))[:70]} — {rej['reason']}")
    for ret in result.get("retirements", []):
        click.echo(f"  retirement proposed: {ret.get('rule_id')} — {ret.get('why')}")
