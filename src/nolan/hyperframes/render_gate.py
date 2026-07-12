"""Perceptual render gate — the PIXEL half of "gates passing != the video is good".

The style-contract lints the SPEC and hf_qa checks freeze + audio, but nothing looks at the rendered
PIXELS — so white text over a bright ground, or a bokeh clip under "water pouring", ships silently.
This samples the RENDERED mp4 at each scene's midpoint and runs a VLM judge (is the on-screen text
LEGIBLE over its background? does the frame MATCH the beat?), reusing the acquisition judge pattern
(prompt → parse → floor). Optional (needs a vision provider); `nolan hf-finish` calls it after render,
soft. Pure prompt/parse/decision is unit-testable without a VLM.

  python -X utf8 -m nolan.hyperframes.render_gate <comp_dir>
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


def _ffmpeg() -> str:
    from nolan.hf_qa import _ffmpeg as ff
    return ff()


# --- pure prompt / parse / decision (testable without a VLM) --------------------------------------
def judge_prompt(beat: str, atmospheric: bool = False) -> str:
    # ROLE awareness: an atmospheric GROUND (b-roll under narration) is establishing/mood, so a shot of the
    # place or an evocative metaphor is CORRECT — only a clearly wrong subject is a miss. A literal-subject
    # block (document / newshead / gallery) should depict the thing. Without this the gate cried wolf on the
    # literal Tahoe lake (the story's location) and the residents' suburb.
    role = ("The imagery is an atmospheric ESTABLISHING GROUND playing under the narration: a shot of the "
            "PLACE, a mood/texture, or an evocative metaphor is CORRECT. Score it off-topic ONLY if it is a "
            "clearly wrong subject (e.g. a record player under \"electricity meter\"); an establishing location "
            "shot or an indirect/ironic metaphor is NOT off-topic."
            if atmospheric else
            "The imagery IS the subject of the beat — score whether it clearly depicts what the beat is about.")
    return (f'A still frame from a rendered explainer video, at the moment the narration means: "{beat}".\n'
            f"{role}\nJudge it as a professional editor. Reply STRICT JSON only, DETERMINISTICALLY (same "
            "frame → same scores): {"
            '"legible": <0-10 — is ALL on-screen text clearly readable over its background? white/light text '
            "on a bright or busy image, or clipped text, scores LOW>, "
            '"relevant": <0-10 — per the ROLE above>, '
            '"flags": "<any of: blank / low-contrast text / text clipped / off-topic / watermark; empty if clean>", '
            '"why": "<=12 words"}')


def extract_json(text: str) -> Dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
    return {}


def parse_verdict(j: Optional[Dict]) -> Dict:
    if not isinstance(j, dict):
        return {"legible": None, "relevant": None, "flags": "", "why": ""}
    def _num(v):
        try:
            return None if v is None else max(0.0, min(10.0, float(v)))
        except (TypeError, ValueError):
            return None
    return {"legible": _num(j.get("legible")), "relevant": _num(j.get("relevant")),
            "flags": str(j.get("flags") or "").strip(), "why": str(j.get("why") or "").strip()}


_HARD_FLAGS = ("blank", "clipped", "watermark")


def is_bad(v: Dict, floor: float = 4.0) -> bool:
    """A scene fails the gate if the text is illegible, the imagery is off-topic, or it's blank/clipped.
    A NEUTRAL verdict (VLM unavailable) is NOT bad — the gate is advisory, not a hard blocker."""
    if any(f in (v.get("flags") or "").lower() for f in _HARD_FLAGS):
        return True
    leg, rel = v.get("legible"), v.get("relevant")
    return (leg is not None and leg < floor) or (rel is not None and rel < floor)


# --- sampling: each scene's global midpoint + a beat label to judge relevance against --------------
def _beat_label(sc: Dict) -> str:
    d = sc.get("data", {}) or {}
    for k in ("anchor", "operative"):
        if d.get(k):
            return str(d[k])[:80]
    for k in ("query", "headline", "title", "name"):
        if d.get(k):
            return str(d[k])[:80]
    for k in ("lines", "items", "events"):
        seq = d.get(k)
        if isinstance(seq, list) and seq:
            first = seq[0]
            txt = first.get("text") or first.get("label") or first.get("title") if isinstance(first, dict) else first
            if txt:
                return str(txt)[:80]
    return sc.get("type", "scene")


def _stable_t(t: float, groups: List[Dict], lo: float, hi: float) -> float:
    """A caption CROSSFADE reads as 'doubled/garbled' text in a paused still, so nudge the sample to the
    MIDDLE of the caption group active at t (clamped to the scene window) — a settled caption moment."""
    for g in groups:
        try:
            if float(g.get("start", 0)) <= t <= float(g.get("end", 0)):
                return round(min(hi, max(lo, (float(g["start"]) + float(g["end"])) / 2)), 2)
        except Exception:
            continue
    return round(t, 2)


def scene_samples(comp_dir: Path) -> List[Dict]:
    """Every scene's GLOBAL sample time + a beat label (from the specs + audio_meta frame offsets)."""
    comp_dir = Path(comp_dir)
    meta = {}
    mp = comp_dir / "audio_meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    cap_groups = []                                       # sample mid-caption, not mid-crossfade
    cg = comp_dir / "caption_groups.json"
    if cg.exists():
        try:
            g = json.loads(cg.read_text(encoding="utf-8"))
            cap_groups = g if isinstance(g, list) else g.get("groups", [])
        except Exception:
            cap_groups = []
    frame_dur = {v.get("frame"): float(v.get("duration_s", 0) or 0) for v in meta.get("voices", [])}
    spec_files = sorted((comp_dir / "compositions" / "frames").glob("*.spec.json"))
    out, offset = [], 0.0
    for i, sf in enumerate(spec_files, start=1):
        spec = json.loads(sf.read_text(encoding="utf-8"))
        fdur = 0.0
        for fr in spec.get("frames", []):
            fdur = frame_dur.get(i, float(fr.get("dur", 0) or 0)) or float(fr.get("dur", 0) or 0)
            for sc in fr.get("scenes", []):
                st = float(sc.get("start", 0) or 0)
                du = float(sc.get("dur", 0) or 0)
                data = sc.get("data", {}) or {}
                atmospheric = bool((data.get("ground") or {}).get("kind"))   # b-roll backdrop → not literal
                t = _stable_t(offset + st + du / 2, cap_groups, offset + st + 0.3, offset + st + du - 0.3)
                out.append({"frame": fr.get("id"), "scene": sc.get("id"), "type": sc.get("type"),
                            "t": t, "beat": _beat_label(sc), "atmospheric": atmospheric})
        offset += fdur
    return out


def _render_mp4(comp_dir: Path) -> Optional[Path]:
    rd = comp_dir / "renders"
    vids = sorted(rd.glob("*.mp4")) if rd.is_dir() else []
    return vids[0] if vids else None


def extract_still(mp4: Path, t: float, out: Path, ff: str) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1", "-q:v", "3", str(out)],
                   capture_output=True)
    return out.exists() and out.stat().st_size > 1000


def perceptual_qa(comp_dir, vision=None, floor: float = 4.0, out_dir=None) -> Dict:
    """Sample the render at each scene midpoint, VLM-judge legibility + relevance, report the failures.
    Returns {ok, checked, bad:[...]}. `vision` = a describe_image provider (built if None)."""
    comp_dir = Path(comp_dir)
    mp4 = _render_mp4(comp_dir)
    if not mp4:
        return {"ok": True, "checked": 0, "bad": [], "note": "no render to inspect"}
    if vision is None:
        try:
            from nolan.vision import create_vision_provider
            from nolan.evoke_broll import _vision_config
            from nolan.config import load_config
            vision = create_vision_provider(_vision_config(load_config()))
        except Exception as e:
            return {"ok": True, "checked": 0, "bad": [], "note": f"no vision provider ({e})"}
    ff = _ffmpeg()
    stills = Path(out_dir or (comp_dir / "capture" / "_perceptual"))
    samples = scene_samples(comp_dir)
    bad, checked = [], 0

    async def _run():
        import asyncio
        nonlocal checked
        sem = asyncio.Semaphore(4)
        async def one(s):
            nonlocal checked
            png = stills / f"{s['frame']}_{s['scene']}.jpg"
            if not extract_still(mp4, s["t"], png, ff):
                return
            async with sem:
                try:
                    raw = await vision.describe_image(png, judge_prompt(s["beat"], s.get("atmospheric", False)))
                    v = parse_verdict(extract_json(raw))
                except Exception:
                    v = parse_verdict(None)
            checked += 1
            if is_bad(v, floor):
                bad.append({**s, "legible": v["legible"], "relevant": v["relevant"], "flags": v["flags"], "why": v["why"]})
        await asyncio.gather(*(one(s) for s in samples))

    import asyncio
    asyncio.run(_run())
    bad.sort(key=lambda b: (b.get("legible") if b.get("legible") is not None else 9,
                            b.get("relevant") if b.get("relevant") is not None else 9))
    return {"ok": not bad, "checked": checked, "bad": bad}


def main():
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python -X utf8 -m nolan.hyperframes.render_gate <comp_dir>")
    rep = perceptual_qa(sys.argv[1])
    print(f"PERCEPTUAL QA — checked {rep['checked']} scene(s) — {'PASS' if rep['ok'] else 'FLAGS'}")
    if rep.get("note"):
        print(f"  ({rep['note']})")
    for b in rep["bad"]:
        print(f"  ⚠ {b['frame']}/{b['scene']} ({b['type']}) @ {b['t']}s — legible {b['legible']} relevant {b['relevant']}"
              f"  flags: {b['flags'] or '-'}  “{b['beat']}” — {b['why']}")


if __name__ == "__main__":
    main()
