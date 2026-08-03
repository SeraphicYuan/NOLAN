"""Subtitle files for upload — exported from the captions that actually shipped.

`caption_groups.json` is the forced-aligner's grouping, already offset onto the global timeline: the
exact lines the burned-in overlay draws, at the exact times it draws them. Exporting from there rather
than re-transcribing means the uploaded subtitles agree with the picture word for word, and proper
nouns the ASR would mangle (Oppenheimer, Gerety, N. W. Ayer, Hopetown) come out right because a human
wrote them in the script.

Falls back to `audio_meta.voices[].words` (per-frame word timings, shifted by the frame offset) when a
comp has no caption groups — the same data one layer down.

Two shapes of cue that YouTube silently DROPS are normalised here, because "some lines are missing"
is a very hard thing to notice in a 13-minute upload:
  * overlapping cues — clamped so each ends before the next begins;
  * zero-length cues — floored at 50 ms.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .edit import _comp_dir

MIN_CUE = 0.05


def _ts(t: float, sep: str = ",") -> str:
    """SRT/VTT timestamp. Shared with `nolan.captions._ts` in shape; kept local so this module has no
    dependency on the Director-path caption stack."""
    t = max(0.0, float(t))
    h, m = int(t // 3600), int((t % 3600) // 60)
    s, ms = int(t % 60), int(round((t - int(t)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _from_groups(comp_dir: Path) -> List[Tuple[float, float, str]]:
    f = comp_dir / "caption_groups.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for g in data.get("groups") or []:
        txt = " ".join(str(g.get("text") or "").split())
        if txt:
            out.append((float(g.get("start", 0) or 0), float(g.get("end", 0) or 0), txt))
    return out


def _from_audio_meta(comp_dir: Path, max_chars: int = 42) -> List[Tuple[float, float, str]]:
    """Fallback: group per-frame word timings into readable lines, shifted onto the global timeline."""
    f = comp_dir / "audio_meta.json"
    if not f.exists():
        return []
    try:
        meta = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    voices = sorted(meta.get("voices") or [], key=lambda v: v.get("frame") or 0)
    out, offset = [], 0.0
    for v in voices:
        cur: List[Dict[str, Any]] = []
        for w in v.get("words") or []:
            cur.append(w)
            text = " ".join(str(x.get("word") or "") for x in cur).strip()
            if len(text) >= max_chars or str(w.get("word", "")).endswith((".", "?", "!")):
                out.append((offset + float(cur[0]["start"]), offset + float(cur[-1].get("end", cur[-1]["start"])),
                            " ".join(text.split())))
                cur = []
        if cur:
            text = " ".join(str(x.get("word") or "") for x in cur).strip()
            if text:
                out.append((offset + float(cur[0]["start"]),
                            offset + float(cur[-1].get("end", cur[-1]["start"])), text))
        offset += float(v.get("duration_s", 0) or 0)
    return out


def cues(comp: str) -> List[Tuple[float, float, str]]:
    """Normalised, non-overlapping cues on the global timeline."""
    cd = _comp_dir(comp)
    raw = _from_groups(cd) or _from_audio_meta(cd)
    raw.sort(key=lambda c: c[0])
    out: List[Tuple[float, float, str]] = []
    for i, (s, e, t) in enumerate(raw):
        if i + 1 < len(raw):
            e = min(e, raw[i + 1][0] - 0.001)      # YouTube drops overlapping cues, silently
        if e - s < MIN_CUE:
            e = s + MIN_CUE
        out.append((s, e, t))
    return out


def to_srt(cs: List[Tuple[float, float, str]]) -> str:
    return "\n".join(f"{i}\n{_ts(s)} --> {_ts(e)}\n{t}\n" for i, (s, e, t) in enumerate(cs, 1))


def to_vtt(cs: List[Tuple[float, float, str]]) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{_ts(s, '.')} --> {_ts(e, '.')}\n{t}\n" for s, e, t in cs)


def write(comp: str, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Write `subtitles.srt` + `subtitles.vtt`. Returns what was produced (never raises on an empty
    comp — a missing subtitle track is reported, not fatal to a finish)."""
    cs = cues(comp)
    d = Path(out_dir) if out_dir else _comp_dir(comp)
    d.mkdir(parents=True, exist_ok=True)
    if not cs:
        return {"ok": False, "cues": 0, "detail": "no caption groups and no aligned words"}
    (d / "subtitles.srt").write_text(to_srt(cs), encoding="utf-8")
    (d / "subtitles.vtt").write_text(to_vtt(cs), encoding="utf-8")
    return {"ok": True, "cues": len(cs), "srt": str(d / "subtitles.srt"), "vtt": str(d / "subtitles.vtt"),
            "ends_at": round(cs[-1][1], 2)}


# ------------------------------------------------------------------ chapters

_SLUG = re.compile(r"^\d+[-_]?")


def chapter_title(frame_id: str) -> str:
    """`04-invent-the-tradition` -> `Invent the tradition`. The frame slug IS the beat's name."""
    s = _SLUG.sub("", str(frame_id)).replace("-", " ").replace("_", " ").strip()
    return (s[:1].upper() + s[1:]) if s else str(frame_id)


def chapters(comp: str) -> List[Dict[str, Any]]:
    """Cumulative VO-section starts — narration owns duration, so the sections ARE the chapters."""
    cd = _comp_dir(comp)
    try:
        meta = json.loads((cd / "audio_meta.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    from .edit import list_frames
    ids = [(f.get("id") if isinstance(f, dict) else f) for f in list_frames(comp)]
    out, t = [], 0.0
    for i, v in enumerate(sorted(meta.get("voices") or [], key=lambda v: v.get("frame") or 0)):
        fid = ids[i] if i < len(ids) else f"chapter-{i + 1}"
        out.append({"t": round(t, 2), "title": v.get("title") or chapter_title(fid), "frame": fid})
        t += float(v.get("duration_s", 0) or 0)
    return out


def chapter_stamp(t: float) -> str:
    """`0:00`, `12:20`, `1:02:03` — YouTube's chapter format, which is NOT the subtitle format.
    (`_ts` is zero-padded to hours; a naive trim of it produced `:00:00` and YouTube ignores the
    whole list when one stamp is unparseable.)"""
    t = int(max(0.0, float(t)))
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapters_text(comp: str) -> str:
    return "\n".join(f"{chapter_stamp(c['t'])} {c['title']}" for c in chapters(comp))


def youtube_chapter_issues(chs: List[Dict[str, Any]], total: float) -> List[str]:
    """YouTube ignores a chapter list that breaks any of these — silently, so it must be asserted."""
    problems = []
    if len(chs) < 3:
        problems.append(f"only {len(chs)} chapters — YouTube needs at least 3")
    if not chs or abs(chs[0]["t"]) > 1e-6:
        problems.append("the first chapter must start at 0:00")
    for a, b in zip(chs, chs[1:] + [{"t": total}]):
        if b["t"] - a["t"] < 10:
            problems.append(f"{a['title']!r} is {b['t'] - a['t']:.0f}s — each chapter must be >=10s")
    return problems
