"""Unit tests for the fleet spawn/kill helpers (pure logic — no live tmux)."""

from nolan import fleet


def test_sanitize_strips_dots_and_colons():
    assert fleet._sanitize("nolan.gold:1") == "nolan-gold-1"
    assert fleet._sanitize("  x  ") == "x"


def test_wsl_repo_dir_is_a_mnt_path():
    wd = fleet._wsl_repo_dir()
    assert wd.startswith("/mnt/")
    assert wd.rstrip("/").endswith("NOLAN")
    assert "\\" not in wd


def test_next_session_name_finds_lowest_gap(monkeypatch):
    monkeypatch.setattr(fleet, "_live_sessions", lambda: ["nolan1", "nolan2", "nolan4"])
    assert fleet.next_session_name() == "nolan3"
    monkeypatch.setattr(fleet, "_live_sessions", lambda: [])
    assert fleet.next_session_name() == "nolan1"
    monkeypatch.setattr(fleet, "_live_sessions", lambda: ["hermes1"])
    assert fleet.next_session_name("nolan") == "nolan1"


def test_spawn_refuses_existing(monkeypatch):
    monkeypatch.setattr(fleet, "has_session", lambda n: True)
    res = fleet.spawn("nolan1")
    assert res["ok"] is False and "exists" in res["error"]
