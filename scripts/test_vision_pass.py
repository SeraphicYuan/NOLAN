"""Test: style-focused vision pass (injected fake provider, no real model).

Usage:
    D:/env/nolan/python.exe scripts/test_vision_pass.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.video_style import vision_pass


class FakeProvider:
    """Mimics vision.VisionProvider.describe_image; frame 3 raises to test skip."""
    def __init__(self):
        self.calls = []

    async def describe_image(self, path, prompt):
        self.calls.append((str(path), prompt))
        if "f03" in str(path):
            raise RuntimeError("vision timeout")
        return f"medium shot, cool low-key grade [{os.path.basename(str(path))}]"


def main():
    paths = [f"/tmp/frames/f{i:02d}.jpg" for i in range(10)]

    # select_frames: evenly pick max_frames
    sel = vision_pass.select_frames(paths, 4)
    assert len(sel) == 4 and str(sel[0]).endswith("f00.jpg"), sel
    print("select_frames OK:", [p.name for p in sel])

    prov = FakeProvider()
    res = asyncio.run(vision_pass.analyze_style_frames(prov, paths, max_frames=4))
    print("frames_read:", res["frames_read"], "errors:", res["errors"])
    assert res["prompt"] == vision_pass.STYLE_PROMPT
    # 4 chosen, one (f03? not selected) — check selected set includes a raising frame
    # selected at step 2.5 -> f00,f02,f05,f07; none is f03, so 4 reads, 0 errors
    assert res["frames_read"] == 4 and len(res["errors"]) == 0, res
    assert all("read" in r and r["read"] for r in res["reads"])
    assert prov.calls and prov.calls[0][1] == vision_pass.STYLE_PROMPT
    print("analyze_style_frames OK")

    # force an error frame into the selection to verify graceful skip
    res2 = asyncio.run(vision_pass.analyze_style_frames(prov, ["/tmp/frames/f03.jpg", "/tmp/frames/f01.jpg"], max_frames=4))
    assert res2["frames_read"] == 1 and len(res2["errors"]) == 1, res2
    assert res2["errors"][0]["frame"] == "f03.jpg"
    print("error-frame skip OK")

    print("\nOK - vision pass verified.")


if __name__ == "__main__":
    main()
