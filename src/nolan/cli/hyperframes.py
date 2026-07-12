"""`nolan hf-finish` — run the compose-first HyperFrames finish DAG as one idempotent command."""
import click

from ._root import main


@main.command("hf-finish")
@click.argument("comp")
@click.option("--no-render", is_flag=True, help="stop before the render (assemble + preview, then re-run)")
@click.option("--no-sound", is_flag=True, help="skip the bgm/sfx bed")
@click.option("--dry-run", is_flag=True, help="print the DAG without running it")
def hf_finish_cmd(comp, no_render, no_sound, dry_run):
    """Run the compose-first FINISH DAG for a HyperFrames comp.

    sync-durations → word-sync → recompose → sound → captions → assemble-index →
    assemble_media (+ freeze-heal) → render → hf_qa + style-lint. Idempotent; fails loud.
    """
    from nolan.hyperframes.finish import finish
    try:
        finish(comp, render=not no_render, sound=not no_sound, dry_run=dry_run)
    except RuntimeError as e:
        raise SystemExit(f"✗ {e}")


@main.command("hf-render")
@click.argument("comp")
@click.option("--only", help="comma-separated frame ids to force-re-render (edit just these)")
@click.option("--no-bgm", is_flag=True, help="skip re-laying the BGM bed")
def hf_render_cmd(comp, only, no_bgm):
    """INCREMENTAL final render: re-render only changed frames (content-hash cache) + stitch.

    A one-frame edit costs one frame render + a fast concat, not the whole 10-min monolith.
    """
    from nolan.hyperframes.incremental import render_incremental
    try:
        render_incremental(comp, only=(only.split(",") if only else None), bgm=not no_bgm)
    except RuntimeError as e:
        raise SystemExit(f"✗ {e}")
