"""Style-focused vision pass over sampled frames.

Distinct from the content-focused indexing description: here we ask the vision
model about *visual style* — shot/framing, camera/lens feel, lighting, color
grade, and on-screen graphics — so the synthesis agent can characterize the
cinematography and motion-graphics dimensions.

Provider is any object with ``async describe_image(path, prompt) -> str`` (i.e.
``vision.VisionProvider``), so it's injectable/mockable in tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

STYLE_PROMPT = (
    "You are a cinematographer analyzing the VISUAL STYLE of this single video "
    "frame — ignore the specific subject/content. In 2–3 concise sentences, cover: "
    "shot type & framing (wide/medium/close; centered vs rule-of-thirds; negative "
    "space); camera/lens feel (depth of field, angle, any motion implied); lighting "
    "(high/low key, direction, mood); color & grade (palette, warm/cool, saturation, "
    "contrast); and any on-screen graphics or text (lower-thirds, titles, captions, "
    "callouts, data viz). Be concrete; describe style, not story."
)


def select_frames(frame_paths: List[Path], n: int) -> List[Path]:
    """Evenly pick up to ``n`` frames across the list."""
    paths = [Path(p) for p in frame_paths]
    if len(paths) <= n:
        return paths
    step = len(paths) / n
    return [paths[int(i * step)] for i in range(n)]


async def analyze_style_frames(provider, frame_paths: List[Path], *,
                               max_frames: int = 6,
                               prompt: str = STYLE_PROMPT) -> Dict[str, Any]:
    """Run the style prompt over representative frames; return per-frame reads.

    The synthesis agent aggregates these into the Cinematography / Motion-Graphics
    sections. A frame that errors is skipped (recorded) rather than failing the run.
    """
    chosen = select_frames(frame_paths, max_frames)
    reads: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []
    for p in chosen:
        try:
            text = await provider.describe_image(Path(p), prompt)
            reads.append({"frame": Path(p).name, "read": (text or "").strip()})
        except Exception as e:  # one bad frame shouldn't sink the pass
            errors.append({"frame": Path(p).name, "error": str(e)})
    return {
        "prompt": prompt,
        "frames_read": len(reads),
        "reads": reads,
        "errors": errors,
    }
