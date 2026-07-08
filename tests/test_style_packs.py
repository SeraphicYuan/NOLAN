"""Style packs — per-format design system + show bible (quality program step 6).

Pins: every SHIPPED pack validates against the live registries (curation
can't rot), resolution precedence (project override → template match →
default), brief integration (theme promotion, grade/pacing fills, guide
wins when it speaks), generated prompt guidance, and the script-craft
linter rules the format section drives.
"""

import json
from pathlib import Path

import pytest

from nolan.style_packs import (
    format_rules, get_pack, load_packs, motion_guidance, pack_for,
    slides_guidance, validate_pack,
)

REPO = Path(__file__).resolve().parents[1]


# --- shipped packs are honest --------------------------------------------------

def test_every_shipped_pack_validates():
    packs = load_packs()
    assert {"default", "historical-narrative", "explainer-punchy"} <= set(packs)
    for pid, p in packs.items():
        assert validate_pack(p) == [], f"pack {pid} fails validation"


def test_validate_catches_unknown_ids():
    bad = {"id": "x", "visual": {
        "motion_preferred": ["no-such-effect"],
        "templates_preferred": ["no_such_template"],
        "themes_preferred": ["no-such-theme"],
        "grade": {"grade": "sepia"},
        "pacing": "frantic"},
        "format": {"lint": {"no_such_rule": True}}}
    errs = "\n".join(validate_pack(bad))
    for frag in ("unknown motion effect", "unknown layout template",
                 "unknown theme", "grade.grade", "pacing", "unknown rule"):
        assert frag in errs, frag


# --- resolution ----------------------------------------------------------------

def test_pack_resolution_precedence(tmp_path):
    # template match
    p = pack_for(tmp_path, template_id="liu-xiu-historical-narrative")
    assert p["id"] == "historical-narrative"
    # project.yaml override wins over template match
    (tmp_path / "project.yaml").write_text("style_pack: explainer-punchy\n",
                                           encoding="utf-8")
    p = pack_for(tmp_path, template_id="liu-xiu-historical-narrative")
    assert p["id"] == "explainer-punchy"
    # nothing matches -> default
    assert pack_for(tmp_path / "nowhere", template_id="zzz")["id"] == "default"


# --- brief integration ----------------------------------------------------------

@pytest.mark.asyncio
async def test_brief_carries_pack_and_fills_defaults(tmp_path, monkeypatch):
    from nolan import project_brief as pb

    async def fake_desc(guide, llm):
        return {"keywords": ["history"], "tone": "warm",
                "accent_hex": None, "music_mood": "somber",
                "pacing": {"avg_scene_s_min": 4, "avg_scene_s_max": 10},
                "grade": {"grade": "none"}}

    def fake_rank(text, tone=""):
        return [{"id": "midnight-press", "score": 0.9, "why": ["dark"]},
                {"id": "kraft-paper", "score": 0.8, "why": ["warm paper"]},
                {"id": "newsroom", "score": 0.5, "why": ["news"]}]

    monkeypatch.setattr(pb, "_extract_descriptors", fake_desc)
    monkeypatch.setattr(pb, "rank_themes", fake_rank)
    (tmp_path / "style_guide.md").write_text("# style", encoding="utf-8")
    brief = await pb.compile_brief(tmp_path,
                                   template_id="liu-xiu-historical-narrative")
    assert brief["pack"] == "historical-narrative"
    # theme promotion: kraft-paper (pack-preferred) beat midnight-press
    assert brief["theme"] == "kraft-paper"
    assert any("pack:" in w for w in brief["theme_why"])
    # pack filled the silent defaults
    assert brief["grade"]["grade"] == "warm"
    assert brief["pacing_profile"] == "contemplative"   # tempo profile from pack
    assert brief["pacing"]["avg_scene_s_min"] == 4      # duration window untouched


@pytest.mark.asyncio
async def test_guide_wins_when_it_speaks(tmp_path, monkeypatch):
    from nolan import project_brief as pb

    async def fake_desc(guide, llm):
        return {"keywords": [], "tone": "", "accent_hex": None,
                "music_mood": "epic",
                "pacing": {"avg_scene_s_min": 3, "avg_scene_s_max": 7},
                "grade": {"grade": "noir", "vignette": 0.5}}

    monkeypatch.setattr(pb, "_extract_descriptors", fake_desc)
    monkeypatch.setattr(pb, "rank_themes", lambda t, tone="": [
        {"id": "kraft-paper", "score": 0.9, "why": ["paper"]}])
    (tmp_path / "style_guide.md").write_text("# style", encoding="utf-8")
    brief = await pb.compile_brief(tmp_path,
                                   template_id="liu-xiu-historical-narrative")
    assert brief["grade"]["grade"] == "noir"      # guide spoke — pack yields


# --- the live-run incident: template id lives on template_provenance ---------

def test_director_reads_template_id_from_provenance():
    """aeneid-2beat-v2 live run: brief compile failed with 'DirectorState has
    no attribute style_template_id' — the id lives on state.template_provenance.
    Pin both the attribute path and the absence of the bad access."""
    from nolan.orchestrator.state import TemplateProvenance
    assert hasattr(TemplateProvenance(), "style_template_id")
    src = (REPO / "src/nolan/orchestrator/director.py").read_text(encoding="utf-8")
    assert "state.style_template_id" not in src, (
        "director accesses style_template_id on DirectorState — it lives on "
        "state.template_provenance")


# --- generated guidance ----------------------------------------------------------

def test_guidance_is_generated_from_the_pack():
    p = get_pack("historical-narrative")
    mg = motion_guidance(p)
    assert "timeline" in mg and "k-shape" in mg and "PREFER" in mg and "AVOID" in mg
    sg = slides_guidance(p)
    assert "source_citation" in sg
    assert motion_guidance(get_pack("default")) == ""   # no curation, no noise


# --- script-craft linter rules ----------------------------------------------------

def _plan(hook, mid_out="And so the trade continued for years.",
          last="The end."):
    return {"schema_version": 2, "sections": {
        "open": [{"id": "s1", "narration_excerpt": hook,
                  "start_seconds": 0, "end_seconds": 8, "visual_type": "b-roll"}],
        "mid": [{"id": "s2", "narration_excerpt": mid_out,
                 "start_seconds": 8, "end_seconds": 16, "visual_type": "b-roll"}],
        "close": [{"id": "s3", "narration_excerpt": last,
                   "start_seconds": 16, "end_seconds": 24, "visual_type": "b-roll"}],
    }}


def test_script_craft_rules_fire_and_pass():
    from nolan.retention import lint_plan
    brief = {"pack": "historical-narrative"}

    flat = lint_plan(_plan("Venice is a city in Italy. It has canals."), brief)
    rules = {f["rule"] for f in flat["findings"]}
    assert {"hook-question", "object-anchor", "section-out-tension"} <= rules

    good = lint_plan(_plan(
        "For 250 years a secret hid in these two letters. Why did no one "
        "speak of them?",
        mid_out="But what the archivists found next made no sense at all…"),
        brief)
    rules = {f["rule"] for f in good["findings"]}
    assert "hook-question" not in rules
    assert "object-anchor" not in rules
    assert "section-out-tension" not in rules


def test_default_pack_skips_object_anchor():
    from nolan.retention import lint_plan
    r = lint_plan(_plan("Why does the internet feel broken?"), {"pack": "default"})
    rules = {f["rule"] for f in r["findings"]}
    assert "object-anchor" not in rules            # default pack doesn't require it
    assert "hook-question" not in rules            # the hook does ask


def test_format_rules_shape():
    fr = format_rules(get_pack("historical-narrative"))
    assert fr["pack"] == "historical-narrative"
    assert fr["hook"] == "mystery-object" and fr["ending"] == "question"
    assert fr["lint"]["object_anchor"] is True


# --- editorial-print (meta-style P2) + texture defaults wiring ---------------------

def test_editorial_print_pack_ships_and_validates():
    from nolan.style_packs import get_pack, validate_pack
    pack = get_pack("editorial-print")
    assert pack, "style_packs/editorial-print.json missing"
    assert validate_pack(pack) == []
    v = pack["visual"]
    assert "cutout-collage" in v["motion_preferred"]
    assert v["texture_defaults"]["edge"] == "boil"
    assert v["grade"]["paper"] == 0.7


def test_texture_defaults_validation_is_loud():
    from nolan.style_packs import validate_pack
    errs = validate_pack({"id": "x", "visual": {
        "texture_defaults": {"jitter": {"fps": 99}, "edge": "wobbly"}}})
    assert any("texture_defaults" in e and "outside" in e for e in errs)
    assert any("wobbly" in e for e in errs)


def test_premium_applies_pack_texture_to_graphic_steps_only(tmp_path, monkeypatch):
    """Pack texture reaches kinetic-type steps; footage and authored
    scene.texture are never touched (locks beat pack priors)."""
    from nolan import premium_render as pr
    monkeypatch.setattr(pr, "_slice_wav", lambda *a, **k: tmp_path / "x.wav")
    monkeypatch.setattr(pr, "_step_words", lambda *a, **k: ([], []))
    monkeypatch.setattr(pr, "_wav_duration", lambda w: 6.0)
    monkeypatch.setattr(pr, "_expand_shots", lambda scene, *a, **k: [
        ({"a": "Kinetic", "b": "Video", "c": "Kinetic"}[scene["id"]], {}, 90)])
    scenes = [
        {"id": "a", "start_seconds": 0.0, "end_seconds": 2.0},
        {"id": "b", "start_seconds": 2.0, "end_seconds": 4.0},
        {"id": "c", "start_seconds": 4.0, "end_seconds": 6.0,
         "texture": {"jitter": {"fps": 6, "amp": 2}}},
    ]
    job = pr.build_section_job(
        "sec", scenes, project_path=tmp_path, section_wav=tmp_path / "s.wav",
        section_start=0.0, out_name="o.mp4", work_dir=tmp_path,
        texture_defaults={"jitter": {"fps": 10, "amp": 4}, "edge": "boil"})
    steps = job["props"]["steps"]
    assert steps[0]["jitter"] == {"fps": 10, "amp": 4.0} and steps[0]["edge"] == "boil"
    assert "jitter" not in steps[1] and "edge" not in steps[1]
    assert steps[2]["jitter"] == {"fps": 6, "amp": 2.0} and "edge" not in steps[2]
