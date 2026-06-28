"""
Demo: 3D PAN vs flat TILT on PhotoMontage (clip_425f844b style).

A "tilt" is an in-plane rotation (`rotation` / rotateZ). A "pan" is a 3D rotation about
the vertical axis (`rotY` / rotateY with perspective) — the card swings in space toward
the camera. This renders both side by side on real library images so the difference is
obvious: left card does a flat tilt, right card does a 3D pan.
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

OUT = os.path.abspath("test_output/photo_montage_pan")
os.makedirs(OUT, exist_ok=True)
LIB = "_library/images"


def pick(title_like):
    db = sqlite3.connect(os.path.join(LIB, "catalog.db"))
    row = db.execute("SELECT path, title FROM assets WHERE status='active' AND title LIKE ? LIMIT 1",
                     (f"%{title_like}%",)).fetchone()
    db.close()
    return os.path.abspath(os.path.join(LIB, row[0])), row[1].strip().rstrip(".").title()


def main():
    from nolan.motion import validate, render

    knight, knight_c = pick("KNIGHT")
    countess, countess_c = pick("COUNTESS")

    spec = {
        "effect": "photo-montage-pro",
        "content": {
            "background": "#241016",
            "cards": [
                # LEFT — flat tilt (rotateZ): appear, hold, then in-plane rotate
                {"src": knight, "x": 0.28, "y": 0.52, "scale": 0.56, "frame": "polaroid",
                 "caption": "tilt (rotateZ)",
                 "keys": [
                     {"at": 0.3, "opacity": 0.0, "rotation": 0},
                     {"at": 1.0, "opacity": 1.0, "rotation": 0, "ease": "out"},
                     {"at": 1.8, "rotation": 0},
                     {"at": 2.5, "rotation": 14, "ease": "inOut"},
                 ]},
                # RIGHT — 3D pan (rotateY): appear, hold, then swing about vertical axis
                {"src": countess, "x": 0.72, "y": 0.52, "scale": 0.56, "frame": "polaroid",
                 "perspective": 1200, "caption": "pan (rotateY)",
                 "keys": [
                     {"at": 0.5, "opacity": 0.0, "rotY": 0},
                     {"at": 1.2, "opacity": 1.0, "rotY": 0, "ease": "out"},
                     {"at": 2.0, "rotY": 0},
                     {"at": 2.9, "rotY": -40, "ease": "inOut"},   # swing in 3D
                 ]},
            ],
        },
        "style": {"vignette": 0.5, "zoomStart": 1.03, "zoomEnd": 1.1, "panX": 0.0},
        "duration": 4.0,
    }

    norm, errors = validate(spec)
    assert not errors, errors
    out = os.path.abspath(f"{OUT}/pan_vs_tilt.mp4")
    print("rendering...")
    render(norm, out)

    import subprocess
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    assert os.path.exists(out) and os.path.getsize(out) > 1024
    for t in (1.4, 2.6, 3.6):
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(t), "-i", out,
                        "-frames:v", "1", f"{OUT}/p_{int(t*10):02d}.png"])
    print(f"PASS -> {out}")


if __name__ == "__main__":
    main()
