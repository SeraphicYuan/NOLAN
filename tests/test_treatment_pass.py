"""Visual treatment pass — full block catalog + motion design gates + auto-shots.

Pins: the 8 new adapters, the TEMPLATES catalog honesty (registry == adapters
== skill doc), the motion_design step's deterministic gate, and tempo's
shots_wanted stamping (bt.shots finally has a reader path).
"""

import re
from pathlib import Path

from nolan.layout_blocks import ADAPTERS, TEMPLATES, adapt

REPO = Path(__file__).resolve().parents[1]


# --- new adapters -----------------------------------------------------------------

def test_bar_chart_adapter():
    block, props = adapt("bar_chart", {
        "title": "AI spend", "unit": "B",
        "bars": [{"label": "2026", "value": 800},
                 {"label": "2027", "value": 1000, "accent": True}]})
    assert block == "BarChart" and len(props["bars"]) == 2
    assert adapt("bar_chart", {"bars": [{"label": "solo", "value": 1}]}) is None


def test_line_chart_adapter_numeric_only():
    block, props = adapt("line_chart", {
        "title": "share of US electricity",
        "points": [[2023, 4.4], [2026, 7.0], [2028, 12.0]], "y_suffix": "%"})
    assert block == "LineChart"
    assert props["series"][0]["points"][0] == {"x": 2023, "y": 4.4}
    assert adapt("line_chart", {"points": [["then", 1], ["now", 2], ["later", 3]]}) is None


def test_pie_data_table_loop_adapters():
    assert adapt("pie_percentage", {"percentage": 43, "title": "water stress"})[0] == "PieCallout"
    assert adapt("pie_percentage", {"percentage": 143}) is None
    blk, props = adapt("data_table", {"columns": ["site", "jobs"],
                                      "rows": [["Stargate", "100"]],
                                      "highlight_row": 0})
    assert blk == "DataTable" and props["highlightRow"] == 0
    assert adapt("loop_diagram", {"nodes": ["cheap", "more use", "more demand"]})[0] == "LoopDiagram"
    assert adapt("loop_diagram", {"nodes": ["a", "b"]}) is None


def test_image_compare_and_detail_loupe():
    blk, props = adapt("image_compare", {
        "left": {"src": "a.jpg", "label": "the boom"},
        "right": {"src": "b.jpg", "label": "the bill"}, "verdict": "both real"})
    assert blk == "ImageCompare" and props["left"]["src"] == "a.jpg"
    assert adapt("image_compare", {"left": {"src": "a.jpg"}, "right": {}}) is None
    blk, props = adapt("detail_loupe", {"src": "doc.png",
                                        "region": [0.1, 0.2, 0.3, 0.2],
                                        "label": "permit by rule"})
    assert blk == "DetailLoupe" and props["region"] == {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.2}


def test_kinetic_headline_adapter():
    blk, props = adapt("kinetic_headline", {"text": "NOBODY VOTED ON THIS",
                                            "accent_words": ["voted"]})
    assert blk == "KineticHeadline" and props["accentWords"] == ["voted"]


# --- catalog honesty ----------------------------------------------------------------

def test_templates_catalog_mirrors_adapters():
    assert set(TEMPLATES) == set(ADAPTERS), (
        "TEMPLATES catalog drifted from ADAPTERS: "
        f"missing={set(ADAPTERS) - set(TEMPLATES)} "
        f"orphans={set(TEMPLATES) - set(ADAPTERS)}")
    for t, meta in TEMPLATES.items():
        assert meta.get("purpose") and meta.get("when_to_use"), t


def test_slide_designer_skill_names_every_template():
    doc = (REPO / "skills" / "orchestrator" / "slide-designer.md").read_text(encoding="utf-8")
    named = set(re.findall(r"`([a-z][a-z0-9_]+)`", doc))
    missing = set(ADAPTERS) - named
    assert missing == set(), f"slide-designer skill doesn't offer: {missing}"


def test_every_new_block_has_budgets():
    from nolan.layout_blocks import BLOCK_BUDGETS
    for blk in ("BarChart", "LineChart", "PieCallout", "DataTable",
                "ImageCompare", "KineticHeadline", "DetailLoupe", "LoopDiagram"):
        assert blk in BLOCK_BUDGETS, f"{blk} renders unbudgeted"


# --- motion design gate ----------------------------------------------------------------

def test_hostable_catalog_excludes_unhostable():
    import json
    from nolan.orchestrator.director import Director
    cat = {e["effect"]: e for e in json.loads(Director._hostable_motion_catalog())}
    assert "stat-over" in cat and "split-screen" in cat and "counter" in cat
    assert "still-motion" not in cat and "line-chart" not in cat
    assert all(e["when_to_use"] for e in cat.values())


def test_motion_design_skill_registered():
    import json
    idx = json.loads((REPO / "skills" / "index.json").read_text(encoding="utf-8"))
    entry = next((s for s in idx["skills"]
                  if s["id"] == "orchestrator.motion-designer"), None)
    assert entry and (REPO / entry["path"]).exists()


def test_pipeline_has_motion_design_step():
    from nolan.orchestrator.director import PIPELINE_STEPS
    assert PIPELINE_STEPS.index("motion_design") == PIPELINE_STEPS.index("slide_designer") + 1


# --- auto-shots stamping -----------------------------------------------------------------

def test_tempo_stamps_shots_wanted():
    from nolan.scenes import Scene, ScenePlan
    from nolan.tempo_plan import BeatTempo, TempoPlan, apply_to_plan
    plan = ScenePlan(sections={"The boom": [Scene(id="s1")]})
    tempo = TempoPlan(slug="t", profile="doc",
                      beats=[BeatTempo(idx=0, title="The boom", energy=0.8,
                                       transition="cut", motion_speed="fast",
                                       shots=3)])
    apply_to_plan(plan, tempo)
    sc = plan.sections["The boom"][0]
    assert sc.extra.get("shots_wanted") == 3
