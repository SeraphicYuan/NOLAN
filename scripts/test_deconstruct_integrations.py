"""Test: deconstruction → creation-pipeline integrations (Q3), no LLM/agent.

Verifies, using the REAL Odyssey extract where available (falls back to a
synthetic extract otherwise):
  1. Template export: extract → scene-plan template dir that template_match
     actually loads and scores.
  2. Clone mode: extract → script project pre-seeded with a constitution
     beatmap (ad beats excluded, word budgets scaled, provenance recorded).
  3. Video-style synthesis brief cites deconstruction case studies.
  4. Retrieval enrichment: shots-overlap lookup + measured facts surfacing in
     the library score prompt and motion prompt.
  5. New hub routes registered (export-template, clone).

Usage:
    D:/env/nolan/python.exe -X utf8 scripts/test_deconstruct_integrations.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REAL_EXTRACT = Path("video_deconstructions/"
                    "the-odyssey-explained-in-25-minutes-best-greek-mythology-documentary/"
                    "extract.json")


def load_extract():
    if REAL_EXTRACT.exists():
        return json.loads(REAL_EXTRACT.read_text(encoding="utf-8")), "real-odyssey"
    beats = [
        {"title": "Hook", "function": "hook", "first_shot": 0, "last_shot": 1,
         "t0": 0, "t1": 10, "shot_count": 2, "energy": 0.7, "operator": "tonal",
         "dominant_treatment": "hold", "said": "opening words"},
        {"title": "Ad", "function": "other", "first_shot": 2, "last_shot": 3,
         "t0": 10, "t1": 40, "shot_count": 2, "energy": 0.4, "operator": "literal",
         "dominant_treatment": "hold", "said": "sponsor"},
        {"title": "Close", "function": "close", "first_shot": 4, "last_shot": 5,
         "t0": 40, "t1": 60, "shot_count": 2, "energy": 0.3, "operator": "literal",
         "dominant_treatment": "hold", "said": "closing words"},
    ]
    return {"duration": 60.0, "video_path": "x.mp4", "beats": beats,
            "shot_count": 6}, "synthetic"


def test_template_export(extract, td: Path):
    from src.nolan.deconstruct.export import export_scene_plan_template
    from src.nolan.orchestrator.template_match import match_scene_plan_template

    dest = td / "assets" / "templates" / "scene_plans"
    res = export_scene_plan_template(extract, "odyssey-test", "Odyssey Doc", dest_root=dest)
    tdir = Path(res["path"])
    meta = json.loads((tdir / "meta.json").read_text(encoding="utf-8"))
    skel = json.loads((tdir / "skeleton.json").read_text(encoding="utf-8"))
    assert meta["kind"] == "scene_plan" and meta["provenance"]["derived_from_deconstruction"] == "odyssey-test"
    assert len(skel["sections"]) == len(extract["beats"]) == res["sections"]
    for sec in skel["sections"]:
        assert sec["pacing"] in ("fast", "standard", "slow")
        assert sec["duration_pct"][0] <= sec["duration_pct"][1]
        assert sec["beat_count_hint"][0] >= 1
    assert (tdir / "template.md").exists()

    # the Director's matcher can actually load + score it
    cands = match_scene_plan_template(
        "documentary", int(extract["duration"]),
        "a mythology documentary explained with paintings", td)
    assert cands and any(c.template_id == res["id"] for c in cands), \
        [getattr(c, "template_id", None) for c in cands]
    print(f"template export OK — {res['id']} ({res['sections']} sections), matcher scores it")


def test_clone(extract, td: Path):
    from src.nolan.deconstruct.clone import clone_to_script_project

    res = clone_to_script_project(extract, "odyssey-test", subject="The Aeneid",
                                  style_id="channel-great-books-explained",
                                  target_minutes=6, store_root=td / "projects")
    pdir = td / "projects" / res["project_slug"]
    assert (pdir / "project.yaml").exists() and (pdir / "script.md").exists()
    bm = (pdir / "scriptgen" / "beatmap.md").read_text(encoding="utf-8")
    assert "CLONED STRUCTURE" in bm and "do NOT re-derive" in bm
    assert "pace:" in bm and "words" in bm
    n_ads = len([b for b in extract["beats"] if b.get("function") == "other"])
    if n_ads:
        assert "sponsor slot" in bm, "ad beat should be noted, not cloned"
        for b in extract["beats"]:
            if b.get("function") == "other":
                assert f"## {b['title']}" not in bm, "ad beat must not be a cloned beat"
    # word budgets ≈ target
    import re
    words = [int(m) for m in re.findall(r"~(\d+) words", bm)]
    total = sum(words)
    assert abs(total - 6 * 150) <= 0.15 * 6 * 150, f"budgets {total} vs target {900}"
    meta = json.loads((pdir / "scriptgen" / "meta.json").read_text(encoding="utf-8"))
    assert meta["cloned_from_deconstruction"] == "odyssey-test"
    ref = json.loads((pdir / "scriptgen" / "reference_structure.json").read_text(encoding="utf-8"))
    assert ref["beats"] and "operator" in ref["beats"][0]

    # the dispatched brief must carry the structure-override clause (the live
    # Aeneid run proved the default brief lets the agent supersede the clone)
    from src.nolan.scriptwriter import ScriptProjectStore, draft_task, v3_task
    store = ScriptProjectStore(td / "projects")
    for builder in (v3_task, draft_task):
        t = builder(res["project_slug"], store)
        assert "CLONED beat structure" in t and "Do NOT rewrite" in t, builder.__name__
        assert "Plan the retention curve BEFORE drafting" not in t, builder.__name__
    print(f"clone OK — project {res['project_slug']}: {res['beats']} beats, "
          f"budget {total}w ≈ {6*150}w, provenance + reference + override brief")


def test_case_studies_brief():
    from src.nolan.video_style.tasks import video_style_synthesis_task
    t = video_style_synthesis_task("s", "S", ["a"], case_studies=["video_deconstructions/x/breakdown.md"])
    assert "Deconstruction case studies" in t and "video_deconstructions/x/breakdown.md" in t
    t2 = video_style_synthesis_task("s", "S", ["a"])
    assert "Deconstruction case studies" not in t2
    print("case-studies brief OK — block present iff studies passed")


def test_retrieval_enrichment(td: Path):
    from src.nolan.indexer import VideoIndex
    from src.nolan.evoke_broll import _library_score_prompt
    from src.nolan.motion_select import _motion_prompt

    idx = VideoIndex(td / "r.db")
    vid = idx.add_video(path="v.mp4", duration=30.0, checksum="c", fingerprint="fp-r")
    idx.add_shots_bulk(vid, [
        {"shot_index": 0, "timestamp_start": 0.0, "timestamp_end": 10.0,
         "camera_motion": "push-in", "treatment_hint": "ken-burns-in",
         "asset_type": "painting", "rep_timestamp": 5.0, "facts_version": 1},
        {"shot_index": 1, "timestamp_start": 10.0, "timestamp_end": 30.0,
         "camera_motion": "static", "treatment_hint": "hold",
         "asset_type": "live-footage", "rep_timestamp": 20.0, "facts_version": 1},
    ])
    over = idx.get_shots_overlapping("v.mp4", 8.0, 12.0)
    assert len(over) == 2, over                     # spans the boundary
    assert idx.get_shots_overlapping("v.mp4", 12.0, 20.0)[0]["camera_motion"] == "static"
    assert idx.get_shots_overlapping("missing.mp4", 0, 5) == []

    cand = {"desc": "a classical painting of a storm",
            "shot_facts": {"asset_type": "painting", "camera_motion": "push-in",
                           "treatment_hint": "ken-burns-in"}}
    p = _library_score_prompt("line", "goal", "", "", [cand])
    assert "measured:" in p and "push-in" in p
    p2 = _library_score_prompt("line", "goal", "", "", [{"desc": "plain"}])
    assert "measured:" not in p2
    mp = _motion_prompt("line", "goal", "tonal", [dict(cand, kind="library")])
    assert "measured in source" in mp and "ken-burns-in" in mp
    print("retrieval enrichment OK — overlap lookup + facts in score & motion prompts")


def test_new_hub_routes(td: Path):
    from src.nolan.indexer import VideoIndex
    VideoIndex(td / "lib.db")
    from src.nolan.hub import create_hub_app
    app = create_hub_app(db_path=td / "lib.db")
    routes = {getattr(r, "path", "") for r in app.routes}
    for p in ("/api/deconstruct/{slug}/export-template", "/api/deconstruct/{slug}/clone"):
        assert p in routes, f"missing {p}"
    print("hub routes OK — export-template + clone registered")


def main():
    extract, src = load_extract()
    print(f"extract source: {src} ({len(extract['beats'])} beats)")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        td = Path(td)
        test_template_export(extract, td)
        test_clone(extract, td)
        test_case_studies_brief()
        test_retrieval_enrichment(td)
        test_new_hub_routes(td)
    print("\nOK - deconstruction integrations verified.")


if __name__ == "__main__":
    main()
