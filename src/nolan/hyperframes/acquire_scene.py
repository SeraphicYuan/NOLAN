"""Scene-scoped acquisition for the edit loop — the FULL engine, one beat at a time.

Before this there were two doors out of the edit loop and neither was the one an agent needed:

  * `replace.search` — scene-scoped and pool-safe, but a DILUTED engine: it called `ctx.search_stock`
    directly, so no library, no clips_library, no transcript tiers, no visuallib, no CLIP relevance, no
    fitness, no dedup, no VLM floor.
  * `edit.run_pool` — the full engine, but whole-project scoped, and it ended in a `pool.json` overwrite
    that would have destroyed a finished essay's 150-entry catalogue.

So a real batch edit used the second with `sources=("stock",)`, hand-bypassed the inventory write, and
hand-placed everything. This is the missing third door: ONE need, the whole engine, merged into the pool.

Scene scope is not a lesser version of the project scope — it knows three things the author pipeline
structurally cannot, and this module spends all three:

  1. **The window.** The scene's `dur` IS the need's `min_duration`. Remote video is fetched at that
     length (`clip_seconds`) instead of being penalised for being short; fixed-length local clips are
     docked in proportion to the looping they would need.
  2. **The narration.** `frame_transcripts` gives the words actually spoken over this scene — a better
     query than anything an LLM would re-derive from the script.
  3. **What the essay already uses.** `asset_scene_usage` knows every asset already on screen elsewhere,
     so the perceptual dedup can refuse to hand the same shot to a second beat.
"""
from __future__ import annotations

import asyncio
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .edit import (_comp_dir, _find_scene, _VID_EXT, add_scene_asset, asset_pool_meta,
                   asset_scene_usage, load_frame_spec, log_activity)
from .replace import REPO, _keywords, _theme, brief as scene_brief

# The whole tier list. The edit loop had access to one of these; the author pipeline has all of them,
# and "full access, not a diluted version" is the point of this module.
DEFAULT_SOURCES = ("clips_library", "transcript_lib", "transcript_frames", "library", "visuallib", "stock")


def _scene_window(comp: str, frame_id: str, scene_id: str) -> float:
    spec, info = load_frame_spec(comp, frame_id)
    sc = _find_scene(spec["frames"][info["i"]], scene_id)
    return float(sc.get("dur", 0) or 0)


def derive_need(comp: str, frame_id: str, scene_id: str, *, query: Optional[str] = None,
                modality: Optional[str] = None, evocative: Optional[bool] = None) -> Dict[str, Any]:
    """The acquisition NEED for one scene, derived from the scene itself.

    `min_duration` is the scene's real window — the field the engine never had, because until now only
    a whole-project need-derivation LLM ever wrote needs, and it is guessing at authoring time while
    this knows. A video need's window is what makes a 2.5s snippet the wrong answer for a 19s hold."""
    b = scene_brief(comp, frame_id, scene_id)
    dur = _scene_window(comp, frame_id, scene_id)
    q = (query or b.get("query") or "").strip() or _keywords(b.get("transcript") or "")
    mt = modality or b.get("modality") or "image"
    need: Dict[str, Any] = {
        "id": f"{frame_id}~{scene_id}",
        "query": q,
        "queries": [x for x in (q, _keywords(b.get("transcript") or "", 12)) if x][:2],
        "media_type": mt,
        "gen_prompt": b.get("prompt") or q,
        "category": "general",
        "_scene": {"frame_id": frame_id, "scene_id": scene_id, "field": b.get("field")},
    }
    if mt == "video" and dur > 0:
        need["min_duration"] = round(dur, 2)
    if evocative is not None:
        need["evocative"] = bool(evocative)
    return need


def _pool_hashes(comp: str, *, exclude_scene: Optional[str] = None) -> List[int]:
    """Perceptual hashes of what this essay ALREADY has on screen, so a scene-scoped fetch cannot hand
    a second beat a shot the viewer has already seen. The project pool build dedups within one run;
    across runs (which is what an edit is) nothing did."""
    from nolan.acquire.engine import avg_hash, video_hash
    cdir = _comp_dir(comp)
    used = set()
    try:
        for name, scenes in (asset_scene_usage(comp).get("by_file") or {}).items():
            if exclude_scene and list(scenes) == [exclude_scene]:
                continue                        # the asset we are REPLACING shouldn't block its own swap
            used.add(name)
    except Exception:
        pass
    out: List[int] = []
    for name in used:
        for base in (cdir / "assets", cdir / "capture" / "assets"):
            p = base / name
            if p.is_file():
                h = video_hash(p) if p.suffix.lower() in _VID_EXT else avg_hash(p)
                if h is not None:
                    out.append(h)
                break
    return out


def acquire_for_scene(comp: str, frame_id: str, scene_id: str, *, query: Optional[str] = None,
                      modality: Optional[str] = None, n: int = 6, sources=None,
                      generate: bool = False, vlm_floor: bool = True,
                      evocative: Optional[bool] = None, log=print) -> Dict[str, Any]:
    """Acquire candidates for ONE scene through the full engine, land them in the pool + the scene's
    shortlist, and return what survived.

    `generate` is OFF by default and that is deliberate: generation is GPU work, and a fleet agent runs
    in its own process where the hub's in-process GPU lock does not reach (see `nolan.gpu_lock`). Turn it
    on only when you mean to spend the GPU, and it will queue behind ComfyUI/TTS through the file lock.

    Nothing here touches the canonical spec — landed assets go to the scene's SHORTLIST. Wiring one into
    the block is a normal proposal, gated and human-accepted like any other edit.
    """
    from nolan.acquire import AcquireConfig, acquire_need, build_context, gen_style_for
    from nolan.config import load_config

    need = derive_need(comp, frame_id, scene_id, query=query, modality=modality, evocative=evocative)
    if not need["query"]:
        return {"ok": False, "detail": "no query — the scene has no narration, prompt or title to derive one from",
                "need": need, "landed": []}
    window = float(need.get("min_duration") or 0)
    cfg = load_config(REPO / "nolan.yaml")
    gs = gen_style_for(_theme(comp))
    # Fetch remote video AT the window rather than docking it for being short: `clip_seconds` bounds the
    # ffmpeg range-seek every remote video source uses, so this is the whole fix for that half.
    clip_seconds = max(int(getattr(cfg, "clip_seconds", 30) or 30), int(math.ceil(window)) + 2) if window else None
    ctx = build_context(cfg, gen_style=gs, want_gen=generate, clip_seconds=clip_seconds,
                        project_dir=_comp_dir(comp))
    acfg = AcquireConfig(per_need=n, sources=tuple(sources or DEFAULT_SOURCES),
                         generate_evocative=generate, vlm_cull=vlm_floor)

    taken = _pool_hashes(comp, exclude_scene=scene_id)
    log(f"  [{need['id']}] {need['media_type']} · {need['query']!r} · window {window or '-'}s · "
        f"{len(acfg.sources)} tier(s) · dedup vs {len(taken)} in-use asset(s)")
    cand_dir = Path(tempfile.mkdtemp(prefix="nolan_scene_acq_"))
    try:
        kept = acquire_need(need, ctx, acfg, cand_dir, taken)
        if not kept:
            log("    nothing survived retrieval + the relevance/fitness gates")
            return {"ok": True, "need": need, "landed": [], "culled": 0}

        # --- the VLM usability FLOOR, on the SAME organ the project pool build uses -----------------
        # This is the gate the edit-loop path never had: of 24 candidates in one real batch, two carried
        # burned-in period-drama subtitles with recognisable actors and several were topically wrong
        # (a museum atrium for "auction house"). Every text-level score was useless; only pixels decided.
        staged = cand_dir / "_staged"
        staged.mkdir(exist_ok=True)
        rows = []
        for i, c in enumerate(kept):
            dest = staged / f"{scene_id}_acq{i}{Path(c.path).suffix or ('.mp4' if c.modality == 'video' else '.jpg')}"
            try:
                shutil.copyfile(str(c.path), str(dest))
            except OSError:
                continue
            rows.append({"id": need["id"], "file": dest.name, "media_type": c.modality,
                         "query": need["query"], "source": c.meta.get("source", c.source),
                         "source_url": c.meta.get("source_url", ""),
                         "photographer": c.meta.get("photographer", ""),
                         "license": c.meta.get("license", ""),
                         "duration": c.meta.get("duration"), "relevance": round(c.relevance, 3),
                         "caption": "", "_cand": c})
        before = len(rows)
        if vlm_floor and rows:
            try:
                from nolan.acquire.vlm_floor import score_and_caption
                bare = [{k: v for k, v in r.items() if k != "_cand"} for r in rows]
                survivors = asyncio.run(score_and_caption(cfg, bare, staged, [need], acfg, log=log))
                keep_files = {s["file"] for s in survivors}
                by_file = {s["file"]: s for s in survivors}
                rows = [{**r, **by_file.get(r["file"], {})} for r in rows if r["file"] in keep_files]
            except Exception as e:                     # a dead VLM must never empty the beat
                log(f"    VLM floor skipped: {type(e).__name__}: {e}")

        landed = []
        for r in rows:
            try:
                item = add_scene_asset(comp, frame_id, scene_id, r["file"], (staged / r["file"]).read_bytes())
            except Exception as e:
                log(f"    could not land {r['file']}: {type(e).__name__}: {e}")
                continue
            _stamp_pool(comp, item["name"], r)
            landed.append({**item, "source": r["source"], "relevance": r["relevance"],
                           "caption": r.get("caption", ""), "duration": r.get("duration"),
                           "flags": r.get("flags", "")})
        log(f"    landed {len(landed)} (VLM floor dropped {before - len(rows)})")
        log_activity(comp, "acquire", f"{len(landed)} candidate(s) for {scene_id}: {need['query'][:60]}",
                     frame_id=frame_id, scene_id=scene_id, outcome="staged")
        return {"ok": True, "need": need, "landed": landed, "culled": before - len(rows)}
    finally:
        shutil.rmtree(cand_dir, ignore_errors=True)


def _stamp_pool(comp: str, name: str, row: Dict[str, Any]) -> None:
    """Fill in the pool row `add_scene_asset` created with the real provenance from acquisition —
    source/licence/attribution/relevance/caption. Without this a fetched asset is indistinguishable
    from a hand-dropped one, and the licence (the thing that decides whether it can ship) is lost."""
    try:
        pool_f = _comp_dir(comp) / "pool.json"
        pool = json.loads(pool_f.read_text(encoding="utf-8")) if pool_f.exists() else []
        for e in pool:
            if isinstance(e, dict) and e.get("file") == name:
                for k in ("source", "source_url", "photographer", "license", "duration", "relevance",
                          "caption", "flags", "usable", "chrome", "caption_verified", "origin_verified",
                          "content_kind"):
                    if row.get(k) not in (None, ""):
                        e[k] = row[k]
                break
        pool_f.write_text(json.dumps(pool, indent=1), encoding="utf-8")
    except Exception:
        pass          # pool bookkeeping must never break an acquisition
