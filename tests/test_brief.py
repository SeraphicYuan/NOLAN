"""The Brief Compiler — style prose → validated render tokens.

Pins: the explainable theme ranking, the deterministic no-LLM compile path,
the validation gate, and the three consumer ladders (render look, voice,
music) including the precedence rules (human's project.yaml always wins).
"""

import asyncio
import json

import pytest

from nolan.project_brief import (compile_brief, load_brief, rank_themes,
                         resolve_render_look, save_brief, validate_brief)

GUIDE = """# Style Guide: Test
## Look
Dark industrial editorial — steel-blue server halls, amber accents, bold
grotesk typography for oversized stat numerals. Data-driven tech essay
about AI infrastructure and the power grid.
## Pacing
Average scene 4-6s in the stat run, 8-12s breathing moments.
"""


# --- theme ranking ---------------------------------------------------------------

def test_rank_themes_is_explainable_and_deterministic():
    a = rank_themes("dark technical AI infrastructure essay", tone="dark")
    b = rank_themes("dark technical AI infrastructure essay", tone="dark")
    assert a == b
    assert a[0]["why"], "top pick must carry auditable signals"
    from pathlib import Path
    themes_dir = Path(__file__).resolve().parents[1] / "themes"
    assert (themes_dir / a[0]["id"] / "theme.json").exists()


def test_rank_themes_falls_back_when_nothing_fires():
    r = rank_themes("zzqx vwpk", tone="")
    assert r[0]["id"], "fallback pick must still name a theme"


# --- compile (deterministic path) -------------------------------------------------

def test_compile_brief_without_llm(tmp_path):
    (tmp_path / "style_guide.md").write_text(GUIDE, encoding="utf-8")
    brief = asyncio.run(compile_brief(tmp_path, llm=None))
    assert validate_brief(brief) == []
    assert brief["theme"] and brief["theme_why"]
    assert brief["provenance"]["descriptors_via"] == "deterministic"
    p = save_brief(tmp_path, brief)
    assert json.loads(p.read_text(encoding="utf-8"))["version"] == 1


# --- the gate ---------------------------------------------------------------------

def test_validate_catches_unknown_theme():
    assert any("theme" in p for p in validate_brief(
        {"theme": "no-such-theme", "tone": "", "pacing":
         {"avg_scene_s_min": 4, "avg_scene_s_max": 8}}))


def test_validate_catches_bad_accent_and_pacing():
    base = {"theme": "bold-signal", "tone": ""}
    assert any("accent" in p for p in validate_brief(
        {**base, "accent": "red", "pacing": {"avg_scene_s_min": 4, "avg_scene_s_max": 8}}))
    assert any("pacing" in p for p in validate_brief(
        {**base, "pacing": {"avg_scene_s_min": 9, "avg_scene_s_max": 2}}))


def test_load_brief_ignores_invalid(tmp_path):
    (tmp_path / "brief.json").write_text(
        json.dumps({"theme": "no-such-theme", "tone": "",
                    "pacing": {"avg_scene_s_min": 4, "avg_scene_s_max": 8}}),
        encoding="utf-8")
    assert load_brief(tmp_path) is None       # un-gated values never reach a render


# --- consumers ---------------------------------------------------------------------

def test_render_look_precedence():
    brief = {"theme": "neon-cyber", "accent": "#ff8800"}
    # human's project.yaml theme outranks the brief; accent rides along
    assert resolve_render_look({"theme": "dune"}, brief) == ("dune", "#ff8800")
    assert resolve_render_look({}, brief) == ("neon-cyber", "#ff8800")
    assert resolve_render_look({}, None) == ("bold-signal", None)


def test_music_config_from_brief(tmp_path):
    from nolan.audio_mix import resolve_music_config
    (tmp_path / "project.yaml").write_text("name: t\n", encoding="utf-8")
    # no music key + no brief -> silent
    assert resolve_music_config(tmp_path)["enabled"] is False
    # brief enables auto + supplies mood
    (tmp_path / "brief.json").write_text(json.dumps(
        {"version": 1, "theme": "bold-signal", "tone": "dark",
         "music_mood": "tense pulsing electronic", "accent": None,
         "voice_id": None,
         "pacing": {"avg_scene_s_min": 4, "avg_scene_s_max": 8}}),
        encoding="utf-8")
    cfg = resolve_music_config(tmp_path)
    assert cfg["enabled"] is True and cfg["music"] is None   # auto
    assert cfg["mood"] == "tense pulsing electronic"
    # explicit opt-out is FINAL even with a brief present
    (tmp_path / "project.yaml").write_text("name: t\nmusic: none\n", encoding="utf-8")
    assert resolve_music_config(tmp_path)["enabled"] is False


def test_voice_ladder_brief_between_yaml_and_default(tmp_path, monkeypatch):
    from nolan import voiceover

    class _Lib:
        def __init__(self, *_): pass
        def get(self, vid): return {"ref_text": "r"} if vid in ("yaml-v", "brief-v", "cfg-v") else None
        def sample_path(self, vid): return tmp_path / f"{vid}.wav"

    import nolan.voice_library
    monkeypatch.setattr(nolan.voice_library, "VoiceLibrary", _Lib)

    class _Cfg:
        class tts:
            default_voice = "cfg-v"

    (tmp_path / "brief.json").write_text(json.dumps(
        {"version": 1, "theme": "bold-signal", "tone": "", "accent": None,
         "music_mood": "", "voice_id": "brief-v",
         "pacing": {"avg_scene_s_min": 4, "avg_scene_s_max": 8}}),
        encoding="utf-8")
    # brief-v is not in the real voice library — bypass that check
    monkeypatch.setattr("nolan.project_brief.validate_brief", lambda b: [])
    _, _, vid = voiceover.resolve_voice_ref(tmp_path, _Cfg)
    assert vid == "brief-v"                    # brief beats config default
    (tmp_path / "project.yaml").write_text("voice_id: yaml-v\n", encoding="utf-8")
    _, _, vid = voiceover.resolve_voice_ref(tmp_path, _Cfg)
    assert vid == "yaml-v"                     # human's yaml beats the brief


# --- SOTA #3: the grade block ------------------------------------------------------

def test_compile_brief_includes_gated_grade(tmp_path):
    (tmp_path / "style_guide.md").write_text(GUIDE, encoding="utf-8")
    brief = asyncio.run(compile_brief(tmp_path, llm=None))
    g = brief["grade"]
    assert g["grade"] in ("none", "warm", "cool", "noir", "vivid")
    for k in ("bloom", "grain", "vignette"):
        assert 0.0 <= g[k] <= 1.0


def test_validate_catches_bad_grade():
    base = {"theme": "bold-signal", "tone": "",
            "pacing": {"avg_scene_s_min": 4, "avg_scene_s_max": 8}}
    assert any("grade.grade" in p for p in validate_brief(
        {**base, "grade": {"grade": "teal-orange", "bloom": 0}}))
    assert any("grade.bloom" in p for p in validate_brief(
        {**base, "grade": {"grade": "cool", "bloom": 3.0}}))
    assert validate_brief({**base, "grade": {"grade": "cool", "bloom": 0.3,
                                             "grain": 0.1, "vignette": 0.35}}) == []
