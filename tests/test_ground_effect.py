"""Effects-umbrella WIRING honesty (compose-first `ground.treatments`) — the sibling test_ground_grade.py
was named as a TODO but never existed. Proves the whole chain is real: the registry SUPERSEDES GRADES
(same css, so the legacy field keeps working), the compose executor applies the colour filter + emits
blended overlay layers, treatments compose with the legacy grade, plate effects no-op without a library
(no crash), the author gate rejects an unknown treatment, and the video-ground path composes a filter too."""
import json
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import compose            # noqa: E402
import author             # noqa: E402
import assemble_media     # noqa: E402
from nolan.effects import registry as reg   # noqa: E402


# --- the registry supersedes GRADES (parity, so the old field keeps working) ---
def test_registry_covers_and_matches_grades():
    color = {e.id: e.css for e in reg.REGISTRY if e.method == "css_filter"}
    for name, css in compose.GRADES.items():
        assert name in color, f"registry lost grade {name!r}"
        assert color[name] == css, f"registry css for {name!r} drifted from compose.GRADES"


# --- the compose executor consumes ground.treatments -------------------------
def test_media_ground_applies_treatment_filter():
    html = "".join(compose.media_ground("s1", {"kind": "image", "src": "a.jpg", "treatments": ["noir"]}, 0, 5)[0])
    assert f"filter:{reg.BY_ID['noir'].css}" in html and "s1-gnd" in html


def test_media_ground_emits_procedural_overlay_layer():
    html = "".join(compose.media_ground("s2", {"kind": "image", "src": "b.jpg", "treatments": ["film-grain"]}, 0, 6)[0])
    assert "s2-fx-film-grain" in html and "mix-blend-mode:overlay" in html


def test_treatments_compose_with_legacy_grade():
    html = "".join(compose.media_ground("s3", {"kind": "image", "src": "c.jpg",
                                               "grade": "cool", "treatments": ["contrast"]}, 0, 5)[0])
    assert compose.GRADES["cool"] in html and reg.BY_ID["contrast"].css in html


def test_plate_treatment_no_overlay_without_library():
    # an element effect (fire) needs a plate; compose passes no resolver -> no overlay emitted, no crash
    html = "".join(compose.media_ground("s4", {"kind": "image", "src": "d.jpg", "treatments": ["fire"]}, 0, 5)[0])
    assert "s4-fx-fire" not in html


def test_no_treatments_no_filter():
    assert "filter:" not in "".join(compose.media_ground("s5", {"kind": "image", "src": "e.jpg"}, 0, 5)[0])


# --- the author gate validates ground.treatments -----------------------------
def _spec(treatments):
    return {"frames": [{"id": "01", "dur": 5, "scenes": [{"id": "s1", "type": "statement", "start": 0, "dur": 5,
            "data": {"lines": ["x"], "ground": {"kind": "image", "src": "a.jpg", "treatments": treatments}}}]}]}


def test_author_gate_rejects_unknown_treatment():
    errs = author.validate_spec(_spec(["no-such-fx"]))
    assert any("treatments" in e for e in errs), errs


def test_author_gate_accepts_valid_treatments():
    assert author.validate_spec(_spec(["noir", {"id": "film-grain", "opacity": 0.3}])) == []


# --- the video-ground path composes a treatments filter ----------------------
def test_video_ground_filter_composes_treatments():
    f = assemble_media._ground_filter({"kind": "video", "src": "v.mp4", "grade": "warm", "treatments": ["contrast"]})
    assert compose.GRADES["warm"] in f and reg.BY_ID["contrast"].css in f


# --- element/damage PLATE overlays root-mount at assemble (can't live in a sub-comp) ---------
def test_collect_video_overlays_roots_a_plate(tmp_path):
    from nolan.effects.library import resolve_plate
    if not resolve_plate("fire"):
        import pytest
        pytest.skip("fire plate not stocked in projects/_library/overlays")
    fdir = tmp_path / "compositions" / "frames"
    fdir.mkdir(parents=True)
    (fdir / "01.spec.json").write_text(json.dumps({"frames": [{"id": "01", "dur": 6, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 6,
         "data": {"lines": ["x"], "ground": {"kind": "image", "src": "a.jpg", "treatments": ["fire"]}}}]}]}), encoding="utf-8")
    ov = assemble_media.collect_video_overlays(tmp_path)
    assert len(ov) == 1
    c = ov[0]
    assert c["blend"] == "screen" and c["track"] >= 20 and c["src"].startswith("assets/overlays/")
    assert (tmp_path / "assets" / "overlays").is_dir()          # the plate is copied into the comp


def test_inject_root_video_stamps_blend_opacity(tmp_path):
    import subprocess
    idx = tmp_path / "index.html"
    idx.write_text('<div id="root" data-composition-id="main"></div>', encoding="utf-8")
    subprocess.run([sys.executable, "-X", "utf8", str(BRIDGE / "inject_root_video.py"), "--index", str(idx),
                    "--clips", json.dumps([{"src": "assets/overlays/fire.mp4", "start": 0, "duration": 6,
                                            "track": 20, "blend": "screen", "opacity": 0.9, "loop": True}])], check=True)
    html = idx.read_text(encoding="utf-8")
    assert "mix-blend-mode:screen" in html and "opacity:0.9" in html
    assert 'data-track-index="20"' in html and " loop " in html


# --- the BAKED per-asset "treat" op (select an asset → apply effects → new file) ----------
def test_treat_cmd_colour_chain_single_input():
    from nolan.hyperframes.quickedit import _treat_cmd
    from nolan.effects.registry import FFMPEG_VF
    cmd = _treat_cmd("ff", "a.jpg", "o.jpg", {"effects": ["sepia", "contrast"]}, "image")
    joined = " ".join(cmd)
    assert FFMPEG_VF["sepia"] in joined and FFMPEG_VF["contrast"] in joined
    assert "-filter_complex" not in cmd and "-frames:v" in cmd and cmd.count("-i") == 1


def test_treat_cmd_plate_overlay_two_input():
    from nolan.hyperframes.quickedit import _treat_cmd
    from nolan.effects.library import resolve_plate
    if not resolve_plate("fire"):
        import pytest
        pytest.skip("fire plate not stocked")
    cmd = _treat_cmd("ff", "a.jpg", "o.mp4", {"effects": ["noir", "fire"]}, "image")
    j = " ".join(cmd)
    assert "-filter_complex" in cmd and "blend=all_mode=screen" in j and "scale2ref" in j
    assert cmd.count("-i") == 2 and "-loop" in cmd and "-t" in cmd     # image looped + plate, capped to a short clip


def test_treat_ext_image_plate_becomes_video(tmp_path):
    from nolan.hyperframes.quickedit import _treat_ext
    from nolan.effects.library import resolve_plate
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\0")
    assert _treat_ext(img, {"effects": ["sepia"]}) is None            # colour only → keep the image ext
    if resolve_plate("fire"):
        assert _treat_ext(img, {"effects": ["fire"]}) == ".mp4"       # a plate → video


def test_treat_cmd_rejects_unbakeable_only():
    from nolan.hyperframes.quickedit import _treat_cmd
    import pytest
    with pytest.raises(ValueError):                                   # scanlines has no -vf and no plate
        _treat_cmd("ff", "a.jpg", "o.jpg", {"effects": ["scanlines"]}, "image")


def test_treat_cmd_preview_downscales_and_shortens():
    from nolan.hyperframes.quickedit import _treat_cmd
    from nolan.effects.library import resolve_plate
    if not resolve_plate("fire"):
        import pytest
        pytest.skip("fire plate not stocked")
    cmd = _treat_cmd("ff", "a.jpg", "o.mp4", {"effects": ["noir", "fire"], "preview": True}, "image")
    assert "scale=480" in " ".join(cmd) and "-t" in cmd and "1.5" in cmd     # low-res + short sample
    full = " ".join(_treat_cmd("ff", "a.jpg", "o.mp4", {"effects": ["noir", "fire"]}, "image"))
    assert "scale=480" not in full and "1.5" not in full                     # the real bake is full-size
