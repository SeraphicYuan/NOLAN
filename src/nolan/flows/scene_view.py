"""Flow → scene-plan view (Phase 3, Gate B).

The project-owned `flow.spec.json` is the source of truth; this projects its beats into the
`scene_plan.json` shape the existing Scene page already renders — each beat a scene row
pointing at its per-beat clip (`.flow/clips/beat_NN.mp4`). So a flow project becomes a
first-class Scene-page citizen with near-zero frontend change; re-render/edit map scene id
(`beat_NN`) ↔ beat index. See web-video-lab/flows/EDITOR.md.
"""
from __future__ import annotations

import json
from pathlib import Path

CLIPS = ".flow/clips"


def beat_id(i: int) -> str:
    return f"beat_{i:02d}"


def beat_index(scene_id: str) -> int:
    return int(scene_id.split("_")[1])


def build_scene_plan(project, fps: int = 30) -> Path:
    """Generate projects/<slug>/scene_plan.json from the flow spec + job. Returns its path."""
    project = Path(project)
    job = json.loads((project / "flow.job.json").read_text(encoding="utf-8"))
    spec = json.loads((project / "flow.spec.json").read_text(encoding="utf-8"))
    flow_id = spec.get("flow", "flow")
    steps = job.get("props", {}).get("steps", [])
    beats = spec.get("beats", [])

    scenes, t = [], 0.0
    for i, st in enumerate(steps):
        dur = st.get("durationInFrames", 1) / fps
        narration = " ".join(w["text"] for w in st.get("words", []))
        beat = beats[i] if i < len(beats) else {}
        clip = project / CLIPS / f"beat_{i:02d}.mp4"
        scenes.append({
            "id": beat_id(i),
            "visual_type": st.get("block", "flow"),
            "narration_excerpt": narration[:280],
            "start_seconds": round(t, 2),
            "end_seconds": round(t + dur, 2),
            "duration": f"{dur:.1f}s",
            "rendered_clip": f"{CLIPS}/beat_{i:02d}.mp4" if clip.exists() else None,
            # flow-specific (for editing / write-back to the spec)
            "block": st.get("block"),
            "segment": beat.get("segment"),
            "flow": flow_id,
        })
        t += dur

    plan_path = project / "scene_plan.json"
    plan_path.write_text(json.dumps({"sections": {flow_id: scenes}}, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return plan_path
