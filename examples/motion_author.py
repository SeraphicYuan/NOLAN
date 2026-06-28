"""Example: author motion scenes from natural language.

Demonstrates the nolan.motion spec system end-to-end: scene design -> LLM -> validated
spec -> render, across categories and both backends (Python + Remotion).

Usage:
    D:\\env\\nolan\\python.exe -X utf8 examples/motion_author.py

Output:
    Renders one clip per scene design into ./motion_out/ and prints each spec.
"""
import asyncio
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg

from nolan.config import load_config
from nolan.llm import create_text_llm
from nolan.motion import compile_spec, render

OUT = Path("motion_out")
FF = imageio_ffmpeg.get_ffmpeg_exe()

SCENES = [
    "Circle the figure $46.6B -- total Lowe's buybacks -- bottom-right, hand-drawn style.",
    "Drop a big +300% counter in the lower third, green, captioned 'market rally 1933-1937'.",
    "Kinetic headline \"making more money won't save you\", stress \"won't\" and \"save\", centered.",
    "Bar comparison: AI data-center capex $520B vs the dot-com telecom peak $160B, glass bars.",
    "Chapter card: kicker 'Player 3', title 'The Government', subtitle 'who writes the rules'.",
    "Feedback loop diagram: stocks rise, their fees rise, they vote for buybacks, buybacks lift stocks.",
]


async def main():
    OUT.mkdir(exist_ok=True)
    client = create_text_llm(load_config())
    for i, scene in enumerate(SCENES, 1):
        spec, errors = await compile_spec(scene, client)
        out = OUT / f"{i:02d}_{spec.get('effect', 'unknown')}.mp4"
        print(f"\n[{i}] {scene}")
        print(f"    spec : {json.dumps({k: spec[k] for k in spec if k != 'target'})}")
        if errors:
            print(f"    warn : {errors}")
        try:
            render(spec, out)
            subprocess.run([FF, "-y", "-ss", "2.4", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                            str(out.with_suffix(".jpg")), "-loglevel", "error"], capture_output=True)
            print(f"    -> {out.name}")
        except Exception as ex:  # noqa: BLE001
            print(f"    RENDER FAILED: {type(ex).__name__}: {str(ex)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
