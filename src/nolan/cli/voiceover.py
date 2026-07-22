"""`nolan voiceover` — generate, retake, and version a project's voiceover (VO).

Fills the gap the review flagged (no dedicated VO command): synthesis was reachable
only via the orchestrator or the webui. All commands operate on a Script Project
(projects/<slug>/script.md) unless --json-project is given for a legacy render project.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from nolan.cli._root import main


def _vo_dir(slug: str) -> Path:
    return Path("projects") / slug / "assets" / "voiceover"


def _resolve_voice(base: Path, config, voice: str | None):
    """(ref_audio, ref_text, voice_id) via the standard ladder (--voice → project.yaml → default)."""
    from nolan.voiceover import resolve_voice_ref
    return resolve_voice_ref(base, config, voice)


@main.group()
def voiceover() -> None:
    """Generate, retake, and version project voiceovers."""


@voiceover.command("generate")
@click.argument("slug")
@click.option("--voice", default=None, help="voice_id to clone (else project.yaml / default)")
@click.option("--mode", type=click.Choice(["full", "segments"]), default="full")
def vo_generate(slug: str, voice: str | None, mode: str) -> None:
    """Synthesize the whole voiceover for a Script Project (archives the prior take)."""
    from nolan.config import load_config
    from nolan.voice_pipeline import synthesize_voiceover
    cfg = load_config()
    ref_audio, ref_text, vid = _resolve_voice(Path("projects") / slug, cfg, voice)
    res = asyncio.run(synthesize_voiceover(
        config=cfg, script_project=slug, mode=mode, voice_id=vid,
        ref_audio=ref_audio, ref_text=ref_text,
        log=click.echo, progress=lambda p, m: click.echo(f"[{p:.0%}] {m}")))
    g = res.get("gate", {})
    click.echo(f"gate ok={g.get('ok')} errors={g.get('errors')} warnings={g.get('warnings')} "
               f"→ {res.get('voiceover') or res.get('dir')}")


@voiceover.command("retake")
@click.argument("slug")
@click.argument("index", type=int)
@click.option("--voice", default=None, help="voice_id (else project.yaml / default)")
@click.option("--text", default=None, help="override the section's text for this take")
@click.option("--delivery", default=None, help="delivery note for this take (e.g. 'somber')")
def vo_retake(slug: str, index: int, voice: str | None, text: str | None,
              delivery: str | None) -> None:
    """Re-synthesize ONE section (a fresh take) and splice it back if it passes the gate."""
    from nolan.config import load_config
    from nolan.voice_pipeline import retake_section
    cfg = load_config()
    ref_audio, ref_text, vid = _resolve_voice(Path("projects") / slug, cfg, voice)
    res = asyncio.run(retake_section(
        config=cfg, script_project=slug, index=index, text=text, delivery=delivery,
        voice_id=vid, ref_audio=ref_audio, ref_text=ref_text,
        log=click.echo, progress=lambda p, m: click.echo(f"[{p:.0%}] {m}")))
    if res.get("accepted"):
        click.echo(f"section {index} retaken ✓ dur={res.get('duration_s')}s "
                   f"captions_invalidated={res.get('captions_invalidated')}")
    else:
        click.echo(f"section {index} retake REJECTED (kept old audio): {res.get('reason')}")


@voiceover.command("takes")
@click.argument("slug")
def vo_takes(slug: str) -> None:
    """List archived full-VO takes (newest first)."""
    from nolan.voice_pipeline import list_takes
    takes = list_takes(_vo_dir(slug))
    if not takes:
        click.echo("(no archived takes)")
        return
    for t in takes:
        click.echo(f"{t['id']}  total={t.get('total_s')}s  mp3={t.get('has_mp3')}")


@voiceover.command("restore")
@click.argument("slug")
@click.argument("take_id")
def vo_restore(slug: str, take_id: str) -> None:
    """Restore a previously-archived take (the current one is archived first)."""
    from nolan.voice_pipeline import restore_take
    ok = restore_take(_vo_dir(slug), take_id)
    click.echo(f"restored {take_id}" if ok else f"take not found: {take_id}")


@voiceover.command("arc")
@click.argument("slug")
@click.option("--apply", "do_apply", is_flag=True,
              help="write the [delivery] markers into script.md (default: dry-run)")
@click.option("--max", "max_marked", type=int, default=None, help="cap on marked beats (~n/3)")
def vo_arc(slug: str, do_apply: bool, max_marked) -> None:
    """P6: assign an emotion arc — the LLM marks the few pivot beats with delivery notes
    (→ CosyVoice instruct). Dry-run by default; --apply writes [delivery: …] into script.md."""
    from nolan.config import load_config
    from nolan.llm import create_text_llm
    from nolan.script import parse_script_sections
    from nolan.emotion_arc import assign_arc, apply_arc_to_script, TONE_REGISTRY
    md_path = Path("projects") / slug / "script.md"
    if not md_path.exists():
        click.echo(f"no script.md for {slug}")
        return
    md = md_path.read_text(encoding="utf-8")
    sections = parse_script_sections(md)
    llm = create_text_llm(load_config())
    deliveries = asyncio.run(assign_arc(sections, generate=llm.generate, max_marked=max_marked))
    marked = [(i, d) for i, d in enumerate(deliveries) if d]
    if not marked:
        click.echo("no pivot beats marked (arc left neutral)")
        return
    for i, d in marked:
        click.echo(f"  beat {i} [{sections[i].get('title')}] → {d}: "
                   f"{TONE_REGISTRY[d].split('—')[0].strip()}")
    if do_apply:
        md_path.write_text(apply_arc_to_script(md, deliveries), encoding="utf-8")
        click.echo(f"✓ wrote {len(marked)} delivery markers to {md_path}")
    else:
        click.echo("(dry-run — re-run with --apply to write the markers)")


@voiceover.command("measure")
@click.argument("slug")
def vo_measure(slug: str) -> None:
    """Print the quality-gate + per-section measurements for the current voiceover."""
    p = _vo_dir(slug) / "voiceover.measure.json"
    if not p.exists():
        click.echo("no voiceover.measure.json — run `nolan voiceover generate` first")
        return
    m = json.loads(p.read_text(encoding="utf-8"))
    click.echo(f"gate ok={m['ok']} errors={m['errors']} warnings={m['warnings']} "
               f"total={m.get('total_s')}s")
    for s in m["sections"]:
        if s.get("present"):
            click.echo(f"  sec {s['index']:>2}: {s['duration_s']}s "
                       f"(exp {s.get('expected_s')}s, Δ{s.get('delta_s')}) "
                       f"rms={s.get('rms_dbfs')}dBFS words={s.get('words')}")
        else:
            click.echo(f"  sec {s['index']:>2}: MISSING")
    for c in m["checks"]:
        click.echo(f"  [{c['level']}] {c['id']} sec={c.get('index')}: {c['message']}")
