"""Smoke test: validate the segment-search-clip + renderer-card -> nolan assemble path.

Builds 2 scenes (1 archival b-roll clip from the source, 1 animated counter card),
a 2-scene ScenePlan, and a 10s audio slice. Then assemble is run separately.
All visual assets are normalized to 1920x1080 @ 30fps so concat -c copy is happy.
"""
import subprocess
from pathlib import Path
import imageio_ffmpeg

from nolan.scenes import Scene, ScenePlan
from nolan.renderer.scenes import CounterRenderer

EXP = Path("projects/US Economy/experiment_roaring20s")
SRC = sorted(Path("projects/US Economy").glob("source/*.mp4"))[0]
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30

(EXP / "clips").mkdir(exist_ok=True)
(EXP / "cards").mkdir(exist_ok=True)

VF = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
      f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS}")


def extract_clip(start: float, dur: float, out: Path) -> None:
    cmd = [FF, "-y", "-ss", str(start), "-i", str(SRC), "-t", str(dur),
           "-vf", VF, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
           "-r", str(FPS), "-loglevel", "error", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"extract failed: {r.stderr[-800:]}")


def slice_audio(start: float, dur: float, out: Path) -> None:
    cmd = [FF, "-y", "-ss", str(start), "-i", str(SRC), "-t", str(dur),
           "-vn", "-c:a", "aac", "-b:a", "192k", "-loglevel", "error", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def main() -> None:
    # 1) Archival b-roll clip (segment-search source): 1920s street scene @134.4s
    broll = EXP / "clips" / "smoke_broll.mp4"
    extract_clip(134.4, 5.0, broll)
    print("b-roll  :", broll, broll.stat().st_size, "bytes")

    # 2) Animated counter card (renderer source): -85% danger style
    counter = CounterRenderer(value=85, label="STOCK MARKET VALUE WIPED OUT",
                              prefix="-", suffix="%", count_duration=2.0)
    if hasattr(counter, "with_danger_style"):
        counter = counter.with_danger_style()
    card = EXP / "cards" / "smoke_counter.mp4"
    counter.render(str(card), duration=5.0, with_qa=False)
    print("card    :", card, card.stat().st_size, "bytes")

    # 3) 10s audio slice (135.0 -> 145.0)
    aud = EXP / "smoke_audio.m4a"
    slice_audio(135.0, 10.0, aud)
    print("audio   :", aud)

    # 4) 2-scene plan (paths relative to plan dir)
    s1 = Scene(id="smoke_broll", visual_type="b-roll", rendered_clip="clips/smoke_broll.mp4",
               start_seconds=0.0, end_seconds=5.0, narration_excerpt="Roaring Twenties")
    s2 = Scene(id="smoke_counter", visual_type="counter", rendered_clip="cards/smoke_counter.mp4",
               start_seconds=5.0, end_seconds=10.0, narration_excerpt="wiped out 85%")
    plan = ScenePlan(sections={"smoke": [s1, s2]})
    plan_path = EXP / "smoke_plan.json"
    plan.save(str(plan_path))
    print("plan    :", plan_path)
    print("\nNext: nolan assemble", plan_path.name)


if __name__ == "__main__":
    main()
