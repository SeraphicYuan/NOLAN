"""
Demo + smoke test for the Remotion `PhotoMontage` composition (spec id `photo-montage-pro`).

Exercises the per-card motion system: each card declares where it rests and how it
arrives independently —
  - one slides UP from the bottom and settles in the MIDDLE,
  - one slides in from the LEFT and rests on the LEFT,
  - one slides in from the RIGHT and rests on the RIGHT,
  - one transparent CUTOUT drops in from the TOP (silhouette drop-shadow).

Renders through the real motion-spec path (validate -> executor -> remotion_source ->
render.mjs), so it also proves multi-image staging works. Needs Windows Node + the
Remotion deps in render-service/node_modules.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.abspath("test_output/photo_montage_pro")
os.makedirs(OUT, exist_ok=True)


def _rect(name, color, size=(560, 720)):
    img = Image.new("RGB", size, color)
    a = np.array(img)
    a[:22, :] = a[-22:, :] = a[:, :22] = a[:, -22:] = (38, 33, 28)
    p = os.path.join(OUT, name)
    Image.fromarray(a).save(p)
    return p


def _cutout(name, color, size=(560, 720)):
    """A transparent PNG with an opaque elliptical 'subject' — for frame:'cutout'."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([40, 40, size[0] - 40, size[1] - 40], fill=color + (255,))
    p = os.path.join(OUT, name)
    img.save(p)
    return p


def main():
    from nolan.motion import validate, render

    a = _rect("center.png", (205, 195, 165))
    b = _rect("left.png", (190, 200, 195))
    c = _rect("right.png", (200, 175, 155))
    d = _cutout("cutout.png", (175, 150, 120))

    spec = {
        "effect": "photo-montage-pro",
        "content": {
            "background": "#241016",
            "cards": [
                {"src": b, "x": 0.2, "y": 0.52, "scale": 0.46, "rotation": -6,
                 "from": "left", "enterAt": 0.2, "enterDur": 0.8, "frame": "polaroid",
                 "caption": "On the left"},
                {"src": c, "x": 0.8, "y": 0.52, "scale": 0.46, "rotation": 6,
                 "from": "right", "enterAt": 0.5, "enterDur": 0.8, "frame": "polaroid",
                 "caption": "On the right"},
                {"src": a, "x": 0.5, "y": 0.52, "scale": 0.54, "rotation": 2,
                 "from": "bottom", "enterAt": 1.0, "enterDur": 0.9, "ease": "spring",
                 "frame": "polaroid", "caption": "Tokugawa Ieyasu"},
                {"src": d, "x": 0.5, "y": 0.26, "scale": 0.34, "from": "top",
                 "enterAt": 1.8, "enterDur": 0.8, "frame": "cutout"},
            ],
        },
        "style": {"vignette": 0.55, "zoomStart": 1.05, "zoomEnd": 1.18, "panX": -0.05},
        "duration": 5.0,
    }

    norm, errors = validate(spec)
    print("validate errors:", errors)
    assert not errors, errors
    print("backend/target:", norm["backend"], norm["target"])

    out = os.path.abspath(f"{OUT}/montage_pro.mp4")
    print("rendering (bundling Remotion, ~1 min)...")
    render(norm, out)

    # verify
    import imageio_ffmpeg
    import subprocess
    assert os.path.exists(out) and os.path.getsize(out) > 1024, "no output"
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ff, "-hide_banner", "-i", out], capture_output=True, text=True)
    info = [l.strip() for l in r.stderr.splitlines() if "Duration" in l or "Video:" in l]
    print("\n".join(info))
    assert "1920x1080" in r.stderr, "bad resolution"
    print(f"\nPASS -> {out}")


if __name__ == "__main__":
    main()
