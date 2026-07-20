"""Script review-loop commands (``nolan scriptgen …``) — the headless entry points
for the review→revise loop (docs/SCRIPT_REVIEW_PROGRAM.md, Phase 1).

- ``review <slug>``  — write the diagnose-only critic brief for the current draft.
- ``revise <slug>``  — write the brief that applies approved findings → next draft.
- ``gate <slug>``    — run the deterministic script gate and print the report.
- ``archetype <slug> [id]`` — show / set the review archetype (typed rubric).

The review/revise briefs are markdown task files a fleet agent executes; these commands
prepare and print them (dispatch is via the hub). The gate is fully local.
"""

import click

from ._root import main


@main.group()
def scriptgen():
    """Grounded-script review→revise loop + gate."""


def _store():
    from pathlib import Path
    from nolan.scriptwriter import ScriptProjectStore
    return ScriptProjectStore(Path("projects"))


@scriptgen.command("review")
@click.argument("slug")
@click.option("--archetype", help="Override the review archetype (typed rubric).")
@click.option("--question", "questions", multiple=True,
              help="Ad-hoc question appended to the rubric (repeatable).")
@click.option("--show/--no-show", default=True, help="Print the brief to stdout.")
def review_cmd(slug, archetype, questions, show):
    """Write the fresh-eyes critique brief for SLUG's current draft."""
    from nolan.scriptwriter import review_task
    store = _store()
    if not store.exists(slug):
        raise click.ClickException(f"script project not found: {slug}")
    if archetype:
        store.set_review_archetype(slug, archetype)
    if questions:
        store.set_ad_hoc_questions(slug, list(questions))

    num, _ = store.current_draft(slug)
    if not num:
        raise click.ClickException("no draft yet — run the draft/v3 phase first.")
    brief = review_task(slug, store)
    path = store.scriptgen_dir(slug) / "review_task.md"
    path.write_text(brief, encoding="utf-8")
    click.echo(f"Review brief → {path}  (archetype: {store.resolve_archetype(slug)}, "
               f"draft #{num})")
    if show:
        click.echo("\n" + brief)


@scriptgen.command("revise")
@click.argument("slug")
@click.option("--show/--no-show", default=True, help="Print the brief to stdout.")
def revise_cmd(slug, show):
    """Write the brief that applies approved findings → the next draft of SLUG."""
    from nolan.scriptwriter import revise_task
    store = _store()
    if not store.exists(slug):
        raise click.ClickException(f"script project not found: {slug}")
    num, _ = store.current_draft(slug)
    if not num:
        raise click.ClickException("no draft to revise.")
    brief = revise_task(slug, store)
    path = store.scriptgen_dir(slug) / "revise_task.md"
    path.write_text(brief, encoding="utf-8")
    click.echo(f"Revise brief → {path}  (draft #{num} → #{num + 1})")
    if show:
        click.echo("\n" + brief)


@scriptgen.command("gate")
@click.argument("slug")
@click.option("--draft", "draft_name", default=None, help="Gate a specific draft file name.")
def gate_cmd(slug, draft_name):
    """Run the deterministic script gate on SLUG's current (or named) draft."""
    from nolan.scriptwriter.gate import run_gate
    store = _store()
    if not store.exists(slug):
        raise click.ClickException(f"script project not found: {slug}")
    report = run_gate(slug, store=store, draft_name=draft_name)
    click.echo(report.summary())
    if not report.ok:
        raise SystemExit(1)


@scriptgen.command("spine")
@click.argument("slug")
@click.option("--structure", help="Structure id (single/chronological/braided/…). Omit to list.")
@click.option("--thread", "threads", multiple=True, help="A thread one-liner (repeatable).")
@click.option("--binding", default="", help="How the threads cohere into one through-line.")
def spine_cmd(slug, structure, threads, binding):
    """Show or set SLUG's composite spine (Phase 2). No --structure lists the choices."""
    from nolan.scriptwriter.spine_structures import STRUCTURES
    store = _store()
    if not store.exists(slug):
        raise click.ClickException(f"script project not found: {slug}")
    if not structure:
        cur = store.get(slug).get("composite_spine") or {}
        click.echo(f"current: {cur.get('structure') or 'single'}"
                   + (f" · {len(cur.get('threads') or [])} threads" if cur else "") + "\n")
        for sid, s in STRUCTURES.items():
            rng = "1" if s.max_threads == 1 else f"{s.min_threads}-{s.max_threads}"
            click.echo(f"  {sid:<28} [{rng} threads] {s.when_to_use}")
        return
    try:
        store.set_composite_spine(slug, structure, list(threads), binding)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f"spine set: {structure} · {len(threads)} thread(s)")


@scriptgen.command("ledger")
@click.option("--archetype", help="Scope to one archetype.")
@click.option("--style", "style_id", help="Scope to one style id.")
def ledger_cmd(archetype, style_id):
    """Show the distilled review-learning ledger (approval rates + recurring questions)."""
    from pathlib import Path
    from nolan.scriptwriter import ledger
    d = ledger.distill(Path("projects"), archetype=archetype, style_id=style_id)
    click.echo(f"events: {d['events']}")
    if not d["events"]:
        return
    click.echo("\nby dimension (approved/rejected · rate):")
    for dim, v in sorted(d["by_dim"].items(), key=lambda kv: -kv[1]["approved"]):
        click.echo(f"  {dim:<26} {v['approved']}/{v['rejected']}  rate={v['rate']}")
    if d["ad_hoc_common"]:
        click.echo("\nrecurring ad-hoc questions:")
        for x in d["ad_hoc_common"]:
            click.echo(f"  ×{x['count']}  {x['q']}")


@scriptgen.command("archetype")
@click.argument("slug")
@click.argument("archetype_id", required=False)
def archetype_cmd(slug, archetype_id):
    """Show or set SLUG's review archetype. With no id, lists the choices + the current one."""
    from nolan.scriptwriter.rubrics import ARCHETYPES, get_rubric
    store = _store()
    if not store.exists(slug):
        raise click.ClickException(f"script project not found: {slug}")
    if archetype_id:
        if archetype_id not in ARCHETYPES:
            raise click.ClickException(
                f"unknown archetype '{archetype_id}'. Choices: {', '.join(ARCHETYPES)}")
        store.set_review_archetype(slug, archetype_id)
        click.echo(f"archetype set: {archetype_id}")
        return
    current = store.resolve_archetype(slug)
    click.echo(f"current (resolved): {current}\n")
    for aid, arch in ARCHETYPES.items():
        mark = "→" if aid == current else " "
        dims = len(get_rubric(aid).review_dimensions())
        click.echo(f" {mark} {aid:<20} {dims} review dims — {arch.when_to_use}")
