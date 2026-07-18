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


# ---- Tier-2: the `spotlight` extension block (Clips→HF effect PROMOTED into a reusable, parametric block) ----

BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"


def test_spotlight_is_registered_and_catalog_parity_holds():
    # the extension block is merged into compose.BLOCKS AND documented in catalog.json (the honesty test that
    # keeps the catalog from rotting: check_catalog.py enforces BLOCKS<->catalog parity over the merged set).
    r = __import__("subprocess").run(["python", "-X", "utf8", "check_catalog.py"], cwd=str(BRIDGE),
                                     capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "spotlight" in r.stdout                                 # spotlight is in the parity-checked set


def test_spotlight_center_composes_subject_over_bilateral_labels():
    name, dst = _comp()
    try:
        r = eff.apply_block(name, "f1", "s1", "spotlight",
                            {"subject": "assets/x.png", "position": "center", "words": ["激励", "计划"],
                             "kicker": "Incentive Plan"})
        assert r.get("applied") is True
        assert "templated" in (r.get("gate") or "")               # counts as a TEMPLATED scene, not bespoke raw
        spec, info = hfedit.load_frame_spec(name, "f1")
        sc = spec["frames"][info["i"]]["scenes"][0]
        assert sc["type"] == "spotlight" and sc["meta"]["effect_block"] == "spotlight"
        html = (dst / "compositions" / "frames" / "f1.html").read_text(encoding="utf-8")
        assert 'id="s1-subj"' in html and 'data-track-index="4"' in html      # subject in front (track 4)
        assert 'id="s1-txtl"' in html and 'id="s1-txtr"' in html              # BOTH side labels
        assert 'data-track-index="2"' in html                                 # labels behind (track 2)
        assert "激励" in html and "计划" in html and "Incentive Plan" in html   # split words + kicker
        assert "data-fit" in html                                             # deterministic auto-resize
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_spotlight_left_bounds_subject_and_puts_label_opposite():
    name, dst = _comp()
    try:
        eff.apply_block(name, "f1", "s1", "spotlight",
                        {"subject": "assets/x.png", "position": "left", "words": "Incentive Plan"})
        html = (dst / "compositions" / "frames" / "f1.html").read_text(encoding="utf-8")
        # subject bounded to its ~47% half (so the opposite label never collides) + single label block on the RIGHT
        assert "width:47%" in html and 'id="s1-subjwrap"' in html
        assert 'id="s1-labb"' in html and "right:0;" in html                  # label hugs the RIGHT (opposite the left subject)
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def _write_cutout(path: Path, w: int, h: int, bar_frac: float, alpha: bool = True):
    """A synthetic bg-removed cutout: a centered vertical bar `bar_frac` wide on a transparent canvas.
    alpha=False writes an OPAQUE image (no silhouette to measure — exercises the fallback)."""
    from PIL import Image, ImageDraw
    mode = "RGBA" if alpha else "RGB"
    bg = (0, 0, 0, 0) if alpha else (255, 255, 255)
    im = Image.new(mode, (w, h), bg)
    bw = int(w * bar_frac)
    ImageDraw.Draw(im).rectangle([(w - bw) // 2, int(h * 0.08), (w + bw) // 2, h - 1],
                                 fill=(30, 30, 50, 255) if alpha else (30, 30, 50))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def _labl_width_px(html: str):
    import re
    m = re.search(r'id="s1-labl"[^>]*?width:([0-9.]+)px', html)
    return float(m.group(1)) if m else None


def test_spotlight_clear_mode_is_asset_aware_and_adapts():
    """Honesty test for the `clear` label_layout: it is CONSUMED (the words are placed in the subject's
    clear zone, not the fixed 47% overlap regions), it ADAPTS to the cutout's silhouette (a narrower
    subject lets the words sit closer / wider), and it falls back LOUDLY when the subject can't be
    measured. Guards the phantom-field + landing-spot-gap failure modes for this field."""
    import importlib.util
    if importlib.util.find_spec("PIL") is None:
        import pytest
        pytest.skip("Pillow not installed")

    name, dst = _comp()
    try:
        assets = dst / "assets"
        _write_cutout(assets / "narrow.png", 500, 900, 0.24)   # thin figure
        _write_cutout(assets / "wide.png", 900, 900, 0.72)     # broad figure
        _write_cutout(assets / "opaque.png", 500, 900, 0.24, alpha=False)

        base = {"position": "center", "words": ["激励", "计划"], "kicker": "Incentive Plan",
                "label_layout": "clear"}

        # 1) narrow: clear mode CONSUMED — banded px labels, NOT the overlap 47% regions
        eff.apply_block(name, "f1", "s1", "spotlight", {**base, "subject": "assets/narrow.png"})
        h_narrow = (dst / "compositions" / "frames" / "f1.html").read_text(encoding="utf-8")
        assert "width:47.0%" not in h_narrow, "clear mode still emitted the overlap 47% regions"
        assert 'id="s1-labl"' in h_narrow and "px;top:" in h_narrow      # absolute banded placement
        assert "fell back" not in h_narrow
        w_narrow = _labl_width_px(h_narrow)
        assert w_narrow is not None

        # 2) wide: SAME field, DIFFERENT geometry — the broad silhouette pushes the words further out
        #    (a smaller left region), proving placement is measured from the asset, not fixed.
        eff.apply_block(name, "f1", "s1", "spotlight", {**base, "subject": "assets/wide.png"})
        h_wide = (dst / "compositions" / "frames" / "f1.html").read_text(encoding="utf-8")
        w_wide = _labl_width_px(h_wide)
        assert w_wide is not None and w_narrow > w_wide + 40, (
            f"clear mode did not adapt to shape: narrow={w_narrow} wide={w_wide}")

        # 3) fallback is LOUD: an opaque subject can't be measured → overlap layout + a visible marker
        eff.apply_block(name, "f1", "s1", "spotlight", {**base, "subject": "assets/opaque.png"})
        h_fallback = (dst / "compositions" / "frames" / "f1.html").read_text(encoding="utf-8")
        assert "fell back" in h_fallback and "width:47.0%" in h_fallback

        # 4) default (no label_layout) is UNCHANGED — the reel overlap look, backward-compatible
        eff.apply_block(name, "f1", "s1", "spotlight",
                        {"subject": "assets/narrow.png", "position": "center", "words": ["激励", "计划"]})
        h_default = (dst / "compositions" / "frames" / "f1.html").read_text(encoding="utf-8")
        assert "width:47.0%" in h_default and "fell back" not in h_default
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_apply_block_rejects_unknown_type():
    name, dst = _comp()
    try:
        assert eff.apply_block(name, "f1", "s1", "not_a_block", {"x": 1}).get("applied") is False
        assert hfedit.load_frame_spec(name, "f1")[0]["frames"][0]["scenes"][0]["type"] == "statement"  # untouched
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_brief_prefers_a_reusable_block():
    name, dst = _comp()
    try:
        brief = eff.effect_task_brief(name, "f1", "s1", clip_ref="x.mp4", comment="figure with flanking words")
        assert "PREFER a reusable block" in brief and "spotlight" in brief    # catalog-blind pitfall closed
        assert '"block"' in brief                                             # the block proposal shape is documented
    finally:
        shutil.rmtree(dst, ignore_errors=True)
