"""Clip-driven FRAME transitions (nolan.hyperframes.transitions) — the registry loads from the manifest,
and transition_segment renders a valid two-clip composite (luma maskedmerge / chroma green reveal). These
are frame-to-frame matte/reveal wipes spliced at the concat seam, distinct from the within-frame GSAP
transitions in compose.TRANSITIONS."""
import json
import subprocess

from nolan.ffmpeg_utils import FFMPEG
from nolan.hyperframes import transitions as tr


def test_registry_loads_and_resolves(tmp_path):
    (tmp_path / "ink-wipe-1.mp4").write_bytes(b"\0")
    (tmp_path / "transitions.json").write_text(json.dumps([
        {"file": "ink-wipe-1.mp4", "kind": "ink-wipe", "type": "luma", "invert": True, "clip_len": 5, "dur": 1.2,
         "license": "Pixabay License", "url": "http://x/y.mp4"}]), encoding="utf-8")
    items = tr.load_transitions(tmp_path)
    assert [i["kind"] for i in items] == ["ink-wipe"]
    assert tr.transition_kinds(tmp_path) == ["ink-wipe"]
    e = tr.resolve("ink-wipe", tmp_path)
    assert e["type"] == "luma" and e["invert"] is True and e["clip_len"] == 5
    assert tr.resolve("nope", tmp_path) is None


def test_transition_segment_renders_stocked_kinds(tmp_path):
    """For every stocked transition, transition_segment renders a valid non-empty segment from two tiny
    distinct clips (proves the ffmpeg composite — luma AND chroma — is wired correctly)."""
    import pytest
    stocked = tr.load_transitions()
    if not stocked:
        pytest.skip("no transition clips stocked in projects/_library/transitions")
    A, B = tmp_path / "A.mp4", tmp_path / "B.mp4"
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "color=red:s=96x54:d=2", "-pix_fmt", "yuv420p", str(A)], capture_output=True)
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "color=blue:s=96x54:d=2", "-pix_fmt", "yuv420p", str(B)], capture_output=True)
    for t in stocked:
        out = tmp_path / f"seg_{t['kind']}.mp4"
        tr.transition_segment(A, B, t["kind"], out, dur=float(t.get("dur", 1.0)), size=(96, 54), fps=15)
        assert out.exists() and out.stat().st_size > 0, f"{t['kind']} produced no segment"


def test_splice_transitions_is_net_zero(tmp_path):
    """splice_transitions replaces a transitioned seam with [A_trim | segment | B_trim] and PRESERVES the
    total timeline duration (net-zero: dur/2 trimmed each side + a dur segment inserted), with audio intact
    on every piece — so the caption overlay + BGM bed stay in sync (narration-owns-duration)."""
    import pytest
    from nolan.hyperframes.incremental import _av_durations, splice_transitions
    stocked = tr.load_transitions()
    if not stocked:
        pytest.skip("no transition clips stocked")
    kind, d = stocked[0]["kind"], 1.0

    def mk(path, color, freq):
        subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color={color}:s=128x72:d=4.0",
                        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=4.0",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000",
                        "-ac", "2", "-shortest", str(path)], capture_output=True)
    A, B = tmp_path / "A.mp4", tmp_path / "B.mp4"
    mk(A, "red", 220)
    mk(B, "blue", 440)
    a0 = _av_durations(A, FFMPEG)[0]
    b0 = _av_durations(B, FFMPEG)[0]
    spliced = splice_transitions([A, B], [{"kind": kind, "dur": d}, None], tmp_path / "work")
    assert len(spliced) == 3, "expected A_trim | segment | B_trim"
    total = sum(_av_durations(p, FFMPEG)[0] for p in spliced)
    assert abs(total - (a0 + b0)) < 0.4, f"net-zero broken: spliced {total:.2f}s vs original {a0 + b0:.2f}s"
    for p in spliced:
        assert _av_durations(p, FFMPEG)[1] > 0.05, f"{p.name} lost its audio"


def test_splice_passthrough_when_no_transitions(tmp_path):
    """No transition specs -> the clip list passes through byte-identical (untouched frames stay a
    lossless stream-copy; only transitioned seams are ever re-encoded)."""
    from nolan.hyperframes.incremental import splice_transitions
    A, B = tmp_path / "A.mp4", tmp_path / "B.mp4"
    A.write_bytes(b"a")
    B.write_bytes(b"b")
    assert splice_transitions([A, B], [None, None], tmp_path / "work") == [A, B]


def test_manifest_is_licensed_and_reproducible():
    """Every committed transition carries a license + (url or source) so the gitignored clip is
    reproducible/attributable — mirrors the overlay-plate manifest contract."""
    import pytest
    manifest = tr.TRANS_LIBRARY / "transitions.json"
    if not manifest.exists():
        pytest.skip("no transitions manifest")
    for e in json.loads(manifest.read_text(encoding="utf-8")):
        assert e.get("file") and e.get("kind") and e.get("type") in ("luma", "chroma")
        assert e.get("license"), f"{e.get('file')}: no license"
        assert str(e.get("url", "")).startswith("http") or e.get("source"), f"{e.get('file')}: not reproducible"
