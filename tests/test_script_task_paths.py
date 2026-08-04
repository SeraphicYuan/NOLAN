"""A task brief must point where its STORE points.

The defect this pins: `ScriptProjectStore(root=...)` was only half a parameter. The store honoured
the root — it would locate a project under a scratch root and correctly identify its current draft
— while `tasks.py` built every path in the dispatched brief from an `f"projects/{slug}"` literal.

So an isolated run read production inputs and would have WRITTEN ITS OUTPUT BACK INTO PRODUCTION,
corrupting the project it was copied from, while every log said it was sandboxed. It was caught by
an assertion in an experiment harness, which is luck rather than engineering.

Every task builder is checked, not just the one that was noticed.
"""

from pathlib import Path

import pytest

from nolan.scriptwriter import ScriptProjectStore, tasks

BUILDERS = [
    ("write_script_task", dict()),
    ("prep_task", dict(unattended=True)),
    ("draft_task", dict(unattended=True)),
    ("v3_task", dict(unattended=True)),
    ("review_task", dict(unattended=True)),
    ("revise_task", dict(unattended=True)),
]


@pytest.fixture()
def sandbox(tmp_path):
    """A project under a NON-default root, shaped enough for every builder to run."""
    slug = "probe-project"
    sg = tmp_path / slug / "scriptgen"
    (sg / "drafts").mkdir(parents=True)
    (sg / "reviews").mkdir(parents=True)
    (sg / "sources" / "raw").mkdir(parents=True)
    (sg / "drafts" / "draft-01.md").write_text(
        "# Video Script\n\n**Total Duration:** 8:00\n\n## A beat [0:00]\n\nWords.\n",
        encoding="utf-8")
    for name in ("brief.md", "facts.md", "beatmap.md", "citations.md", "factcheck.md",
                 "angles.md"):
        (sg / name).write_text("x\n", encoding="utf-8")
    (sg / "meta.json").write_text(
        '{"slug": "probe-project", "name": "Probe", "subject": "s",'
        ' "style_id": "channel-great-books-explained", "target_minutes": 8.0,'
        ' "mode": "auto", "sources": []}', encoding="utf-8")
    return slug, ScriptProjectStore(tmp_path)


def test_project_paths_follow_the_store_root(sandbox, tmp_path):
    slug, store = sandbox
    base, sg = tasks.project_paths(slug, store)
    assert slug in base and base.endswith(slug)
    assert sg == f"{base}/scriptgen"
    # An out-of-tree root cannot be made repo-relative; it must still resolve to something usable.
    assert tmp_path.as_posix().split("/")[-1] in base or Path(base).is_absolute() or ".." not in base


@pytest.mark.parametrize("builder,kwargs", BUILDERS)
def test_no_builder_leaks_the_production_root(sandbox, builder, kwargs):
    """THE REGRESSION. Not one of these briefs may name `projects/` when the store points
    elsewhere — a single leaked path is a write into someone else's project."""
    slug, store = sandbox
    fn = getattr(tasks, builder)
    text = fn(slug, store, **kwargs)
    leaked = [ln.strip() for ln in text.splitlines()
              if "projects/" in ln and "script_styles/" not in ln]
    assert not leaked, (
        f"{builder} leaked the production root under a sandbox store:\n  "
        + "\n  ".join(leaked[:4]))


@pytest.mark.parametrize("builder,kwargs", BUILDERS)
def test_the_default_root_is_unchanged(builder, kwargs):
    """The fix must not move production. With the default store these briefs still say
    `projects/<slug>/scriptgen`, exactly as before."""
    store = ScriptProjectStore(Path("projects"))
    slugs = [p.get("slug") for p in store.list()]
    if "homer-auto" not in slugs:
        pytest.skip("homer-auto not present in this checkout")
    text = getattr(tasks, builder)("homer-auto", store, **kwargs)
    assert "projects/homer-auto/scriptgen" in text
