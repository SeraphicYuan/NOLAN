# -*- coding: utf-8 -*-
"""Effect execution bench — render every Chapter-hostable motion effect with
standard content and extract frames for an editor's-eye audit.

"Same module name != same craft" (quality program step 3): the registry can
list 19 effects while half of them move like slideware. This bench renders
one probe step per hostable effect (+ an ArtworkStage camera-grammar probe),
then tiles early/mid/late frames per effect into contact sheets to LOOK at.

Run (Windows python):  python -X utf8 scripts/bench_effects.py
Output:  render-service/remotion-lib/output/bench_effects.mp4
         D:/tmp/refframes/bench_sheet_[12].jpg
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nolan.flows.base import FFMPEG, render_chapter  # noqa: E402
from nolan.motion.executor import chapter_step_for_spec  # noqa: E402
from nolan.motion.registry import BY_ID  # noqa: E402

PROJ = REPO / "projects" / "homer-2beat-test"
ART = PROJ / "assets" / "art"
IMG1 = str(ART / "scene_012.jpg")     # Exekias amphora (museum photo)
IMG2 = str(ART / "scene_016.jpg")     # Siren Vase
IMG3 = str(ART / "scene_018.jpg")     # Douris kylix
IMG4 = str(ART / "scene_020.jpg")     # Turner painting
VID1 = str(PROJ / "assets" / "broll_video" / "scene_002.mp4")

FPS = 30
STEP_FRAMES = 96                      # ~3.2s per probe

# Standard content per effect — enough to exercise the real motion.
CONTENT = {
    "annotate-stat": {"value": "$28,000", "label": "per amphora at auction"},
    "annotate-video": {"label": "the wine-dark sea", "videoSrc": VID1},
    "bar-compare": {"title": "Ships at Troy", "suffix": "",
                    "bars": [{"label": "Mycenae", "value": 100},
                             {"label": "Pylos", "value": 90},
                             {"label": "Ithaca", "value": 12}]},
    "clip-montage": {"clips": [{"path": IMG1, "kind": "image", "duration": 1.2},
                               {"path": IMG2, "kind": "image", "duration": 1.2},
                               {"path": IMG3, "kind": "image", "duration": 1.2}],
                     "transition": "fade"},
    "comparison": {"left_text": "Iliad", "right_text": "Odyssey",
                   "left_subtitle": "wrath", "right_subtitle": "cunning"},
    "counter": {"value": 24, "label": "books in the Odyssey", "suffix": ""},
    "k-shape": {"title": "Fame of the epics", "topLabel": "Odyssey",
                "bottomLabel": "lost epics"},
    "kinetic-text": {"text": "Sung, not written", "highlights": ["sung"]},
    "lower-third": {"name": "Homer", "title": "poet, maybe several"},
    "photo-grid": {"cards": [{"src": IMG1}, {"src": IMG2}, {"src": IMG3},
                             {"src": IMG4}] * 10, "cols": 8, "rows": 5},
    "photo-montage-pro": {"cards": [
        {"src": IMG1, "x": 0.3, "y": 0.45, "from": "left", "caption": "the game"},
        {"src": IMG2, "x": 0.68, "y": 0.5, "from": "bottom", "enterAt": 0.9,
         "caption": "the mast"}]},
    "premium-card": {"title": "The Wanderer", "subtitle": "earns his myth",
                     "kicker": "PART TWO"},
    "route-map": {"title": "The long way home",
                  "pins": [{"x": 0.22, "y": 0.4, "label": "Troy"},
                           {"x": 0.55, "y": 0.62, "label": "Aeaea"},
                           {"x": 0.8, "y": 0.35, "label": "Ithaca"}]},
    "split-screen": {"left": IMG1, "right": IMG2,
                     "left_label": "Achilles", "right_label": "Odysseus"},
    "stat-over": {"image": IMG4, "value": 2700, "suffix": " yrs",
                  "caption": "the story has survived"},
    "title": {"title": "The Odyssey", "subtitle": "a bench probe"},
    "timeline": {"title": "Greek memory", "start": -800, "end": 1950,
                 "eras": [{"label": "Archaic", "from": -800, "to": -480},
                          {"label": "Classical", "from": -480, "to": -323}],
                 "markers": [{"year": -750, "label": "Homer composes"},
                             {"year": -300, "label": "Alexandria edits", "isNew": True}],
                 "focus": {"from": -800, "to": -200}},
}

SKIP = {"still-motion", "line-chart", "loop-diagram",
        "clip-montage"}   # not Chapter-hostable (standalone/python renderers)


def main():
    steps, order = [], []
    for eff_id, spec in sorted(BY_ID.items()):
        if eff_id in SKIP:
            continue
        content = CONTENT.get(eff_id)
        if content is None:
            print(f"!! no sample content for {eff_id} — add it"); continue
        hosted = chapter_step_for_spec(
            {"effect": eff_id, "backend": spec.backend, "target": spec.target,
             "content": content}, PROJ)
        if hosted is None:
            print(f"!! {eff_id} unexpectedly unhostable"); continue
        block, props = hosted
        steps.append({"block": block, "props": props, "revealFrames": [0],
                      "words": [], "durationInFrames": STEP_FRAMES})
        order.append(eff_id)

    # still-treatment probes (the path that carries most minutes of most
    # videos — the aeneid "abrupt zoom" feedback lived here): one continuous
    # eased move per mode, whole-step duration
    for mode in ("kenburns-in", "kenburns-out", "kenburns-pan", "drift"):
        steps.append({
            "block": "ArtworkStage",
            "props": {"src": IMG4, "mode": mode,
                      "focuses": [{"word": "", "x": 0.30, "y": 0.25,
                                   "w": 0.55, "h": 0.55}],
                      "durationInFrames": STEP_FRAMES},
            "revealFrames": [0], "words": [],
            "durationInFrames": STEP_FRAMES})
        order.append(f"STILL-{mode}")

    # camera-grammar probe: ArtworkStage with two word-cued focuses (glide
    # proportionality + no pull-back + ambient drift all visible here)
    steps.append({
        "block": "ArtworkStage",
        "props": {"src": IMG3,
                  "label": {"title": "Arms of Achilles", "artist": "Douris",
                            "date": "c. 490 BC", "collection": "KHM Vienna"},
                  "focuses": [
                      {"word": "athena", "x": 0.38, "y": 0.25, "w": 0.3, "h": 0.3,
                       "caption": "Athena presides"},
                      {"word": "vote", "x": 0.15, "y": 0.45, "w": 0.35, "h": 0.35}],
                  "introHold": 30, "glide": 26,
                  "durationInFrames": STEP_FRAMES * 2},
        "revealFrames": [0],
        "words": [{"text": "athena", "startFrame": 45, "endFrame": 55},
                  {"text": "vote", "startFrame": 120, "endFrame": 130}],
        "durationInFrames": STEP_FRAMES * 2})
    order.append("ARTWORK-GRAMMAR")

    job = {"out": "bench_effects.mp4", "theme": "vintage-editorial", "fps": FPS,
           "captions": False, "scale": 0.5, "props": {"steps": steps}}
    job_path = REPO / "render-service" / "remotion-lib" / "output" / "bench_job.json"
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(json.dumps(job, indent=1), encoding="utf-8")
    print(f"{len(steps)} probe steps -> rendering...")
    mp4 = render_chapter(job_path)
    print("rendered", mp4)

    # frame triptychs: early / mid / late per probe (see the MOTION, not a pose)
    out_dir = Path(r"D:\tmp\refframes")
    out_dir.mkdir(parents=True, exist_ok=True)
    f0 = 0
    shots = []
    for eff_id, step in zip(order, steps):
        dur = step["durationInFrames"]
        for tag, off in (("a", 10), ("b", dur // 2), ("c", dur - 6)):
            shots.append((f"{eff_id}_{tag}", f0 + off))
        f0 += dur
    for name, fr in shots:
        subprocess.run([str(FFMPEG), "-y", "-i", str(mp4),
                        "-vf", f"select=eq(n\\,{fr})", "-vframes", "1",
                        str(out_dir / f"bench_{name}.png")],
                       capture_output=True)
    print(f"extracted {len(shots)} frames to {out_dir}")
    print("order:", ", ".join(order))


if __name__ == "__main__":
    main()
