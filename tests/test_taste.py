"""The taste feedback loop — anti-lock-in mechanics pinned.

The owner's stated fear: early videos are merely OK, and hardened OK-rules
would cage the system at a local maximum. These tests pin the design that
prevents it: tiered language (prefer vs locked), the experiment clause, the
evidence gate, retirability, and test-project exclusion.
"""

import asyncio
import json

import pytest

import nolan.taste as taste


@pytest.fixture(autouse=True)
def _isolated_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(taste, "PROFILES", tmp_path)
    monkeypatch.setattr(taste, "RULES_PATH", tmp_path / "taste.json")
    monkeypatch.setattr(taste, "LEDGER_PATH", tmp_path / "ledger.jsonl")


def _rule(**kw):
    base = {"scope": "channel", "stage": "slides",
            "rule": "Prefer bar_chart over statistic when comparing quantities",
            "why": "test", "evidence": [], "confidence": 0.6,
            "status": "active", "source": "owner"}
    base.update(kw)
    return taste.upsert_rule(base)


# --- lifecycle -----------------------------------------------------------------

def test_rule_lifecycle_and_validation():
    r = _rule(status="proposed")
    assert taste.load_rules()[0]["status"] == "proposed"
    taste.set_rule_status(r["id"], "active")
    taste.set_rule_status(r["id"], "locked")
    taste.set_rule_status(r["id"], "retired")
    assert taste.load_rules()[0]["status"] == "retired"
    with pytest.raises(ValueError):
        taste.set_rule_status(r["id"], "doctrine")
    with pytest.raises(ValueError):
        taste.upsert_rule({"scope": "galaxy", "stage": "slides", "rule": "x",
                           "status": "active", "source": "owner",
                           "confidence": 0.5, "evidence": []})


# --- anti-lock-in: the language tiers ----------------------------------------------

def test_guidance_tiers_prefer_vs_locked():
    _rule(rule="Use bar charts for comparisons")                  # active
    _rule(rule="Never use tweet cards", status="locked")
    _rule(rule="Invisible until accepted", status="proposed")
    _rule(rule="Old habit", status="retired")
    g = taste.guidance_for("slides")
    assert "PREFER" in g and "deviate when you see a clearly better" in g
    assert "[LOCKED" in g and "Never use tweet cards" in g
    assert "Invisible until accepted" not in g
    assert "Old habit" not in g
    assert "EXPERIMENT" in g                     # the standing escape hatch


def test_guidance_scopes_and_empty():
    assert taste.guidance_for("motion") == ""    # no rules -> clean prompt
    _rule(stage="motion", scope="type:essay-doc-explainer-v1",
          rule="Lean on stat-over for money numbers")
    assert taste.guidance_for("motion", "") == ""            # type rule hidden
    g = taste.guidance_for("motion", "essay-doc-explainer-v1")
    assert "stat-over" in g and "essay-doc-explainer-v1" in g


# --- ledger + exclusion --------------------------------------------------------------

def test_test_projects_are_excluded(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "project.yaml").write_text("name: t\ntest_project: true\n",
                                       encoding="utf-8")
    ok = taste.record_taste_event(project="proj", stage="slides",
                                  context="c", proposed="a", chose="b",
                                  project_path=proj)
    assert ok is False and taste.load_ledger() == []
    (proj / "project.yaml").write_text("name: t\n", encoding="utf-8")
    assert taste.record_taste_event(project="proj", stage="slides",
                                    context="c", proposed="a", chose="b",
                                    project_path=proj) is True
    assert len(taste.load_ledger()) == 1


# --- the evidence gate ------------------------------------------------------------------

class _FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    async def generate(self, prompt):
        return json.dumps(self.payload)


def _seed_ledger(n, projects=("p1", "p2")):
    for i in range(n):
        taste.record_taste_event(project=projects[i % len(projects)],
                                 stage="slides", context=f"s{i}",
                                 proposed="statistic", chose="bar_chart")


def test_distiller_evidence_gate_rejects_thin_proposals():
    _seed_ledger(4)
    llm = _FakeLLM({"proposals": [
        {"scope": "channel", "stage": "slides",
         "rule": "Prefer bar_chart", "why": "pattern", "event_idx": [0, 1, 2, 3]},
        {"scope": "channel", "stage": "slides",
         "rule": "Superstition from one event", "why": "?", "event_idx": [0]},
    ]})
    out = asyncio.run(taste.distill(llm))
    assert len(out["proposed"]) == 1
    assert out["proposed"][0]["status"] == "proposed"     # awaits the human
    assert len(out["rejected"]) == 1 and "evidence gate" in out["rejected"][0]["reason"]


def test_distiller_single_project_rejected():
    _seed_ledger(4, projects=("only-one",))
    llm = _FakeLLM({"proposals": [{"scope": "channel", "stage": "slides",
                                   "rule": "r", "why": "w",
                                   "event_idx": [0, 1, 2, 3]}]})
    out = asyncio.run(taste.distill(llm))
    assert out["proposed"] == [] and len(out["rejected"]) == 1


def test_distiller_empty_ledger_is_honest():
    out = asyncio.run(taste.distill(_FakeLLM({})))
    assert "ledger empty" in out["note"]
