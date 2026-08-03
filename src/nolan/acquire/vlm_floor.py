"""The VLM usability FLOOR — one vision call per acquired asset that scores it, captions it, and drops
the junk CLIP cannot see.

WHY THIS MODULE EXISTS (a routing bug, not a preference). This pass lived in
`render-service/_lab_hyperframes/bridge/pool.py` — a CLI script — so it was reachable only by running
the whole-project pool build. Every other way of acquiring an asset therefore shipped without it. The
edit loop's scene-scoped `replace.search` had no floor at all, and a real batch edit landed 24
candidates of which two carried burned-in period-drama subtitles with recognisable actors and several
were topically wrong (a museum atrium for "auction house"). Captions and CLIP scores decided nothing;
pixels decided everything, and the organ that looks at pixels was on the other path.

So it moves here, next to `judge.py` (which owns the PROMPT and the verdict parsing), and the bridge
imports it. One implementation, two callers, no drift — `tests/test_acquire_vlm_floor.py` pins that the
bridge still routes through this module rather than growing a second copy.

Contained by design: a dead VLM yields a NEUTRAL verdict and the asset is KEPT, so an outage can never
empty a pool. Generated stills are exempt (they are bespoke, not retrieved).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional


def video_still(clip: Path) -> Optional[Path]:
    """A 3-frame FILMSTRIP (start / mid / end, hstacked) of a video clip → one temp jpg, so the VLM
    judges the clip's whole ARC in a single call — a clip that opens black, ends on a logo, or changes
    subject isn't misjudged from one mid-frame. Mirrors how the video-indexer samples several timestamps
    per clip (indexer.analyze_frame). Falls back to a single still, then None."""
    from nolan.hf_qa import _ffmpeg, probe
    ff = _ffmpeg()
    dur = probe(Path(clip)).duration or 4.0
    stills: List[Path] = []
    for frac in (0.15, 0.5, 0.85):
        fd, t = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        t = Path(t)
        subprocess.run([ff, "-y", "-ss", f"{max(0.1, dur * frac):.2f}", "-i", str(clip), "-frames:v", "1",
                        "-vf", "scale=480:-1", "-q:v", "3", str(t)], capture_output=True)
        if t.exists() and t.stat().st_size > 1000:
            stills.append(t)
        else:
            t.unlink(missing_ok=True)
    if not stills:
        return None
    if len(stills) == 1:
        return stills[0]
    fd, out = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    out = Path(out)
    inputs = [x for s in stills for x in ("-i", str(s))]
    subprocess.run([ff, "-y", *inputs, "-filter_complex", f"hstack=inputs={len(stills)}", "-q:v", "3",
                    str(out)], capture_output=True)
    for s in stills:
        s.unlink(missing_ok=True)
    return out if (out.exists() and out.stat().st_size > 1000) else None


async def score_and_caption(cfg, pool, assets_dir: Path, needs, acfg=None, log=print):
    """Fused VLM SCORE + CAPTION pass. One vision call per kept asset returns a usability + RELEVANCE
    verdict (usable / flags / caption); junk is dropped — the semantic FLOOR that CLIP can't do (a sports
    car for "permit", a record player for "electricity meter"). VIDEO is judged too, by sampling a
    filmstrip (blind duration-only selection shipped off-topic clips). Generated stills are exempt.
    Contained: a dead VLM yields a NEUTRAL verdict → the asset is KEPT, so an outage never empties the
    pool. Mutates `pool` items in place and returns the survivors."""
    from nolan.acquire import AcquireConfig, extract_json, is_junk, judge_prompt, parse_verdict
    from nolan.acquire.judge import caption_verified, is_scraped
    from nolan.acquire.shared import downscale_for_vision
    from nolan.evoke_broll import _vision_config
    from nolan.vision import create_vision_provider
    acfg = acfg or AcquireConfig()
    prov = create_vision_provider(_vision_config(cfg))
    need_by_id = {n["id"]: n for n in needs}
    sem = asyncio.Semaphore(4)

    async def judge(item):
        # The cull cascade USED TO SKIP the VLM entirely for library clips ("pre-captioned + curated +
        # already past the CLIP gate"). That exemption is what shipped a talking head captioned as a
        # "stock ticker" and a clip hard-subbed with another creator's subtitles: the stored description
        # describes the SOURCE video, not the range we trimmed, and a scraped upload's branding is
        # invisible to every cheap gate. Scraped sources are judged like anything else — the saving was
        # never worth an unverified caption on someone else's footage.
        need = need_by_id.get(item["id"], {"query": item.get("query", "")})
        img = assets_dir / item["file"]
        is_video = item["media_type"] == "video"
        tmp = None
        if is_video:
            img = video_still(img)
            if img is None:
                item["caption"] = f"[video] {item['query']} (stock clip, {item.get('duration') or '?'}s)"
                return
            send = img
        else:
            send, tmp = downscale_for_vision(img)      # stills: 1024px copy so big images don't error
        async with sem:
            try:
                raw = await prov.describe_image(send, judge_prompt(need, video=is_video))
                v = parse_verdict(extract_json(raw))
            except Exception as e:
                v = parse_verdict(None)
                log(f"    judge failed {item['file']}: {type(e).__name__}")
        if tmp:
            tmp.unlink(missing_ok=True)
        if is_video:
            img.unlink(missing_ok=True)
            item["caption"] = ("[video] " + (v["caption"] or item.get("query", ""))).strip()
        else:
            item["caption"] = v["caption"] or f"({item['query']})"
        if v.get("content_kind"):
            item["content_kind"] = v["content_kind"]                 # placement signal, same VLM call
        item["usable"], item["flags"] = v["usable"], v["flags"]      # → /pool curation badges
        # PROVENANCE the author (and a human) can act on. `depicts=False` keeps the asset — it is often
        # still good b-roll — but the caption now comes from what the VLM SAW, so record that the
        # original claim failed rather than silently swapping it. `origin_verified` is False for scraped
        # sources until pixels confirm; it is what the `[unverified-origin]` menu tag reads.
        if v.get("chrome") is not None:
            item["chrome"] = bool(v["chrome"])
        cv = caption_verified(v)
        if cv is not None:
            item["caption_verified"] = bool(cv)
        if is_scraped(item.get("source", "")):
            item["origin_verified"] = bool(v.get("chrome") is False)
        item["_verdict"] = v

    await asyncio.gather(*(judge(it) for it in pool))

    # FLOOR: drop non-generated assets the editor scored as junk. Generated stills are bespoke (exempt).
    # Report exactly what was dropped — no silent cap.
    kept, culled = [], []
    for it in pool:
        v = it.pop("_verdict", None)
        generated = "generat" in str(it.get("source", "")).lower()
        if acfg.vlm_cull and v is not None and not generated and is_junk(v, acfg.vlm_floor):
            culled.append(it)
        else:
            kept.append(it)
    for it in culled:
        (assets_dir / it["file"]).unlink(missing_ok=True)
        reason = it.get("flags") or f"usable {it.get('usable')}"
        log(f"    ✂ culled {it['file']} [{it['id']}] — {reason}")
    if culled:
        log(f"  VLM floor: dropped {len(culled)} junk asset(s), {len(kept)} survive")

    # COVERAGE REPORT — failures are loud at the pool boundary. An empty/thin need after culling used to
    # vanish silently (three empties were found only by diffing filenames) → the author unknowingly
    # authors a beat with no asset. Report every need's got/culled so substitution is a DELIBERATE step.
    got, cull_by = Counter(it["id"] for it in kept), Counter(it["id"] for it in culled)
    q_of: Dict[str, str] = {n["id"]: n.get("query", "") for n in needs}
    empty = [n["id"] for n in needs if got.get(n["id"], 0) == 0]
    thin = [n["id"] for n in needs if 0 < got.get(n["id"], 0) < 3]
    if empty or thin:
        log("  ⚠ POOL COVERAGE — some needs came back short:")
        for nid in empty:
            log(f"    ✗ {nid} EMPTY (0 kept, {cull_by.get(nid, 0)} culled) — {q_of.get(nid, '')!r} — "
                f"SUBSTITUTE or re-run this need")
        for nid in thin:
            log(f"    ⚠ {nid} THIN ({got[nid]} kept) — {q_of.get(nid, '')!r}")
    else:
        log(f"  pool coverage: all {len(needs)} needs have ≥3 assets ✓")
    return kept
