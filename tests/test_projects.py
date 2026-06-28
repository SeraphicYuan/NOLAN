"""Tests for the unified project model (C1, src/nolan/projects.py)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nolan import projects as P


def _scene_plan(path: Path, n=2):
    path.write_text(json.dumps({"sections": {"S": [{"id": f"s{i}"} for i in range(n)]}}))


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "projects"
    r.mkdir()
    # a: scenes project (scene_plan) + imagelib subdir
    a = r / "alpha"; (a / "imagelib").mkdir(parents=True)
    _scene_plan(a / "scene_plan.json", 3)
    # b: script project (scriptgen/meta.json) only
    b = r / "beta"; (b / "scriptgen").mkdir(parents=True)
    (b / "scriptgen" / "meta.json").write_text('{"subject": "x"}')
    # c: orchestrator project
    c = r / "gamma"; (c / ".orchestrator").mkdir(parents=True)
    (c / "project.yaml").write_text("name: Gamma Show\n")
    # nested segment project under alpha
    seg = a / "segment_01"; seg.mkdir()
    seg.joinpath("segment_meta.json").write_text("{}")
    _scene_plan(seg / "scene_plan.json", 1)
    # a non-project dir + project sub-dirs that must NOT be listed
    (r / "_clips").mkdir()
    return r


def test_discovers_all_kinds(root):
    found = {p.slug: p for p in P.discover_projects(root)}
    assert set(found) == {"alpha", "beta", "gamma", "alpha/segment_01"}


def test_capability_flags(root):
    f = {p.slug: p for p in P.discover_projects(root)}
    assert f["alpha"].has_scene_plan and f["alpha"].has_imagelib and f["alpha"].scene_count == 3
    assert f["beta"].has_scriptgen and not f["beta"].has_scene_plan
    assert f["gamma"].has_orchestrator and f["gamma"].name == "Gamma Show"
    assert f["alpha/segment_01"].has_segment and f["alpha/segment_01"].scene_count == 1


def test_kinds(root):
    f = {p.slug: p for p in P.discover_projects(root)}
    assert "scenes" in f["alpha"].kinds
    assert f["beta"].kinds == ["script"]
    assert "orchestrator" in f["gamma"].kinds


def test_subdirs_not_treated_as_projects(root):
    slugs = {p.slug for p in P.discover_projects(root)}
    # scriptgen/, imagelib/, .orchestrator/, _clips/ must never appear
    assert not any(s.endswith("scriptgen") or s.endswith("imagelib")
                   or "_clips" in s or ".orchestrator" in s for s in slugs)


def test_get_project(root):
    p = P.get_project("beta", root)
    assert p and p.slug == "beta" and p.has_scriptgen
    assert P.get_project("nope", root) is None


def test_to_dict_serializable(root):
    d = P.get_project("alpha", root).to_dict()
    assert d["slug"] == "alpha" and isinstance(d["path"], str) and "scenes" in d["kinds"]


def test_db_link_resolved_when_index_given(root):
    index = MagicMock()
    index.get_project_id_by_slug.side_effect = lambda s: "ID123" if s == "alpha" else None
    f = {p.slug: p for p in P.discover_projects(root, index=index)}
    assert f["alpha"].library_project_id == "ID123"
    assert f["beta"].library_project_id is None


def test_link_db_project_idempotent(root):
    index = MagicMock()
    index.get_project_id_by_slug.side_effect = [None, "NEW"]  # first miss, then exists
    index.create_project.return_value = {"id": "NEW"}
    proj = P.get_project("beta", root)
    assert P.link_db_project(index, proj) == "NEW"      # created
    index.create_project.assert_called_once()
    assert P.link_db_project(index, proj) == "NEW"      # reused, no second create
    index.create_project.assert_called_once()


def test_empty_or_missing_root(tmp_path):
    assert P.discover_projects(tmp_path / "nope") == []


# ---------------------------------------------------------------- Phase 2: endpoint
def test_api_projects_unified_endpoint(root):
    from starlette.testclient import TestClient
    from nolan.hub import create_hub_app

    client = TestClient(create_hub_app(db_path=None, projects_dir=root))
    data = client.get("/api/projects").json()
    by_slug = {p["slug"]: p for p in data["projects"]}
    assert data["total"] == 4
    assert set(by_slug) == {"alpha", "beta", "gamma", "alpha/segment_01"}
    assert "scenes" in by_slug["alpha"]["kinds"]
    assert by_slug["beta"]["kinds"] == ["script"]
    # no library DB -> no link
    assert by_slug["alpha"]["library_project_id"] is None


# ---------------------------------------------------------------- Phase 3: FS<->DB link
def test_fs_db_link_roundtrip(root, tmp_path):
    from nolan.indexer import VideoIndex

    idx = VideoIndex(tmp_path / "lib.db")
    before = P.discover_projects(root, index=idx)
    assert all(p.library_project_id is None for p in before)   # nothing linked yet

    for p in before:
        P.link_db_project(idx, p)

    after = {p.slug: p for p in P.discover_projects(root, index=idx)}
    assert after["alpha"].library_project_id          # FS project now has a DB row
    assert after["beta"].library_project_id
    # idempotent: re-linking doesn't create duplicates
    n_before = len(idx.list_projects())
    P.link_db_project(idx, after["alpha"])
    assert len(idx.list_projects()) == n_before
