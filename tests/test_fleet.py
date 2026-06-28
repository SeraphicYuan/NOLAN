"""Tests for the scene-edit agent fleet (status protocol + dispatch)."""
import json
from pathlib import Path

import pytest

from nolan import fleet


@pytest.fixture(autouse=True)
def _tmp_fleet_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(fleet, "FLEET_DIR", tmp_path / "agents")


def test_status_write_read_merge():
    fleet.write_status("nolan4", state="working", scene_ids=["b6b"], message="start")
    s = fleet.read_status("nolan4")
    assert s["state"] == "working" and s["scene_ids"] == ["b6b"]
    assert "updated_at" in s
    # merge: a later partial update keeps prior fields
    fleet.write_status("nolan4", message="rendering")
    s2 = fleet.read_status("nolan4")
    assert s2["message"] == "rendering" and s2["scene_ids"] == ["b6b"] and s2["state"] == "working"


def test_read_missing_is_none():
    assert fleet.read_status("ghost") is None


def test_fleet_joins_sessions_and_status(monkeypatch):
    monkeypatch.setattr(fleet, "_live_sessions", lambda: ["nolan4", "nolan5", "hermes1"])
    fleet.write_status("nolan4", state="working", scene_ids=["b1"])
    board = fleet.fleet()
    agents = {a["agent"]: a for a in board}
    assert "hermes1" not in agents                 # only nolan* count as workers
    assert agents["nolan4"]["state"] == "working" and agents["nolan4"]["session_alive"]
    assert agents["nolan5"]["state"] == "idle"     # live session, no status -> idle
    assert agents["nolan5"]["session_alive"]


def test_fleet_flags_dead_status(monkeypatch):
    # a status file whose tmux session is gone must show session_alive False
    monkeypatch.setattr(fleet, "_live_sessions", lambda: [])
    fleet.write_status("nolan9", state="done")
    board = {a["agent"]: a for a in fleet.fleet()}
    assert board["nolan9"]["session_alive"] is False and board["nolan9"]["state"] == "done"


def test_dispatch_prompt_has_skill_scene_note():
    p = fleet.build_dispatch_prompt("nolan4", "plan.json", ["b6b_title", "b7"], "use remotion")
    assert "nolan-scene-edit skill" in p
    assert "nolan4" in p and "b6b_title, b7" in p and "use remotion" in p
    assert ".nolan/agents/nolan4.json" in p          # tells the agent where to report


def test_dispatch_writes_status_and_sends(monkeypatch):
    sent = {}
    monkeypatch.setattr("nolan.webui.operations._dispatch_to_tmux",
                        lambda session, message: sent.update(session=session, message=message))
    status = fleet.dispatch("nolan4", "plan.json", "ProjX", ["b6b"], "rework it")
    assert sent["session"] == "nolan4" and "nolan-scene-edit" in sent["message"]
    assert status["state"] == "dispatched" and status["project"] == "ProjX"
    assert status["scene_ids"] == ["b6b"] and status["note"] == "rework it"
