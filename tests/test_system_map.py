"""The Live NOLAN Map — the catalog must be true, not decorative."""

from nolan.system_map import ARTIFACTS, ORGAN_MODULES, build_map


def test_catalog_builds_offline():
    m = build_map(ping=False)
    assert len(m["spine"]) >= 10
    assert {s["name"] for s in m["spine"]} >= {"voiceover", "soundtrack", "render"}
    assert all(s["purpose"] for s in m["spine"]), "every step needs a docstring"


def test_every_listed_organ_imports():
    m = build_map(ping=False)
    missing = [o["module"] for o in m["organs"] if not o["ok"]]
    assert not missing, f"map lists organs that no longer exist: {missing}"
    assert all(o["purpose"] for o in m["organs"] if o["ok"]), \
        "every organ needs a module docstring"


def test_spine_matches_pipeline_steps():
    from nolan.orchestrator.director import PIPELINE_STEPS
    m = build_map(ping=False)
    assert [s["name"] for s in m["spine"]] == PIPELINE_STEPS


def test_skills_registry_readable():
    m = build_map(ping=False)
    assert m["skills"]["count"] > 0 and m["skills"]["skills"]


def test_bridges_live_wires():
    """Every 'live' NOLAN<->HyperFrames bridge must have its wire on disk — the Bridge
    tab can't lie. 'lab' bridges (working-tree / vendored, may be absent) are exempt."""
    m = build_map(ping=False)
    assert m["bridges"], "no bridges listed"
    broken = [b["id"] for b in m["bridges"] if b.get("stage") == "live" and not b["ok"]]
    assert not broken, f"live bridges with a missing wire: {broken}"


def test_hyperframes_introspected():
    """When HyperFrames is installed, the map lists its skills/workflows/pipeline."""
    hf = build_map(ping=False)["hyperframes"]
    if hf.get("ok"):  # optional integration — only assert when the skills are present
        assert any(s["ok"] for s in hf["domain_skills"]), "no HyperFrames domain skills"
        assert any(w["ok"] for w in hf["workflows"]), "no HyperFrames workflows"
        assert hf["pipeline"], "HyperFrames pipeline missing"


def test_surfaces_verified_against_app(tmp_path):
    from pathlib import Path
    from nolan.hub import create_hub_app
    db = tmp_path / "stub.db"          # db-gated routes (library/clips) register
    db.write_bytes(b"")
    app = create_hub_app(db_path=db, projects_dir=Path("projects"))
    m = build_map(app=app, ping=False)
    bad = [s["label"] for s in m["surfaces"] if s["ok"] is False]
    badlabs = [l["label"] for l in m["labs"] if l["ok"] is False]
    assert not bad and not badlabs, f"map points at missing routes: {bad + badlabs}"


def test_bridge_kb_docs_exist():
    """Every knowledge-base doc listed on the Bridge tab must exist on disk — the KB section
    can't cite a note that isn't there (same honesty rule as the live bridges)."""
    m = build_map(ping=False)
    kb = m.get("bridge_kb", [])
    assert kb, "no Bridge knowledge-base docs listed"
    missing = [k["id"] for k in kb if not k["ok"]]
    assert not missing, f"Bridge KB lists docs that don't exist: {missing}"
