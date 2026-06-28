"""
Test the photo_montage template.

Reproduces the "photos on a table" documentary effect: Polaroid-framed stills on a
textured surface, a slow Ken Burns camera, and a hero card that slides in with a
handwritten caption. Generates synthetic placeholder images so it runs standalone.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from src.nolan.renderer.scenes import PhotoMontageRenderer

OUTPUT_DIR = "test_output/photo_montage"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _make_placeholder(path, color, size=(600, 760)):
    """A flat color card with a darker border, standing in for an archival still."""
    img = Image.new("RGB", size, color)
    a = np.array(img)
    a[:24, :] = a[-24:, :] = a[:, :24] = a[:, -24:] = (40, 35, 30)
    Image.fromarray(a).save(path)
    return path


def test_render():
    print("\n[1/1] Rendering photo-montage demo...")
    scroll = _make_placeholder(f"{OUTPUT_DIR}/scroll.png", (210, 200, 170), (560, 760))
    portrait = _make_placeholder(f"{OUTPUT_DIR}/portrait.png", (200, 205, 200), (560, 720))
    hero = _make_placeholder(f"{OUTPUT_DIR}/hero.png", (190, 170, 150), (620, 700))

    out = f"{OUTPUT_DIR}/montage.mp4"
    duration = 6.0
    PhotoMontageRenderer(
        hero={"image_path": hero, "caption": "Tokugawa Ieyasu", "x": 0.6, "y": 0.52,
              "scale": 0.5, "rotation": 3, "slide_from": "right"},
        cards=[
            {"image_path": portrait, "x": 0.26, "y": 0.5, "scale": 0.5, "rotation": -7},
            {"image_path": scroll, "x": 0.5, "y": 0.42, "scale": 0.46, "rotation": 4,
             "caption": None},
        ],
        bg_color=(58, 18, 22),
        zoom_start=1.06, zoom_end=1.2, pan_direction="left",
    ).render(out, duration=duration, with_qa=False)

    # --- verify: real 1920x1080 video, right duration, and actual motion ---
    import imageio_ffmpeg
    from moviepy import VideoFileClip

    assert os.path.exists(out) and os.path.getsize(out) > 1024, "no output file"
    clip = VideoFileClip(out)
    assert clip.size == [1920, 1080], f"bad resolution: {clip.size}"
    assert abs(clip.duration - duration) < 0.3, f"bad duration: {clip.duration}"
    f_early = clip.get_frame(1.0).astype(np.int16)
    f_late = clip.get_frame(4.5).astype(np.int16)
    motion = np.abs(f_early - f_late).mean()
    clip.close()
    assert motion > 1.0, f"no motion detected between frames (diff={motion:.2f})"
    print(f"  OK  1920x1080  {duration}s  motion-diff={motion:.1f}  -> {out}")


if __name__ == "__main__":
    test_render()
    print("\nPASS")
