"""SceneContext — the design-time facts a brief resolves against.

Holds the scene's duration and word-level narration timing (scene-local seconds), plus
a warnings sink. Kept as a plain injected value so resolvers stay pure and testable —
cue resolution is just a lookup over `words`, not a side effect.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(w).lower())


def _word_tuple(c: Any, base: float) -> Optional[Tuple[str, float, float]]:
    """Coerce a word/cue (object, dict, or tuple) to (text, start, end), scene-local."""
    if c is None:
        return None
    text = start = end = None
    for attr in ("word", "text", "value"):
        if hasattr(c, attr):
            text = getattr(c, attr)
            break
    if hasattr(c, "start"):
        start, end = getattr(c, "start", None), getattr(c, "end", None)
    if isinstance(c, dict):
        text = c.get("word", c.get("text", text))
        start, end = c.get("start", start), c.get("end", end)
    if text is None and isinstance(c, (list, tuple)) and len(c) >= 3:
        text, start, end = c[0], c[1], c[2]
    if text is None or start is None:
        return None
    s = float(start) - base
    e = float(end if end is not None else start) - base
    return (str(text), s, e)


@dataclass
class SceneContext:
    duration: float
    words: List[Tuple[str, float, float]] = field(default_factory=list)
    assets_root: str = "."
    warnings: List[str] = field(default_factory=list)
    assets: dict = field(default_factory=dict)   # id -> {id, kind, src, label?, thumb?}

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def find_cue(self, phrase: str) -> Optional[Tuple[float, float]]:
        """Return (start, end) seconds of the first run of `words` matching `phrase`."""
        toks = [_norm(t) for t in str(phrase).split() if _norm(t)]
        if not toks or not self.words:
            return None
        norms = [_norm(w[0]) for w in self.words]
        for i in range(len(norms) - len(toks) + 1):
            if norms[i:i + len(toks)] == toks:
                return (self.words[i][1], self.words[i + len(toks) - 1][2])
        return None

    @classmethod
    def from_scene(cls, scene, words: Optional[list] = None) -> "SceneContext":
        """Build context from a Scene-like object OR a raw scene dict. `words` (a transcript
        word list, abs seconds) overrides scene.subtitle_cues when given — pass the project
        transcript sliced to this scene for cue matching."""
        def _field(key, default=None):
            return scene.get(key, default) if isinstance(scene, dict) else getattr(scene, key, default)

        s0 = float(_field("start_seconds", 0) or 0)
        s1 = float(_field("end_seconds", 0) or 0)
        dur = max(0.5, s1 - s0) if s1 > s0 else 4.0
        raw = words if words is not None else (_field("subtitle_cues", None) or [])
        out: List[Tuple[str, float, float]] = []
        for c in raw:
            wt = _word_tuple(c, s0)
            if wt and -0.01 <= wt[1] <= dur + 0.5:
                out.append(wt)
        assets = {}
        for a in (_field("assets", None) or []):
            if isinstance(a, dict) and a.get("id") and a.get("src"):
                assets[str(a["id"])] = a
        return cls(duration=dur, words=out, assets=assets)
