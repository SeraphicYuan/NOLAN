"""
PhotoGrid demo — 40 real library images choreographed into a grid.

Renders three clips:
  grid_one_by_one.mp4 — full 3 steps: fly in one-by-one -> one zooms to center
                        (grid peters out) -> zooms back, grid returns.
  grid_row.mp4        — fly in one ROW at a time (fill only).
  grid_col.mp4        — fly in one COLUMN at a time (fill only).

Usage:
  python scripts/test_photo_grid.py            # render all three
  python scripts/test_photo_grid.py one        # just the full one-by-one choreography
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

OUT = os.path.abspath("test_output/photo_grid")
os.makedirs(OUT, exist_ok=True)
LIB = "_library/images"
COLS, ROWS = 8, 5   # 40 cells (fills 16:9; pass 5x8 for a portrait grid)


def load_images(n):
    db = sqlite3.connect(os.path.join(LIB, "catalog.db"))
    rows = db.execute(
        "SELECT path, title FROM assets WHERE status='active' ORDER BY id LIMIT ?", (n,)
    ).fetchall()
    db.close()
    return [{"src": os.path.abspath(os.path.join(LIB, p)),
             "caption": (t or "").strip().rstrip(".").title()} for p, t in rows]


def render_clip(name, order, duration, full, cards, focus_index=None):
    from nolan.motion import validate, render
    content = {
        "cards": cards, "cols": COLS, "rows": ROWS, "background": "#221018",
    }
    if full:
        content["focusIndex"] = focus_index if focus_index is not None else (COLS * ROWS) // 2
    style = {
        "order": order,
        "flyFrom": "edges",
        "stagger": 0.06 if order == "one-by-one" else (0.2 if order == "row" else 0.14),
        "flyDur": 0.55,
        "fillStart": 0.3,
        "vignette": 0.5,
    }
    if not full:
        style["focusAt"] = 999  # never trigger the focus step

    spec = {"effect": "photo-grid", "content": content, "style": style, "duration": duration}
    norm, errors = validate(spec)
    assert not errors, errors
    out = os.path.abspath(f"{OUT}/{name}.mp4")
    print(f"rendering {name} ({order}, {duration}s)...")
    render(norm, out)

    import subprocess
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    assert os.path.exists(out) and os.path.getsize(out) > 1024
    # sample a few frames
    stamps = [1.0, 2.5, 4.6, 5.8] if full else [0.6, 1.4, 2.6]
    for t in stamps:
        if t < duration:
            subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(t), "-i", out,
                            "-frames:v", "1", f"{OUT}/{name}_{int(t*10):02d}.png"])
    print(f"  -> {out}")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    cards = load_images(COLS * ROWS)
    print(f"loaded {len(cards)} images")

    # full choreography: fly in one-by-one, focus a portrait near the middle, return
    render_clip("grid_one_by_one", "one-by-one", 8.0, full=True, cards=cards, focus_index=18)
    if which == "all":
        render_clip("grid_row", "row", 3.2, full=False, cards=cards)
        render_clip("grid_col", "col", 3.2, full=False, cards=cards)
    print("PASS")


if __name__ == "__main__":
    main()
