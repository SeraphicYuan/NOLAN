"""Extract the original voiceover for the Roaring Twenties segment (Beat 1-8).

Span: ~02:15.0 -> ~03:41.0 of the source (the self-contained
'golden era -> cracks -> 1929 crash -> rally while breadlines' arc).
Uses the imageio-ffmpeg bundled binary so no system ffmpeg is required.
"""
import subprocess
from pathlib import Path
import imageio_ffmpeg

PROJECT = Path("projects/US Economy")
OUT = PROJECT / "experiment_roaring20s"

START = 135.0      # 02:15.0  "I'm sure a lot of you have heard about the Roaring Twenties"
DURATION = 86.0    # -> 03:41.0  "...recovery wasn't really a reality for most."

src = sorted(PROJECT.glob("source/*.mp4"))[0]
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
out_audio = OUT / "vo.m4a"

cmd = [
    ffmpeg, "-y",
    "-ss", str(START), "-t", str(DURATION),
    "-i", str(src),
    "-vn", "-c:a", "aac", "-b:a", "192k",
    str(out_audio),
]
print("Source :", src.name)
print("Span   :", f"{START}s for {DURATION}s")
print("Output :", out_audio)
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    print("FFMPEG ERROR:\n", r.stderr[-2000:])
    raise SystemExit(r.returncode)
print(f"OK -> {out_audio} ({out_audio.stat().st_size} bytes)")
