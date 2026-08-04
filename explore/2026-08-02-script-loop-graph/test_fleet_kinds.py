"""The fleet lifecycle invariants — ownership, and never dispatching into a dead prompt.

`fleet_kinds` is the module with the sharpest failure modes in this experiment: it kills tmux
sessions and it types into them. Both are irreversible from the harness's point of view, and both
have already gone wrong once (probe agents landing on a human's board; three briefs typed into a
modal dialog). These tests pin the fixes.

    D:\\env\\nolan\\python.exe -X utf8 -m pytest explore/2026-08-02-script-loop-graph/ -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import fleet_kinds as fk                                        # noqa: E402


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Never let a test read or write the real reservation registry."""
    monkeypatch.setattr(fk, "RESV_DIR", tmp_path)
    return tmp_path


def _res(session, *, registered=False, sandbox=None):
    if registered:
        (sandbox / f"{session}.json").write_text("{}", encoding="utf-8")
    return fk.Reservation(kind=fk.SCRIPT_LOOP.name, session=session, started_at=0.0)


def _reserve(sandbox, session="nfleet-script-deadbeef"):
    return _res(session, registered=True, sandbox=sandbox)


# --- readiness -------------------------------------------------------------------------------

def test_await_ready_returns_as_soon_as_the_agent_is_idle(sandbox, monkeypatch):
    res = _reserve(sandbox)
    monkeypatch.setattr(fk._f, "_live_sessions", lambda: [res.session])
    monkeypatch.setattr(fk._f, "detect_status", lambda _n: "idle")
    fk.await_ready(res, timeout_s=5, poll_s=0.01)          # no raise == ready


def test_await_ready_raises_with_the_pane_when_the_agent_never_prompts(sandbox, monkeypatch):
    """THE 25-MINUTE BUG. Three agents booted into a settings-error dialog; the harness slept a
    fixed 14s, typed a brief into a modal that does not read keystrokes, then waited out its whole
    timeout reporting '0/3 done' with no cause. The pane knew the answer the entire time.

    `detect_status` returns 'unknown' for such a dialog — it matches neither the idle nor the busy
    patterns — so waiting on 'not busy' would have sailed straight past it. Readiness is
    specifically 'idle', and everything else is a reason to stop and show the operator the screen.
    """
    res = _reserve(sandbox)
    monkeypatch.setattr(fk._f, "_live_sessions", lambda: [res.session])
    monkeypatch.setattr(fk._f, "detect_status", lambda _n: "unknown")
    monkeypatch.setattr(fk._f, "capture_pane", lambda _n, _l=16:
                        "Settings Error\n"
                        "/mnt/d/ClaudeProjects/NOLAN/.claude/settings.json\n"
                        "  Settings file could not be read: EIO: i/o error, stat\n"
                        "  1. Fix with Claude\n  2. Exit and fix manually")
    with pytest.raises(fk.NotReady) as e:
        fk.await_ready(res, timeout_s=0.05, poll_s=0.01)
    assert "never reached a prompt" in str(e.value)
    assert "Settings file could not be read" in str(e.value)     # the diagnosis, not a guess


def test_await_ready_does_not_wait_out_the_timeout_on_a_dead_session(sandbox, monkeypatch):
    """An agent that died has nothing to wait for. Polling it to the deadline would turn a fast,
    certain failure into a slow one."""
    res = _reserve(sandbox)
    monkeypatch.setattr(fk._f, "_live_sessions", lambda: [])
    monkeypatch.setattr(fk._f, "detect_status",
                        lambda _n: pytest.fail("must not ask a dead session for status"))
    with pytest.raises(fk.NotReady, match="died before it was ready"):
        fk.await_ready(res, timeout_s=30, poll_s=0.01)


def test_a_busy_agent_is_not_ready(sandbox, monkeypatch):
    """Typing at an agent mid-task appends to whatever it is already doing."""
    res = _reserve(sandbox)
    monkeypatch.setattr(fk._f, "_live_sessions", lambda: [res.session])
    monkeypatch.setattr(fk._f, "detect_status", lambda _n: "busy")
    with pytest.raises(fk.NotReady):
        fk.await_ready(res, timeout_s=0.05, poll_s=0.01)


# --- ownership -------------------------------------------------------------------------------

def test_names_cannot_collide_by_construction(sandbox):
    """Not 'lowest unused index', which two callers can race and both win."""
    names = {fk._new_name(fk.SCRIPT_LOOP) for _ in range(400)}
    assert len(names) == 400
    assert all(n.startswith("nfleet-script-") for n in names)


def test_our_names_never_land_on_the_human_fleet_board(sandbox):
    """`nolan.fleet.fleet()` selects with startswith('nolan'), so a 'nolan-probe-' name shows up
    on the board a human uses to watch nolan1..6 — which is how this went wrong the first time."""
    assert not fk._new_name(fk.SCRIPT_LOOP).startswith("nolan")


def test_we_refuse_to_release_a_session_we_did_not_reserve(sandbox):
    """Prefix matching is never sufficient authority to kill. nolan1..6 are a human's, made by
    hand for other work."""
    for stranger in ("nolan3", "nfleet-script-notours"):
        with pytest.raises(fk.NotOurs):
            fk.release(_res(stranger))


def test_ownership_is_the_registry_not_the_prefix(sandbox):
    """A session named like ours but absent from the registry is still not ours — the registry is
    the only authority, so a stale or forged name cannot get anything killed."""
    assert not fk._owned("nfleet-script-ghost")
    (sandbox / "nfleet-script-ghost.json").write_text("{}", encoding="utf-8")
    assert fk._owned("nfleet-script-ghost")
