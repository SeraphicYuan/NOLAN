"""Asset-first build of the Roaring Twenties video essay (~86s).

Exercises all three sources:
  - segment search  -> archival b-roll clips cut from the indexed source
  - renderer/motion -> animated counter / title / lower-third cards
  - ComfyUI         -> a generated breadline 'hero' still + Ken Burns (graceful fallback)

Produces a scene_plan.json + normalized 1920x1080@30 clips. Assemble is run separately:
  nolan assemble scene_plan.json vo.m4a -o final.mp4 -r 1920x1080 --fps 30
"""
import asyncio
import subprocess
from pathlib import Path

import imageio_ffmpeg

from nolan.scenes import Scene, ScenePlan
from nolan.renderer.scenes import (
    CounterRenderer, TitleRenderer, LowerThirdRenderer, KenBurnsRenderer,
)

EXP = Path("projects/US Economy/experiment_roaring20s")
SRC = sorted(Path("projects/US Economy").glob("source/*.mp4"))[0]
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30
VF = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
      f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS}")

CLIPS = EXP / "clips"; CARDS = EXP / "cards"; GEN = EXP / "generated"
for d in (CLIPS, CARDS, GEN):
    d.mkdir(exist_ok=True)


def extract_clip(start: float, dur: float, out: Path) -> None:
    cmd = [FF, "-y", "-ss", str(start), "-i", str(SRC), "-t", str(dur),
           "-vf", VF, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
           "-r", str(FPS), "-loglevel", "error", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"extract {out.name}: {r.stderr[-400:]}")


async def comfyui_hero(prompt: str, png: Path) -> bool:
    """Generate a still on the live ComfyUI (8080). Returns True on success."""
    try:
        from nolan.comfyui import ComfyUIClient
        client = ComfyUIClient(host="127.0.0.1", port=8080, width=1344, height=768, steps=22)
        if not await client.check_connection():
            print("  ComfyUI not reachable -> fallback")
            return False
        await client.generate(prompt, png, timeout=240.0)
        return png.exists() and png.stat().st_size > 0
    except Exception as ex:  # noqa: BLE001 - any gen failure -> fallback
        print(f"  ComfyUI gen failed ({ex}) -> fallback")
        return False


def main() -> None:
    scenes = []

    def add(scene_id, vtype, start, end, rendered_clip, narration):
        scenes.append(Scene(id=scene_id, visual_type=vtype, rendered_clip=rendered_clip,
                            start_seconds=start, end_seconds=end, narration_excerpt=narration))

    # --- b1: archival 1920s street (golden era) ---
    extract_clip(134.4, 6.5, CLIPS / "b1.mp4")
    add("b1_roaring", "b-roll", 0.0, 6.5, "clips/b1.mp4", "the Roaring Twenties, a golden era on paper")

    # --- b2: counter 6x (Dow boom) ---
    CounterRenderer(value=6, label="DOW JONES  -  1922 to 1929", suffix="x",
                    count_duration=2.0).with_success_style().render(
        str(CARDS / "b2.mp4"), duration=9.5, with_qa=False)
    add("b2_dow", "counter", 6.5, 16.0, "cards/b2.mp4", "the Dow had gone up six times in eight years")

    # --- b3: archival farmers / factories (the cracks) ---
    extract_clip(157.4, 11.5, CLIPS / "b3.mp4")
    add("b3_cracks", "b-roll", 16.0, 27.5, "clips/b3.mp4", "farmers drowning in debt, factories overproducing")

    # --- b4: archival trading floor (borrowing to bet) ---
    extract_clip(172.0, 10.5, CLIPS / "b4.mp4")
    add("b4_bets", "b-roll", 27.5, 38.0, "clips/b4.mp4", "borrowing money to place bigger bets. Sound familiar?")

    # --- b5a: archival 1929 crash / discarded papers ---
    extract_clip(178.1, 6.0, CLIPS / "b5a.mp4")
    add("b5a_crash", "b-roll", 38.0, 44.0, "clips/b5a.mp4", "in 1929 the stocks stopped, the Great Depression hit")

    # --- b5b: counter 1 in 4 unemployed (danger) ---
    CounterRenderer(value=25, label="U.S. UNEMPLOYMENT  -  1 IN 4 AMERICANS", suffix="%",
                    count_duration=2.0).with_danger_style().render(
        str(CARDS / "b5b.mp4"), duration=6.0, with_qa=False)
    add("b5b_unemp", "counter", 44.0, 50.0, "cards/b5b.mp4", "unemployment hit one in four Americans")

    # --- b6a: counter +300% rally (success) ---
    CounterRenderer(value=300, label="STOCK MARKET RALLY  -  1933 to 1937", prefix="+", suffix="%",
                    count_duration=2.0).with_success_style().render(
        str(CARDS / "b6a.mp4"), duration=7.0, with_qa=False)
    add("b6a_rally", "counter", 50.0, 57.0, "cards/b6a.mp4", "the market rallied back over 300 percent")

    # --- b6b: title 'but only the stock market' ---
    TitleRenderer(title="BUT ONLY THE STOCK MARKET",
                  subtitle="the economy told a different story").render(
        str(CARDS / "b6b.mp4"), duration=6.0, with_qa=False)
    add("b6b_title", "title", 57.0, 63.0, "cards/b6b.mp4", "that was again just the stock market")

    # --- b7: ComfyUI breadline hero + Ken Burns (fallback: archival breadline) ---
    prompt = ("1930s Great Depression breadline, a long line of poor unemployed men in worn "
              "coats and flat caps waiting outside a soup kitchen, black and white archival "
              "documentary photograph, 35mm film grain, somber overcast light, deep focus, "
              "photorealistic, historical")
    hero_png = GEN / "b7_breadline.png"
    ok = asyncio.run(comfyui_hero(prompt, hero_png))
    if ok:
        KenBurnsRenderer(image_path=str(hero_png), zoom_start=1.0, zoom_end=1.12,
                         pan_direction="up").render(str(CLIPS / "b7.mp4"), duration=11.0, with_qa=False)
        print("  b7: ComfyUI hero + Ken Burns OK")
    else:
        extract_clip(216.2, 11.0, CLIPS / "b7.mp4")
        print("  b7: fallback archival breadline clip")
    add("b7_breadline", "generated-image", 63.0, 74.0, "clips/b7.mp4",
        "while ordinary Americans still stood in breadlines")

    # --- b8a: archival despondent man ---
    extract_clip(217.4, 6.0, CLIPS / "b8a.mp4")
    add("b8a_despondent", "b-roll", 74.0, 80.0, "clips/b8a.mp4", "recovery wasn't really a reality")

    # --- b8b: lower-third closing line ---
    LowerThirdRenderer(name="Stock market  =/=  your life",
                       title="recovery wasn't a reality for most").render(
        str(CARDS / "b8b.mp4"), duration=6.0, with_qa=False)
    add("b8b_close", "lower-third", 80.0, 86.0, "cards/b8b.mp4", "for most")

    plan = ScenePlan(sections={"roaring_twenties": scenes})
    plan_path = EXP / "scene_plan.json"
    plan.save(str(plan_path))
    print(f"\nBuilt {len(scenes)} scenes -> {plan_path}")
    for s in scenes:
        print(f"  {s.start_seconds:5.1f}-{s.end_seconds:5.1f}  {s.id:16s} {s.rendered_clip}")


if __name__ == "__main__":
    main()
