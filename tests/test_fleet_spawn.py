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


def test_smart_reaper_preserves_inflight_reaps_orphan_and_stale(monkeypatch, tmp_path):
    """The reaper keeps a young, unfinished, registered agent (in-flight across a restart) but
    reaps an unregistered orphan and a stale one — never the persistent nolanN fleet."""
    import json, time
    from nolan import fleet
    monkeypatch.setattr(fleet, "_run_registry_path", lambda: tmp_path / "_run_agents.json")
    killed_calls = []
    monkeypatch.setattr(fleet, "kill", lambda n: (killed_calls.append(n), True)[1])
    monkeypatch.setattr(fleet, "_live_sessions",
                        lambda: ["nolan-run-A-review", "nolan-run-B-v3", "nolan1"])
    fleet.register_run_agent("nolan-run-A-review", "noproj", "review")   # young, no sentinel
    killed = fleet.reap_run_agents()
    assert "nolan-run-B-v3" in killed          # unregistered orphan → reaped
    assert "nolan-run-A-review" not in killed  # young in-flight → PRESERVED
    assert "nolan1" not in killed              # persistent fleet untouched
    # now age it past the max → stale → reaped
    reg = json.loads((tmp_path / "_run_agents.json").read_text(encoding="utf-8"))
    reg["nolan-run-A-review"]["started"] = time.time() - 3000
    (tmp_path / "_run_agents.json").write_text(json.dumps(reg), encoding="utf-8")
    monkeypatch.setattr(fleet, "_live_sessions", lambda: ["nolan-run-A-review"])
    assert "nolan-run-A-review" in fleet.reap_run_agents()
