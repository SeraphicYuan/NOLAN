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

import pytest

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


def test_git_records_every_harness_copy_as_a_regular_file():
    """The other half of "never a symlink": what GIT stores, not just what is on disk.

    The filesystem check above passed while every one of the twelve copies was committed with mode
    120000 — a git symlink whose blob happened to hold the entire 9KB document. On this Windows
    checkout `core.symlinks=false` hides that (git compares content and calls it clean), but a
    symlink-capable clone would try to create a link whose TARGET PATH is the whole document text.
    The copies became real files without the mode following, because git preserves an existing
    entry's mode and cannot see a type change it is configured not to materialise.

    Skipped where git is unavailable; this asserts a repository fact, not a runtime one.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "ls-files", "-s", "--", ".claude/skills/"],
            cwd=REPO, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git unavailable")
    if out.returncode != 0:
        pytest.skip("not a git checkout")

    linked = [
        line.split("\t", 1)[1]
        for line in out.stdout.splitlines()
        if line.startswith("120000") and line.rstrip().endswith("SKILL.md")
    ]
    assert not linked, (
        "harness copies committed as git symlinks (mode 120000) — a symlink-capable clone would "
        "create a link named after the file's own contents. Fix with:\n"
        + "\n".join(
            f"  sha=$(git hash-object -w '{p}'); git update-index --add --cacheinfo 100644,$sha,'{p}'"
            for p in linked
        )
    )


def test_organ_skills_declare_a_harness_slug():
    """Every organ/lab/pipeline skill is routable by name from the harness — CLAUDE.md's "LOAD its
    skill before modifying a subsystem" is unfollowable for a skill with no `.claude/skills/` entry."""
    from nolan import skills as sk
    missing = [s.id for s in sk.load_skills()
               if s.tier in ("primary", "organ", "lab") and s.status == "active" and not s.harness]
    assert not missing, f"no harness: slug, so unreachable via Skill(): {missing}"


def test_hf_edit_skill_documents_the_batch_surfaces():
    """The AI batch mode had NO skill: the whole contract lived as a Python string literal inside
    `compile_batch_brief`, and the batch agent that prompted this work had to read compose.py to learn
    which fields a block consumes. The skill is the durable half; the brief is per-run data.

    Bound the same way every organ skill is: `documents:` targets must exist (checked above), and the
    rules the loop actually enforces must be NAMED here, or the doc can drift from the code silently."""
    s = SKILLS.get("pipeline.hyperframes-edit")
    assert s, "the edit/batch loop must have a skill in the registry"
    doc = (REPO / s["path"]).read_text(encoding="utf-8")
    for token in ("propose_scene_edit", "CAPABILITY-GAP", "acquire_for_scene", "gpu_lock",
                  "batch --verify", "rollback_batch", "render_scene", "deferred"):
        assert token in doc, f"pipeline.hyperframes-edit does not document `{token}`"
    for fn in ("accept_proposals", "rollback_batch", "render_scene", "acquire_for_scene",
               "batch_verify", "build_sheet", "list_gaps", "list_deferred"):
        import nolan.hyperframes as H
        assert hasattr(H, fn), f"{fn} is documented/exported inconsistently"


def test_the_batch_brief_points_at_the_skill_rather_than_restating_it():
    """A contract kept as a string literal in a builder function is the thing that rots."""
    import inspect
    from nolan.hyperframes import batch as hfbatch
    src = inspect.getsource(hfbatch.compile_batch_brief)
    assert "nolan-hf-edit" in src
