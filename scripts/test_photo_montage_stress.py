"""
Stress test for the PhotoMontage motion system — the four motion categories:

  3 (518fb653) usual entrance + settle angle      -> `from` sugar
  4 (5a03bf04) fade in/out + move up/down/...      -> keyframe `opacity`/`y` track
  2 (425f844b) appear, THEN tilt to an angle       -> keyframe `rotation` track (delayed)
  1 (985f7653) complex multi-step path, layers,    -> multi-key `x/y/scale/rotation`
               different sizes                          on several layered cards

Renders one composition and dumps frames across the timeline so the sequencing is
visible. Needs Windows Node + render-service/node_modules.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import numpy as np
from PIL import Image

OUT = os.path.abspath("test_output/photo_montage_stress")
os.makedirs(OUT, exist_ok=True)


def _rect(name, color, size=(560, 720)):
    img = Image.new("RGB", size, color)
    a = np.array(img)
    a[:20, :] = a[-20:, :] = a[:, :20] = a[:, -20:] = (40, 35, 30)
    p = os.path.join(OUT, name)
    Image.fromarray(a).save(p)
    return p


def main():
    from nolan.motion import validate, render

    base = _rect("base.png", (205, 195, 165))
    left = _rect("left.png", (190, 200, 195))
    tilt = _rect("tilt.png", (200, 175, 155))
    inout = _rect("inout.png", (180, 185, 205))
    small = _rect("small.png", (210, 190, 175))

    spec = {
        "effect": "photo-montage-pro",
        "content": {
            "background": "#221018",
            "cards": [
                # --- category 3: usual entrance + settle angle (from-sugar) ---
                {"src": base, "x": 0.22, "y": 0.55, "scale": 0.42, "rotation": -5,
                 "from": "left", "enterAt": 0.1, "enterDur": 0.8, "frame": "polaroid",
                 "caption": "entrance"},

                # --- category 4: fade in (move up), hold, fade out (move up) ---
                {"src": inout, "x": 0.5, "y": 0.55, "scale": 0.4, "rotation": 2,
                 "frame": "polaroid", "caption": "fade in/out",
                 "keys": [
                     {"at": 0.4, "y": 0.72, "opacity": 0.0},
                     {"at": 1.1, "y": 0.55, "opacity": 1.0, "ease": "out"},
                     {"at": 3.0, "y": 0.55, "opacity": 1.0},
                     {"at": 3.8, "y": 0.40, "opacity": 0.0, "ease": "inOut"},
                 ]},

                # --- category 2: appear flat, THEN tilt to an angle ---
                {"src": tilt, "x": 0.8, "y": 0.55, "scale": 0.42, "frame": "polaroid",
                 "caption": "tilt later",
                 "keys": [
                     {"at": 0.8, "opacity": 0.0, "rotation": 0, "scale": 0.42},
                     {"at": 1.4, "opacity": 1.0, "rotation": 0, "ease": "out"},
                     {"at": 2.4, "rotation": 0},                       # hold flat
                     {"at": 2.9, "rotation": 14, "ease": "inOut"},     # then tilt
                 ]},

                # --- category 1: complex multi-step path + different sizes/layers ---
                {"src": small, "x": 0.15, "y": 0.3, "scale": 0.22, "frame": "plain",
                 "keys": [
                     {"at": 2.0, "x": 0.15, "y": 0.30, "scale": 0.18, "rotation": -8, "opacity": 0.0},
                     {"at": 2.6, "x": 0.4, "y": 0.25, "scale": 0.26, "rotation": 4, "opacity": 1.0, "ease": "out"},
                     {"at": 3.6, "x": 0.62, "y": 0.7, "scale": 0.34, "rotation": -3, "ease": "inOut"},
                     {"at": 4.4, "x": 0.85, "y": 0.32, "scale": 0.2, "rotation": 10, "ease": "inOut"},
                 ]},
            ],
        },
        "style": {"vignette": 0.5, "zoomStart": 1.04, "zoomEnd": 1.14, "panX": -0.03},
        "duration": 5.0,
    }

    norm, errors = validate(spec)
    print("validate errors:", errors)
    assert not errors, errors

    out = os.path.abspath(f"{OUT}/stress.mp4")
    print("rendering (bundling Remotion)...")
    render(norm, out)

    import subprocess
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    assert os.path.exists(out) and os.path.getsize(out) > 1024
    r = subprocess.run([ff, "-hide_banner", "-i", out], capture_output=True, text=True)
    assert "1920x1080" in r.stderr, "bad resolution"
    for t in (0.6, 1.3, 2.5, 3.4, 4.2, 4.8):
        fp = f"{OUT}/s_{int(t*10):02d}.png"
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(t), "-i", out, "-frames:v", "1", fp])
    print(f"PASS -> {out}  (frames s_06..s_48)")


if __name__ == "__main__":
    main()
