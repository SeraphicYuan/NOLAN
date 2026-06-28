"""v2 re-cut using the new renderer capabilities:

  - compositing  : counters / lower-thirds / titles OVER moving b-roll (not black cards)
  - line chart   : the 1922->1929->crash->1933-37 arc as a real animated chart
  - fades        : gentle fade in/out on cuts so it breathes

Outputs clips into clips_v2/ and a scene_plan_v2.json. Assemble separately:
  nolan assemble scene_plan_v2.json vo.m4a -o final_v2.mp4 -r 1920x1080 --fps 30
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg

from nolan.scenes import Scene, ScenePlan
from nolan.renderer.scenes import (
    CounterRenderer, TitleRenderer, LowerThirdRenderer, KenBurnsRenderer, LineChartRenderer,
)
from nolan.renderer.composite import composite_over_broll

EXP = Path("projects/US Economy/experiment_roaring20s")
SRC = sorted(Path("projects/US Economy").glob("source/*.mp4"))[0]
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30
CL = EXP / "clips_v2"; CL.mkdir(exist_ok=True)
VF = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
      f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS}")


def extract(start, dur, out, fade=0.0):
    vf = VF
    if fade > 0:
        vf += f",fade=t=in:st=0:d={fade},fade=t=out:st={dur - fade:.3f}:d={fade}"
    cmd = [FF, "-y", "-ss", str(start), "-i", str(SRC), "-t", str(dur),
           "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
           "-r", str(FPS), "-loglevel", "error", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"extract {out.name}: {r.stderr[-400:]}")


def main():
    scenes = []
    def add(sid, vtype, a, b, clip, narr):
        scenes.append(Scene(id=sid, visual_type=vtype, rendered_clip=clip,
                            start_seconds=a, end_seconds=b, narration_excerpt=narr))

    # b1 0-6.5: TITLE composited over 1920s street (start past the burned-in title)
    bg = CL / "b1_bg.mp4"; extract(138.5, 6.5, bg)
    composite_over_broll(
        TitleRenderer(title="THE ROARING TWENTIES", subtitle="a golden era - on paper"),
        str(bg), str(CL / "b1.mp4"), duration=6.5, scrim=0.35, fade=0.4, ffmpeg=FF)
    add("b1", "b-roll", 0.0, 6.5, "clips_v2/b1.mp4", "the Roaring Twenties, a golden era on paper")

    # b2 6.5-16: line chart RISE 1922->1929
    LineChartRenderer([("1922", 100), ("1924", 175), ("1926", 280), ("1928", 430), ("1929", 600)],
                      title="DOW JONES  -  1922 to 1929", draw_duration=7.0).render(
        str(CL / "b2.mp4"), duration=9.5, with_qa=False)
    add("b2", "graphic", 6.5, 16.0, "clips_v2/b2.mp4", "the Dow had gone up six times in eight years")

    # b3 16-27.5: archival factory / farmers (pure b-roll + fade)
    extract(157.4, 11.5, CL / "b3.mp4", fade=0.4)
    add("b3", "b-roll", 16.0, 27.5, "clips_v2/b3.mp4", "farmers drowning in debt, factories overproducing")

    # b4 27.5-38: LOWER-THIRD composited over trading-floor crowd
    bg = CL / "b4_bg.mp4"; extract(173.0, 10.5, bg)
    composite_over_broll(
        LowerThirdRenderer(name="The market ran on borrowed money",
                           title="bigger and bigger bets on stocks going up"),
        str(bg), str(CL / "b4.mp4"), duration=10.5, scrim=0.42, fade=0.4, ffmpeg=FF)
    add("b4", "b-roll", 27.5, 38.0, "clips_v2/b4.mp4", "borrowing money to place bigger bets. Sound familiar?")

    # b5 38-50: line chart FULL ARC (rise -> 1929 crash -> 1933-37 rally)
    LineChartRenderer(
        [("1922", 100), ("1925", 280), ("1929", 600), ("1930", 300), ("1932", 90),
         ("1934", 200), ("1937", 360)],
        title="DOW JONES INDEX  -  1922 to 1937", draw_duration=9.5).render(
        str(CL / "b5.mp4"), duration=12.0, with_qa=False)
    add("b5", "graphic", 38.0, 50.0, "clips_v2/b5.mp4", "in 1929 the crash wiped out 85 percent, then it rallied back")

    # b6a 50-57: COUNTER +300% composited over archival street
    bg = CL / "b6a_bg.mp4"; extract(138.5, 7.0, bg)
    composite_over_broll(
        CounterRenderer(value=300, label="STOCK MARKET RALLY  -  1933 to 1937", prefix="+",
                        suffix="%", count_duration=2.0).with_success_style(),
        str(bg), str(CL / "b6a.mp4"), duration=7.0, scrim=0.5, fade=0.4, ffmpeg=FF)
    add("b6a", "counter", 50.0, 57.0, "clips_v2/b6a.mp4", "the market rallied back over 300 percent")

    # b6b 57-63: title card (full frame)
    TitleRenderer(title="BUT ONLY THE STOCK MARKET",
                  subtitle="the economy told a different story").render(
        str(CL / "b6b.mp4"), duration=6.0, with_qa=False)
    add("b6b", "title", 57.0, 63.0, "clips_v2/b6b.mp4", "that was again just the stock market")

    # b7 63-74: FLUX breadline hero (variant A) + Ken Burns
    KenBurnsRenderer(image_path=str(EXP / "generated" / "b7_flux_a.png"),
                     zoom_start=1.0, zoom_end=1.12, pan_direction="up").render(
        str(CL / "b7.mp4"), duration=11.0, with_qa=False)
    add("b7", "generated-image", 63.0, 74.0, "clips_v2/b7.mp4",
        "while ordinary Americans still stood in breadlines")

    # b8 74-86: LOWER-THIRD composited over FLUX breadline variant B (Ken Burns bg)
    KenBurnsRenderer(image_path=str(EXP / "generated" / "b7_flux_b.png"),
                     zoom_start=1.05, zoom_end=1.0).render(
        str(CL / "b8_bg.mp4"), duration=12.0, with_qa=False)
    composite_over_broll(
        LowerThirdRenderer(name="Stock market  =/=  your life",
                           title="recovery wasn't a reality for most"),
        str(CL / "b8_bg.mp4"), str(CL / "b8.mp4"), duration=12.0, scrim=0.35, fade=0.5, ffmpeg=FF)
    add("b8", "lower-third", 74.0, 86.0, "clips_v2/b8.mp4", "recovery wasn't really a reality for most")

    plan = ScenePlan(sections={"roaring_twenties_v2": scenes})
    plan.save(str(EXP / "scene_plan_v2.json"))
    print(f"Built {len(scenes)} v2 scenes -> scene_plan_v2.json")
    for s in scenes:
        print(f"  {s.start_seconds:5.1f}-{s.end_seconds:5.1f}  {s.id:5s} {s.rendered_clip}")


if __name__ == "__main__":
    main()
