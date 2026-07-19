"""Sound umbrella honesty — registry, skill, wiring, resolver all agree.

The module contract's enforcement for `sound` (mirrors test_umbrella_skills.py
for motion/pairing/composition): every cue-kind appears in the skill doc,
nothing undocumented hides there, the map serves the catalog, and the shared
resolver turns a kind into a curated file. UMBRELLA_WIRING/CATALOG_CONSUMERS
truth is covered generically by test_umbrella_wiring.py + test_catalog_consumers.py.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _doc_headings(path: Path) -> set:
    return set(re.findall(r"^## ([a-z][a-z0-9-]+)$", path.read_text(encoding="utf-8"), re.M))


def test_sound_skill_covers_every_cue():
    from nolan.sound import KINDS
    headings = _doc_headings(REPO / "skills" / "common" / "sound-craft.md")
    assert set(KINDS) - headings == set(), f"skill doc missing cue-kinds: {set(KINDS) - headings}"
    assert headings - set(KINDS) == set(), f"skill doc lists unregistered kinds: {headings - set(KINDS)}"


def test_every_cue_has_purpose_and_when_to_use():
    from nolan.sound.registry import REGISTRY, FAMILIES
    for c in REGISTRY:
        assert c.purpose.strip() and c.when_to_use.strip(), f"{c.id} lacks craft guidance"
        assert c.family in FAMILIES, f"{c.id} bad family {c.family!r}"
        assert c.duration_preserving, f"{c.id}: sound is additive → must be duration_preserving"


def test_sound_registered_in_index():
    idx = json.loads((REPO / "skills" / "index.json").read_text(encoding="utf-8"))
    ids = {s["id"]: s for s in idx["skills"]}
    assert "common.sound-craft" in ids, "common.sound-craft not in skills/index.json"
    assert (REPO / ids["common.sound-craft"]["path"]).exists()
    assert idx["count"] == len(idx["skills"])


def test_map_serves_sound_catalog():
    from nolan.system_map import _umbrellas
    um = _umbrellas()
    assert isinstance(um.get("sound"), list) and um["sound"], "sound umbrella missing/empty in map"
    for e in um["sound"]:
        assert e.get("when_to_use") and e.get("purpose")


def test_sound_declares_wiring_and_consumers():
    from nolan.system_map import UMBRELLA_WIRING, CATALOG_CONSUMERS
    assert UMBRELLA_WIRING.get("sound", {}).get("authored_by")
    assert UMBRELLA_WIRING.get("sound", {}).get("executed_by")
    assert CATALOG_CONSUMERS.get("sound")


def test_validate_scene_sound():
    from nolan.sound import validate_scene_sound
    assert validate_scene_sound({"id": "s", "data": {"sfx": [{"cue": "whoosh", "at": 1.0}]}}) == []
    assert validate_scene_sound({"id": "s", "sfx": [{"cue": "nope"}]}), "unknown cue must be flagged"


def test_resolve_cue_picks_a_curated_file():
    """The shared resolver both pipelines (Director + HyperFrames) use."""
    from nolan.sound.resolve import resolve_cue, sfx_event_for_cue
    r = resolve_cue("whoosh", vary=False)   # sfx.json (committed manifest) has whooshes
    assert r is not None, "no curated whoosh in the bank manifest"
    assert r["kind"] == "whoosh" and r["file"].endswith(".wav") and r["gain"] > 0
    # (resolve_cue round-robins the top tier for variety, so a fresh call may
    # pick a different whoosh — assert the HF event shape, not file equality)
    ev = sfx_event_for_cue("whoosh", frame=1, offset_s=2.5)
    assert ev and ev["offset_s"] == 2.5 and ev["file"].endswith(".wav")
    assert {"frame", "file", "offset_s", "duration_s", "volume"} <= set(ev)


def test_hf_sfx_merge_preserves_voices():
    """HyperFrames usability: build audio_meta.sfx[] + merge without dropping VO."""
    import pytest
    from nolan.hyperframes.sound import build_audio_meta_sfx, merge_sfx_into_audio_meta
    evs = build_audio_meta_sfx([(2, 3.1, "whoosh"), (2, 5.0, "impact-hard")])
    assert evs and all(e["file"].endswith(".wav") and "offset_s" in e for e in evs)
    am = {"voices": [{"frame": 1, "path": "01.wav"}], "bgm": {"path": "b.mp3"}}
    out = merge_sfx_into_audio_meta(am, evs)
    assert out["voices"] == am["voices"] and out["bgm"] == am["bgm"]  # untouched
    assert out["sfx"] == evs
    with pytest.raises(ValueError):                 # refuses to drop the VO
        merge_sfx_into_audio_meta({"voices": []}, evs)


def test_apply_scene_sfx_end_to_end(tmp_path, monkeypatch):
    """scene.data.sfx → resolve → STAGE into assets/sfx/ → audio_meta.sfx[].

    No underwiring: the executor stages a real file and writes a PROJECT-RELATIVE
    path (what assemble-index mounts), keyed by 1-based frame number, offset =
    aligned scene.start + at, and voices[] survive.
    """
    from nolan.hyperframes import edit as _edit
    from nolan.hyperframes.sound import apply_scene_sfx

    # a minimal comp: audio_meta with voices + a global sfx bank with a whoosh
    (tmp_path / "audio_meta.json").write_text(json.dumps(
        {"voices": [{"frame": 2, "path": "assets/voice/02.wav"}], "bgm": None, "sfx": []}),
        encoding="utf-8")
    bank = tmp_path / "_bank"
    bank.mkdir()
    (bank / "w.wav").write_bytes(b"RIFF....WAVE")
    (bank / "sfx.json").write_text(json.dumps(
        [{"curated": True, "kind": "whoosh", "file": "w.wav", "id": "1", "rating": 5,
          "duration": 0.4}]), encoding="utf-8")

    frame = {"frames": [{"id": "02-x", "scenes": [
        {"id": "s1", "start": 3.0, "data": {"sfx": [{"cue": "whoosh", "at": 0.4}]}}]}]}
    monkeypatch.setattr(_edit, "_project_dir", lambda c: tmp_path)
    monkeypatch.setattr(_edit, "list_frames", lambda c: [{"id": "02-x"}])
    monkeypatch.setattr(_edit, "load_frame_spec", lambda c, fid: (frame, {"i": 0}))
    # point the resolver's bank at our fixture
    monkeypatch.setattr("nolan.sound.resolve.library_dir", lambda: bank)

    res = apply_scene_sfx("dummy")
    assert res["events"] == 1 and res["staged"] == 1 and not res["unresolved"]
    assert (tmp_path / "assets" / "sfx" / "w.wav").exists()        # staged into the comp
    am = json.loads((tmp_path / "audio_meta.json").read_text(encoding="utf-8"))
    assert am["voices"], "voices[] must survive"                    # not regenerated
    ev = am["sfx"][0]
    assert ev["frame"] == 2 and ev["file"] == "assets/sfx/w.wav"    # relative, right frame
    assert ev["offset_s"] == 3.4                                    # scene.start + at
    # idempotent: a second run doesn't duplicate
    apply_scene_sfx("dummy")
    assert len(json.loads((tmp_path / "audio_meta.json").read_text(encoding="utf-8"))["sfx"]) == 1


def test_sfx_design_reads_both_signals(tmp_path, monkeypatch):
    """The pairing operator places from the VISUAL (spec) AND VERBAL (transcript)."""
    from nolan.hyperframes import edit as _edit
    from nolan.hyperframes import sfx_design as D
    (tmp_path / "audio_meta.json").write_text(json.dumps({"voices": [
        {"frame": 1, "words": [
            {"text": "the", "start": 0.0, "end": 0.2}, {"text": "document", "start": 0.3, "end": 0.7},
            {"text": "cost", "start": 3.0, "end": 3.2}, {"text": "$43", "start": 3.3, "end": 3.7},
            {"text": "billion", "start": 3.7, "end": 4.1}]}]}), encoding="utf-8")
    frame = {"frames": [{"id": "01-x", "scenes": [
        {"id": "s1", "type": "document", "start": 0.0, "dur": 3.0, "data": {"cue": 0.4}},
        {"id": "s2", "type": "statement", "start": 3.0, "dur": 2.0,
         "data": {"operative": "billion"}}]}]}
    monkeypatch.setattr(_edit, "_project_dir", lambda c: tmp_path)
    monkeypatch.setattr(_edit, "list_frames", lambda c: [{"id": "01-x"}])
    monkeypatch.setattr(_edit, "load_frame_spec", lambda c, f: (frame, {"i": 0}))

    res = D.design("x")                                    # dry run
    got = {(p["scene"], c["cue"]) for p in res["plan"] for c in p["cues"]}
    assert ("s1", "whoosh") in got and ("s1", "paper") in got  # visual: doc→paper, frame-first→whoosh
    assert ("s2", "cash") in got                               # verbal: spoken $ → cash
    s2 = next(p for p in res["plan"] if p["scene"] == "s2")
    cash = next(c for c in s2["cues"] if c["cue"] == "cash")
    assert 0.0 <= cash["at"] <= 1.0                            # anchored to the spoken figure (~0.3s)


def test_finish_dag_includes_scene_sfx_step():
    """The finish DAG actually calls the executor (not a dangling field)."""
    src = (REPO / "src/nolan/hyperframes/finish.py").read_text(encoding="utf-8")
    assert "apply_scene_sfx" in src, "finish.py no longer runs the scene-sfx step"


def test_assemble_index_mounts_sfx():
    """The render side consumes audio_meta.sfx (else the field is a phantom)."""
    p = REPO / ".agents/skills/faceless-explainer/scripts/assemble-index.mjs"
    if not p.exists():
        import pytest
        pytest.skip("faceless-explainer skill not installed")
    text = p.read_text(encoding="utf-8", errors="replace")
    assert "audio.sfx" in text, "assemble-index no longer mounts audio_meta.sfx"
