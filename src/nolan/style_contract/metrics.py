"""Style-contract metrics — measure an authored essay against the craft dimensions.

Backend-agnostic: everything runs over a normalized ``SceneView`` list, so the same metrics lint a
HyperFrames frame-spec essay OR (later) a scene_plan.json. The measurements are the *verifiable* half
of the contract — a directive nobody can measure is one the author quietly ignores.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List

# --- block taxonomy -----------------------------------------------------------
# family: what ROLE a block plays (drives dataviz-share + layout grouping). Whether a *specific*
# scene actually carries an asset is measured per-scene from its data (see SceneView.media), NOT
# from the family. Kept in sync with the catalog by tests/test_style_contract.py (can't go stale).
BLOCK_FAMILY: Dict[str, str] = {
    "statement": "text", "lower_third": "text", "code": "text", "document": "text",
    "stat": "dataviz", "chart": "dataviz", "geo": "dataviz", "diagram": "dataviz", "timeline": "dataviz",
    "collage": "media", "gallery": "media", "carousel": "media", "linedraw": "media",
    "comparison": "media", "newshead": "media", "social_card": "media",
    "raw": "structural",
}
# blocks that CAN host a real photo/clip (used to suggest upgrades for text-only beats)
MEDIA_CAPABLE = {"statement", "comparison", "newshead", "collage", "gallery", "carousel",
                 "social_card", "linedraw", "raw", "document"}

_TEXT_KEYS = {"lines", "title", "sub", "label", "kicker", "operative", "text", "name", "role",
              "quote", "headline", "titleHi", "body", "caption"}


def block_family(block: str) -> str:
    return BLOCK_FAMILY.get(block, "text")


@dataclass
class SceneView:
    """One cut, normalized across backends."""
    frame_id: str
    scene_id: str
    block: str
    dur: float
    media: str = "none"          # "none" | "image" | "video"
    register: str = "paper"
    num_count: int = 0           # numbers on screen (stat over-stuffing)
    words: int = 0               # words on screen (reading load)
    first_in_frame: bool = False

    @property
    def family(self) -> str:
        return block_family(self.block)

    @property
    def tone(self) -> str:
        return "light" if self.register in ("paper", "light", "") else "dark"


def _walk_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_strings(v)


def scene_media(data: dict) -> str:
    """Does this scene carry a real asset — video, image, or none — inferred from its data."""
    blob = json.dumps(data).lower()
    if ".mp4" in blob or '"video"' in blob or '"kind": "video"' in blob:
        return "video"
    if any(x in blob for x in ("assets/", "capture/", ".jpg", ".jpeg", ".png", ".webp", ".svg")):
        return "image"
    return "none"


def scene_words(data: dict) -> int:
    n = 0
    for s in _walk_strings({k: v for k, v in data.items() if k in _TEXT_KEYS} if isinstance(data, dict) else data):
        if "/" in s or s.startswith("#") or s.startswith("assets"):
            continue
        n += len(s.split())
    return n


def scene_num_count(block: str, data: dict) -> int:
    if block == "stat":
        return len(data.get("items", []) or [])
    return 0


# --- aggregate measurement ----------------------------------------------------
def _cv(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    if m == 0:
        return 0.0
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return math.sqrt(var) / m


def _max_run(seq: List) -> int:
    best = run = 0
    prev = object()
    for x in seq:
        run = run + 1 if x == prev else 1
        prev = x
        best = max(best, run)
    return best


def measure(scenes: List[SceneView]) -> Dict:
    """Compute every metric the linter can check, from a normalized scene list."""
    n = len(scenes)
    if n == 0:
        return {"n_scenes": 0}
    durs = [s.dur for s in scenes]
    total = sum(durs)
    frames = sorted({s.frame_id for s in scenes})
    media = Counter(s.media for s in scenes)
    blocks = Counter(s.block for s in scenes)
    grounded_openers = sum(1 for s in scenes if s.first_in_frame and s.media != "none")
    dataviz = sum(1 for s in scenes if s.family == "dataviz")
    return {
        "n_scenes": n,
        "n_frames": len(frames),
        "total_dur": round(total, 2),
        # evidence coverage
        "coverage": round((media["image"] + media["video"]) / n, 3),
        "video_share": round(media["video"] / n, 3),
        "grounded_openers": round(grounded_openers / max(len(frames), 1), 3),
        "media_mix": dict(media),
        # pacing
        "pacing_cv": round(_cv(durs), 3),
        "cuts_per_min": round(n / (total / 60), 2) if total else 0.0,
        "mean_dur": round(total / n, 2),
        # layout variety
        "layout_max_share": round(max(blocks.values()) / n, 3),
        "layout_max_run": _max_run([s.block for s in scenes]),
        "distinct_blocks": len(blocks),                          # palette coverage (advisory)
        "block_dist": dict(blocks.most_common()),
        # chart appropriateness
        "dataviz_share": round(dataviz / n, 3),
        "overstuffed_stats": sum(1 for s in scenes if s.block == "stat" and s.num_count > 3),
        # tone rhythm (bonus dimension)
        "tone_max_run": _max_run([s.tone for s in scenes]),
    }
