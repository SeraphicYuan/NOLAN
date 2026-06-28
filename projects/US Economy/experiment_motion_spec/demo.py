"""Proof-of-concept: scene design (natural language) -> LLM -> precise render spec -> render.

Proves the "skill awareness" idea across 3 categories / 2 backends, with `position`
controlled by the LLM (one parameterized effect handles any location -- no per-location
scripts). Run:
    D:\\env\\nolan\\python.exe -X utf8 "projects/US Economy/experiment_motion_spec/demo.py"
"""
import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

from nolan.config import load_config
from nolan.llm import create_text_llm
from nolan import remotion_source
from nolan.renderer.scenes import CounterRenderer

EXP = Path("projects/US Economy/experiment_motion_spec")
FF = imageio_ffmpeg.get_ffmpeg_exe()
MANIFEST = json.loads((EXP / "motion_manifest.json").read_text(encoding="utf-8"))

# One shared anchor->fraction map (mirrors layout.ts / Python POSITIONS) so we always
# hand both backends a concrete {x,y} and avoid preset-name mismatches.
FRAC = {
    "top-left": (0.2, 0.18), "top": (0.5, 0.16), "top-right": (0.8, 0.18),
    "left": (0.2, 0.5), "center": (0.5, 0.5), "right": (0.8, 0.5),
    "bottom-left": (0.2, 0.82), "bottom": (0.5, 0.84), "bottom-right": (0.8, 0.82),
    "upper-third": (0.5, 0.3), "lower-third": (0.5, 0.72),
}


def to_xy(position):
    if isinstance(position, dict) and "x" in position:
        return {"x": float(position["x"]), "y": float(position["y"])}
    fx, fy = FRAC.get(str(position), (0.5, 0.5))
    return {"x": fx, "y": fy}


GUIDE = (
    "You translate a one-line video-essay scene design into a precise render spec for "
    "NOLAN's motion library. Pick the single best effect. Output ONLY a JSON object:\n"
    '  {"effect","content","style","position","theme"}\n'
    "- position: a named anchor or {x,y} in 0..1 (where the element sits on screen).\n"
    "- theme: dark-editorial | light | high-contrast (default dark-editorial).\n"
    "- content/style: use exactly the fields listed for the chosen effect.\n\n"
    "CAPABILITY MANIFEST:\n" + json.dumps(MANIFEST, indent=2) + "\n\n"
    "EXAMPLES:\n"
    'Scene: "show the 88% stat, circled, hand-drawn, top-left"\n'
    '{"effect":"annotate-stat","content":{"value":"88%","label":"of the S&P 500"},'
    '"style":{"shapeStyle":"scribble"},"position":"top-left","theme":"dark-editorial"}\n'
    'Scene: "reveal the line \'making more money won\'t save you\', stress \'won\'t save\', centered"\n'
    '{"effect":"kinetic-text","content":{"text":"making more money won\'t save you",'
    '"highlights":["won\'t","save"]},"style":{},"position":"center","theme":"dark-editorial"}\n'
)

SCENES = [
    "Circle the figure $28,000 -- that's stock buybacks per employee -- in the bottom-right, hand-drawn style.",
    "Drop a big +300% counter in the lower third, green, captioned 'market rally 1933-1937'.",
    "Kinetic headline 'two completely different economies', stress 'two' and 'economies', place it toward the top.",
]


async def compile_spec(client, scene: str) -> dict:
    raw = await client.generate(scene, system_prompt=GUIDE)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(m.group(0))


def execute(spec: dict, idx: int) -> Path:
    eff = spec["effect"]
    pos = to_xy(spec.get("position", "center"))
    theme = spec.get("theme", "dark-editorial")
    c = spec.get("content", {})
    st = spec.get("style", {})
    out_name = f"spec_{idx}_{eff}.mp4"

    if eff == "counter":
        r = CounterRenderer(value=int(re.sub(r"[^0-9]", "", str(c.get("value", 0))) or 0),
                            label=c.get("label"), prefix=c.get("prefix", ""), suffix=c.get("suffix", ""),
                            position=pos)
        tone = st.get("tone", "neutral")
        if tone == "success":
            r = r.with_success_style()
        elif tone == "danger":
            r = r.with_danger_style()
        out = EXP / out_name
        r.render(str(out), duration=4.0, with_qa=False)
        return out

    if eff == "annotate-stat":
        props = {"value": c.get("value", ""), "label": c.get("label", ""),
                 "shapeStyle": st.get("shapeStyle", "clean"), "position": pos, "theme": theme}
        p = remotion_source.render("AnnotateStat", props, out_name, duration_frames=110)
    elif eff == "kinetic-text":
        props = {"text": c.get("text", ""), "highlights": c.get("highlights", []),
                 "position": pos, "theme": theme, "scrim": 0}
        p = remotion_source.render("Kinetic", props, out_name, duration_frames=110)
    else:
        raise ValueError(f"unknown effect {eff}")
    dst = EXP / out_name
    shutil.copy(p, dst)
    return dst


async def main():
    client = create_text_llm(load_config())
    for i, scene in enumerate(SCENES, 1):
        spec = await compile_spec(client, scene)
        print(f"\n[{i}] SCENE: {scene}")
        print("    SPEC:", json.dumps(spec))
        out = execute(spec, i)
        # QA still
        subprocess.run([FF, "-y", "-ss", "2.6", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                        str(EXP / f"spec_{i}_{spec['effect']}.jpg"), "-loglevel", "error"], capture_output=True)
        print("    ->", out.name)


if __name__ == "__main__":
    asyncio.run(main())
