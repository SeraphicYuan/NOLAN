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

# the skill domains that describe a code organ / pipeline / lab (as opposed to pure craft/prompt)
ORGAN_DOMAINS = ("pipeline", "organ", "lab")


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


def test_acquire_skill_documents_every_unusable_flag():
    """Strong binding for organ.acquire (like the DAG-step test): the VLM usability FLOOR
    vocabulary is a contract — every UNUSABLE_FLAGS entry must appear in the skill. Parsed
    from source (not imported — acquire pulls heavy deps and is under active refactor)."""
    s = SKILLS.get("organ.acquire")
    if not s:
        return
    src = (REPO / "src" / "nolan" / "acquire" / "judge.py").read_text(encoding="utf-8")
    m = re.search(r"UNUSABLE_FLAGS\s*=\s*\(([^)]*)\)", src)
    assert m, "could not find UNUSABLE_FLAGS in judge.py (regex drift?)"
    flags = re.findall(r'"([^"]+)"', m.group(1))
    assert flags, "UNUSABLE_FLAGS parsed empty"
    body = (REPO / s["path"]).read_text(encoding="utf-8")
    missing = [f for f in flags if f not in body]
    assert not missing, f"organ.acquire skill missing usability flags: {missing}"


def test_router_region_is_fresh():
    """The auto-generated skill-router in the `nolan` skill must match the catalog.
    Add/rename a skill and forget `python -m nolan.skills --emit-router` → this fails."""
    from nolan.skills import router_is_fresh
    assert router_is_fresh(), (
        "the `nolan` skill's AUTOGEN:skill-router region is stale — "
        "run `python -m nolan.skills --emit-router`")


def test_every_harness_copy_is_a_real_file_and_in_sync():
    """A skill authored in `skills/` reaches the agent harness through a REAL generated file at
    `.claude/skills/<harness>/SKILL.md` — never a symlink.

    This is not a style rule. A symlink created from WSL is a Linux reparse point that Windows cannot
    even stat (`OSError: [WinError 1920]`), so on the Windows client the skill silently does not
    exist: `Skill(nolan-transcript-library)` answers "Unknown skill", and `git add` fails with
    "Invalid argument". Both clients have to work, so the copy must be a plain file with its source's
    exact bytes. Regenerate with `python -m nolan.skills --sync-harness`."""
    from nolan import skills as sk
    drift = sk.harness_drift()
    assert not drift, "harness copies out of sync:\n" + "\n".join(
        f"  {sid:28} {slug:26} {why}" for sid, slug, why in drift)


def test_organ_skills_declare_a_harness_slug():
    """Every organ/lab/pipeline skill is routable by name from the harness — CLAUDE.md's "LOAD its
    skill before modifying a subsystem" is unfollowable for a skill with no `.claude/skills/` entry."""
    from nolan import skills as sk
    missing = [s.id for s in sk.load_skills()
               if s.tier in ("primary", "organ", "lab") and s.status == "active" and not s.harness]
    assert not missing, f"no harness: slug, so unreachable via Skill(): {missing}"
