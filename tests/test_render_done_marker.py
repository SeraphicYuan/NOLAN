"""R1 (post-mortem): hf-finish writes a completion sentinel so a DETACHED run is observable via a
file, not via the render's chrome-exit (which hangs on orphaned headless procs).

The sentinel MOVED. It was `renders/.done` containing `{"comp": ..., "rendered": true}` — a boolean,
which could say "a render finished" but never "does that file reflect the current specs?". It is now
`renders/render.json`, which carries the deliverable's name and a per-frame fingerprint, so staleness
is a comparison instead of a memory. Keeping both would be two staleness markers for one decision
(WIRING_CHECKLIST #4), so the manifest ABSORBS `.done` — but a legacy `.done` still reads as complete
for comps rendered before the change.

This test pins the ORIGINAL R1 intent — cleared before a run, written after, discoverable as a file —
against the new sentinel.
"""
import json


def test_the_sentinel_is_cleared_before_a_run_and_written_after(tmp_path):
    from nolan.hyperframes import manifest as M
    from nolan.hyperframes.finish import _clear_render_done, _mark_render_done, _render_done_path

    p = _render_done_path(tmp_path)
    assert p == tmp_path / "renders" / M.MANIFEST

    # a stale sentinel from a previous run is cleared before a fresh render (can't false-fire a watcher)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stale")
    _clear_render_done(tmp_path)
    assert not p.exists()
    assert M.is_done(tmp_path) is False

    # a successful finish writes it back, recording the comp AND what was rendered
    out = _mark_render_done(tmp_path, "the-comp", mode="incremental")
    assert out == p and p.exists()
    man = json.loads(p.read_text(encoding="utf-8"))
    assert man["comp"] == "the-comp" and man["deliverable"] == M.DELIVERABLE
    assert man["mode"] == "incremental" and man["rendered_at"]
    assert M.is_done(tmp_path) is True


def test_a_legacy_done_still_reads_as_complete(tmp_path):
    """Comps rendered before the manifest must not look unfinished."""
    from nolan.hyperframes import manifest as M
    (tmp_path / "renders").mkdir(parents=True)
    (tmp_path / "renders" / ".done").write_text('{"comp":"old","rendered":true}', encoding="utf-8")
    assert M.is_done(tmp_path) is True


def test_writing_the_manifest_retires_the_boolean(tmp_path):
    from nolan.hyperframes import manifest as M
    (tmp_path / "renders").mkdir(parents=True)
    (tmp_path / "renders" / ".done").write_text('{"comp":"old","rendered":true}', encoding="utf-8")
    M.write("the-comp", tmp_path, mode="whole")
    assert not (tmp_path / "renders" / ".done").exists(), "one sentinel, not two"


def test_an_unenumerable_comp_still_gets_its_completion_signal(tmp_path):
    """A render SUCCEEDED. Failing to enumerate frames afterwards must not lose that fact — the
    detached watcher would hang forever on a run that actually finished."""
    from nolan.hyperframes import manifest as M
    man = M.write("no-such-comp", tmp_path, mode="whole")
    assert man["frames"] == {} and M.is_done(tmp_path) is True
