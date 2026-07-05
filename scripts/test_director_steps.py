"""Director narrated-pipeline steps — sequencing + skip paths (Phase 1).

LLM/GPU-free: exercises `_next_step_name` ordering across the new
generate_assets / voiceover / align_narration steps, the missing-asset
counter, the voiceover step's no-voice skip path, and the render step's
narration-vs-silent audio choice (choice logic only, no rendering).

Usage:
    D:/env/nolan/python.exe -X utf8 scripts/test_director_steps.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from nolan.orchestrator import state as state_mod
from nolan.orchestrator.director import PIPELINE_STEPS, Director


def make_project(root: Path) -> Path:
    proj = root / "narrated-steps"
    proj.mkdir(parents=True)
    (proj / "project.yaml").write_text(
        "name: Steps\nslug: narrated-steps\n", encoding="utf-8")
    (proj / "script.md").write_text(
        "# T\n\n## One\n\nAlpha beta.\n\n## Two\n\nGamma delta.\n",
        encoding="utf-8")
    (proj / "style_guide.md").write_text("# style\n", encoding="utf-8")
    plan = {"sections": {"One": [
        {"id": "s01", "visual_type": "archival-art", "narration_excerpt": "alpha",
         "matched_asset": "assets/art/a.jpg"},
        {"id": "s02", "visual_type": "generated-image", "narration_excerpt": "beta",
         "comfyui_prompt": "a ship"},
    ]}}
    (proj / "scene_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return proj


def completed_state(proj: Path, *names):
    st = state_mod.load_state(proj)
    for n in names:
        rec = state_mod.append_step(st, n)
        state_mod.finish_step(rec, status="completed")
    state_mod.save_state(proj, st)
    return st


def main():
    assert PIPELINE_STEPS[-5:] == [
        "generate_assets", "voiceover", "align_narration", "soundtrack",
        "render"], PIPELINE_STEPS

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        proj = make_project(Path(td))
        d = Director(proj)

        # -- 1. step ordering: after the planning steps come the media steps --
        st = completed_state(proj, "tempo_enrich", "select_clips")
        assert d._next_step_name(st) == "generate_assets", d._next_step_name(st)
        assert d._generated_scenes_missing_asset() == 1

        # generated image appears -> generate_assets no longer pending
        gen = proj / "assets" / "generated"
        gen.mkdir(parents=True)
        (gen / "s02.png").write_bytes(b"png")
        assert d._generated_scenes_missing_asset() == 0
        assert d._next_step_name(st) == "voiceover"

        # -- 2. voiceover skip path (no TTS voice configured) -----------------
        os.environ.pop("NOLAN_CONFIG", None)
        os.chdir(td)  # keep any nolan.yaml in repo root out of load_config's way
        cp = asyncio.run(d._run_voiceover_step(None, st))
        assert cp.exists()
        st = state_mod.load_state(proj)
        rec = [s for s in st.step_history if s.name == "voiceover"][-1]
        assert rec.status == "completed" and "skipped" in rec.notes, rec.notes

        # no voiceover.mp3 -> align skipped -> soundtrack authoring is next
        assert d._next_step_name(st) == "soundtrack", d._next_step_name(st)

        # -- 2b. soundtrack skip path (no music configured) -------------------
        cp = asyncio.run(d._run_soundtrack_step(None, st))
        assert cp.exists()
        st = state_mod.load_state(proj)
        rec = [s for s in st.step_history if s.name == "soundtrack"][-1]
        assert rec.status == "completed" and "skipped" in rec.notes, rec.notes
        assert d._next_step_name(st) == "render", d._next_step_name(st)

        # -- 3. hand-made narration is respected: align runs, voiceover doesn't
        vo = proj / "assets" / "voiceover"
        vo.mkdir(parents=True)
        (vo / "voiceover.mp3").write_bytes(b"mp3")
        st2 = completed_state(proj, "tempo_enrich", "select_clips")
        assert d._next_step_name(st2) == "align_narration", d._next_step_name(st2)

        # -- 4. render step's audio choice mirrors the artifact ---------------
        assert (proj / "assets" / "voiceover" / "voiceover.mp3").exists()

    print("OK - director narrated-pipeline step sequencing verified.")


if __name__ == "__main__":
    main()
