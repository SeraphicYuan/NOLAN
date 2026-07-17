"""Per-scene ✨ Replace (nolan.hyperframes.replace): the editable brief is DERIVED from the scene — the current
asset's stored gen_prompt when it was generated, else the narration; modality follows the current asset. (The
stock/gen fan-out reuses nolan.acquire providers and is exercised live, not in unit tests.)"""
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import replace as rep  # noqa: E402


def test_replace_brief_derives_from_scene():
    name = "_hf_replace_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "compositions" / "frames").mkdir(parents=True)
    (dst / "compositions" / "frames" / "01-x.spec.json").write_text(json.dumps({"frames": [{"id": "01-x", "dur": 8.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 4, "data": {"lines": ["a"], "ground": {"kind": "video", "src": "assets/g.mp4"}}},
        {"id": "s2", "type": "statement", "start": 4, "dur": 4, "data": {"lines": ["b"], "ground": {"kind": "image", "src": "assets/p.png"}}},
    ]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "audio_meta.json").write_text(json.dumps({"voices": [{"frame": "1", "words": [
        {"word": "nervous", "start": 0.2, "end": 1.0}, {"word": "man", "start": 1.0, "end": 1.5},
        {"word": "golden", "start": 4.5, "end": 5.0}, {"word": "sunset", "start": 5.0, "end": 5.6},
    ]}]}), encoding="utf-8")
    (dst / "pool.json").write_text(json.dumps([
        {"file": "assets/p.png", "gen_prompt": "a golden sunset over the ocean", "source": "generated"}]), encoding="utf-8")
    try:
        b1 = rep.brief(name, "01-x", "s1")            # video ground, NOT generated → prompt from narration
        assert b1["field"] == "ground" and b1["modality"] == "video" and b1["current"] == "assets/g.mp4"
        assert "nervous man" in b1["prompt"] and "nervous" in b1["query"]

        b2 = rep.brief(name, "01-x", "s2")            # image ground WITH a stored gen_prompt → that wins
        assert b2["modality"] == "image"
        assert b2["prompt"] == "a golden sunset over the ocean"
        assert b2["gen_style"]                        # a theme-derived style string is present
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_style_presets_loaded():
    # the BONUS_PROMPT_STYLE_* presets are shipped + shaped for the gen dropdown (label + prompt to prepend)
    ps = rep.style_presets()
    assert len(ps) >= 50
    names = {p["name"] for p in ps}
    assert {"PHOTOREALISM", "FILM_NOIR"} <= names
    fn = next(p for p in ps if p["name"] == "FILM_NOIR")
    assert fn["label"] == "Film Noir" and "noir" in fn["prompt"].lower()
