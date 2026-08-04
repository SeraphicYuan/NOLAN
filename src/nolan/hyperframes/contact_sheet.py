"""The batch REVIEW artifact — one before/after page over every scene a batch touched.

The human accepts proposals one at a time, but the question they are actually asking is not "is this
op correct?", it is "does the essay still hang together?". Nothing answered that until a 25-minute
render landed, so a 25-proposal batch was reviewed 25 times at the wrong altitude and once, far too
late, at the right one.

Everything needed already existed and was never assembled:

  * BEFORE — a frame grab from the per-frame `clip.mp4` that `hf-render` already caches. Free,
    truthful (it is the shipped pixels, grounds included), and it needs no browser.
  * AFTER  — `proposal_preview`, which composes the proposal onto a COPY and snapshots it.
  * The rationale, the requirement coverage, the gate findings and any capability gap, all of which
    are already on the proposal and were only ever visible one modal at a time.
  * The ANCHOR delta, because a re-anchor is the one edit whose effect is invisible in a still.

Deliberately lazy and resumable: each cell is computed on demand and cached on disk, so opening the
sheet costs the cells you look at. `build_sheet` returns data; rendering it is the caller's business
(the /hyperframes page renders HTML, `write_markdown` writes a file you can read in a terminal).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .edit import (_comp_dir, _find_scene, _frames_dir, frame_transcripts, list_proposals,
                   load_frame_spec, proposal_preview)


def _sheet_dir(comp: str) -> Path:
    d = _comp_dir(comp) / "compositions" / "_preview" / "_sheet"
    d.mkdir(parents=True, exist_ok=True)
    return d


def before_still(comp: str, frame_id: str, at: float, force: bool = False) -> Optional[Path]:
    """A frame grab of the SHIPPED pixels at `at` seconds into the frame.

    Straight out of the cached per-frame `clip.mp4` with ffmpeg — no browser, no scaffold, no compose.
    That is not just cheaper than re-rendering the old state, it is more honest: the clip is what the
    viewer last saw, video grounds and all, rather than a re-derivation of it."""
    clip = _frames_dir(comp) / f"{frame_id}.clip.mp4"
    if not clip.is_file():
        return None
    out = _sheet_dir(comp) / f"before_{frame_id}_{at:.2f}.jpg"
    if out.is_file() and not force:
        return out
    try:
        from nolan.hf_qa import _ffmpeg
        subprocess.run([_ffmpeg(), "-y", "-ss", f"{max(0.0, at):.2f}", "-i", str(clip), "-frames:v", "1",
                        "-vf", "scale=640:-1", "-q:v", "4", str(out)], capture_output=True, timeout=60)
    except Exception:
        return None
    return out if out.is_file() and out.stat().st_size > 0 else None


def _anchor_of(sc: Dict[str, Any]) -> str:
    return str((sc.get("data") or {}).get("anchor") or sc.get("anchor") or "")


def _ops_summary(ops: List[Dict[str, Any]]) -> List[str]:
    out = []
    for op in ops or []:
        k = op.get("op")
        if k == "patch":
            fields = list((op.get("patch") or {}).keys()) + [f"-{d}" for d in (op.get("deletes") or [])]
            out.append(f"patch {op.get('scene_id')}: {', '.join(fields) or '(nothing)'}")
        elif k == "add":
            out.append(f"add {(op.get('scene') or {}).get('type')} {(op.get('scene') or {}).get('id')}")
        elif k == "retime":
            out.append(f"retime {op.get('scene_id')} start={op.get('start')} dur={op.get('dur')}")
        else:
            out.append(f"{k} {op.get('scene_id') or ''}".strip())
    return out


def _anchor_delta(comp: str, p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Did this proposal change an anchor, and does the new one actually EXIST in the narration?

    A re-anchor is the one edit a before/after still cannot show — the pixels are identical and the
    scene simply lands somewhere else at the next sync. It is also the edit that produced the only real
    regression of the batch this module comes from ("someone taught it to you" vs the spoken
    "somebody"). So the sheet resolves it against the transcript and shows the verdict."""
    new = None
    for op in p.get("ops") or []:
        for k, v in (op.get("patch") or {}).items():
            if k in ("data.anchor", "anchor"):
                new = str(v)
    if new is None:
        return None
    spec, info = load_frame_spec(comp, p["frame_id"])
    try:
        old = _anchor_of(_find_scene(spec["frames"][info["i"]], p.get("scene_id")))
    except KeyError:
        old = ""
    resolved, suggestion = None, None
    try:
        from nolan.hyperframes.sync import _phrase_time, _suggest_anchor_span
        from nolan.aligner import flatten_words
        from nolan.whisper import WordTimestamp
        meta = json.loads((_comp_dir(comp) / "audio_meta.json").read_text(encoding="utf-8"))
        import re as _re
        m = _re.match(r"(\d+)", str(p["frame_id"]))
        voice = next((v for v in meta.get("voices", []) if v.get("frame") == (int(m.group(1)) if m else None)),
                     None)
        words = [WordTimestamp(word=w["word"], start=w["start"], end=w["end"])
                 for w in (voice or {}).get("words", [])]
        if words:
            t = _phrase_time(new, words)
            resolved = None if t is None else round(t, 2)
            if t is None:
                suggestion = _suggest_anchor_span(new, [tok for (tok, _s, _e) in flatten_words(words)])
    except Exception:
        pass
    return {"old": old, "new": new, "resolved_at": resolved,
            "verdict": "UNRESOLVED — will be placed by fallback" if resolved is None else "resolves",
            "suggest": suggestion}


def build_sheet(comp: str, proposal_ids: Optional[List[str]] = None, *, previews: bool = True,
                status: str = "proposed") -> Dict[str, Any]:
    """The review data for a batch: one row per proposal, ordered by frame then scene.

    `previews=False` returns everything but the pixels — instant, and enough to triage which rows are
    worth looking at (gate failures, capability gaps, unmet requirements, unresolved anchors)."""
    props = [p for p in list_proposals(comp) if (proposal_ids is None or p.get("id") in proposal_ids)
             and (proposal_ids is not None or p.get("status") == status)]
    rows: List[Dict[str, Any]] = []
    for p in props:
        fid, sid = p.get("frame_id"), p.get("scene_id")
        row: Dict[str, Any] = {
            "proposal_id": p.get("id"), "frame_id": fid, "scene_id": sid,
            "status": p.get("status"), "gate_ok": p.get("gate_ok"),
            "rationale": p.get("rationale", ""), "ops": _ops_summary(p.get("ops")),
            "requirements": p.get("requirements") or [],
            "layout": p.get("layout") or [],
            # Seam changes and non-durable retimes. Written by the gate since e9d558e and read by
            # NOBODY until now — an advisory nothing renders is worse than none, because the review
            # then reads as "checked" (the phantom-field lesson, and this was one).
            "timing": p.get("timing") or [],
            "capability_gap": bool(p.get("capability_gap")),
            "gate_out": p.get("gate_out", ""),
            "agent": (p.get("provenance") or {}).get("agent"),
        }
        try:
            spec, info = load_frame_spec(comp, fid)
            sc = _find_scene(spec["frames"][info["i"]], sid) if sid else None
        except (KeyError, OSError):
            sc = None
        if sc:
            start, dur = float(sc.get("start", 0) or 0), float(sc.get("dur", 0) or 0)
            row.update(block=sc.get("type"), start=round(start, 2), dur=round(dur, 2),
                       narration=(frame_transcripts(comp, fid) or {}).get(sid, "")[:240])
            at = start + 0.6 * dur
            # A footage-grounded scene cannot be told the truth by a still (a seeked <video> does not
            # decode into a snapshot) — flag it so the reviewer knows to spend a `render_scene` there
            # rather than trusting an empty-looking plate.
            g = (sc.get("data") or {}).get("ground") or {}
            row["needs_motion_check"] = bool(g.get("kind") == "video")
            if previews:
                b = before_still(comp, fid, at)
                row["before"] = str(b) if b else None
                try:
                    pv = proposal_preview(comp, p["id"], at=at - start)
                    row["after"] = pv.get("png")
                except Exception as e:
                    row["after"], row["after_error"] = None, f"{type(e).__name__}: {e}"
        ad = _anchor_delta(comp, p)
        if ad:
            row["anchor"] = ad
        rows.append(row)
    rows.sort(key=lambda r: (str(r.get("frame_id")), r.get("start", 0), str(r.get("scene_id"))))
    unmet = sum(1 for r in rows for q in r["requirements"] if q.get("status") in ("unmet", "partial"))
    return {"comp": comp, "rows": rows,
            "summary": {"proposals": len(rows),
                        "frames": len({r["frame_id"] for r in rows}),
                        "blocked": sum(1 for r in rows if r.get("gate_ok") is False),
                        "capability_gaps": sum(1 for r in rows if r["capability_gap"]),
                        "unmet_requirements": unmet,
                        "unresolved_anchors": sum(1 for r in rows
                                                  if (r.get("anchor") or {}).get("resolved_at") is None
                                                  and r.get("anchor")),
                        "needs_motion_check": sum(1 for r in rows if r.get("needs_motion_check")),
                        "timing_notes": sum(len(r.get("timing") or []) for r in rows)}}


def write_markdown(comp: str, sheet: Optional[Dict[str, Any]] = None, out: Optional[Path] = None) -> Path:
    """The sheet as a readable file — the whole batch as PROSE, in scene order.

    This is the cheap answer to "does it still hang together": reading the essay's beats in order with
    what each one now shows and what is spoken over it costs a minute, catches continuity and ordering
    problems a grid of thumbnails does not, and works before any pixels exist."""
    sheet = sheet or build_sheet(comp, previews=False)
    s = sheet["summary"]
    L = [f"# Batch review — `{comp}`", "",
         f"{s['proposals']} proposal(s) across {s['frames']} frame(s) · "
         f"{s['blocked']} blocked · {s['capability_gaps']} capability gap(s) · "
         f"{s['unmet_requirements']} unmet/partial requirement(s) · "
         f"{s['unresolved_anchors']} unresolved anchor(s) · "
         f"{s['needs_motion_check']} scene(s) a still cannot verify · "
         f"{s.get('timing_notes', 0)} timing note(s)", ""]
    frame = None
    for r in sheet["rows"]:
        if r["frame_id"] != frame:
            frame = r["frame_id"]
            L += ["", f"## `{frame}`", ""]
        head = f"### {r['proposal_id']} · `{r.get('scene_id')}` ({r.get('block','?')}) " \
               f"@{r.get('start','?')}s +{r.get('dur','?')}s"
        L += [head, ""]
        if r.get("narration"):
            L.append(f"> VO: {r['narration']}")
        L.append(f"- **why**: {r['rationale'] or '(none given)'}")
        L.append(f"- **ops**: {'; '.join(r['ops']) or '(none)'}")
        if r.get("anchor"):
            a = r["anchor"]
            L.append(f"- **anchor**: {a['old']!r} → {a['new']!r} — **{a['verdict']}**"
                     + (f" · try {a['suggest']!r}" if a.get("suggest") else ""))
        for q in r["requirements"]:
            L.append(f"- **{q.get('req_id')}** {q.get('status')}: {q.get('note', '')}")
        if r["capability_gap"]:
            L.append("- **CAPABILITY GAP** — the block cannot do what the note asked (logged as a request)")
        if r.get("gate_ok") is False:
            L.append(f"- **BLOCKED**: {(r.get('gate_out') or '')[:300]}")
        if r.get("needs_motion_check"):
            L.append("- ⚠ video ground — a still cannot verify this; "
                     f"`render_scene(comp, '{r['frame_id']}', '{r['scene_id']}')`")
        for v in r["layout"][:4]:
            L.append(f"- layout: {v}")
        for v in (r.get("timing") or [])[:4]:
            L.append(f"- **timing**: {v}")
        if r.get("before") or r.get("after"):
            L.append(f"- before: `{r.get('before')}` · after: `{r.get('after')}`")
        L.append("")
    out = Path(out) if out else (_comp_dir(comp) / "BATCH_REVIEW.md")
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out
