"""Honesty test for the image-library base path (imagelib/store.py:library_paths).

Locks POST_MORTEM #1: library_paths returned a CWD-relative base, so running acquisition from
render-service/_lab_hyperframes/bridge/ (the hub's run_pool CWD) opened an EMPTY library and every
library-first need returned 0 with no error. The base must be ABSOLUTE and anchored to the repo root
regardless of the process CWD.
"""
from pathlib import Path

from nolan.imagelib.store import library_paths

REPO = Path(__file__).resolve().parents[1]


def test_global_base_absolute_and_repo_anchored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                       # simulate cwd=BRIDGE (the bug's trigger)
    base = library_paths("global")
    assert base.is_absolute()
    assert base == REPO / "_library" / "images"


def test_project_base_absolute_and_repo_anchored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = library_paths("project", project="demo")
    assert base.is_absolute()
    assert base == REPO / "projects" / "demo" / "imagelib"


def test_base_is_stable_across_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO)
    from_root = library_paths("global")
    monkeypatch.chdir(tmp_path)
    from_elsewhere = library_paths("global")
    assert from_root == from_elsewhere               # CWD-independent
