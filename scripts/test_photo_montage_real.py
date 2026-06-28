"""
PhotoMontage on REAL pictures from the NOLAN picture library (`_library/images/`).

Same four motion categories as test_photo_montage_stress.py, but each card is a real
public-domain Holbein "Dance of Death" engraving pulled from the library by title —
so the montage looks like an actual montage, not placeholder rectangles.
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

OUT = os.path.abspath("test_output/photo_montage_real")
os.makedirs(OUT, exist_ok=True)
LIB = "_library/images"


def pick(title_like):
    """Resolve a library image to an absolute path by title (first match)."""
    db = sqlite3.connect(os.path.join(LIB, "catalog.db"))
    row = db.execute(
        "SELECT path, title FROM assets WHERE status='active' AND title LIKE ? LIMIT 1",
        (f"%{title_like}%",),
    ).fetchone()
    db.close()
    if not row:
        raise SystemExit(f"no library image matching {title_like!r}")
    return os.path.abspath(os.path.join(LIB, row[0])), row[1].strip().rstrip(".").title()


def main():
    from nolan.motion import validate, render

    knight, knight_c = pick("KNIGHT")
    physician, phys_c = pick("PHYSICIAN")
    countess, countess_c = pick("COUNTESS")
    oldwoman, _ = pick("OLD WOMAN")
    print("using:", knight_c, "|", phys_c, "|", countess_c, "| Old Woman")

    spec = {
        "effect": "photo-montage-pro",
        "content": {
            "background": "#241016",
            "cards": [
                # cat 3 — usual entrance + settle angle
                {"src": knight, "x": 0.22, "y": 0.55, "scale": 0.5, "rotation": -5,
                 "from": "left", "enterAt": 0.1, "enterDur": 0.8, "frame": "polaroid",
                 "caption": knight_c},
                # cat 4 — fade in (rise), hold, fade out (rise)
                {"src": physician, "x": 0.5, "y": 0.55, "scale": 0.48, "rotation": 2,
                 "frame": "polaroid", "caption": phys_c,
                 "keys": [
                     {"at": 0.4, "y": 0.72, "opacity": 0.0},
                     {"at": 1.1, "y": 0.55, "opacity": 1.0, "ease": "out"},
                     {"at": 3.0, "y": 0.55, "opacity": 1.0},
                     {"at": 3.8, "y": 0.40, "opacity": 0.0, "ease": "inOut"},
                 ]},
                # cat 2 — appear flat, THEN tilt
                {"src": countess, "x": 0.8, "y": 0.55, "scale": 0.5, "frame": "polaroid",
                 "caption": countess_c,
                 "keys": [
                     {"at": 0.8, "opacity": 0.0, "rotation": 0},
                     {"at": 1.4, "opacity": 1.0, "rotation": 0, "ease": "out"},
                     {"at": 2.4, "rotation": 0},
                     {"at": 2.9, "rotation": 12, "ease": "inOut"},
                 ]},
                # cat 1 — complex multi-step path + different size/layer
                {"src": oldwoman, "x": 0.15, "y": 0.3, "scale": 0.24, "frame": "plain",
                 "keys": [
                     {"at": 2.0, "x": 0.16, "y": 0.30, "scale": 0.2, "rotation": -8, "opacity": 0.0},
                     {"at": 2.6, "x": 0.4, "y": 0.26, "scale": 0.28, "rotation": 4, "opacity": 1.0, "ease": "out"},
                     {"at": 3.6, "x": 0.6, "y": 0.68, "scale": 0.36, "rotation": -3, "ease": "inOut"},
                     {"at": 4.4, "x": 0.85, "y": 0.34, "scale": 0.22, "rotation": 9, "ease": "inOut"},
                 ]},
            ],
        },
        "style": {"vignette": 0.5, "zoomStart": 1.04, "zoomEnd": 1.14, "panX": -0.03},
        "duration": 5.0,
    }

    norm, errors = validate(spec)
    assert not errors, errors
    out = os.path.abspath(f"{OUT}/montage_real.mp4")
    print("rendering...")
    render(norm, out)

    import subprocess
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    assert os.path.exists(out) and os.path.getsize(out) > 1024
    for t in (1.3, 2.7, 4.6):
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(t), "-i", out,
                        "-frames:v", "1", f"{OUT}/r_{int(t*10):02d}.png"])
    print(f"PASS -> {out}")


if __name__ == "__main__":
    main()
