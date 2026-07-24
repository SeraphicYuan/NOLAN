"""R1 (post-mortem): hf-finish writes a renders/.done completion sentinel so a DETACHED run is observable
via a file, not via the render's chrome-exit (which hangs on orphaned headless procs)."""
import json


def test_render_done_marker_clear_then_write(tmp_path):
    from nolan.hyperframes.finish import _render_done_path, _clear_render_done, _mark_render_done
    p = _render_done_path(tmp_path)
    assert p == tmp_path / "renders" / ".done"

    # a stale sentinel from a previous run is cleared before a fresh render (can't false-fire a watcher)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stale")
    _clear_render_done(tmp_path)
    assert not p.exists()

    # a successful finish writes it back, recording the comp
    out = _mark_render_done(tmp_path, "the-comp")
    assert out == p and p.exists()
    assert json.loads(p.read_text(encoding="utf-8")) == {"comp": "the-comp", "rendered": True}
