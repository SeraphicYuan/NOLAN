"""P0.1 — word-level narration → scene sync.

`audio.mjs sync-durations` pins only the 7 FRAME boundaries; inside a frame the scene cuts were
author-typed open-loop (audio_meta.words was empty), so visuals drift ahead of narration (measured
5–25s on v2). This closes that seam:

  1. align_voices  — run the existing whisper aligner over each assets/voice/0N.wav, write per-word
                     times into audio_meta.voices[].words (SECTION-relative). Cached by wav mtime.
  2. place_scenes  — set each scene.start/dur to the moment its ANCHOR (the distinctive SPOKEN phrase
                     it illustrates) is said. Absent an anchor, fall back to the scene's visible text.
                     Monotonic-clamped; if a frame's anchors don't resolve in order, warn + fall back
                     to proportional spacing FOR THAT FRAME ONLY (never silently).

Reveal/cue re-derivation (count-ups/chart-draws firing as spoken) is the follow-up step — placing the
scene windows is necessary but not sufficient (see COMPOSE_FIRST_UPGRADE_PLAN P0.1 item 4).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_ANCHOR_TEXT_KEYS = ("anchor", "operative")            # prefer the spoken anchor; then the operative word
_VISIBLE_TEXT_KEYS = ("lines", "title", "titleHi", "kicker", "sub", "label", "quote", "headline")

try:                                                   # per-block readable minimums (single source of truth)
    from nolan.style_contract.metrics import (MIN_READABLE as _MIN_READABLE, BLOCK_FAMILY as _BF,
                                              scene_media as _scene_media)
    _MOTION_BLOCKS = {b for b, f in _BF.items() if f == "dataviz"}   # animate continuously → not a static hold
except Exception:
    _MIN_READABLE = {"newshead": 5.0, "comparison": 5.0, "document": 5.0, "timeline": 5.0}
    _MOTION_BLOCKS = {"stat", "chart", "geo", "diagram", "timeline"}
    _scene_media = lambda block, data: (data.get("ground", {}) or {}).get("kind") or "none"


def _voice_wavs(comp_dir: Path) -> List[Path]:
    return sorted((comp_dir / "assets" / "voice").glob("[0-9]*.wav"))


def align_voices(comp_dir, force: bool = False) -> Dict:
    """Force-align each section wav → audio_meta.voices[].words (section-relative). Idempotent:
    skips a voice whose words are already present (unless force). Returns a per-voice summary."""
    from nolan.flows import source
    comp_dir = Path(comp_dir)
    meta_path = comp_dir / "audio_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    voices = meta.get("voices", [])
    by_frame = {v.get("frame"): v for v in voices}
    wavs = _voice_wavs(comp_dir)
    todo = []
    for i, wav in enumerate(wavs, start=1):
        v = by_frame.get(i)
        if v is not None and not force and (v.get("words")):
            continue
        todo.append((i, wav))
    summary = {"aligned": [], "skipped": len(wavs) - len(todo)}
    if todo:
        words_by_stem = source.word_timestamps([w for _, w in todo])   # {stem: [{word,start,end}]}
        for i, wav in todo:
            words = words_by_stem.get(wav.stem, [])
            v = by_frame.get(i)
            if v is not None:
                v["words"] = words
                summary["aligned"].append({"frame": i, "words": len(words)})
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return summary


def _scene_query(sc: dict) -> str:
    """The phrase to locate in the narration — the spoken anchor if the author gave one, else the
    scene's visible text (best-effort; typography like '61,000' won't match spoken 'sixty-one thousand')."""
    d = sc.get("data", {}) or {}
    for k in _ANCHOR_TEXT_KEYS:
        val = d.get(k) or sc.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    parts: List[str] = []
    for k in _VISIBLE_TEXT_KEYS:
        val = d.get(k)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            parts.extend(str(x) for x in val)
    return " ".join(parts).strip()


def _proportional(n: int, frame_dur: float) -> List[float]:
    return [round(frame_dur * j / n, 3) for j in range(n)]


def _norm(s: str) -> List[str]:
    try:
        from nolan.aligner import normalize_text
        return normalize_text(s).split()
    except Exception:
        import re
        return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def _phrase_time(phrase: str, words, after: float = 0.0) -> Optional[float]:
    """First spoken time of `phrase` (a token subsequence) at/after `after` seconds; None if unsaid.

    Uses the FLATTENED token stream (aligner.flatten_words) so a hyphenated/possessive spoken word
    contributes all its sub-tokens — the old form kept only the FIRST sub-token of each word
    (`_norm(w.word)[0]`), so 'forty-one'->'forty' and any anchor/operative containing such a word
    silently missed (holbein POST_MORTEM #5)."""
    from nolan.aligner import flatten_words
    toks = _norm(phrase)
    if not toks:
        return None
    stream = flatten_words(words)                       # [(token, start, end)] — sub-tokens expanded
    n = len(toks)
    for i in range(len(stream) - n + 1):
        if stream[i][1] < after:
            continue
        if all(stream[i + j][0] == toks[j] for j in range(n)):
            return stream[i][1]
    return None


def _retime_reveals(sc: Dict, d: Dict, words) -> int:
    """Spread a scene's FIXED-OFFSET reveals across its (possibly stretched) window so they don't all
    fire in the first ~2s and then hold static — the 'reads like a slide' anti-pattern that bites long
    ungrounded holds. compose.py already reads a per-item `cue`, so this rewrites those WITHOUT touching
    the composer: word-anchor an item to its spoken phrase when it carries an `anchor`, else spread the
    items proportionally over [lead, dur-tail]. Returns how many reveals it retimed. (stat count-ups
    today; chart bars need an addressable per-bar cue in compose.py — the follow-up.)"""
    if sc.get("type") != "stat":
        return 0
    items = d.get("items")
    if not isinstance(items, list) or not items:
        return 0
    start, dur = float(sc.get("start", 0) or 0), float(sc.get("dur", 0) or 0)
    lead, tail = 0.6, 0.8
    span = max(0.1, dur - lead - tail)
    n = len(items)
    done = 0
    for k, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        cue = lead + (span * k / (n - 1) if n > 1 else 0.0)      # proportional across the window
        anchor = it.get("anchor")
        if anchor and words:                                    # …or land on the spoken number
            t = _phrase_time(anchor, words, after=start)
            if t is not None and start <= t < start + dur:
                cue = t - start
        it["cue"] = round(cue, 2)
        done += 1
    return done


def place_scenes(comp_dir, write: bool = True) -> Dict:
    """Set scene start/dur from where each scene's anchor/text is spoken. Writes back to the specs
    unless ``write=False`` — the `--report` dry-run computes and returns every scene's implied window
    WITHOUT mutating the specs (no recompose, no render), so an author can re-space anchors in
    seconds instead of a full sync→recompose→render iteration (holbein POST_MORTEM #4)."""
    from nolan import aligner
    from nolan.whisper import WordTimestamp
    comp_dir = Path(comp_dir)
    meta = json.loads((comp_dir / "audio_meta.json").read_text(encoding="utf-8"))
    by_frame = {v.get("frame"): v for v in meta.get("voices", [])}
    spec_files = sorted((comp_dir / "compositions" / "frames").glob("*.spec.json"))
    report = {"frames": [], "fallbacks": 0, "weak_total": 0, "problems": [], "windows": []}

    for i, sf in enumerate(spec_files, start=1):
        spec = json.loads(sf.read_text(encoding="utf-8"))
        for fr in spec.get("frames", []):
            scenes = fr.get("scenes", []) or []
            frame_dur = float(fr.get("dur", 0) or 0)
            words_raw = (by_frame.get(i) or {}).get("words") or []
            words = [WordTimestamp(word=w["word"], start=w["start"], end=w["end"]) for w in words_raw]
            fb = None
            weak = []
            unresolved = set()                           # scene ids whose anchor did not match at all
            if not scenes or not words:
                fb = "no words/scenes"
                starts = _proportional(len(scenes), frame_dur) if scenes else []
                unresolved = {sc.get("id") for sc in scenes}
            else:
                q = [{"id": sc.get("id", f"s{j}"), "narration_excerpt": _scene_query(sc)}
                     for j, sc in enumerate(scenes)]
                results, unmatched = aligner.align_scenes_to_audio(q, words)
                by_id = {r.scene_id: r for r in results}
                raw = [getattr(by_id.get(sc.get("id", f"s{j}")), "start_seconds", None)
                       for j, sc in enumerate(scenes)]
                starts = _validate_monotonic(raw, frame_dur)
                if starts is None:                       # anchors missing / out of order → this frame only
                    starts = _proportional(len(scenes), frame_dur)
                    fb = "proportional (anchors unmatched/out-of-order)"
                    report["fallbacks"] += 1
                unresolved = {u.scene_id for u in (unmatched or []) if float(u.confidence) <= 0.0}
                # LOUD: the aligner KNOWS which anchors matched weakly (confidence < 0.8), but a
                # low-confidence-yet-monotonic placement lands silently otherwise — Whisper mis-
                # transcription ('Jevons'→'Jevin's') mis-places a scene with nothing reported.
                weak = [{"scene": u.scene_id, "conf": round(float(u.confidence), 2),
                         "excerpt": (u.narration_excerpt or "")[:48]} for u in (unmatched or [])]
            drift = 0.0
            for j, sc in enumerate(scenes):
                old = float(sc.get("start", 0) or 0)
                sc["start"] = round(starts[j], 3)
                nxt = starts[j + 1] if j + 1 < len(starts) else frame_dur
                sc["dur"] = round(max(0.1, nxt - starts[j]), 3)
                drift = max(drift, abs(sc["start"] - old))
            cues = revs = 0
            for sc in scenes:                        # fire reveals ON the spoken word (or spread — never clustered)
                d = sc.get("data", {}) or {}
                op = d.get("operative")
                if op and words:                     # the operative highlight sweep
                    t = _phrase_time(op, words, after=float(sc.get("start", 0)))
                    if t is not None and sc["start"] <= t < sc["start"] + sc["dur"]:
                        d["cue"] = round(t - sc["start"], 2)
                        cues += 1
                revs += _retime_reveals(sc, d, words)  # spread fixed-offset reveals over the (retimed) window
            # anchor-lint: per-scene WINDOW + verdict, so degenerate windows are visible BEFORE a render
            # (a mis-heard anchor silently produces a 0.94s or 27s window — this was ~80% of the rework).
            for sc in scenes:
                block, dur = sc.get("type", "?"), float(sc.get("dur", 0) or 0)
                minr = _MIN_READABLE.get(block, 3.0)
                grounded = _scene_media(block, sc.get("data", {}) or {}) != "none"   # document/newshead count
                sid = sc.get("id")
                resolved = sid not in unresolved
                if dur + 1e-6 < minr:
                    v = f"SHORT {dur:.1f}s < {minr:.0f}s (unreadable)"
                elif dur > 8 and not grounded and block not in _MOTION_BLOCKS:
                    v = f"LONG-HOLD {dur:.1f}s ungrounded"
                elif not resolved:
                    v = "UNRESOLVED (anchor not found — placed by fallback)"
                else:
                    v = None
                report["windows"].append({"frame": fr.get("id"), "scene": sid, "block": block,
                                          "start": round(float(sc.get("start", 0) or 0), 2),
                                          "dur": round(dur, 2), "resolved": resolved,
                                          "anchor": (_scene_query(sc) or "")[:60], "verdict": v or "ok"})
                if v:
                    report["problems"].append({"frame": fr.get("id"), "scene": sid,
                                               "block": block, "dur": round(dur, 2), "issue": v})
            if weak:
                report["weak_total"] += len(weak)
                print(f"  ⚠ {fr.get('id')}: {len(weak)} weak anchor(s) (Whisper may have mis-heard) — "
                      + ", ".join(f"{w['scene']}@conf {w['conf']} “{w['excerpt']}”" for w in weak))
            report["frames"].append({"frame": fr.get("id"), "scenes": len(scenes),
                                     "max_shift_s": round(drift, 2), "cues_synced": cues,
                                     "reveals_retimed": revs,
                                     "fallback": fb, "weak_anchors": weak})
        if write:
            sf.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return report


def report_windows(comp_dir) -> Dict:
    """Dry-run preview: align (idempotent, cached) then resolve every scene's implied window WITHOUT
    moving scenes or writing specs — the fast loop for re-spacing anchors (POST_MORTEM #4)."""
    align_voices(comp_dir)                               # cached by wav mtime; needed for spoken times
    return place_scenes(comp_dir, write=False)


def _validate_monotonic(raw: List[Optional[float]], frame_dur: float) -> Optional[List[float]]:
    """Scene 1 opens the frame (start 0); the rest must resolve to strictly-increasing times inside
    the frame. Any gap or inversion => None (caller falls back to proportional for the frame)."""
    if not raw:
        return None
    out = [0.0]
    prev = 0.0
    for v in raw[1:]:
        if v is None or v <= prev + 0.15 or v >= frame_dur:
            return None
        out.append(round(v, 3))
        prev = v
    return out


def main():
    """python -X utf8 -m nolan.hyperframes.sync <comp> [--align-only]
    Force-align the section wavs, then place each scene on its spoken anchor (recompose + re-render after)."""
    import argparse
    import json as _json
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.sync")
    ap.add_argument("comp", help="composition dir (…/videos/<slug>)")
    ap.add_argument("--force", action="store_true", help="re-align even if words already present")
    ap.add_argument("--align-only", action="store_true", help="align the wavs but don't move scenes")
    ap.add_argument("--report", action="store_true",
                    help="DRY-RUN: print per-scene windows + SHORT/LONG/UNRESOLVED flags without "
                         "moving scenes / recompose / render (fast anchor-tuning loop)")
    a = ap.parse_args()

    if a.report:
        rep = report_windows(a.comp)
        cur = None
        for w in rep["windows"]:
            if w["frame"] != cur:
                cur = w["frame"]
                print(f"\n{cur}")
            mark = "✓" if w["verdict"] == "ok" else "✗"
            end = round(w["start"] + w["dur"], 2)
            print(f"  {mark} {w['scene']:>4} [{w['block']:<10}] {w['start']:6.2f}–{end:<6.2f} "
                  f"({w['dur']:>4.1f}s)  {w['verdict']}")
            if w["verdict"] != "ok":
                print(f"           anchor: “{w['anchor']}”")
        probs = rep.get("problems") or []
        print(f"\n— {len(rep['windows'])} scene(s); {len(probs)} degenerate window(s); "
              f"{rep['fallbacks']} frame(s) on proportional fallback; {rep['weak_total']} weak anchor(s)")
        print("  (dry-run — specs unchanged. Fix anchors, re-run --report, then `sync` to commit + recompose.)")
        return

    print("ALIGN:", _json.dumps(align_voices(a.comp, force=a.force)))
    if not a.align_only:
        rep = place_scenes(a.comp)
        for f in rep["frames"]:
            print(f"  {f['frame']:14} scenes={f['scenes']} max_shift={f['max_shift_s']}s "
                  f"cues={f['cues_synced']} fallback={f['fallback']}")
        print(f"fallbacks: {rep['fallbacks']} frame(s) — add `anchor` to those scenes for word-accurate placement")
        if rep.get("weak_total"):
            print(f"⚠ weak anchors: {rep['weak_total']} scene(s) matched at low confidence — verify their "
                  f"placement (Whisper may have mis-transcribed the anchor phrase); see weak_anchors per frame")
        probs = rep.get("problems") or []
        if probs:
            print(f"\n✗ ANCHOR-LINT: {len(probs)} window problem(s) — FIX BEFORE RENDER "
                  f"(a mis-heard anchor silently made these):")
            for p in probs:
                print(f"    {p['frame']}/{p['scene']} ({p['block']}) — {p['issue']}")
        else:
            print("anchor-lint: all scene windows readable ✓")


if __name__ == "__main__":
    main()

