"""B1: script→voice written-state readiness (guards voicing a scaffold)."""

from nolan.scriptwriter import ScriptProjectStore


def test_vo_readiness_transitions(tmp_path):
    st = ScriptProjectStore(tmp_path)
    slug = "de-beers"
    st.project_dir(slug).mkdir(parents=True, exist_ok=True)

    # no script.md → not ready
    assert st.vo_readiness(slug) == {"written": False, "words": 0, "promoted_draft": 0}

    # a real script (≥1 `## ` beat) → ready, words counted
    st.script_path(slug).write_text(
        "# Video Script\n**Total Duration:** 0:30\n---\n"
        "## Cold open\nFor a century, one company controlled the supply.\n",
        encoding="utf-8")
    r = st.vo_readiness(slug)
    assert r["written"] is True and r["words"] >= 8

    # scaffold placeholder → not ready (no beats)
    st.script_path(slug).write_text("# Video Script\n\nScript not written yet\n", encoding="utf-8")
    assert st.vo_readiness(slug)["written"] is False


def test_create_voice_preset(tmp_path):
    """B5: a create-time voice_id lands in project.yaml (resolve_voice_ref reads it) + meta."""
    import json
    import yaml
    st = ScriptProjectStore(tmp_path)
    slug = st.create("P", subject="x", style_id="s", voice_id="narrator-a")
    y = yaml.safe_load(st.project_yaml_path(slug).read_text(encoding="utf-8"))
    m = json.loads(st.meta_path(slug).read_text(encoding="utf-8"))
    assert y["voice_id"] == "narrator-a" and m["voice_id"] == "narrator-a"
    # empty → Auto: no voice_id key in project.yaml
    slug2 = st.create("Q", subject="y", style_id="s")
    y2 = yaml.safe_load(st.project_yaml_path(slug2).read_text(encoding="utf-8"))
    assert "voice_id" not in y2
