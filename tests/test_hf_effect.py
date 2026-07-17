"""Tier-1 Clips→HyperFrames effect adaptation (nolan.hyperframes.effect): an agent-authored GSAP effect lands
on ONE scene as a `raw` block THROUGH the author.py gate (a malformed effect reverts); the dedup catalog +
task brief are GSAP-retargeted (not Remotion). The live clip-analysis agent is exercised separately."""
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import effect as eff  # noqa: E402
from nolan.hyperframes import edit as hfedit  # noqa: E402


def _comp():
    name = "_hf_effect_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "compositions" / "frames").mkdir(parents=True)
    (dst / "compositions" / "frames" / "f1.spec.json").write_text(json.dumps({"frames": [{"id": "f1", "dur": 6.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 4, "data": {"lines": ["hi"]}}]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    return name, dst


def test_apply_effect_gates_and_lands():
    name, dst = _comp()
    try:
        html = ['<div id="s1-fx" class="clip" data-start="0" data-duration="4" data-track-index="2" '
                'style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text)">FX</div>']
        tl = ['tl.fromTo("#s1-fx",{opacity:0,scale:0.8},{opacity:1,scale:1,duration:0.8,ease:"power3.out"},0.1);']
        r = eff.apply_effect(name, "f1", "s1", html, tl)
        assert r.get("applied") is True
        spec, info = hfedit.load_frame_spec(name, "f1")
        sc = spec["frames"][info["i"]]["scenes"][0]
        assert sc["type"] == "raw" and sc["data"]["html"] and sc["data"]["tl"]
        assert sc["meta"]["effect_source"] == "agent-clip-clone"      # provenance stamped
        composed = (dst / "compositions" / "frames" / "f1.html").read_text(encoding="utf-8")
        assert "s1-fx" in composed                                    # the effect recomposed into the frame
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_empty_effect_rejected():
    name, dst = _comp()
    try:
        assert eff.apply_effect(name, "f1", "s1", [], []).get("applied") is False   # no html → rejected, scene untouched
        assert hfedit.load_frame_spec(name, "f1")[0]["frames"][0]["scenes"][0]["type"] == "statement"
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_catalog_and_brief_are_gsap_retargeted():
    name, dst = _comp()
    try:
        cat = eff.hf_catalog_md()
        assert "statement" in cat and "scramble" in cat            # HF blocks + reveals, not the Remotion registry
        brief = eff.effect_task_brief(name, "f1", "s1", clip_ref="x.mp4", comment="a slow push-in")
        assert "GSAP" in brief and "not Remotion" in brief and "data.tl" in brief
        assert "a slow push-in" in brief                           # the human note is carried
    finally:
        shutil.rmtree(dst, ignore_errors=True)
