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
