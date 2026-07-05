"""E2E smoke test — a tiny fixture project through the whole narrated chain.

THE regression net for the consolidation (Phase 0): plan → beat-anchored VO
windows → tempo-motion stamping → render (Remotion stills + MoviePy layouts)
→ annotate → assemble with narration. Asserts:

  1. video duration ≡ audio duration (the sync contract)
  2. every scene rendered (no silent skips / black frames)
  3. plan round-trip is LOSSLESS end-to-end (unknown keys survive all stages)
  4. assemble writes where the caller asked (CWD-relative -o) and exits honestly

Requirements: bundled ffmpeg on PATH, render-service on :3010 (still-motion).
LLM-free and network-free by design — every stage here is deterministic.

Usage:
    D:/env/nolan/python.exe -X utf8 scripts/test_e2e_smoke.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

REPO = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECTION_SECONDS = [8.0, 10.0, 6.0]          # 3 beats → 24s narration


def _require_render_service():
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:3010/health", timeout=4)
    except Exception:
        print("SKIP-FAIL: render-service (:3010) is required for still-motion scenes")
        raise SystemExit(2)


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_format", str(path)], capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def make_fixture_project(root: Path) -> Path:
    import cv2
    proj = root / "smoke-project"
    (proj / "assets" / "art").mkdir(parents=True)
    (proj / "assets" / "voiceover" / "_work").mkdir(parents=True)
    (proj / "output").mkdir()
    (proj / "project.yaml").write_text("name: smoke\nslug: smoke-project\n", encoding="utf-8")

    # two textured fixture images (trackable by design)
    rng = np.random.default_rng(5)
    for i in (1, 2):
        img = (rng.random((720, 1280, 3)) * 255).astype(np.uint8)
        img = cv2.GaussianBlur(img, (31, 31), 0)
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
        cv2.imwrite(str(proj / "assets" / "art" / f"fix{i}.jpg"), img)

    # per-section sine "narration" + concat mp3 (exact beat anchors)
    vo_dir = proj / "assets" / "voiceover"
    concat_list = []
    for i, secs in enumerate(SECTION_SECONDS):
        f = vo_dir / "_work" / f"sec_{i:04d}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-f", "lavfi",
                        "-i", f"sine=frequency={300 + 100 * i}:duration={secs}",
                        "-ar", "44100", str(f)], check=True)
        concat_list.append(f"file '{f.as_posix()}'")
    lst = vo_dir / "_work" / "_concat.txt"
    lst.write_text("\n".join(concat_list), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-codec:a", "libmp3lame", "-b:a", "128k",
                    str(vo_dir / "voiceover.mp3")], check=True)

    # scene plan: 3 sections / 5 scenes, unknown keys injected at every level
    plan = {
        "_meta": {"source": "e2e-smoke"}, "x_top": 1,
        "sections": {
            "Beat One": [
                {"id": "s01", "visual_type": "archival-art", "narration_excerpt": "alpha " * 8,
                 "duration": "4s", "matched_asset": "assets/art/fix1.jpg",
                 "energy": 0.7, "motion_speed": "fast", "x_scene": {"keep": True}},
                {"id": "s02", "visual_type": "text-overlay", "narration_excerpt": "beta " * 8,
                 "duration": "4s", "energy": 0.4,
                 "layout_spec": {"template": "quote",
                                 "params": {"quote": "Arma virumque cano",
                                            "attribution": "Virgil"}}},
            ],
            "Beat Two": [
                {"id": "s03", "visual_type": "archival-art", "narration_excerpt": "gamma " * 12,
                 "duration": "5s", "matched_asset": "assets/art/fix2.jpg",
                 "energy": 0.3, "motion_speed": "slow"},
                {"id": "s04", "visual_type": "graphic", "narration_excerpt": "delta " * 8,
                 "duration": "5s", "energy": 0.6,
                 "layout_spec": {"template": "counter",
                                 "params": {"value": 1200, "label": "words"}}},
            ],
            "Beat Three": [
                {"id": "s05", "visual_type": "archival-art", "narration_excerpt": "epsilon " * 10,
                 "duration": "6s", "matched_asset": "assets/art/fix1.jpg",
                 "energy": 0.5, "motion_speed": "medium"},
            ],
        },
    }
    (proj / "scene_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return proj


def main():
    _require_render_service()
    from src.nolan.orchestrator import render as render_mod
    from src.nolan.scenes import ScenePlan, anchor_scenes_to_sections

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        proj = make_fixture_project(Path(td))
        plan_p = proj / "scene_plan.json"
        audio = proj / "assets" / "voiceover" / "voiceover.mp3"
        audio_dur = _ffprobe_duration(audio)

        # 1. beat-anchored windows (exact section spans — no whisper needed)
        sp = ScenePlan.load(str(plan_p))
        n = anchor_scenes_to_sections(sp, SECTION_SECONDS)
        assert n == 5, n
        sp.save(str(plan_p))

        # 2. stamp tempo motions + render + annotate (dict layer, as the Director does)
        scene_plan = json.loads(plan_p.read_text(encoding="utf-8"))
        stamped = render_mod.stamp_tempo_motions(scene_plan, proj)
        assert stamped == 3, f"expected 3 stills stamped, got {stamped}"
        outcomes = render_mod.render_all(scene_plan, proj, proj / "assets" / "rendered")
        rendered = [o for o in outcomes if o.rendered_clip]
        assert len(rendered) == 5, [f"{o.scene_id}:{o.skipped_reason}" for o in outcomes]
        total, count = render_mod.annotate_scene_plan(scene_plan, outcomes)
        plan_p.write_text(json.dumps(scene_plan, indent=2, ensure_ascii=False),
                          encoding="utf-8")
        assert abs(total - audio_dur) < 1.0, f"timeline {total} vs audio {audio_dur}"

        # 3. assemble with RELATIVE -o from a different CWD (regression: used to
        #    resolve against the plan dir and exit 0 while writing nowhere)
        rel_out = "output/final.mp4"
        r = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "nolan", "assemble",
             str(plan_p), str(audio), "-o", rel_out],
            capture_output=True, text=True, cwd=str(proj))
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
        final = proj / rel_out
        assert final.exists() and final.stat().st_size > 100_000, "no real output"

        # 4. sync contract: video duration ≡ audio duration
        vid_dur = _ffprobe_duration(final)
        assert abs(vid_dur - audio_dur) < 1.0, f"video {vid_dur} vs audio {audio_dur}"

        # 5. no black scenes reported
        assert "BLACK" not in r.stdout, "black scenes in assemble output"

        # 6. losslessness survived the WHOLE chain
        out = json.loads(plan_p.read_text(encoding="utf-8"))
        assert out.get("x_top") == 1 and out.get("_meta", {}).get("source") == "e2e-smoke"
        s01 = out["sections"]["Beat One"][0]
        assert s01.get("x_scene") == {"keep": True}, "scene unknown key lost in chain"
        assert s01.get("rendered_clip"), "annotate did not stamp rendered_clip"

        print(f"E2E SMOKE PASS — {len(rendered)}/5 scenes, video {vid_dur:.1f}s ≡ "
              f"audio {audio_dur:.1f}s, lossless plan, honest assemble")


if __name__ == "__main__":
    main()
