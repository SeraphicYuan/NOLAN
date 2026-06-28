"""Voiceover word-timing for cue-anchored edits (`{cue: "..."}` in a photo_brief).

Cue timing needs word-level VO timestamps. Scenes rarely carry `subtitle_cues`, but the
segment pipeline records `vo_path` in `segment_meta.json`. This module resolves a project's
words once and caches them to `voiceover.words.json` next to the plan, so the scene-edit
router can anchor `{cue: "keyword"}` to a real timestamp. Best-effort: returns None if no
VO / Whisper is unavailable, and the brief layer falls back to anchors with a warning.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

_CACHE = "voiceover.words.json"


def _segment_meta(plan_path: Path) -> dict:
    mp = plan_path.parent / "segment_meta.json"
    if mp.exists():
        try:
            return json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _resolve(p: str, plan_path: Path) -> Optional[Path]:
    """Resolve a (possibly repo-root- or project-relative) media path to something on disk."""
    for cand in (Path(p), plan_path.parent / p, Path(__file__).resolve().parents[3] / p):
        if cand.exists():
            return cand
    return None


def scene_words(plan_path, allow_transcribe: bool = True) -> Optional[List[Tuple[str, float, float]]]:
    """Return the project VO as [(word, start, end)] in absolute seconds, or None.

    Order: a cached `voiceover.words.json` → (if allowed) transcribe `vo_path` once and
    cache it. The caller passes this to `apply_edit(transcript_words=...)`; the brief
    layer windows it per scene.
    """
    plan_path = Path(plan_path)
    cache = plan_path.parent / _CACHE
    if cache.exists():
        try:
            return [tuple(w) for w in json.loads(cache.read_text(encoding="utf-8"))]
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    if not allow_transcribe:
        return None
    vo = _segment_meta(plan_path).get("vo_path")
    if not vo:
        return None
    vo_path = _resolve(vo, plan_path)
    if not vo_path:
        return None
    try:
        from nolan.whisper import WhisperTranscriber, WhisperConfig
        words = WhisperTranscriber(WhisperConfig(model_size="base")).transcribe_words(vo_path)
        data = [[w.word.strip(), float(w.start), float(w.end)] for w in words]
        try:
            cache.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass
        return [tuple(w) for w in data]
    except Exception:  # noqa: BLE001 - whisper/ffmpeg unavailable -> fall back to anchors
        return None
