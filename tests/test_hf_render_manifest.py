"""The deliverable has ONE name, ONE resolver, and a computable staleness.

INCIDENT (measured, 2026-08-03). `render_incremental` defaulted to `renders/<comp>.mp4` while
`finish.py` passed `out=renders/video.mp4` — one function, two names, and nothing marking which was
the deliverable. Across the lab that left 2-4 top-level mp4s per comp. Then BOTH QA gates resolved
their input with `sorted(rd.glob("*.mp4"))[0]` — alphabetically first — and almost every composition
id sorts before "video", so the perceptual and temporal gates were scoring a file nobody ships:

    homer-hf                -> homer-hf-sfx-preview.mp4   (an SFX *preview*)
    aeneid-essay            -> aeneid-essay.mp4
    ai-datacenter-debate-v5 -> v46.mp4
    the-openai-debate       -> the-openai-debate.mp4

A gate that reports on the wrong artifact is a FALSE NEGATIVE — a bad render passes because a good
preview scored — which is worse than no gate at all.

And `renders/.done` was `{"comp": ..., "rendered": true}`: a boolean where a comparison is needed.
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import manifest as M              # noqa: E402


@pytest.fixture()
def comp():
    name = "_hf_manifest_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    for i, fid in enumerate(("01-alpha", "02-beta"), 1):
        (fdir / f"{fid}.spec.json").write_text(json.dumps({"frames": [{"id": fid, "dur": 5.0, "scenes": [
            {"id": f"s{i}", "type": "statement", "start": 0, "dur": 5,
             "data": {"lines": [f"line {i}"]}}]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "renders").mkdir()
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def _cd(comp):
    from nolan.hyperframes.edit import _comp_dir
    return _comp_dir(comp)


# --- the resolver ---------------------------------------------------------------------------------

def test_no_module_resolves_the_render_by_globbing():
    """The fork that caused this: two modules each kept a private `sorted(glob("*.mp4"))[0]`.

    Asserted over the AST, not the text — the modules now *describe* the old bug in their docstrings,
    and a substring check matched the prose that documents the fix. A test that a comment can fail is
    a test that gets deleted."""
    import ast
    import inspect
    from nolan.hyperframes import render_gate, temporal_gate
    for mod in (render_gate, temporal_gate):
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "glob"):
                lit = [a.value for a in node.args if isinstance(a, ast.Constant)]
                assert "*.mp4" not in lit, f"{mod.__name__} still globs for the deliverable"
        assert "from .manifest import deliverable" in inspect.getsource(mod), \
            f"{mod.__name__} must ask the manifest"


def test_a_decoy_mp4_does_not_win(comp):
    """`aaa.mp4` sorts first. Under the old resolver it WAS the answer."""
    rd = _cd(comp) / "renders"
    (rd / "aaa-preview.mp4").write_bytes(b"decoy")
    (rd / M.DELIVERABLE).write_bytes(b"real")
    M.write(comp, _cd(comp), mode="incremental")
    assert M.deliverable(_cd(comp)).name == M.DELIVERABLE

    from nolan.hyperframes.render_gate import _render_mp4 as g1
    from nolan.hyperframes.temporal_gate import _render_mp4 as g2
    assert g1(_cd(comp)).name == M.DELIVERABLE
    assert g2(_cd(comp)).name == M.DELIVERABLE, "the SFX-preview-scored-instead-of-the-render bug"


def test_a_comp_with_no_manifest_falls_back_to_video_mp4_not_a_guess(comp):
    rd = _cd(comp) / "renders"
    (rd / "aaa-preview.mp4").write_bytes(b"decoy")
    assert M.deliverable(_cd(comp)) is None, "no deliverable is an honest None, never 'some mp4'"
    (rd / M.DELIVERABLE).write_bytes(b"real")
    assert M.deliverable(_cd(comp)).name == M.DELIVERABLE


def test_the_incremental_default_is_the_canonical_name():
    """The literal second name. Three callers pass no `out=`; they must not mint `<comp>.mp4`."""
    import inspect
    from nolan.hyperframes import incremental
    src = inspect.getsource(incremental.render_incremental)
    assert 'f"{comp}.mp4"' not in src
    assert "DELIVERABLE" in src


# --- staleness ------------------------------------------------------------------------------------

def test_staleness_names_the_frames_that_moved(comp):
    (_cd(comp) / "renders" / M.DELIVERABLE).write_bytes(b"x")
    M.write(comp, _cd(comp), mode="incremental")
    assert M.staleness(comp, _cd(comp))["state"] == "current"

    spec_f = _cd(comp) / "compositions" / "frames" / "02-beta.spec.json"
    spec = json.loads(spec_f.read_text(encoding="utf-8"))
    spec["frames"][0]["scenes"][0]["data"]["lines"] = ["changed"]
    spec_f.write_text(json.dumps(spec), encoding="utf-8")

    st = M.staleness(comp, _cd(comp))
    assert st["state"] == "stale"
    assert st["stale_frames"] == ["02-beta"], \
        "the point of per-frame sigs: 'which frames' is actionable, 'N edits behind' is not"
    assert "01-alpha" not in st["stale_frames"]


def test_no_manifest_is_unknown_not_stale(comp):
    st = M.staleness(comp, _cd(comp))
    assert st["state"] == "unknown", "'we cannot tell' must not masquerade as 'it isn't current'"


def test_the_manifest_absorbs_the_done_sentinel(comp):
    """Two staleness markers would be two dialects for one decision."""
    rd = _cd(comp) / "renders"
    (rd / ".done").write_text('{"comp":"x","rendered":true}', encoding="utf-8")
    (rd / M.DELIVERABLE).write_bytes(b"x")
    assert M.is_done(_cd(comp)) is True, "a legacy .done still reads as complete"
    M.write(comp, _cd(comp), mode="whole")
    assert not (rd / ".done").exists(), "writing the manifest retires the boolean"
    assert M.is_done(_cd(comp)) is True
    M.clear(_cd(comp))
    assert M.is_done(_cd(comp)) is False


def test_the_manifest_records_what_it_needs_to(comp):
    (_cd(comp) / "renders" / M.DELIVERABLE).write_bytes(b"x")
    man = M.write(comp, _cd(comp), mode="incremental", duration_s=815.19, gates={"temporal": "pass"})
    assert man["deliverable"] == M.DELIVERABLE and man["mode"] == "incremental"
    assert man["duration_s"] == 815.19 and man["gates"] == {"temporal": "pass"}
    assert set(man["frames"]) == {"01-alpha", "02-beta"} and man["sig"]


# --- one predecessor, not an unbounded history ------------------------------------------------------

def test_rotation_keeps_exactly_one_predecessor(comp):
    rd = _cd(comp) / "renders"
    for cut in (b"cut1", b"cut2", b"cut3"):
        (rd / M.DELIVERABLE).write_bytes(cut)
        M.rotate_previous(_cd(comp))
    assert (rd / M.PREVIOUS).read_bytes() == b"cut3"
    assert not (rd / M.DELIVERABLE).exists()
    assert len(list(rd.glob("*.mp4"))) == 1, "history must not accumulate ~900 MB per render"


def test_tag_is_the_opt_in_escape(comp):
    rd = _cd(comp) / "renders"
    (rd / M.DELIVERABLE).write_bytes(b"published")
    kept = M.tag(_cd(comp), "v1 published/cut")
    assert kept and kept.parent.name == "history"
    assert kept.name == "v1-published-cut.mp4", "a label becomes a safe filename"
    assert kept.read_bytes() == b"published"


# --- intermediates stay out of the delivery directory ------------------------------------------------

def test_intermediates_are_written_to_work(comp):
    import inspect
    from nolan.hyperframes import incremental
    for fn in (incremental.concat_clips, incremental.render_caption_overlay):
        src = inspect.getsource(fn)
        assert "work_dir(" in src, f"{fn.__name__} still writes intermediates beside the deliverable"
    assert 'out.parent / "_concat.txt"' not in inspect.getsource(incremental.concat_clips)


def test_stray_files_are_reported(comp):
    rd = _cd(comp) / "renders"
    (rd / M.DELIVERABLE).write_bytes(b"x")
    (rd / M.PREVIOUS).write_bytes(b"y")
    M.write(comp, _cd(comp), mode="whole")
    assert M.stray_files(_cd(comp)) == [], "a clean renders/ has no strays"
    (rd / "_concat.txt").write_text("leak", encoding="utf-8")
    (rd / ".captions_overlay.hf-transaction-abc").mkdir()
    assert set(M.stray_files(_cd(comp))) == {"_concat.txt", ".captions_overlay.hf-transaction-abc"}
