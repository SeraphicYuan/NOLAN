"""asset_pool_meta — surfaces a generated asset's ENHANCED prompt (gen_prompt) to the /hyperframes edit UI,
keyed by file basename so a scene's media src can be looked up, with the VLM caption as a labelled fallback
for assets that pre-date prompt persistence."""
import json
import shutil
from pathlib import Path

import pytest

from nolan.hyperframes import edit as hfedit

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"


@pytest.fixture()
def comp():
    name = "_hf_poolmeta_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "compositions" / "frames").mkdir(parents=True)   # _comp_dir requires this to resolve the comp
    (dst / "pool.json").write_text(json.dumps([
        {"file": "generated/s1_gen.png", "source": "krea2 (generated)", "generated": True,
         "gen_prompt": "a cinematic wide shot, cool blue palette", "gen_negative": "text, watermark",
         "caption": "a blue room"},
        {"file": "videos/s2_03.mp4", "source": "pexels", "caption": "city street"},                 # stock
        {"file": "generated/s3_gen.png", "source": "krea2 (generated)", "generated": True,
         "caption": "old gen, prompt not saved"},                                                    # pre-persistence
    ]), encoding="utf-8")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_gen_asset_surfaces_enhanced_prompt(comp):
    m = hfedit.asset_pool_meta(comp)
    g = m["s1_gen.png"]
    assert g["generated"] is True
    assert g["gen_prompt"] == "a cinematic wide shot, cool blue palette"
    assert g["gen_negative"] == "text, watermark"


def test_stock_asset_is_not_generated(comp):
    s = hfedit.asset_pool_meta(comp)["s2_03.mp4"]
    assert s["generated"] is False and s["gen_prompt"] == ""


def test_pre_persistence_gen_asset_falls_back_to_caption(comp):
    g = hfedit.asset_pool_meta(comp)["s3_gen.png"]
    # generated but no prompt was stored → empty prompt, VLM caption available as the labelled fallback
    assert g["generated"] is True and g["gen_prompt"] == "" and g["caption"] == "old gen, prompt not saved"
