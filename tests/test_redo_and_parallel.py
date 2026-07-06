"""--redo step reset + parallel-render ordering guarantees."""

import json
from pathlib import Path

import pytest

from nolan.orchestrator import state as state_mod
from nolan.orchestrator.director import Director, DirectorError, PIPELINE_STEPS


def _project(tmp_path):
    proj = tmp_path / "proj"
    (proj / "output").mkdir(parents=True)
    (proj / ".orchestrator").mkdir()
    (proj / "project.yaml").write_text("name: t\nslug: proj\n", encoding="utf-8")
    (proj / "output" / "final.mp4").write_bytes(b"x")
    st = state_mod.load_state(proj)
    for name in ("tempo_enrich", "render"):
        rec = state_mod.append_step(st, name)
        state_mod.finish_step(rec, status="completed")
    state_mod.save_state(proj, st)
    return proj


def test_redo_resets_history_and_artifact(tmp_path):
    proj = _project(tmp_path)
    notes = Director(proj).redo_step("render")
    assert any("output/final.mp4" in n for n in notes)
    assert not (proj / "output" / "final.mp4").exists()
    st = state_mod.load_state(proj)
    names = [s.name for s in st.step_history]
    assert "render" not in names and "tempo_enrich" in names


def test_redo_unknown_step_is_loud(tmp_path):
    proj = _project(tmp_path)
    with pytest.raises(DirectorError):
        Director(proj).redo_step("colorize")
    assert (proj / "output" / "final.mp4").exists()   # nothing touched


def test_redo_artifact_map_names_real_steps():
    assert set(Director._REDO_ARTIFACTS) <= set(PIPELINE_STEPS)


def test_parallel_render_preserves_section_order():
    """The concat must always be section order regardless of finish order."""
    from concurrent.futures import ThreadPoolExecutor
    import time
    order = [2, 0, 1]                      # finish out of order on purpose

    def fake_render(i):
        time.sleep(0.02 * order.index(i))
        return f"clip_{i}"

    job_paths = [(i, f"sec{i}", f"job{i}") for i in range(3)]
    ordered = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(fake_render, i): i for i, _n, _j in job_paths}
        for fut in futures:
            ordered[futures[fut]] = fut.result()
    clips = [ordered[i] for i, _n, _j in job_paths]
    assert clips == ["clip_0", "clip_1", "clip_2"]
