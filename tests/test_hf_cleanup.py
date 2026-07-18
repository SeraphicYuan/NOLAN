"""Composite pool asset-cleanup (nolan.hyperframes.cleanup): DETECT (logo / burned-in captions / stray
head+tail frames) -> PLAN one same-aspect crop + trim -> EXECUTE in one ffmpeg pass -> a new pool asset.

Deterministic CV detectors are exercised on hand-built numpy fixtures (no media, no network); the vision
`confirm` hook is INJECTED as a stub so analyze()'s orchestration is testable offline; build_cmd() is
asserted at the argv level; and one real bundled-ffmpeg pass proves the plan->new-pool-asset chain end to
end. The wiring honesty tests lock the op into the QUICK_EDITS registry + the routes."""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from nolan.hyperframes import cleanup as cl
from nolan.hyperframes import edit as hfedit
from nolan.hyperframes import quickedit as qe

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"


# ============================================================ wiring / registry honesty

def test_cleanup_op_registered():
    op = qe.QUICK_EDITS.get("cleanup")
    assert op and op["label"] == "Clean up (auto)"
    assert set(op["media"]) == {"image", "video"}              # accepts stills AND video
    assert op.get("background") is True and callable(op["cmd"]) and callable(op["out_ext"])


def test_cleanup_op_surfaced_and_exported():
    assert "cleanup" in hfedit.quick_edit_ops()                # reaches the /hyperframes UI registry
    from nolan import hyperframes as hf
    assert hasattr(hf, "cleanup_analyze") and hasattr(hf, "cleanup_asset")
    assert "cleanup_analyze" in hf.__all__ and "cleanup_asset" in hf.__all__


def test_cleanup_ext_is_media_aware():
    assert qe._cleanup_ext(Path("x.png"), {"plan": {"kind": "image"}}) == ".png"
    assert qe._cleanup_ext(Path("x.webp"), {"plan": {"kind": "image"}}) == ".webp"
    assert qe._cleanup_ext(Path("x.mp4"), {"plan": {"kind": "video"}}) == ".mp4"


def test_cleanup_cmd_requires_a_plan():
    with pytest.raises(ValueError):                            # the argv builder never re-analyzes
        qe._cleanup_cmd("ffmpeg", "in.mp4", "out.mp4", {}, "video")


# ============================================================ crop planner (keep W x H + aspect)

def test_plan_crop_none_when_nothing_to_clear():
    assert cl.plan_crop(640, 360, [], None) is None


def test_plan_crop_clears_a_corner_logo_keeps_aspect_and_even_dims():
    logo = {"x": 0.02, "y": 0.03, "w": 0.12, "h": 0.09}       # top-left
    c = cl.plan_crop(640, 360, [logo], None)
    assert c is not None
    for k in ("x", "y", "w", "h"):
        assert c[k] % 2 == 0                                   # encoders want even dims
    assert abs((c["w"] / c["h"]) - (640 / 360)) < 0.02         # same aspect ratio as the source
    assert c["y"] >= logo["y"] * 360 or c["x"] >= logo["x"] * 640   # the crop starts past the logo edge


def test_plan_crop_clears_a_caption_from_the_bottom():
    c = cl.plan_crop(640, 360, [], {"top": 0.85})
    assert c is not None and c["h"] < 360                      # trimmed the bottom band
    assert abs((c["w"] / c["h"]) - (640 / 360)) < 0.02


def test_plan_crop_bails_when_it_would_zoom_too_hard():
    huge = {"x": 0.0, "y": 0.0, "w": 0.9, "h": 0.66}           # clearing this leaves < 40% height
    assert cl.plan_crop(640, 360, [huge], None) is None        # over-detection -> refuse rather than wreck it


# ============================================================ build_cmd (argv)

def _crop():
    return {"x": 0, "y": 0, "w": 600, "h": 338}


def test_build_cmd_image_is_a_single_still_no_trim():
    plan = {"kind": "image", "ow": 640, "oh": 360, "crop": _crop()}
    a = cl.build_cmd("FF", Path("in.png"), Path("out.png"), plan)
    assert a[:4] == ["FF", "-y", "-i", "in.png"]
    assert "-frames:v" in a and "1" in a and "-update" in a
    assert "-ss" not in a and "libx264" not in a               # a still: no seek, no video encode
    vf = a[a.index("-vf") + 1]
    assert vf.startswith("crop=600:338:0:0") and "scale=640:360" in vf   # crop -> scale back to source W x H


def test_build_cmd_video_trims_and_crops_in_one_pass():
    plan = {"kind": "video", "ow": 640, "oh": 360, "dur": 3.0,
            "trim_in": 0.2, "trim_out": 2.8, "crop": _crop()}
    a = cl.build_cmd("FF", Path("in.mp4"), Path("out.mp4"), plan)
    assert a[a.index("-ss") + 1] == "0.200"                    # input-seek to the head trim
    assert a[a.index("-t") + 1] == "2.600"                     # length = trim_out - trim_in
    assert "libx264" in a and "aac" in a
    vf = a[a.index("-vf") + 1]
    assert vf.startswith("crop=600:338:0:0") and "scale=640:360" in vf


def test_build_cmd_video_crop_only_has_no_seek_or_length():
    plan = {"kind": "video", "ow": 640, "oh": 360, "dur": 3.0,
            "trim_in": 0.0, "trim_out": 3.0, "crop": _crop()}
    a = cl.build_cmd("FF", Path("in.mp4"), Path("out.mp4"), plan)
    assert "-ss" not in a and "-t" not in a                    # nothing trimmed -> keep the whole timeline
    assert "-vf" in a and "libx264" in a


# ============================================================ detectors (synthetic numpy fixtures)

def test_detect_captions_finds_a_glyph_line_and_ignores_a_blank_band():
    H, W, N = 270, 480, 6
    stack = np.full((N, H, W), 30, np.uint8)                  # dark frames
    for gi in range(8):                                       # a row of 8 glyph-sized bright blocks, spread wide
        x = 60 + gi * 45
        stack[:, 210:222, x:x + 8] = 255
    cap = cl.detect_captions(stack)
    assert cap is not None and 0.62 <= cap["top"] <= 0.98 and cap["coverage"] >= 0.35

    blank = np.full((N, H, W), 30, np.uint8)
    assert cl.detect_captions(blank) is None                  # no text -> no caption


def test_detect_captions_ignores_a_few_bright_specks():
    H, W, N = 270, 480, 6
    stack = np.full((N, H, W), 30, np.uint8)
    stack[:, 210:222, 100:108] = 255                          # only 1-2 blobs -> below the >=6 glyph floor
    stack[:, 210:222, 300:308] = 255
    assert cl.detect_captions(stack) is None


def test_detect_logo_finds_a_persistent_corner_graphic():
    H, W, N = 270, 480, 12
    stack = np.full((N, H, W), 100, np.uint8)                 # flat bg (Canny sees no edges)
    stack[:, 6:30, 6:46] = 255                                # a fixed bright block in the TOP-LEFT, every frame
    out = cl.detect_logo(stack)
    assert len(out) == 1                                       # exactly one corner, no false positives on flat bg
    b = out[0]
    assert b["x"] < 0.5 and b["y"] < 0.5                       # located top-left


def test_detect_logo_empty_on_flat_frames():
    stack = np.full((8, 270, 480), 100, np.uint8)
    assert cl.detect_logo(stack) == []                        # nothing structured -> nothing


def test_detect_logo_static_proposes_for_a_single_image():
    frame = np.full((270, 480), 100, np.uint8)
    frame[8:40, 8:70] = 255                                    # a corner graphic on a 1-frame (image) stack
    out = cl.detect_logo(frame[None, :, :])                   # N==1 -> the spatial proposer path
    assert out and out[0]["x"] < 0.5 and out[0]["y"] < 0.5


def _cut_stack(pattern):
    """(N,4,4) uint8 stack: `pattern` is a list of (count, value) runs."""
    frames = []
    for count, val in pattern:
        frames += [np.full((4, 4), val, np.uint8)] * count
    return np.stack(frames)


def test_detect_trim_auto_trims_a_short_head_stray():
    gray = _cut_stack([(6, 200), (84, 50)])                   # 0.2s of one shot, hard cut to another
    t_in, t_out, cands = cl.detect_trim(gray, 30.0, 90, list(range(90)))
    assert abs(t_in - 0.2) < 1e-6 and not cands               # unambiguous crumb -> auto-trimmed


def test_detect_trim_auto_trims_a_short_tail_stray():
    gray = _cut_stack([(84, 50), (6, 200)])                   # hard cut 0.2s before the end
    t_in, t_out, cands = cl.detect_trim(gray, 30.0, 90, list(range(90)))
    assert abs(t_out - 2.8) < 1e-6 and t_in == 0.0


def test_detect_trim_surfaces_an_ambiguous_cut_as_a_candidate():
    gray = _cut_stack([(18, 200), (72, 50)])                  # 0.6s head: too long to auto-trust
    t_in, t_out, cands = cl.detect_trim(gray, 30.0, 90, list(range(90)))
    assert t_in == 0.0 and len(cands) == 1 and cands[0]["side"] == "head"   # left for vision/human review


# ============================================================ analyze() orchestration (injected confirm)

def _patch_load(monkeypatch, is_video, ow=640, oh=360):
    n = 2 if is_video else 1
    fps, total = (30.0, 90) if is_video else (0.0, 1)
    monkeypatch.setattr(cl, "_load",
                        lambda p, **k: (np.zeros((n, 4, 4), np.uint8), ow, oh, fps, total, list(range(n))))


def test_analyze_confirm_rejects_a_false_logo_and_caption(monkeypatch):
    _patch_load(monkeypatch, is_video=True)
    monkeypatch.setattr(cl, "detect_logo", lambda g, **k: [{"x": 0.02, "y": 0.03, "w": 0.1, "h": 0.08}])
    monkeypatch.setattr(cl, "detect_captions", lambda g, **k: {"top": 0.85, "coverage": 0.9})
    monkeypatch.setattr(cl, "detect_trim", lambda *a, **k: (0.0, 3.0, []))
    reject = lambda kind, info: False                          # vision says "not a logo / not a subtitle"
    p = cl.analyze("clip.mp4", confirm=reject)
    assert p["logos"] == [] and p["caption"] is None
    assert p["crop"] is None and p["changed"] is False         # nothing survived -> no-op


def test_analyze_confirm_keeps_real_detections(monkeypatch):
    _patch_load(monkeypatch, is_video=True)
    monkeypatch.setattr(cl, "detect_logo", lambda g, **k: [{"x": 0.02, "y": 0.03, "w": 0.1, "h": 0.08}])
    monkeypatch.setattr(cl, "detect_captions", lambda g, **k: None)
    monkeypatch.setattr(cl, "detect_trim", lambda *a, **k: (0.0, 3.0, []))
    p = cl.analyze("clip.mp4", confirm=lambda kind, info: True)
    assert p["logos"] and p["crop"] is not None and p["changed"] is True
    assert p["kind"] == "video"


def test_analyze_confirms_an_ambiguous_trim_candidate(monkeypatch):
    _patch_load(monkeypatch, is_video=True)
    monkeypatch.setattr(cl, "detect_logo", lambda g, **k: [])
    monkeypatch.setattr(cl, "detect_captions", lambda g, **k: None)
    cand = {"side": "head", "t": 0.6, "len": 0.6, "frac": 0.2, "mag": 99.0}
    monkeypatch.setattr(cl, "detect_trim", lambda *a, **k: (0.0, 3.0, [cand]))
    yes = cl.analyze("clip.mp4", confirm=lambda kind, info: kind == "trim")
    assert yes["trim_in"] == 0.6 and yes["changed"] is True and not yes["trim_candidates"]
    no = cl.analyze("clip.mp4", confirm=lambda kind, info: False)
    assert no["trim_in"] == 0.0 and no["trim_candidates"] == [cand]   # unconfirmed -> surfaced, not applied


def test_analyze_image_skips_trim(monkeypatch):
    _patch_load(monkeypatch, is_video=False)
    monkeypatch.setattr(cl, "detect_logo", lambda g, **k: [])
    monkeypatch.setattr(cl, "detect_captions", lambda g, **k: {"top": 0.82, "coverage": 1.0})
    called = {"trim": False}
    monkeypatch.setattr(cl, "detect_trim", lambda *a, **k: called.__setitem__("trim", True) or (0.0, 0.0, []))
    p = cl.analyze("frame.png", confirm=lambda kind, info: True)
    assert p["kind"] == "image" and called["trim"] is False    # trim is a video-only concept
    assert p["trim_in"] == 0.0 and p["caption"] and p["changed"] is True


# ============================================================ batch analyze (shared provider, error isolation)

def test_cleanup_analyze_batch_shares_one_provider_and_isolates_errors(monkeypatch):
    monkeypatch.setattr(hfedit, "_resolve_asset_path", lambda comp, p: Path("/pool") / p)
    sentinel = object()
    monkeypatch.setattr(cl, "default_vision_provider", lambda config=None: sentinel)
    seen = []
    monkeypatch.setattr(cl, "make_vision_confirm",
                        lambda src, provider=None: (seen.append(provider), (lambda k, i: True))[1])

    def fake_analyze(src, confirm=None):
        if "bad" in src:
            raise RuntimeError("boom")
        return {"changed": True, "kind": "video"}
    monkeypatch.setattr(cl, "analyze", fake_analyze)

    res = hfedit.cleanup_analyze_batch("c", ["a.mp4", "bad.mp4", "b.png"], confirm=True)["results"]
    assert len(res) == 3
    assert res[0]["plan"]["changed"] and res[2]["plan"]["changed"]
    assert "error" in res[1] and "boom" in res[1]["error"]          # one bad file doesn't sink the batch
    assert seen and set(id(p) for p in seen) == {id(sentinel)}      # every confirm reused the ONE provider


def test_cleanup_analyze_batch_survives_vision_unavailable(monkeypatch):
    monkeypatch.setattr(hfedit, "_resolve_asset_path", lambda comp, p: Path("/pool") / p)
    monkeypatch.setattr(cl, "default_vision_provider",
                        lambda config=None: (_ for _ in ()).throw(RuntimeError("no key")))
    got = {}
    monkeypatch.setattr(cl, "make_vision_confirm", lambda src, provider=None: got.__setitem__("prov", provider))
    monkeypatch.setattr(cl, "analyze", lambda src, confirm=None: {"changed": False})
    res = hfedit.cleanup_analyze_batch("c", ["a.mp4"], confirm=True)["results"]
    assert res[0]["plan"] == {"changed": False} and got["prov"] is None   # provider build failed -> CV-only


# ============================================================ end-to-end: plan -> new pool asset (real ffmpeg)

def _ffmpeg_or_skip():
    try:
        from nolan.hf_qa import _ffmpeg
        return _ffmpeg()
    except Exception:
        pytest.skip("ffmpeg unavailable")


def _dims(ff, p):
    import re
    o = subprocess.run([ff, "-i", str(p)], capture_output=True, text=True)
    ls = [l for l in (o.stdout + o.stderr).splitlines() if "Video:" in l]
    m = re.search(r"(\d{2,5})x(\d{2,5})", ls[0]) if ls else None
    return m.group(0) if m else "?"


@pytest.fixture()
def comp():
    ff = _ffmpeg_or_skip()
    name = "_hf_cleanup_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "compositions" / "frames").mkdir(parents=True)      # marks a real comp for _comp_dir
    (dst / "assets").mkdir(parents=True)
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "testsrc=s=320x240:d=1:r=30",
                    "-c:v", "libx264", "-t", "1", str(dst / "assets" / "clip.mp4")], capture_output=True)
    try:
        yield name, ff, dst
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_cleanup_asset_applies_a_plan_to_a_new_pool_asset(comp):
    name, ff, dst = comp
    plan = {"kind": "video", "ow": 320, "oh": 240, "dur": 1.0, "fps": 30.0,
            "logos": [{"x": 0.0, "y": 0.0, "w": 0.15, "h": 0.15}], "caption": None,
            "trim_in": 0.0, "trim_out": 1.0, "trim_candidates": [],
            "crop": {"x": 0, "y": 0, "w": 280, "h": 210}, "zoom": 1.14, "changed": True}
    r = hfedit.cleanup_asset(name, "assets/clip.mp4", plan=plan)     # plan passed -> no analyze, no network
    assert r["changed"] is True and r["name"].endswith("_clean.mp4")
    out = dst / r["path"]
    assert out.exists() and _dims(ff, out) == "320x240"             # cropped then scaled back to source W x H
    assert r["name"] in (dst / "pool.json").read_text(encoding="utf-8")   # registered as a pool asset


def test_cleanup_asset_noop_writes_nothing(comp):
    name, ff, dst = comp
    before = json.loads((dst / "pool.json").read_text(encoding="utf-8")) if (dst / "pool.json").exists() else []
    plan = {"kind": "video", "ow": 320, "oh": 240, "dur": 1.0, "logos": [], "caption": None,
            "trim_in": 0.0, "trim_out": 1.0, "trim_candidates": [], "crop": None, "changed": False}
    r = hfedit.cleanup_asset(name, "assets/clip.mp4", plan=plan)
    assert r["changed"] is False and "path" not in r               # nothing detected -> no new asset
    after = json.loads((dst / "pool.json").read_text(encoding="utf-8")) if (dst / "pool.json").exists() else []
    assert len(after) == len(before)


# ============================================================ route wiring (TestClient over the real hub app)

@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient
    from nolan.hub import create_hub_app
    return TestClient(create_hub_app(db_path=None, projects_dir=None))


def test_route_cleanup_requires_comp_and_path(client):
    assert client.post("/api/hf/asset/cleanup", json={"comp": "x"}).status_code == 400
    assert client.post("/api/hf/asset/cleanup-analyze", json={"path": "y"}).status_code == 400


def test_route_cleanup_dispatches_to_the_engine(client, monkeypatch):
    from nolan import hyperframes as hf
    monkeypatch.setattr(hf, "cleanup_asset",
                        lambda comp, path, confirm=True, plan=None: {"changed": True, "name": "z_clean.mp4",
                                                                     "path": "assets/z_clean.mp4", "plan": {}})
    r = client.post("/api/hf/asset/cleanup", json={"comp": "c", "path": "assets/z.mp4"})
    assert r.status_code == 200 and r.json()["name"] == "z_clean.mp4"


def test_route_cleanup_analyze_dispatches(client, monkeypatch):
    from nolan import hyperframes as hf
    monkeypatch.setattr(hf, "cleanup_analyze",
                        lambda comp, path, confirm=True: {"path": path, "plan": {"changed": False}})
    r = client.post("/api/hf/asset/cleanup-analyze", json={"comp": "c", "path": "assets/z.mp4"})
    assert r.status_code == 200 and r.json()["plan"] == {"changed": False}


def test_route_cleanup_batch_validates_and_dispatches(client, monkeypatch):
    assert client.post("/api/hf/asset/cleanup-analyze-batch", json={"comp": "c"}).status_code == 400
    assert client.post("/api/hf/asset/cleanup-analyze-batch", json={"comp": "c", "paths": []}).status_code == 400
    from nolan import hyperframes as hf
    monkeypatch.setattr(hf, "cleanup_analyze_batch",
                        lambda comp, paths, confirm=True: {"results": [{"path": p, "plan": {"changed": True}} for p in paths]})
    r = client.post("/api/hf/asset/cleanup-analyze-batch", json={"comp": "c", "paths": ["a.mp4", "b.png"]})
    assert r.status_code == 200 and len(r.json()["results"]) == 2
