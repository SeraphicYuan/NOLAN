"""Tests for the rhythm/tempo foundation: ScriptContext parsing + the Editorial Arc pass.

Hermetic — builds a tiny project workspace in a tmp dir; no LLM, no network. Covers the
deterministic core (markdown parsing, beatmap/facts alignment, rule-based tempo arc)."""

import pytest

from nolan.script_context import ScriptContext
from nolan.tempo_plan import design_tempo, profile_for, BeatTempo


SCRIPT_MD = """# Video Script

**Total Duration:** 3:00

---

## Hook — the shock [0:00]

An opening line that grabs. A second sentence that pivots.

## The build [1:00]

Fact one. Fact two. Fact three, delivered fast.

## The close [2:30]

A slow, quiet landing. Let it breathe.
"""

BEATMAP_MD = """# Beat-map — Test

**Angle (spine):** The one-line spine of the piece.

---

## Hook · pace:d · covers:[S1] · serves-spine: open on the void, then pivot
## The build · pace:a · covers:[S1,S2] · serves-spine: accelerated fact cluster
## The close · pace:d · covers:[S1] · serves-spine: contemplative unknowing close
"""

FACTS_MD = """# Fact sheet — Test

## Beat: HOOK  (the grab)

- A striking fact for the hook — src:[S1] · conf:verified

## Beat: THE BUILD

- Build fact one — src:[S1] · conf:verified
- Build fact two — src:[S2] · conf:verified
"""


def _make_project(tmp_path):
    p = tmp_path / "proj"
    (p / "scriptgen").mkdir(parents=True)
    (p / "script.md").write_text(SCRIPT_MD, encoding="utf-8")
    (p / "scriptgen" / "beatmap.md").write_text(BEATMAP_MD, encoding="utf-8")
    (p / "scriptgen" / "facts.md").write_text(FACTS_MD, encoding="utf-8")
    (p / "scriptgen" / "meta.json").write_text(
        '{"slug": "proj", "subject": "Test Subject", "style_id": "channel-great-books-explained",'
        ' "target_minutes": 3.0}', encoding="utf-8")
    return p


class TestScriptContext:
    def test_parses_beats_with_timecodes(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        assert [b.title for b in ctx.beats] == ["Hook — the shock", "The build", "The close"]
        assert ctx.beats[0].timecode == "0:00"
        assert ctx.beats[1].timecode == "1:00"
        assert "grabs" in ctx.beats[0].narration

    def test_attaches_beatmap_pace(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        assert ctx.beats[0].pace == "decelerate"
        assert ctx.beats[1].pace == "accelerate"
        assert ctx.beats[2].pace == "decelerate"
        assert ctx.beats[1].covers == ["S1", "S2"]
        assert "fact cluster" in ctx.beats[1].serves

    def test_attaches_facts(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        assert any("striking fact" in f for f in ctx.beats[0].facts)
        assert len(ctx.beats[1].facts) == 2

    def test_meta_and_angle(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        assert ctx.subject == "Test Subject"
        assert ctx.angle == "The one-line spine of the piece."
        assert ctx.style_id == "channel-great-books-explained"

    def test_brief_and_beat_context(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        brief = ctx.brief()
        assert "SUBJECT: Test Subject" in brief
        assert "pace:decelerate" in brief
        bc = ctx.beat_context(1)
        assert "beat 2 of 3" in bc
        assert "THIS BEAT" in bc

    def test_missing_beatmap_degrades(self, tmp_path):
        p = tmp_path / "bare"
        (p / "scriptgen").mkdir(parents=True)
        (p / "script.md").write_text(SCRIPT_MD, encoding="utf-8")
        ctx = ScriptContext.load(p)
        assert len(ctx.beats) == 3
        assert all(b.pace == "" for b in ctx.beats)  # no beatmap → no pace, no crash

    def test_find_beat(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        b = ctx.find_beat("Fact one. Fact two.")
        assert b is not None and b.title == "The build"


class TestTempoPlan:
    def test_profile_inference(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        assert profile_for(ctx) == "punchy"                 # great-books → explainer/punchy
        assert profile_for(ctx, "contemplative") == "contemplative"

    def test_rule_plan_shape(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        plan = design_tempo(ctx)                            # no llm → rules
        assert plan.source == "rules"
        assert len(plan.beats) == 3
        assert all(isinstance(b, BeatTempo) for b in plan.beats)
        assert all(0.0 <= b.energy <= 1.0 for b in plan.beats)
        assert all(b.transition in ("cut", "dissolve", "fade") for b in plan.beats)
        assert all(b.motion_speed in ("slow", "medium", "fast") for b in plan.beats)

    def test_accelerate_beat_is_hotter(self, tmp_path):
        ctx = ScriptContext.load(_make_project(tmp_path))
        plan = design_tempo(ctx)
        # the middle beat is pace:accelerate → should carry more energy than the decelerate close
        assert plan.beats[1].energy > plan.beats[2].energy

    def test_empty_script(self, tmp_path):
        p = tmp_path / "empty"
        (p / "scriptgen").mkdir(parents=True)
        (p / "script.md").write_text("# Video Script\n", encoding="utf-8")
        plan = design_tempo(ScriptContext.load(p))
        assert plan.beats == []


class TestApplyToPlan:
    def test_annotates_scenes_by_section(self, tmp_path):
        from nolan.scenes import Scene, ScenePlan
        from nolan.tempo_plan import apply_to_plan
        ctx = ScriptContext.load(_make_project(tmp_path))
        tempo = design_tempo(ctx)                            # rules
        # a scene plan whose SECTION titles == the script beat titles
        plan = ScenePlan()
        plan.sections["Hook — the shock"] = [Scene(id="s1", narration_excerpt="x"),
                                             Scene(id="s2", narration_excerpt="y")]
        plan.sections["The build"] = [Scene(id="s3", narration_excerpt="z")]
        plan.sections["The close"] = [Scene(id="s4", narration_excerpt="w")]
        res = apply_to_plan(plan, tempo)
        assert res == {"sections": 3, "scenes": 4, "matched": 4}
        # every scene got a transition + energy + motion_speed (was None before)
        for sc in plan.all_scenes:
            assert sc.transition in ("cut", "dissolve", "fade")
            assert sc.energy is not None
            assert sc.motion_speed in ("slow", "medium", "fast")
        # the accelerate "build" beat should be hotter than the decelerate "close"
        build = plan.sections["The build"][0]
        close = plan.sections["The close"][0]
        assert build.energy > close.energy

    def test_timecode_range_stripped(self, tmp_path):
        # FLOW-style headings use a range "[0:00 - 0:35]"; the title must come out clean
        p = tmp_path / "rng"
        (p / "scriptgen").mkdir(parents=True)
        (p / "script.md").write_text(
            "# Video Script\n\n## Hook [0:00 - 0:35]\n\nText.\n\n## Close [7:00 - 7:21]\n\nEnd.\n",
            encoding="utf-8")
        ctx = ScriptContext.load(p)
        assert [b.title for b in ctx.beats] == ["Hook", "Close"]
        assert ctx.beats[0].timecode == "0:00"

    def test_apply_to_flow_spec_modulates_relatively(self, tmp_path):
        from nolan.tempo_plan import apply_to_flow_spec
        ctx = ScriptContext.load(_make_project(tmp_path))
        tempo = design_tempo(ctx)                            # 3 beats: decel/accel/decel
        spec = {"beats": [
            {"segment": "b0", "introHold": 50, "maxZoom": 1.5},   # low-energy hook
            {"segment": "b1", "introHold": 50, "maxZoom": 1.5},   # accelerate build
            {"segment": "b2", "block": "TextCard"},               # no motion knobs
        ]}
        res = apply_to_flow_spec(spec, tempo)
        assert res == {"beats": 3, "matched": 3}
        # every beat stamped with metadata
        for b in spec["beats"]:
            assert b["_energy"] is not None and b["_transition"] in ("cut", "dissolve", "fade")
        # the accelerate beat cuts in faster (shorter hold) than the decelerate hook
        assert spec["beats"][1]["introHold"] < spec["beats"][0]["introHold"]
        # values stay near the block's baseline (modulated, not overwritten to absolutes)
        assert 15 <= spec["beats"][0]["introHold"] <= 70
        # a block without the knobs is left alone (no invented fields)
        assert "introHold" not in spec["beats"][2] and "maxZoom" not in spec["beats"][2]

    def test_roundtrip_preserves_tempo(self, tmp_path):
        from nolan.scenes import Scene, ScenePlan
        from nolan.tempo_plan import apply_to_plan
        ctx = ScriptContext.load(_make_project(tmp_path))
        plan = ScenePlan()
        plan.sections["The build"] = [Scene(id="s3", narration_excerpt="z")]
        apply_to_plan(plan, design_tempo(ctx))
        out = tmp_path / "sp.json"
        plan.save(str(out))
        reloaded = ScenePlan.load(str(out))
        sc = reloaded.sections["The build"][0]
        assert sc.energy is not None and sc.motion_speed in ("slow", "medium", "fast")
