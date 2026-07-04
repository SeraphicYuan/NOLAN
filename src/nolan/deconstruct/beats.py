"""Editorial beat segmentation — group shots into narrative-function units.

An editorial *beat* is a run of consecutive shots serving ONE narrative
function (hook the viewer, establish context, present evidence, turn the
argument, close). This is interpretation, so it's an LLM pass (text-LLM API,
same as clustering's StoryBoundaryDetector) — with a deterministic fallback
(library clusters if present, else an even time split) so the pipeline never
blocks on a model failure.

Beat-function vocabulary intentionally matches the scriptwriter facts
taxonomy (``hook|context|evidence|turn|close``) so reverse analysis and
forward grounding speak the same language.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

BEAT_FUNCTIONS = ("hook", "context", "evidence", "turn", "close", "other")

_SYS = """You are a film editor deconstructing a finished essay/documentary video.
Group its shots into EDITORIAL BEATS: consecutive runs of shots that serve one
narrative function. Beats are 3-60 shots typically; a beat changes when the
video's narrative JOB changes (not merely the imagery). Reply with STRICT JSON only."""


def _shot_line(s: Dict[str, Any], said: str) -> str:
    t0, t1 = s.get("timestamp_start", 0), s.get("timestamp_end", 0)
    bits = [f"[{s.get('shot_index')}] {t0:.0f}-{t1:.0f}s",
            f"cam:{s.get('camera_motion') or '?'}"]
    if s.get("asset_type"):
        bits.append(f"asset:{s['asset_type']}")
    if said:
        bits.append(f'said:"{said[:110]}"')
    return " · ".join(bits)


def _prompt(shot_lines: List[str], duration: float) -> str:
    return f"""Video duration: {duration:.0f}s, {len(shot_lines)} shots. One line per shot
(index, time range, camera motion, asset type, what the narration SAYS over it):

{chr(10).join(shot_lines)}

Group ALL shots into editorial beats (in order, covering every shot exactly once).
For each beat give:
- "title": short editorial label (e.g. "Cold-open shock quote", "The kingdom decays")
- "function": one of {list(BEAT_FUNCTIONS)}
- "first_shot": first shot index in the beat
- "last_shot": last shot index in the beat

Return STRICT JSON: {{"beats": [{{"title": "...", "function": "...", "first_shot": 0, "last_shot": 5}}, ...]}}"""


def _parse_json(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def _normalize(beats_raw: List[Dict[str, Any]], n_shots: int) -> List[Dict[str, Any]]:
    """Force beats into an ordered, gap-free, full cover of [0, n_shots)."""
    beats = []
    for b in beats_raw:
        try:
            f, l = int(b.get("first_shot")), int(b.get("last_shot"))
        except (TypeError, ValueError):
            continue
        f, l = max(0, f), min(n_shots - 1, l)
        if l < f:
            continue
        fn = str(b.get("function") or "other").lower()
        beats.append({"title": str(b.get("title") or "beat").strip()[:80],
                      "function": fn if fn in BEAT_FUNCTIONS else "other",
                      "first_shot": f, "last_shot": l})
    beats.sort(key=lambda b: b["first_shot"])
    fixed, cursor = [], 0
    for b in beats:
        if b["last_shot"] < cursor:
            continue                       # fully swallowed by previous beat
        b["first_shot"] = max(b["first_shot"], cursor)
        if fixed and b["first_shot"] > cursor:
            fixed[-1]["last_shot"] = b["first_shot"] - 1   # close the gap
        fixed.append(b)
        cursor = b["last_shot"] + 1
    if not fixed:
        return []
    fixed[0]["first_shot"] = 0
    fixed[-1]["last_shot"] = n_shots - 1
    return fixed


def _fallback_beats(shots: List[Dict[str, Any]], n_beats: int = 6) -> List[Dict[str, Any]]:
    """Even time split — used only when the LLM path yields nothing."""
    if not shots:
        return []
    n_beats = max(1, min(n_beats, len(shots)))
    per = len(shots) / n_beats
    beats = []
    for i in range(n_beats):
        f, l = int(i * per), min(len(shots) - 1, int((i + 1) * per) - 1)
        fn = "hook" if i == 0 else ("close" if i == n_beats - 1 else "evidence")
        beats.append({"title": f"Beat {i + 1}", "function": fn,
                      "first_shot": f, "last_shot": max(f, l)})
    beats[-1]["last_shot"] = len(shots) - 1
    return beats


async def segment_beats(shots: List[Dict[str, Any]], shot_said: List[str],
                        duration: float, llm=None) -> Dict[str, Any]:
    """Return {"beats": [...], "source": "llm"|"fallback"}.

    ``shot_said`` is the narration text aligned to each shot (same order).
    """
    if not shots:
        return {"beats": [], "source": "fallback"}
    if llm is not None:
        lines = [_shot_line(s, shot_said[i] if i < len(shot_said) else "")
                 for i, s in enumerate(shots)]
        try:
            raw = await llm.generate(_prompt(lines, duration), system_prompt=_SYS)
            beats = _normalize((_parse_json(raw) or {}).get("beats") or [], len(shots))
            if beats:
                return {"beats": beats, "source": "llm"}
        except Exception:
            pass
    return {"beats": _fallback_beats(shots), "source": "fallback"}
