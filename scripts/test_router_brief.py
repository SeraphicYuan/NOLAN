"""
End-to-end scene-edit ROUTER test for the brief layer.

A real human comment -> real LLM (revise_scene gate) -> photo_brief -> resolve_brief
(cue timing from the scene's narration) -> motion_spec on the scene -> render.

Proves the wiring: "use these 6 pictures, 2x3 grid, fly in one by one, zoom the 4th
when the voiceover says 'keyword'" lands a photo-grid motion_spec whose focus fires at
the cue's timestamp.
"""
import os
import sys
import json
import asyncio
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

PROJ = os.path.abspath("projects/_test_brief_grid")
PLAN = os.path.join(PROJ, "scene_plan.json")
LIB = "_library/images"


def lib_paths(n):
    db = sqlite3.connect(os.path.join(LIB, "catalog.db"))
    rows = db.execute("SELECT path FROM assets WHERE status='active' ORDER BY id LIMIT ?", (n,)).fetchall()
    db.close()
    return [os.path.abspath(os.path.join(LIB, r[0])) for r in rows]


def write_plan():
    os.makedirs(PROJ, exist_ok=True)
    open(os.path.join(PROJ, "segment_meta.json"), "w").write("{}")  # marks pipeline=segment
    # narration with 'keyword' planted at 3.2s, as scene subtitle_cues
    cues = [{"text": "the", "start": 0.2, "end": 0.4}, {"text": "market", "start": 0.5, "end": 0.9},
            {"text": "crashed", "start": 1.0, "end": 1.5}, {"text": "and", "start": 1.6, "end": 1.8},
            {"text": "then", "start": 1.9, "end": 2.2}, {"text": "the", "start": 2.4, "end": 2.6},
            {"text": "keyword", "start": 3.2, "end": 3.6}, {"text": "appeared", "start": 3.7, "end": 4.3}]
    plan = {"sections": {"main": [{
        "id": "p_grid", "start_seconds": 0.0, "end_seconds": 6.0, "duration": "6s",
        "narration_excerpt": "the market crashed and then the keyword appeared",
        "visual_type": "generated-image", "motion_spec": None, "rendered_clip": None,
        "subtitle_cues": cues,
    }]}}
    json.dump(plan, open(PLAN, "w", encoding="utf-8"), indent=2)


async def main():
    from nolan.config import load_config
    from nolan.llm import create_text_llm
    from nolan.iterate import apply_edit
    from nolan.iterate.engine import load_plan_raw, find_scene

    write_plan()
    pics = lib_paths(6)
    comment = (
        "Make this scene a photo montage from these 6 pictures arranged as a 2x3 grid. "
        "Fly them in one by one. When the voiceover says \"keyword\", zoom the 4th picture "
        "(index 3) to the center of the screen while the rest of the grid fades out. "
        "Pictures:\n" + "\n".join(pics)
    )
    print("COMMENT:\n", comment[:300], "...\n")

    client = create_text_llm(load_config())
    patch = await apply_edit(PLAN, "p_grid", note=comment, client=client)

    scene = find_scene(load_plan_raw(PLAN), "p_grid")
    spec = scene.get("motion_spec")
    print("patch keys:", sorted(patch))
    assert spec, f"router did not produce a motion_spec; patch={patch}"
    print("effect:", spec.get("effect"))
    assert spec["effect"] == "photo-grid", spec.get("effect")
    c, st = spec["content"], spec.get("style", {})
    print("grid:", c.get("cols"), "x", c.get("rows"), "| cards:", len(c.get("cards", [])),
          "| focusIndex:", c.get("focusIndex"), "| focusAt:", st.get("focusAt"))
    assert c["cols"] * c["rows"] >= 6
    # the cue resolved to ~3.2s (not a guess) — the load-bearing assertion
    assert st.get("focusAt") is not None and abs(st["focusAt"] - 3.2) < 0.3, st.get("focusAt")
    print("\n  ✓ cue 'keyword' resolved to focusAt =", st["focusAt"], "(VO says it at 3.2s)")

    # render the resolved spec (what `nolan rerender --scenes p_grid` does for a motion scene)
    if "--render" in sys.argv:
        from nolan.motion import render
        import subprocess, imageio_ffmpeg
        out = os.path.join(PROJ, "clips", "p_grid.mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        print("rendering...")
        render(spec, out)
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run([ff, "-hide_banner", "-i", out], capture_output=True, text=True)
        assert "1920x1080" in r.stderr
        print("  rendered ->", out)
    print("\nROUTER TEST PASS")


if __name__ == "__main__":
    asyncio.run(main())
