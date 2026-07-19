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
