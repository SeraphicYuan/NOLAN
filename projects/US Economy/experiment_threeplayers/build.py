"""'Three players' (asset managers) — 4-source build (~57s).

Sources: segment search (archival finance b-roll), ComfyUI (boardroom plate),
Python renderers (counter/comparison/line-chart/title + compositing), and the
Lottie motion library (animated lower-third via the render-service).

Run: D:\\env\\nolan\\python.exe -X utf8 "projects/US Economy/experiment_threeplayers/build.py"
Then: nolan assemble scene_plan.json vo.m4a -o final.mp4 -r 1920x1080 --fps 30
"""
import asyncio
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

from nolan.scenes import Scene, ScenePlan
from nolan.renderer.scenes import (
    CounterRenderer, TitleRenderer, LowerThirdRenderer, ComparisonRenderer,
    LineChartRenderer, KenBurnsRenderer,
)
from nolan.renderer.composite import composite_over_broll
from nolan.comfyui import ComfyUIClient
from nolan.lottie import render_template
from nolan.infographic_client import InfographicClient, Engine

EXP = Path("projects/US Economy/experiment_threeplayers")
SRC = sorted(Path("projects/US Economy").glob("source/*.mp4"))[0]
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30
CL = EXP / "clips"; GEN = EXP / "generated"; TMP = EXP / "tmp"
for d in (CL, GEN, TMP):
    d.mkdir(parents=True, exist_ok=True)
VF = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
      f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS}")


def extract(start, dur, out, fade=0.0):
    vf = VF + (f",fade=t=in:st=0:d={fade},fade=t=out:st={dur-fade:.3f}:d={fade}" if fade else "")
    r = subprocess.run([FF, "-y", "-ss", str(start), "-i", str(SRC), "-t", str(dur),
                        "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                        "-r", str(FPS), "-loglevel", "error", str(out)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"extract {out.name}: {r.stderr[-300:]}")


def normalize(inp, out, dur):
    r = subprocess.run([FF, "-y", "-i", str(inp), "-t", str(dur), "-vf", VF,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", "-r", str(FPS),
                        "-loglevel", "error", str(out)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"normalize {out.name}: {r.stderr[-300:]}")


async def gen_image(prompt, png, workflow="workflows/image/basic-z-image.json", node="27"):
    c = ComfyUIClient(host="127.0.0.1", port=8080, workflow_file=Path(workflow), prompt_node=node)
    await c.generate(prompt, png, timeout=240.0)
    return png.exists()


async def render_lottie(template_rel, out_clip, duration, **fields):
    """Customize a catalog Lottie (text/colors) then rasterize via the render-service."""
    tpl = Path("assets/common/lottie") / template_rel
    custom = TMP / (tpl.stem + "_custom.json")
    render_template(str(tpl), output_path=str(custom), **fields)
    client = InfographicClient(host="127.0.0.1", port=3010)
    if not await client.health_check():
        raise RuntimeError("render-service not reachable on 127.0.0.1:3010")
    vid = await client.render(engine=Engine.REMOTION,
                              data={"lottie_path": str(custom.resolve()), "width": W, "height": H, "fps": FPS},
                              duration=duration, width=W, height=H)
    p = Path(str(vid))
    if not p.exists():
        p = Path("render-service/output") / p.name
    normalize(p, out_clip, duration)   # guarantee 1920x1080@30 for concat
    return out_clip


async def main():
    scenes = []
    def add(sid, vtype, a, b, clip, narr):
        scenes.append(Scene(id=sid, visual_type=vtype, rendered_clip=clip,
                            start_seconds=a, end_seconds=b, narration_excerpt=narr))

    # b1 0-8: name card (brand-as-text) + $24T, composited over trading-floor b-roll (search)
    bg = TMP / "b1_bg.mp4"; extract(1072.0, 8.0, bg)
    composite_over_broll(
        TitleRenderer(title="BLACKROCK  -  VANGUARD  -  STATE STREET",
                      subtitle="$24 trillion under management"),
        str(bg), str(CL / "b1.mp4"), duration=8.0, scrim=0.5, fade=0.4, ffmpeg=FF)
    add("b1", "b-roll", 0.0, 8.0, "clips/b1.mp4", "BlackRock, Vanguard and State Street manage over 24 trillion")

    # b2 8-15: counter 88% over trading-screens b-roll (search + renderer composite)
    bg = TMP / "b2_bg.mp4"; extract(1185.9, 7.0, bg)
    composite_over_broll(
        CounterRenderer(value=88, label="LARGEST SHAREHOLDER IN 88% OF THE S&P 500", suffix="%",
                        count_duration=2.0).with_danger_style(),
        str(bg), str(CL / "b2.mp4"), duration=7.0, scrim=0.5, fade=0.4, ffmpeg=FF)
    add("b2", "counter", 8.0, 15.0, "clips/b2.mp4", "largest single shareholder in 88% of S&P 500 companies")

    # b3 15-21: ComfyUI boardroom + composite lower-third (generation + renderer)
    boardroom = GEN / "boardroom.png"
    ok = await gen_image(
        "corporate boardroom, executives in suits seated around a long polished table at a "
        "shareholder meeting, raising hands to vote, modern glass office, cinematic, photorealistic",
        boardroom)
    if ok:
        KenBurnsRenderer(image_path=str(boardroom), zoom_start=1.0, zoom_end=1.1).render(
            str(TMP / "b3_bg.mp4"), duration=6.0, with_qa=False)
        b3bg = TMP / "b3_bg.mp4"
    else:
        extract(1072.0, 6.0, TMP / "b3_bg.mp4"); b3bg = TMP / "b3_bg.mp4"
    composite_over_broll(
        LowerThirdRenderer(name="They vote on behalf of millions",
                           title="at every corporate shareholder meeting"),
        str(b3bg), str(CL / "b3.mp4"), duration=6.0, scrim=0.35, fade=0.4, ffmpeg=FF)
    add("b3", "generated-image", 15.0, 21.0, "clips/b3.mp4", "vote on behalf of millions of investors")

    # b4 21-28: LOTTIE animated lower-third (source #4)
    await render_lottie("lower-thirds/modern.json", CL / "b4.mp4", duration=7.0,
                        headline="A SAY ON CEO PAY & BUYBACKS")
    add("b4", "lottie", 21.0, 28.0, "clips/b4.mp4", "a lot of say on CEO compensation or buyback programs")

    # b5 28-36: lower-third 'fees on % of assets' over trading-floor b-roll (search + renderer)
    bg = TMP / "b5_bg.mp4"; extract(98.1, 8.0, bg)
    composite_over_broll(
        LowerThirdRenderer(name="They charge a fee on a % of assets",
                           title="when the market rises, their revenue rises automatically"),
        str(bg), str(CL / "b5.mp4"), duration=8.0, scrim=0.45, fade=0.4, ffmpeg=FF)
    add("b5", "b-roll", 28.0, 36.0, "clips/b5.mp4", "they charge fees on the percentage of total assets")

    # b6 36-41: mini rising line chart — revenue follows the market (renderer)
    LineChartRenderer([("", 100), ("", 160), ("", 240), ("", 360)],
                      title="THEIR FEE REVENUE FOLLOWS THE MARKET UP", draw_duration=3.5).render(
        str(CL / "b6.mp4"), duration=5.0, with_qa=False)
    add("b6", "graphic", 36.0, 41.0, "clips/b6.mp4", "anytime the stock market goes up their revenue goes up")

    # b7 41-49: the conflict — comparison (renderer)
    ComparisonRenderer(left_text="PROFIT", right_text="VOTE",
                       left_subtitle="more when stocks rise",
                       right_subtitle="on CEO buybacks that lift stocks",
                       center_label="&").render(str(CL / "b7.mp4"), duration=8.0, with_qa=False)
    add("b7", "comparison", 41.0, 49.0, "clips/b7.mp4", "same firms that profit when stocks rise also vote on buybacks")

    # b8 49-57.2: the punchline (renderer title, full frame)
    TitleRenderer(title="VOTING AGAINST BUYBACKS",
                  subtitle="would mean voting against their own revenue - so they never do").render(
        str(CL / "b8.mp4"), duration=8.2, with_qa=False)
    add("b8", "title", 49.0, 57.2, "clips/b8.mp4", "voting against buybacks would be voting against their own revenue")

    ScenePlan(sections={"three_players": scenes}).save(str(EXP / "scene_plan.json"))
    print(f"Built {len(scenes)} scenes -> scene_plan.json")
    for s in scenes:
        print(f"  {s.start_seconds:5.1f}-{s.end_seconds:5.1f}  {s.id:4s} {s.rendered_clip}")


if __name__ == "__main__":
    asyncio.run(main())
