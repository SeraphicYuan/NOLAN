"""Organ / pipeline skills can't rot — each stays bound to the code it documents.

This generalizes the umbrella-skill honesty pattern (test_umbrella_skills.py) to the
per-organ / per-pipeline skills. The contract, in the module contract's spirit
("docs claim, tests enforce"):

  - every `pipeline.*` / `organ.*` skill is registered in skills/index.json;
  - its `documents:` target(s) point at real files (the binding isn't dangling);
  - its `loaded_by:` paths exist;
  - where it `documents: {dag: <module>}`, EVERY `_run("<step>")` step in that driver
    appears in the skill body — a step added to the DAG that nobody documented fails here.

Add a new organ/pipeline skill and it is covered automatically; no per-skill wiring.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INDEX = json.loads((REPO / "skills" / "index.json").read_text(encoding="utf-8"))
SKILLS = {s["id"]: s for s in INDEX["skills"]}

# the skill domains that describe a code organ / pipeline (as opposed to pure craft/prompt)
ORGAN_DOMAINS = ("pipeline", "organ")


def _organ_skills():
    return [s for sid, s in SKILLS.items() if sid.split(".")[0] in ORGAN_DOMAINS]


def _dag_steps(module_rel: str) -> set:
    """Every `_run("<label>", ...)` step label in a finish-style DAG driver."""
    text = (REPO / module_rel).read_text(encoding="utf-8")
    return set(re.findall(r'_run\(\s*"([^"]+)"', text))


def test_index_count_matches():
    assert INDEX["count"] == len(INDEX["skills"])


def test_organ_skills_documents_target_exists():
    """A pipeline/organ skill's `documents:` binding must point at real code."""
    for s in _organ_skills():
        docs = s.get("documents") or {}
        assert isinstance(docs, dict) and docs, (
            f"{s['id']}: an organ/pipeline skill must declare `documents:` binding it to code")
        for key, target in docs.items():
            assert (REPO / target).exists(), f"{s['id']}: documents.{key} -> missing path {target}"


def test_organ_skills_loaded_by_exists():
    for s in _organ_skills():
        for lb in s.get("loaded_by") or []:
            assert (REPO / lb).exists(), f"{s['id']}: loaded_by -> missing path {lb}"


def test_hyperframes_pipeline_documents_every_dag_step():
    """The exemplar: pipeline.hyperframes must document every step in the finish DAG.
    Add a `_run("newstep", ...)` to finish.py and this fails until the skill mentions it."""
    s = SKILLS["pipeline.hyperframes"]
    dag = (s.get("documents") or {}).get("dag")
    assert dag, "pipeline.hyperframes must declare documents.dag"
    body = (REPO / s["path"]).read_text(encoding="utf-8")
    steps = _dag_steps(dag)
    assert steps, f"no _run() steps found in {dag} (regex drift?)"
    missing = {step for step in steps if step not in body}
    assert not missing, f"pipeline.hyperframes skill doc missing finish-DAG steps: {sorted(missing)}"


def test_router_region_is_fresh():
    """The auto-generated skill-router in the `nolan` skill must match the catalog.
    Add/rename a skill and forget `python -m nolan.skills --emit-router` → this fails."""
    from nolan.skills import router_is_fresh
    assert router_is_fresh(), (
        "the `nolan` skill's AUTOGEN:skill-router region is stale — "
        "run `python -m nolan.skills --emit-router`")
